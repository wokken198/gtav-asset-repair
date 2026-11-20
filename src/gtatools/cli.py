"""Command line entry points."""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys

from . import cw, dds, normals, ymt

DEFAULT_TEXCONV = os.environ.get("TEXCONV", "texconv.exe")
DEFAULT_PS1 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "resources", "pack_ytd.ps1")


def _is_badge_diffuse(name: str) -> bool:
    low = name.lower()
    if not low.endswith((".dds", ".png")):
        return False
    if "badge" not in low:
        return False
    return not (low.endswith("_n.dds") or low.endswith("_n.png") or "normal" in low)


def cmd_normals(args) -> int:
    files = glob.glob(os.path.join(args.src, "**", "*"), recursive=True)
    candidates = [f for f in files if _is_badge_diffuse(f)]
    if not candidates:
        print("no badge diffuse found under", args.src)
        return 1

    work = args.work or os.path.join(args.out, "_work")
    os.makedirs(work, exist_ok=True)
    by_dir: dict[str, list[str]] = {}
    for f in candidates:
        by_dir.setdefault(os.path.dirname(f), []).append(f)

    rows = []
    made = 0
    for d, group in sorted(by_dir.items()):
        png_dir = os.path.join(work, os.path.basename(d))
        dds_files = [f for f in group if f.lower().endswith(".dds")]
        if dds_files:
            dds.decode(png_dir, dds_files, args.texconv)
        for f in group:
            base = os.path.splitext(os.path.basename(f))[0]
            png = os.path.join(png_dir, base + ".png")
            if not os.path.exists(png):
                print("skip (no decoded png):", f)
                continue
            rgba = normals.load_rgba(png)
            h = normals.height_field(rgba, blur=args.blur)
            n = normals.normal_from_height(h, strength=args.strength)
            out_dir = os.path.join(args.out, os.path.basename(d))
            npath = os.path.join(png_dir, base + "_n.png")
            from PIL import Image
            Image.fromarray(n, "RGB").save(npath)
            mips = min(max(1, int(max(n.shape[:2]).bit_length()) - 1), args.max_mips)
            dds.encode(npath, args.fmt, mips, out_dir, args.texconv)
            made += 1
            if args.sheet and len(rows) < args.sheet_rows:
                diff = Image.open(png).convert("RGBA")
                bg = Image.new("RGBA", diff.size, (255, 255, 255, 255))
                bg.alpha_composite(diff)
                lit = (normals.shade_preview(rgba, n) * 255).astype("uint8")
                rows.append((f, bg.convert("RGB"), Image.fromarray(n), Image.fromarray(lit)))
        print(f"{os.path.basename(d)}: {len(group)} source(s)")

    if args.sheet and rows:
        normals.contact_sheet(rows, args.sheet)
        print("sheet:", args.sheet)
    print(f"normals written: {made}")
    return 0


def cmd_audit(args) -> int:
    result = ymt.audit_xml(args.file)
    print(ymt.format_report(result, os.path.basename(args.file)))
    if args.json:
        payload = {
            "components": [
                {"slot": r.slot, "name": r.slot_name, "compIndex": r.comp_index,
                 "numAvailTex": r.declared, "texSum": r.texture_sum, "drawbles": r.drawbles}
                for r in result.components
            ],
            "compInfos": result.comp_infos,
            "drawbles": result.drawble_total,
            "problems": result.problems,
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print("json:", args.json)
    return 0 if result.ok else 2


def cmd_scale(args) -> int:
    jobs = []  # (path, relative output subdir)
    for p in args.paths:
        if os.path.isdir(p):
            for hit in glob.glob(os.path.join(p, "**", "*.dds"), recursive=True):
                jobs.append((hit, os.path.relpath(os.path.dirname(hit), p)))
        else:
            jobs.append((p, ""))
    if not jobs:
        print("no dds found")
        return 1

    os.makedirs(args.out, exist_ok=True)
    work = os.path.join(args.out, "_work")
    ok, skipped, failed = 0, 0, 0
    for p, sub in jobs:
        try:
            h = dds.read_header(p)
        except ValueError as exc:
            print("skip:", exc)
            skipped += 1
            continue
        long_edge = max(h.width, h.height)
        if long_edge <= args.min_edge:
            skipped += 1
            continue
        scale = args.long_edge / long_edge
        tw = max(4, int(round(h.width * scale / 4) * 4))
        th = max(4, int(round(h.height * scale / 4) * 4))
        try:
            png_dir = os.path.join(work, "png")
            dds.decode(png_dir, [p], args.texconv)
            stem = os.path.splitext(os.path.basename(p))[0]
            png = os.path.join(png_dir, stem + ".png")
            resized = os.path.join(png_dir, f"{stem}_{tw}x{th}.png")
            dds.resize_rgba(png, (tw, th), resized)
            mips = min(h.mips, max(1, int(max(tw, th).bit_length()) - 1))
            out_dir = os.path.join(args.out, sub)
            made = dds.encode(resized, h.texconv_fmt, mips, out_dir, args.texconv)
            final = os.path.join(out_dir, os.path.basename(p))
            if os.path.normcase(made) != os.path.normcase(final):
                os.replace(made, final)
            ok += 1
            print(f"{os.path.basename(p)}: {h.width}x{h.height} -> {tw}x{th} {h.label} mips={mips}")
        except Exception as exc:  # noqa: BLE001 - batch tool, report and continue
            failed += 1
            print("fail:", p, exc)
    print(f"done: ok={ok} skipped={skipped} failed={failed}")
    return 0 if failed == 0 else 1


def cmd_pack(args) -> int:
    core = cw.find_corewalker(args.core_dir, start=os.path.dirname(os.path.abspath(args.xml)))
    if core is None:
        print(cw.MISSING_HINT, file=sys.stderr)
        return 2
    print(f"codewalker: {core}")
    cmd = ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", args.ps1,
           "-Xml", os.path.abspath(args.xml), "-Build", os.path.abspath(args.build),
           "-Out", os.path.abspath(args.out), "-CoreDir", core]
    if args.legacy:
        cmd += ["-Legacy"]
    if args.original:
        cmd += ["-Original", os.path.abspath(args.original)]
    print(" ".join(cmd))
    return subprocess.call(cmd)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gtatools", description="GTA V asset helpers")
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("normals", help="badge diffuse -> normal map (DDS)")
    n.add_argument("src")
    n.add_argument("--out", default="out")
    n.add_argument("--work", default="")
    n.add_argument("--strength", type=float, default=6.5)
    n.add_argument("--blur", type=float, default=1.2)
    n.add_argument("--fmt", default="DXT5", help="texconv format, e.g. DXT5 / BC5_UNORM")
    n.add_argument("--max-mips", type=int, default=12)
    n.add_argument("--sheet", default="")
    n.add_argument("--sheet-rows", type=int, default=12)
    n.add_argument("--texconv", default=DEFAULT_TEXCONV)
    n.set_defaults(func=cmd_normals)

    a = sub.add_parser("audit", help="audit a CPedVariationInfo XML")
    a.add_argument("file")
    a.add_argument("--json", default="")
    a.set_defaults(func=cmd_audit)

    s = sub.add_parser("scale", help="rescale DDS files, keeping their format and mip depth")
    s.add_argument("paths", nargs="+")
    s.add_argument("--out", default="out")
    s.add_argument("--long-edge", type=int, default=1536)
    s.add_argument("--min-edge", type=int, default=0, help="skip files whose long edge is <= this")
    s.add_argument("--texconv", default=DEFAULT_TEXCONV)
    s.set_defaults(func=cmd_scale)

    k = sub.add_parser("pack", help="pack a YTD from CodeWalker XML + DDS folder")
    k.add_argument("--xml", required=True)
    k.add_argument("--build", required=True)
    k.add_argument("--out", required=True)
    k.add_argument("--core-dir", default="",
                   help="CodeWalker folder holding CodeWalker.Core.dll; auto-detected when omitted")
    k.add_argument("--legacy", action="store_true")
    k.add_argument("--original", default="", help="copy G9/usage descriptors from this archive")
    k.add_argument("--ps1", default=DEFAULT_PS1)
    k.set_defaults(func=cmd_pack)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
