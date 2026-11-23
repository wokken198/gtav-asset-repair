"""Command line entry points."""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys

from . import cw, dds, lite, normals, ymt, ytd as ytdmod

DEFAULT_TEXCONV = os.environ.get("TEXCONV", "texconv.exe")
DEFAULT_PS1 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "resources", "pack_ytd.ps1")

# Set by --work. Every default output path lives below it, so the whole run stays in one folder.
WORK = ""


def work_path(*parts: str) -> str:
    """Resolve a default output path under --work (or the current directory)."""
    base = WORK or os.getcwd()
    return os.path.join(base, *parts)


def ensure_dir(path: str) -> str:
    if path:
        os.makedirs(path, exist_ok=True)
    return path


def _emit_json(payload, target: str) -> bool:
    """Write `payload` to `target`; "-" means stdout. Returns True when it went to stdout."""
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if target == "-":
        print(text)
        return True
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print("json:", target)
    return False


def _is_badge_diffuse(name: str) -> bool:
    low = name.lower()
    if not low.endswith((".dds", ".png")):
        return False
    if "badge" not in low:
        return False
    return not (low.endswith("_n.dds") or low.endswith("_n.png") or "normal" in low)


def cmd_normals(args) -> int:
    if not os.path.exists(args.src):
        print("no such file or folder:", args.src, file=sys.stderr)
        return 1
    files = glob.glob(os.path.join(args.src, "**", "*"), recursive=True) if os.path.isdir(args.src) else [args.src]
    candidates = [f for f in files if _is_badge_diffuse(f)]
    if not candidates:
        print("no badge diffuse found under", args.src)
        return 1

    src_root = args.src if os.path.isdir(args.src) else os.path.dirname(args.src) or "."
    out_root = args.out or work_path("normals")
    work = args.scratch or os.path.join(out_root, "_work")
    os.makedirs(work, exist_ok=True)
    by_dir: dict[str, list[str]] = {}
    for f in candidates:
        by_dir.setdefault(os.path.dirname(f), []).append(f)

    rows = []
    made = 0
    for d, group in sorted(by_dir.items()):
        rel = os.path.relpath(d, src_root)
        tag = "root" if rel in (".", "") else rel.replace("\\", "/")
        rel_dir = "" if rel in (".", "") else rel
        png_dir = os.path.join(work, tag)
        dds_files = [f for f in group if f.lower().endswith(".dds")]
        if dds_files:
            dds.decode(png_dir, dds_files, args.texconv)
        out_dir = os.path.join(out_root, rel_dir) if rel_dir else out_root
        for f in group:
            base = os.path.splitext(os.path.basename(f))[0]
            png = os.path.join(png_dir, base + ".png")
            if not os.path.exists(png):
                print("skip (no decoded png):", f)
                continue
            rgba = normals.load_rgba(png)
            h = normals.height_field(rgba, blur=args.blur)
            n = normals.normal_from_height(h, strength=args.strength)
            npath = os.path.join(png_dir, base + "_n.png")
            from PIL import Image
            Image.fromarray(n, "RGB").save(npath)
            mips = min(max(1, int(max(n.shape[:2]).bit_length())), args.max_mips)
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
    if not os.path.exists(args.file):
        print("no such file:", args.file, file=sys.stderr)
        return 1
    result = ymt.audit_xml(args.file)
    payload = {
        "file": os.path.basename(args.file),
        "ok": result.ok,
        "components": [
            {"slot": r.slot, "name": r.slot_name, "compIndex": r.comp_index,
             "numAvailTex": r.declared, "texSum": r.texture_sum, "drawbles": r.drawbles}
            for r in result.components
        ],
        "compInfos": result.comp_infos,
        "drawbles": result.drawble_total,
        "problems": result.problems,
    }
    if args.json == "-":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(ymt.format_report(result, os.path.basename(args.file)))
        if args.json:
            _emit_json(payload, args.json)
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

    out_root = args.out or work_path("scaled")
    os.makedirs(out_root, exist_ok=True)
    work = os.path.join(out_root, "_work")
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
        if args.long_edge >= long_edge:
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
            mips = min(h.mips, max(1, int(max(tw, th).bit_length())))
            out_dir = os.path.join(out_root, sub)
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
    for label, path in (("--xml", args.xml), ("--build", args.build)):
        if not os.path.exists(path):
            print(f"no such {label} path: {path}", file=sys.stderr)
            return 1
    if not args.out:
        stem = os.path.splitext(os.path.basename(args.xml))[0]
        if stem.endswith(".ytd"):
            stem = stem[:-4]
        args.out = work_path("packed", stem + ".ytd")
        ensure_dir(os.path.dirname(args.out))
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


def cmd_ytd_list(args) -> int:
    try:
        infos = ytdmod.inspect(args.files, core_dir=args.core_dir, ps1=args.ps1, legacy=args.legacy)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not infos:
        print("nothing read", file=sys.stderr)
        return 1
    if args.only:
        for info in infos:
            info.textures = info.find(args.only)
    failed = any(i.error for i in infos)
    if args.json == "-":
        _emit_json([{"file": os.path.basename(i.file), "error": i.error,
                     "textures": [t.__dict__ for t in i.textures]} for i in infos], "-")
    else:
        print(ytdmod.format_table(infos))
        if args.json:
            _emit_json([{"file": os.path.basename(i.file), "error": i.error,
                         "textures": [t.__dict__ for t in i.textures]} for i in infos], args.json)
    return 2 if failed else 0


def cmd_mips_check(args) -> int:
    dds_paths, ytd_paths = [], []
    for p in args.paths:
        if os.path.isdir(p):
            for hit in glob.glob(os.path.join(p, "**", "*.dds"), recursive=True):
                dds_paths.append(hit)
            for hit in glob.glob(os.path.join(p, "**", "*.ytd"), recursive=True):
                ytd_paths.append(hit)
        elif p.lower().endswith(".ytd"):
            ytd_paths.append(p)
        else:
            dds_paths.append(p)

    rows = []  # (source, name, width, height, mips, expected, format)
    for p in dds_paths:
        try:
            h = dds.read_header(p)
        except ValueError as exc:
            print("skip:", exc)
            continue
        rows.append((os.path.basename(p), os.path.basename(p), h.width, h.height, h.mips,
                     max(h.width, h.height).bit_length(), h.label))

    if ytd_paths:
        try:
            infos = ytdmod.inspect(ytd_paths, core_dir=args.core_dir, ps1=args.ps1, legacy=args.legacy)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        for info in infos:
            for t in info.textures:
                rows.append((os.path.basename(info.file), t.name, t.width, t.height, t.mips,
                             t.expected_mips, t.format))

    if not rows:
        print("nothing to check")
        return 1

    bad = [r for r in rows if r[4] < r[5]]
    width = max(len(r[1]) for r in rows) + 2
    payload = [{"source": s, "name": n, "width": w, "height": h, "mips": m,
                "expected": e, "format": f, "ok": m >= e} for s, n, w, h, m, e, f in rows]
    if args.json == "-":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if not bad else 2
    for src, name, w, h, m, exp, fmt in rows:
        if m < exp:
            print(f"BAD  {src:28s} {name:{width}s} {w:5d}x{h:<4d} {m:2d}/{exp:<2d} {fmt}")
    for r in [x for x in rows if x[4] >= x[5]]:
        if args.all:
            print(f"ok   {r[0]:28s} {r[1]:{width}s} {r[2]:5d}x{r[3]:<4d} {r[4]:2d}/{r[5]:<2d} {r[6]}")
    print(f"checked {len(rows)} texture(s): {len(bad)} incomplete, {len(rows) - len(bad)} ok")
    if args.json:
        _emit_json(payload, args.json)
    return 0 if not bad else 2


def cmd_lite(args) -> int:
    files = []
    for p in args.files:
        if os.path.isdir(p):
            files.extend(glob.glob(os.path.join(p, "**", "*.ytd"), recursive=True))
        else:
            files.append(p)
    if not files:
        print("no .ytd files given", file=sys.stderr)
        return 1
    out_dir = ""
    if args.out and len(files) > 1:
        out_dir = args.out
        os.makedirs(out_dir, exist_ok=True)
    failed = 0
    payload = []
    for src in files:
        out = args.out if (args.out and not out_dir) else (
            os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0] + "_lite.ytd") if out_dir else "")
        try:
            written, report = lite.make_lite(src, out_path=out, mode=args.mode, cap=args.cap,
                                             core_dir=args.core_dir, texconv=args.texconv,
                                             report_path=args.report, inplace=args.inplace)
        except Exception as exc:  # noqa: BLE001 - report the file, keep the batch going
            failed += 1
            payload.append({"file": os.path.basename(src), "error": str(exc)})
            print(f"err {os.path.basename(src)}: {exc}")
            continue
        if not written:
            payload.append({"file": os.path.basename(src), "skipped": report})
            print("skip %s: %s" % (os.path.basename(src), report))
            continue
        before, after = os.path.getsize(src), os.path.getsize(written)
        payload.append({"file": os.path.basename(src), "out": written, "before": before, "after": after,
                        "plan": report.splitlines()})
        print(report)
        print(f"ok  {os.path.basename(src)} -> {written} ({before} B -> {after} B)")
    if args.json == "-":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.json:
        _emit_json(payload, args.json)
    return 0 if failed == 0 else 1


def _ped_targets(paths) -> list[tuple[str, str, str]]:
    from . import ped as pedmod
    found: list[tuple[str, str, str]] = []
    for raw in paths:
        path = os.path.abspath(raw)
        if os.path.isdir(path):
            found.extend(pedmod.pairs(path))
            continue
        stem = os.path.splitext(path)[0]
        ydd, ymt = stem + ".ydd", stem + ".ymt"
        if os.path.isfile(ydd) and os.path.isfile(ymt):
            found.append((os.path.basename(stem), ydd, ymt))
    seen, unique = set(), []
    for item in found:
        key = item[1].lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def cmd_mips_fix(args) -> int:
    paths = []
    for p in args.paths:
        if os.path.isdir(p):
            paths.extend(sorted(glob.glob(os.path.join(p, "**", "*.ytd"), recursive=True)))
        else:
            paths.append(p)
    if not paths:
        print("no .ytd files given", file=sys.stderr)
        return 2

    out_dir = ""
    single_out = ""
    if args.out:
        if len(paths) == 1 and not os.path.isdir(args.out):
            single_out = args.out
        else:
            out_dir = args.out
            os.makedirs(out_dir, exist_ok=True)

    done = failed = 0
    for path in paths:
        out_path = ""
        if single_out:
            out_path = single_out
        elif out_dir:
            out_path = os.path.join(out_dir, os.path.basename(path))
        try:
            final, report = lite.fix_mips(path, out_path=out_path, core_dir=args.core_dir,
                                          texconv=args.texconv, inplace=args.inplace)
        except Exception as exc:
            failed += 1
            print("err  %s: %s" % (os.path.basename(path), exc))
            continue
        done += 1
        changed = len([1 for line in report.splitlines() if line.strip()])
        print("ok   %s -> %s (%d texture(s) rebuilt)" % (os.path.basename(path),
                                                         os.path.basename(final), changed))
    print("%d rebuilt, %d failed" % (done, failed))
    return 0 if failed == 0 else 2


def cmd_ped_check(args) -> int:
    from . import ped as pedmod
    core = args.core_dir or cw.find_corewalker()
    if not core:
        print("err  CodeWalker not found; pass --core-dir", file=sys.stderr)
        return 2
    targets = _ped_targets(args.paths)
    if not targets:
        print("err  no .ydd / .ymt pairs found", file=sys.stderr)
        return 2
    rows, bad = [], 0
    for stem, ydd, ymt in targets:
        try:
            report = pedmod.check_pair(stem, ydd, ymt, core)
        except Exception as exc:                          # noqa: BLE001
            bad += 1
            rows.append({"name": stem, "ok": False, "problems": [str(exc)]})
            print("bad  %-30s %s" % (stem, str(exc)[:110]))
            continue
        if report.ok:
            rows.append({"name": stem, "ok": True, "problems": [], "notes": report.notes,
                         "legacy": report.legacy})
            print("ok   %-30s %d drawable(s)%s" % (stem, len(report.ydd_drawables),
                                                   "  gen8" if report.legacy else ""))
        else:
            bad += 1
            rows.append({"name": stem, "ok": False, "problems": report.problems,
                         "notes": report.notes, "legacy": report.legacy})
            print("bad  %-30s %s" % (stem, report.problems[0][:110]))
            for extra in report.problems[1:3]:
                print("     %s" % extra[:110])
    print("\n%d PED(s): %d ok, %d with problems" % (len(targets), len(targets) - bad, bad))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
        print("json -> %s" % args.json)
    return 0 if bad == 0 else 1


def cmd_ped_fix(args) -> int:
    from . import ped as pedmod
    core = args.core_dir or cw.find_corewalker()
    if not core:
        print("err  CodeWalker not found; pass --core-dir", file=sys.stderr)
        return 2
    targets = _ped_targets(args.paths)
    if not targets:
        print("err  no .ydd / .ymt pairs found", file=sys.stderr)
        return 2
    done = failed = skipped = 0
    for stem, ydd, ymt in targets:
        try:
            report = pedmod.check_pair(stem, ydd, ymt, core)
        except Exception as exc:                          # noqa: BLE001
            failed += 1
            print("bad  %-30s %s" % (stem, str(exc)[:110]))
            continue
        if report.ok:
            skipped += 1
            print("skip %-30s already ok" % stem)
            continue
        structural = any(("drawable" in p or "compInfos" in p) for p in report.problems)
        action = "align" if structural else "repair"
        if not args.apply:
            print("plan %-30s %s (%s)" % (stem, action, report.problems[0][:90]))
            continue
        try:
            if structural:
                changes, _ = pedmod.align_pair(stem, ydd, ymt, core, apply=True)
            else:
                changes, _ = pedmod.fix_pair(stem, ydd, ymt, core)
            done += 1
            print("ok   %-30s %s: %d change(s), backup %s.bak" % (stem, action, len(changes), os.path.basename(ymt)))
        except Exception as exc:                          # noqa: BLE001
            failed += 1
            print("bad  %-30s %s" % (stem, str(exc)[:110]))
    if not args.apply:
        print("\ndry run: %d pair(s) would change; add --apply to write (a .bak is kept)" % (len(targets) - skipped))
        return 0
    print("\n%d fixed, %d skipped, %d failed" % (done, skipped, failed))
    return 0 if failed == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gtatools", description="GTA V asset helpers")
    p.add_argument("--work", default="",
                   help="working folder; every default output goes below it")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--work", default=argparse.SUPPRESS,
                        help="working folder; every default output goes below it")

    json_help = "write JSON here; bare --json prints it to stdout"

    n = sub.add_parser("normals", parents=[common], help="badge diffuse -> normal map (DDS)")
    n.add_argument("src", help="DDS/PNG file, or a folder searched recursively")
    n.add_argument("--out", default="", help="output folder (default: <work>/normals, mirrors the input tree)")
    n.add_argument("--scratch", default="", help="scratch folder for decoded PNGs (default: <out>/_work)")
    n.add_argument("--strength", type=float, default=6.5, help="slope gain (default 6.5)")
    n.add_argument("--blur", type=float, default=1.2, help="height-field blur radius (default 1.2)")
    n.add_argument("--fmt", default="DXT5", help="texconv format, e.g. DXT5 / BC5_UNORM")
    n.add_argument("--max-mips", type=int, default=12, help="cap the generated mip chain")
    n.add_argument("--sheet", default="", help="write a before/after contact sheet here")
    n.add_argument("--sheet-rows", type=int, default=12, help="max rows in the contact sheet")
    n.add_argument("--texconv", default=DEFAULT_TEXCONV, help="path to texconv.exe")
    n.set_defaults(func=cmd_normals)

    a = sub.add_parser("audit", parents=[common], help="audit a CPedVariationInfo XML")
    a.add_argument("file", help="a .ymt.xml exported by CodeWalker")
    a.add_argument("--json", nargs="?", const="-", default="", help=json_help)
    a.set_defaults(func=cmd_audit)

    s = sub.add_parser("scale", parents=[common], help="rescale DDS files, keeping their format and mip depth")
    s.add_argument("paths", nargs="+", help="DDS files or folders")
    s.add_argument("--out", default="", help="output folder (default: <work>/scaled, mirrors the input tree)")
    s.add_argument("--long-edge", type=int, default=1536, help="target long edge")
    s.add_argument("--min-edge", type=int, default=0, help="skip files whose long edge is <= this")
    s.add_argument("--texconv", default=DEFAULT_TEXCONV, help="path to texconv.exe")
    s.set_defaults(func=cmd_scale)

    k = sub.add_parser("pack", parents=[common], help="pack a YTD from CodeWalker XML + DDS folder")
    k.add_argument("--xml", required=True, help="the .ytd.xml exported by CodeWalker")
    k.add_argument("--build", required=True, help="folder holding the DDS payloads")
    k.add_argument("--out", default="", help="path of the .ytd to write (default: <work>/packed/<name>.ytd)")
    k.add_argument("--core-dir", default="",
                   help="CodeWalker folder holding CodeWalker.Core.dll; auto-detected when omitted")
    k.add_argument("--legacy", action="store_true", help="write gen8 (version 165) instead of gen9")
    k.add_argument("--original", default="", help="copy G9/usage descriptors from this archive")
    k.add_argument("--ps1", default=DEFAULT_PS1, help="the pack_ytd.ps1 bridge script")
    k.set_defaults(func=cmd_pack)

    y = sub.add_parser("ytd", parents=[common], help="inspect a texture dictionary (read-only)")
    ysub = y.add_subparsers(dest="ytd_cmd", required=True)
    yl = ysub.add_parser("list", help="list the textures inside .ytd files")
    yl.add_argument("files", nargs="+", help=".ytd files")
    yl.add_argument("--only", default="", help="only show names containing this substring")
    yl.add_argument("--json", nargs="?", const="-", default="", help=json_help)
    yl.add_argument("--legacy", action="store_true", help="parse as gen8 (165) instead of gen9 (159)")
    yl.add_argument("--core-dir", default="", help="CodeWalker folder; auto-detected when omitted")
    yl.add_argument("--ps1", default=ytdmod.DEFAULT_PS1, help="the ytd_inspect.ps1 bridge script")
    yl.set_defaults(func=cmd_ytd_list)

    li = sub.add_parser("lite", parents=[common],
                        help="write lite.ytd: shrink the textures of an existing dictionary")
    li.add_argument("files", nargs="+", help=".ytd files or folders")
    li.add_argument("--mode", default=lite.MODE_CAP, choices=list(lite.MODES),
                    help="cap: shrink anything above --cap; tier: snap to 1024/1536/2048; "
                         "agg: cap plus format conversion")
    li.add_argument("--cap", type=int, default=2048, help="long-edge limit for cap/agg modes")
    li.add_argument("--out", default="", help="output .ytd, or a folder when several inputs are given")
    li.add_argument("--inplace", action="store_true",
                    help="overwrite each input and keep the previous file as <name>.ytd.bak")
    li.add_argument("--report", default="", help="write the per-texture plan here")
    li.add_argument("--core-dir", default="", help="CodeWalker folder; auto-detected when omitted")
    li.add_argument("--texconv", default=DEFAULT_TEXCONV, help="path to texconv.exe")
    li.add_argument("--json", nargs="?", const="-", default="", help=json_help)
    li.set_defaults(func=cmd_lite)

    m = sub.add_parser("mips", parents=[common], help="check or repair mip chains")
    msub = m.add_subparsers(dest="mips_cmd", required=True)
    mc = msub.add_parser("check", help="report textures whose mip chain is incomplete")
    mc.add_argument("paths", nargs="+", help=".ytd and/or .dds files or folders")
    mc.add_argument("--all", action="store_true", help="also print the textures that are fine")
    mc.add_argument("--json", nargs="?", const="-", default="", help=json_help)
    mc.add_argument("--legacy", action="store_true", help="parse .ytd as gen8 (165)")
    mc.add_argument("--core-dir", default="", help="CodeWalker folder; auto-detected when omitted")
    mc.add_argument("--ps1", default=ytdmod.DEFAULT_PS1, help="the ytd_inspect.ps1 bridge script")
    mc.set_defaults(func=cmd_mips_check)

    mf = msub.add_parser("fix", help="rebuild the dictionary with full mip chains (keeps a .bak with --inplace)")
    mf.add_argument("paths", nargs="+", help=".ytd files or folders")
    mf.add_argument("--out", default="", help="output .ytd, or a folder for several inputs")
    mf.add_argument("--inplace", action="store_true", help="overwrite each input, keeping <name>.ytd.bak")
    mf.add_argument("--core-dir", default="", help="CodeWalker folder; auto-detected when omitted")
    mf.add_argument("--texconv", default="", help="path to texconv.exe")
    mf.set_defaults(func=cmd_mips_fix)

    p_ = sub.add_parser("ped", parents=[common], help="audit or repair ped .ymt against its .ydd")
    psub = p_.add_subparsers(dest="ped_cmd", required=True)

    pc = psub.add_parser("check", help="report peds whose .ymt does not match the .ydd")
    pc.add_argument("paths", nargs="+", help="ped folders, or a .ydd / .ymt file")
    pc.add_argument("--core-dir", default="", help="folder holding CodeWalker.Core.dll")
    pc.add_argument("--json", default="", metavar="PATH", help="also write the findings as JSON")
    pc.set_defaults(func=cmd_ped_check)

    pf = psub.add_parser("fix", help="repair the .ymt files (keeps a .bak); dry run without --apply")
    pf.add_argument("paths", nargs="+", help="ped folders, or a .ydd / .ymt file")
    pf.add_argument("--core-dir", default="", help="folder holding CodeWalker.Core.dll")
    pf.add_argument("--apply", action="store_true", help="actually write; otherwise only report the action")
    pf.set_defaults(func=cmd_ped_fix)
    return p


def _safe_console() -> None:
    """Never let a print() kill the run: replace characters the console cannot encode."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:                                   # noqa: BLE001
            pass


def main(argv=None) -> int:
    _safe_console()
    args = build_parser().parse_args(argv)
    global WORK
    raw = getattr(args, "work", "")
    if raw:
        WORK = os.path.abspath(raw)
        os.makedirs(WORK, exist_ok=True)
        print(f"work: {WORK}")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
