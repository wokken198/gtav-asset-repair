"""Build a `lite.ytd`: re-encode the textures of an existing dictionary at a smaller size.

The pipeline is export -> resize (texconv) -> pack, all through CodeWalker so the
container keeps its original generation (gen9 stays gen9). Every texture is decided
before anything is written; the plan can be inspected without touching the archive.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from typing import Iterable

from . import cw, dds, ytd as ytdmod

MODE_CAP = "cap"
MODE_TIER = "tier"
MODE_AGGRESSIVE = "agg"
MODES = (MODE_CAP, MODE_TIER, MODE_AGGRESSIVE)

TIERS = (1024, 1536, 2048)
MIN_SIDE = 1024

def _find_resource(name: str) -> str:
    """Locate a bundled .ps1: PyInstaller temp dir, exe dir, then the source tree."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    mei = getattr(sys, "_MEIPASS", "")
    if mei:
        candidates.append(os.path.join(mei, name))
        candidates.append(os.path.join(mei, "resources", name))
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0] or ""))
    candidates.append(os.path.join(exe_dir, name))
    candidates.append(os.path.join(exe_dir, "resources", name))
    candidates.append(os.path.join(here, name))
    candidates.append(os.path.join(here, "..", "..", "resources", name))
    candidates.append(os.path.join(os.getcwd(), "resources", name))
    for path in candidates:
        if path and os.path.isfile(path):
            return os.path.abspath(path)
    return os.path.abspath(os.path.join(here, "..", "..", "resources", name))

DEFAULT_EXPORT_PS1 = _find_resource("ytd_export.ps1")
DEFAULT_PACK_PS1 = _find_resource("pack_ytd.ps1")

NORMAL_HINTS = ("_n", "_nrm", "_normal", "normal")
KEEP_FORMAT_HINTS = ("spec", "gloss", "dirt", "decal", "_s_", "mask", "script_rt")

if sys.platform == "win32":
    _NO_WINDOW = subprocess.CREATE_NO_WINDOW
    _HIDDEN = subprocess.STARTUPINFO()
    _HIDDEN.dwFlags |= subprocess.STARTF_USESHOWWINDOW
else:
    _NO_WINDOW = 0
    _HIDDEN = None


@dataclass
class Entry:
    name: str
    file: str
    width: int
    height: int
    mips: int
    format: str
    usage: str = ""


@dataclass
class Step:
    entry: Entry
    new_width: int = 0
    new_height: int = 0
    new_mips: int = 0
    new_format: str = ""
    resize: bool = False
    reformat: bool = False
    skip: bool = False
    reason: str = ""

    @property
    def changed(self) -> bool:
        return (self.resize or self.reformat) and not self.skip


def _mips_for(width: int, height: int) -> int:
    return max(width, height).bit_length()


def _round4(value: int) -> int:
    return max(4, (value + 2) & ~3)


def target_size(width: int, height: int, mode: str, cap: int) -> tuple[int, int] | None:
    """Return the new size for one texture, or None when it should keep its size."""
    long_side = max(width, height)
    if long_side <= MIN_SIDE:
        return None
    if mode in (MODE_CAP, MODE_AGGRESSIVE):
        if long_side <= cap:
            return None
        target = cap
    else:
        target = None
        for tier in TIERS:
            if long_side >= tier:
                target = tier
        if target is None or target == long_side:
            return None
    scale = target / float(long_side)
    return _round4(int(round(width * scale))), _round4(int(round(height * scale)))


def _is_normal(entry: Entry) -> bool:
    name = entry.name.lower()
    if entry.usage.upper() == "NORMAL":
        return True
    if entry.format.upper() in ("D3DFMT_ATI2", "ATI2", "BC5U", "D3DFMT_BC5"):
        return True
    return any(hint in name for hint in NORMAL_HINTS)


def _keep_format(entry: Entry) -> bool:
    name = entry.name.lower()
    return any(hint in name for hint in KEEP_FORMAT_HINTS)


def _format_for(entry: Entry, alpha_used: bool, grayscale: bool) -> str:
    """Aggressive mode: the one format swap worth doing, guarded by name and pixels."""
    if _is_normal(entry) or _keep_format(entry):
        return entry.format
    fmt = entry.format.upper()
    if fmt in ("D3DFMT_A8R8G8B8", "D3DFMT_A8B8G8R8", "A8R8G8B8", "B8G8R8A8"):
        return "D3DFMT_DXT5"
    if fmt == "D3DFMT_DXT5" and not alpha_used:
        return "D3DFMT_DXT1"
    return entry.format


def plan(entries: Iterable[Entry], mode: str, cap: int = 2048,
         pixels: dict[str, tuple[bool, bool]] | None = None) -> list[Step]:
    """Decide what to do with every texture. `pixels` maps name -> (alpha_used, grayscale)."""
    steps: list[Step] = []
    for entry in entries:
        step = Step(entry=entry, new_width=entry.width, new_height=entry.height,
                    new_mips=entry.mips, new_format=entry.format)
        long_side = max(entry.width, entry.height)
        if long_side < MIN_SIDE:
            step.skip = True
            step.reason = "below %d px" % MIN_SIDE
            steps.append(step)
            continue
        size = target_size(entry.width, entry.height, mode, cap)
        if size is not None:
            step.new_width, step.new_height = size
            step.resize = True
            need = _mips_for(step.new_width, step.new_height)
            step.new_mips = min(need, entry.mips) if entry.mips > 1 else 1
        if mode == MODE_AGGRESSIVE:
            alpha_used, grayscale = (pixels or {}).get(entry.name, (True, False))
            fmt = _format_for(entry, alpha_used, grayscale)
            if fmt != entry.format:
                step.new_format = fmt
                step.reformat = True
        if not (step.resize or step.reformat):
            step.skip = True
            step.reason = "already within limit" if size is None else "no change"
        steps.append(step)
    return steps


BLOCK_BYTES = {
    "DXT1": 8, "BC1_UNORM": 8, "BC1_TYPELESS": 8,
    "DXT5": 16, "BC3_UNORM": 16, "BC2_UNORM": 16,
    "BC7_UNORM": 16, "BC5_UNORM": 16, "ATI2": 16,
    "L8": 1, "A8": 1, "R8": 1,
    "A8R8G8B8": 4, "B8G8R8A8": 4, "R8G8B8A8": 4,
}


def tex_bytes(width: int, height: int, fmt: str, mips: int) -> int:
    """Rough payload size of one texture, mips included."""
    block = BLOCK_BYTES.get(fmt.upper() if isinstance(fmt, str) else fmt, 0)
    w, h, total = max(1, width), max(1, height), 0
    for _ in range(max(1, mips)):
        if block:
            total += max(1, w // 4) * max(1, h // 4) * block
        else:
            total += w * h * 4
        w, h = max(1, w // 2), max(1, h // 2)
    return total


def step_bytes(step: "Step", after: bool = False) -> int:
    if after:
        width = step.new_width or step.entry.width
        height = step.new_height or step.entry.height
        mips = step.new_mips or step.entry.mips
        fmt = step.new_format or step.entry.format
    else:
        width, height = step.entry.width, step.entry.height
        mips, fmt = step.entry.mips, step.entry.format
    return tex_bytes(width, height, fmt, mips)


def totals(steps: list["Step"]) -> tuple[int, int]:
    """(before, after) payload bytes for a plan."""
    before = sum(step_bytes(step, False) for step in steps)
    after = sum(step_bytes(step, True) for step in steps)
    return before, after


def plan_text(steps: list[Step]) -> str:
    lines = []
    for step in steps:
        e = step.entry
        before = "%dx%d %s %d mips" % (e.width, e.height, e.format, e.mips)
        if step.skip:
            lines.append("%-32s %-34s skipped (%s)" % (e.name, before, step.reason))
            continue
        after = "%dx%d %s %d mips" % (step.new_width, step.new_height, step.new_format, step.new_mips)
        tags = []
        if step.resize:
            tags.append("resize")
        if step.reformat:
            tags.append("format")
        lines.append("%-32s %-34s -> %-34s %s" % (e.name, before, after, "+".join(tags)))
    return "\n".join(lines)


# ---------------------------------------------------------------- reading xml

_ITEM_RE = re.compile(r"<Item>(.*?)</Item>", re.S)


def _tag(block: str, name: str) -> str:
    """Read `<Name>text</Name>`, `<Width value="256" />` and `<Format>X</Format>` alike."""
    empty = re.search(r"<%s\b([^>]*?)/>" % name, block)
    if empty:
        value = re.search(r'value="([^"]*)"', empty.group(1))
        return value.group(1).strip() if value else ""
    full = re.search(r"<%s\b([^>]*)>(.*?)</%s>" % (name, name), block, re.S)
    if not full:
        return ""
    value = re.search(r'value="([^"]*)"', full.group(1))
    if value:
        return value.group(1).strip()
    return full.group(2).strip()


def read_entries(xml_path: str) -> list[Entry]:
    with open(xml_path, encoding="utf-8") as fh:
        text = fh.read()
    entries = []
    for block in _ITEM_RE.findall(text):
        entries.append(Entry(
            name=_tag(block, "Name"),
            file=_tag(block, "FileName"),
            width=int(_tag(block, "Width") or 0),
            height=int(_tag(block, "Height") or 0),
            mips=int(_tag(block, "MipLevels") or 0),
            format=_tag(block, "Format"),
            usage=_tag(block, "Usage"),
        ))
    return entries


def write_entries(xml_path: str, steps: list[Step]) -> None:
    """Update the per-item size/mip/format fields to match what texconv produced."""
    with open(xml_path, encoding="utf-8") as fh:
        text = fh.read()
    by_name = {step.entry.name: step for step in steps if step.changed}

    def repl(match):
        block = match.group(0)
        name = _tag(block, "Name")
        step = by_name.get(name)
        if step is None:
            return block
        block = re.sub(r"<Width value=\"\d+\" />", '<Width value="%d" />' % step.new_width, block)
        block = re.sub(r"<Height value=\"\d+\" />", '<Height value="%d" />' % step.new_height, block)
        block = re.sub(r"<MipLevels value=\"\d+\" />", '<MipLevels value="%d" />' % step.new_mips, block)
        block = re.sub(r"<Format>[^<]*</Format>", "<Format>%s</Format>" % step.new_format, block)
        return block

    text = _ITEM_RE.sub(repl, text)
    with open(xml_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# --------------------------------------------------------------- pixel probing

def probe_pixels(dds_path: str, png_dir: str, texconv: str, samples: int = 4096) -> tuple[bool, bool]:
    """Return (alpha_used, grayscale) by decoding the DDS once and sampling it."""
    from PIL import Image

    dds.decode(png_dir, [dds_path], texconv)
    base = os.path.splitext(os.path.basename(dds_path))[0]
    png = os.path.join(png_dir, base + ".png")
    if not os.path.exists(png):
        for f in os.listdir(png_dir):
            if f.lower() == base.lower() + ".png":
                png = os.path.join(png_dir, f)
                break
    im = Image.open(png).convert("RGBA")
    im.thumbnail((128, 128))
    pixels = list(im.getdata())
    step = max(1, len(pixels) // samples)
    picked = pixels[::step]
    alpha_used = any(p[3] < 250 for p in picked)
    grayscale = all(abs(p[0] - p[1]) <= 6 and abs(p[1] - p[2]) <= 6 for p in picked)
    return alpha_used, grayscale


# ------------------------------------------------------------------- pipeline

def _ps1_error(stderr: str, stdout: str) -> str:
    """Pull the human readable message out of PowerShell's error noise."""
    lines = [ln.strip() for ln in (stderr or stdout or "").splitlines() if ln.strip()]
    keep = []
    for line in lines:
        if line.startswith("+") or line.startswith("At ") or line.startswith("CategoryInfo") \
                or line.startswith("FullyQualifiedErrorId"):
            continue
        keep.append(line)
    for line in keep:
        if ".ps1 :" in line:                    # drop the script path PowerShell prefixes
            line = line.split(".ps1 :", 1)[1].strip()
        if "Load" in line and ("异常" in line or "Exception" in line or "调用" in line):
            return "CodeWalker could not read this archive (corrupt, or not a texture dictionary)"
        if "Texture file not found:" in line:
            missing = line.split("Texture file not found:", 1)[1].strip()
            return "the export is missing a texture file (%s); the archive cannot be rebuilt" % missing
        if "Exception calling" in line and ":" in line:
            continue
        if "Exception" in line and len(keep) == 1:
            return line[:400]
    if keep:
        return keep[0][:400]
    return "PowerShell failed without a message"


def _decode(raw: bytes) -> str:
    """PowerShell writes GBK on a Chinese Windows console; try UTF-8 first, then GBK."""
    if not raw:
        return ""
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _run_ps1(args: list[str]) -> str:
    proc = subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass"] + args,
                          capture_output=True,
                          creationflags=_NO_WINDOW, startupinfo=_HIDDEN)
    if proc.returncode != 0:
        raise RuntimeError(_ps1_error(_decode(proc.stderr), _decode(proc.stdout)))
    return _decode(proc.stdout)


_TEXCONV_FMT = {
    "D3DFMT_A8R8G8B8": "B8G8R8A8_UNORM",
    "A8R8G8B8": "B8G8R8A8_UNORM",
    "D3DFMT_A8B8G8R8": "R8G8B8A8_UNORM",
    "B8G8R8A8": "B8G8R8A8_UNORM",
    "D3DFMT_DXT1": "BC1_UNORM",
    "D3DFMT_DXT2": "BC2_UNORM",
    "D3DFMT_DXT3": "BC2_UNORM",
    "D3DFMT_DXT4": "BC3_UNORM",
    "D3DFMT_DXT5": "BC3_UNORM",
    "D3DFMT_ATI2": "BC5_UNORM",
    "ATI2": "BC5_UNORM",
    "D3DFMT_BC7": "BC7_UNORM",
    "D3DFMT_L8": "R8_UNORM",
    "D3DFMT_A8": "A8_UNORM",
}


def _placeholder(path: str, entry: Entry, texconv: str, scratch: str) -> None:
    """Write a blank texture so a dictionary missing an export file can still be packed."""
    from PIL import Image

    fmt = _TEXCONV_FMT.get(entry.format.upper(), "")
    if not fmt:
        raise RuntimeError("cannot rebuild missing texture %s (format %s)" % (entry.name, entry.format))
    tmp = os.path.join(scratch, "blank-%s.png" % uuid.uuid4().hex[:8])
    Image.new("RGBA", (max(4, entry.width), max(4, entry.height)), (0, 0, 0, 0)).save(tmp)
    out_dir = os.path.dirname(path)
    dds._run_hidden([dds.resolve_texconv(texconv), "-y", "-o", out_dir,
                     "-w", str(max(4, entry.width)), "-h", str(max(4, entry.height)),
                     "-m", str(max(1, entry.mips)), "-f", fmt, tmp])
    made = os.path.join(out_dir, os.path.splitext(os.path.basename(tmp))[0] + ".dds")
    if not os.path.exists(made):
        raise RuntimeError("could not rebuild missing texture %s" % entry.name)
    if os.path.exists(path):
        os.remove(path)
    os.replace(made, path)


def export(ytd_path: str, work_dir: str, core_dir: str = "", legacy: bool = False,
           texconv: str = "") -> str:
    """Export the dictionary to `work_dir`; return the XML path."""
    core = cw.find_corewalker(core_dir or None, start=os.path.dirname(os.path.abspath(ytd_path)))
    if core is None:
        raise RuntimeError(cw.MISSING_HINT)
    args = ["-File", DEFAULT_EXPORT_PS1, "-Ytd", ytd_path, "-OutDir", work_dir, "-CoreDir", core]
    if legacy:
        args.append("-Legacy")
    _run_ps1(args)
    stem = os.path.splitext(os.path.basename(ytd_path))[0]
    xml = os.path.join(work_dir, stem + ".ytd.xml")
    if not os.path.exists(xml):
        raise RuntimeError("export produced no XML: %s" % xml)
    entries = read_entries(xml)
    missing = [e for e in entries if e.file and not os.path.exists(os.path.join(work_dir, e.file))]
    if missing:
        if not texconv:
            names = ", ".join(e.file for e in missing[:4])
            raise RuntimeError("the export is missing %d texture file(s): %s" % (len(missing), names))
        for entry in missing:
            _placeholder(os.path.join(work_dir, entry.file), entry, texconv, work_dir)
    return xml


def pack(xml_path: str, build_dir: str, out_path: str, original: str, core_dir: str = "",
         legacy: bool = False) -> str:
    core = cw.find_corewalker(core_dir or None, start=os.path.dirname(os.path.abspath(original)))
    if core is None:
        raise RuntimeError(cw.MISSING_HINT)
    args = ["-File", DEFAULT_PACK_PS1, "-Xml", xml_path, "-Build", build_dir, "-Out", out_path,
            "-CoreDir", core, "-Original", original]
    if legacy:
        args.append("-Legacy")
    return _run_ps1(args)


def _apply_one(step: Step, folder: str, texconv: str, work_dir: str) -> None:
    src = os.path.join(folder, step.entry.file)
    if not os.path.exists(src):
        raise FileNotFoundError("missing exported texture: %s" % src)
    cmd = [dds.resolve_texconv(texconv), "-y", "-o", folder]
    if step.resize:
        cmd += ["-w", str(step.new_width), "-h", str(step.new_height)]
    cmd += ["-m", str(step.new_mips)]
    if step.reformat:
        target = {"D3DFMT_DXT1": "BC1_UNORM", "D3DFMT_DXT5": "BC3_UNORM"}.get(step.new_format, "")
        if not target:
            raise ValueError("no texconv mapping for %s" % step.new_format)
        cmd += ["-f", target]
    cmd.append(src)
    dds._run_hidden(cmd)
    if not os.path.exists(src):
        raise RuntimeError("texconv removed the texture without writing a replacement")


def report_header(steps: list[Step], source: str, output: str) -> str:
    """Three lines: texture memory, file size, and the saving that matters to the user."""
    before_mem, after_mem = totals(steps)
    try:
        before_file = os.path.getsize(source)
        after_file = os.path.getsize(output)
    except OSError:
        before_file = after_file = 0
    def pct(before, after):
        if not before:
            return "0%"
        return "%d%%" % round((after - before) * 100.0 / before)
    return "\n".join([
        "memory   %8.1f MB -> %8.1f MB  (%s)" % (before_mem / 1048576.0, after_mem / 1048576.0, pct(before_mem, after_mem)),
        "file     %8.1f MB -> %8.1f MB  (%s)" % (before_file / 1048576.0, after_file / 1048576.0, pct(before_file, after_file)),
    ])


def _publish(final: str, built: str) -> str:
    """Move a freshly built archive onto *final*, keeping the old copy as .bak."""
    if os.path.abspath(final) == os.path.abspath(built):
        return ""
    bak = final + ".bak"
    if os.path.exists(bak):
        try:
            os.remove(bak)
        except OSError:
            pass
    backup = ""
    if os.path.exists(final):
        try:
            os.replace(final, bak)
            backup = bak
        except OSError:
            pass
    os.replace(built, final)
    return backup


def make_lite(ytd_path: str, out_path: str = "", mode: str = MODE_CAP, cap: int = 2048,
              core_dir: str = "", texconv: str = "", report_path: str = "",
              progress=None, inplace: bool = False) -> tuple[str, str]:
    """Compress one dictionary; return (output path, report text)."""
    if mode not in MODES:
        raise ValueError("unknown mode: %s" % mode)
    ytd_path = os.path.abspath(ytd_path)
    version = ytdmod.rsc7_version(ytd_path)
    if version is None:
        raise ValueError("%s is not an RSC7 archive (bad or missing header)" % os.path.basename(ytd_path))
    if version not in (ytdmod.YTD_VERSION_GEN9, ytdmod.YTD_VERSION_LEGACY):
        raise ValueError("%s has RSC7 version %s - not a texture dictionary" % (os.path.basename(ytd_path), version))
    legacy = version == ytdmod.YTD_VERSION_LEGACY

    if out_path:
        final = os.path.abspath(out_path)
    elif inplace:
        final = ytd_path
    else:
        stem = os.path.splitext(os.path.basename(ytd_path))[0]
        final = os.path.join(os.path.dirname(ytd_path), "%s_lite.ytd" % stem)

    scratch = os.path.join(_temp_root(), "lite-" + uuid.uuid4().hex[:8])
    folder = os.path.join(scratch, "tex")
    png_dir = os.path.join(scratch, "png")
    os.makedirs(folder, exist_ok=True)
    os.makedirs(png_dir, exist_ok=True)
    try:
        xml = export(ytd_path, folder, core_dir=core_dir, legacy=legacy, texconv=texconv)
        entries = read_entries(xml)
        pixels = {}
        for entry in entries:
            if max(entry.width, entry.height) < MIN_SIDE or mode != MODE_AGGRESSIVE:
                continue
            try:
                pixels[entry.name] = probe_pixels(os.path.join(folder, entry.file), png_dir, texconv)
            except Exception:
                pixels[entry.name] = (True, False)
        steps = plan(entries, mode, cap, pixels)
        changed = [step for step in steps if step.changed]
        if not changed:
            return "", "nothing to compress: every texture is under the limit or already small"
        total = max(1, len(changed))
        if progress:
            progress(0, total, "resizing %d texture(s)" % total)
        for index, step in enumerate(changed, start=1):
            _apply_one(step, folder, texconv, scratch)
            if progress:
                progress(index, total, step.entry.name)
        built = os.path.join(scratch, "out.ytd")
        if progress:
            progress(total, total, "writing %s" % os.path.basename(final))
        write_entries(xml, steps)
        pack(xml, folder, built, ytd_path, core_dir=core_dir, legacy=legacy)
        check = ytdmod.inspect([built], core_dir=core_dir, legacy=legacy)
        if check and check[0].error:
            raise RuntimeError("written archive cannot be read back: %s" % check[0].error)
        if check and len(check[0].textures) != len(entries):
            raise RuntimeError("texture count changed: %d -> %d" % (len(entries), len(check[0].textures)))
        backup = _publish(final, built)
        report = report_header(steps, ytd_path, final) + "\n" + plan_text(steps)
        if backup:
            report += "\nprevious file kept as %s" % os.path.basename(backup)
        report_path = report_path or (os.path.splitext(final)[0] + "_report.txt")
        with open(report_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(report + "\n")
        return final, report
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


def fix_mips(ytd_path: str, out_path: str = "", core_dir: str = "", texconv: str = "",
             progress=None, only: set | None = None,
             inplace: bool = False) -> tuple[str, str]:
    """Rebuild one dictionary with full mip chains; returns (output path, report text)."""
    ytd_path = os.path.abspath(ytd_path)
    version = ytdmod.rsc7_version(ytd_path)
    if version is None:
        raise ValueError("%s is not an RSC7 archive (bad or missing header)" % os.path.basename(ytd_path))
    if version not in (ytdmod.YTD_VERSION_GEN9, ytdmod.YTD_VERSION_LEGACY):
        raise ValueError("%s has RSC7 version %s - not a texture dictionary" % (os.path.basename(ytd_path), version))
    legacy = version == ytdmod.YTD_VERSION_LEGACY

    if out_path:
        final = os.path.abspath(out_path)
    elif inplace:
        final = ytd_path
    else:
        stem = os.path.splitext(os.path.basename(ytd_path))[0]
        final = os.path.join(os.path.dirname(ytd_path), "%s_mips.ytd" % stem)

    scratch = os.path.join(_temp_root(), "mips-" + uuid.uuid4().hex[:8])
    folder = os.path.join(scratch, "tex")
    os.makedirs(folder, exist_ok=True)
    try:
        xml = export(ytd_path, folder, core_dir=core_dir, legacy=legacy, texconv=texconv)
        entries = read_entries(xml)
        pending = []
        for entry in entries:
            if entry.name.lower().startswith("script_rt"):
                continue
            need = _mips_for(entry.width, entry.height)
            if only is not None and entry.name not in only:
                continue
            if entry.mips and entry.mips < need:
                pending.append((entry, need))
        if not pending:
            return "", "nothing to fix: every texture already has a full mip chain"

        total = len(pending)
        if progress:
            progress(0, total, "adding mips to %d texture(s)" % total)
        fixed = []
        for index, (entry, need) in enumerate(pending, start=1):
            src = os.path.join(folder, entry.file)
            if os.path.exists(src):
                dds._run_hidden([dds.resolve_texconv(texconv), "-y", "-o", folder,
                                 "-m", str(need), src])
                fixed.append((entry, need))
            if progress:
                progress(index, total, entry.name)

        by_name = {entry.name: need for entry, need in fixed}
        with open(xml, encoding="utf-8") as fh:
            text = fh.read()

        def repl(match):
            block = match.group(0)
            name = _tag(block, "Name")
            need = by_name.get(name)
            if need is None:
                return block
            return re.sub(r"<MipLevels value=\"\d+\" />",
                          '<MipLevels value="%d" />' % need, block)

        text = _ITEM_RE.sub(repl, text)
        with open(xml, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

        built = os.path.join(scratch, "out.ytd")
        if progress:
            progress(total, total, "writing %s" % os.path.basename(final))
        pack(xml, folder, built, ytd_path, core_dir=core_dir, legacy=legacy)
        check = ytdmod.inspect([built], core_dir=core_dir, legacy=legacy)
        if check and check[0].error:
            raise RuntimeError("written archive cannot be read back: %s" % check[0].error)
        _publish(final, built)

        lines = ["%s %dx%d %s  %d -> %d mips" % (entry.name, entry.width, entry.height,
                                                entry.format, entry.mips, need)
                 for entry, need in fixed]
        report = "\n".join(lines)
        report_path = os.path.splitext(final)[0] + "_report.txt"
        with open(report_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(report + "\n")
        return final, report
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)


def _temp_root() -> str:
    """A writable scratch root: %TEMP%, else LOCALAPPDATA, else the home directory."""
    candidates = []
    for env in ("TEMP", "TMP"):
        value = os.environ.get(env)
        if value:
            candidates.append(os.path.join(value, "gtav_asset_repair"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(os.path.join(local, "gtav_asset_repair", "_tmp"))
    candidates.append(os.path.join(os.path.expanduser("~"), "gtav_asset_repair-output"))
    for path in candidates:
        try:
            os.makedirs(path, exist_ok=True)
            probe = os.path.join(path, ".probe")
            with open(probe, "w") as fh:
                fh.write("x")
            os.remove(probe)
            return path
        except OSError:
            continue
    raise RuntimeError("no writable scratch directory")
