"""Regenerate car-badge normal maps inside every .ytd of a folder.

Usage:  python tools/rebuild_badge_normals.py "D:/vehicles.rpf" [--dry] [--only zentorno]

Old normals are wrong (green channel inverted) and far too flat; this rebuilds
them from the diffuse that sits next to them, as DXT1 at the original size.
"""
import os, sys, json, time, shutil, subprocess, tempfile, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from gtav_asset_repair import ytd_write, normals as N
from PIL import Image

TEXCONV = os.environ.get("TEXCONV", "texconv.exe")
STRENGTH, BLUR = 4.5, 1.2
BASE = ""
TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_tmp_norm")
y = ytd_write._y()


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if p.returncode != 0:
        raise RuntimeError("cmd=%s | rc=%d | %s" % (" ".join(cmd), p.returncode, (p.stderr or p.stdout or "").strip()[-400:]))


def to_png(dds_path, out_dir):
    run([TEXCONV, "-nologo", "-y", "-ft", "png", "-o", out_dir, dds_path])
    return os.path.join(out_dir, os.path.splitext(os.path.basename(dds_path))[0] + ".png")


def to_dds(png_path, out_dir, mips):
    run([TEXCONV, "-nologo", "-y", "-ft", "dds", "-f", "BC1_UNORM", "-m", str(mips),
         "-o", out_dir, png_path])
    return os.path.join(out_dir, os.path.splitext(os.path.basename(png_path))[0] + ".dds")


def process(ytd_path, dry=False):
    raw = open(ytd_path, "rb").read()
    d = y.read_ytd(raw)
    by_name = {t.name.lower(): i for i, t in enumerate(d.textures)}
    jobs = []
    for i, t in enumerate(d.textures):
        low = t.name.lower()
        if low.endswith(("_n", "_normal")):
            continue
        if not any(k in low for k in ("badge", "logo", "emblem")):
            continue
        for suf in ("_n", "_normal"):
            if low + suf in by_name:
                j = by_name[low + suf]
                jobs.append((i, j, t.name, d.textures[j].name))
                break
    if not jobs:
        return None

    tmp = TEMP_DIR
    tag = "%d_%s" % (time.time_ns() % 10**9, os.path.splitext(os.path.basename(ytd_path))[0][:12])
    try:
        changed = []
        for di, ni, dname, nname in jobs:
            src = d.textures[di]
            old = d.textures[ni]
            dds = os.path.join(tmp, tag + "_d.dds")
            open(dds, "wb").write(src.to_dds_bytes())
            png = to_png(dds, tmp)
            rgba = N.load_rgba(png)
            h = N.height_field(rgba, blur=BLUR)
            arr = N.normal_from_height(h, strength=STRENGTH)
            out_png = os.path.join(tmp, tag + "_n.png")
            Image.fromarray(arr).save(out_png)
            # The rebuilt map follows the diffuse size, which can be smaller than the
            # old normal (some packs ship a 256x128 normal under a 128x128 badge).
            # Asking texconv for more levels than the new size allows fails hard.
            from PIL import Image as _I
            _w, _h = _I.open(out_png).size
            mips = min(old.mip_count, max(_w, _h).bit_length())
            new_dds = to_dds(out_png, tmp, mips)
            if dry:
                changed.append((nname, "would rewrite"))
                continue
            d.textures[ni] = ytd_write.texture_from_dds(nname, new_dds, like=old)
            changed.append((nname, f"{old.format_name}->BC1 {old.width}x{old.height}"))
    finally:
        for fn in os.listdir(TEMP_DIR):
            if fn.startswith(tag):
                try:
                    os.remove(os.path.join(TEMP_DIR, fn))
                except OSError:
                    pass

    if not dry and changed:
        ytd_write.save(d, ytd_path, source=raw, keep_size_flags=not ytd_write.is_gen9(raw))
    return changed


def main():
    global BASE, TEXCONV, TEMP_DIR, STRENGTH, BLUR
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="folder holding .ytd files")
    ap.add_argument("--only", help="only files whose name contains this")
    ap.add_argument("--dry", action="store_true", help="work out the maps but write nothing")
    ap.add_argument("--texconv", default=TEXCONV)
    ap.add_argument("--strength", type=float, default=4.5)
    ap.add_argument("--blur", type=float, default=1.2)
    a = ap.parse_args()
    BASE, TEXCONV = a.folder, a.texconv
    STRENGTH, BLUR = a.strength, a.blur
    os.makedirs(TEMP_DIR, exist_ok=True)
    if not (os.path.isfile(TEXCONV) or shutil.which(TEXCONV)):
        sys.exit("texconv.exe not found (%s). Pass --texconv PATH or put it on PATH." % TEXCONV)
    todo = sorted(f for f in os.listdir(BASE) if f.lower().endswith(".ytd"))
    if a.only:
        todo = [f for f in todo if a.only.lower() in f.lower()]

    t0, ok, fail, rows = time.time(), 0, 0, []
    for k, f in enumerate(todo, 1):
        p = os.path.join(BASE, f)
        try:
            ch = process(p, dry=a.dry)
            if ch:
                ok += 1
                rows.append({"file": f, "changed": [c[0] for c in ch], "detail": [c[1] for c in ch]})
                print(f"[{k}/{len(todo)}] {f}: {', '.join(c[0] for c in ch)}", flush=True)
        except Exception as e:
            fail += 1
            rows.append({"file": f, "error": str(e)[:200]})
            print(f"[{k}/{len(todo)}] {f}: FAIL {e}", flush=True)
    print(f"\ndone {ok} files, {fail} failed, {time.time()-t0:.0f}s")
    json.dump(rows, open(os.path.join(TEMP_DIR, "rebuild_result.json"), "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
