"""Read a `.ytd` texture dictionary and print its contents.

Parsing runs in-process through the vendored fivefury reader (public domain, see
`vendor/fivefury/LICENSE`), so listing a dictionary no longer needs CodeWalker or
a PowerShell round trip. Everything here is read-only: no archive is modified.
"""
from __future__ import annotations

import os
import struct
import sys
from dataclasses import dataclass, field
from typing import Iterable

_VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")

# fivefury reports GTA texture formats through its engine enum while CodeWalker
# printed the Direct3D name; keep our output identical to what users already saw.
_FORMAT_NAMES = {"BC1": "DXT1", "BC2": "DXT3", "BC3": "DXT5"}


def _format_name(fmt: object) -> str:
    """Map a reader format enum to the D3D name the old bridge printed."""
    name = getattr(fmt, "name", None) or str(fmt)
    return _FORMAT_NAMES.get(name, name)


def _load_reader():
    """Import the bundled fivefury reader once, without disturbing sys.path."""
    if _VENDOR not in sys.path:
        sys.path.insert(0, _VENDOR)
    from fivefury.ytd import read_ytd        # noqa: PLC0415 - intentionally lazy
    return read_ytd

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

DEFAULT_PS1 = ""

# RSC7 header: "RSC7" + int32 version. Gen9 texture dictionaries are 5, legacy ones 13.
YTD_VERSION_GEN9 = 5
YTD_VERSION_LEGACY = 13


def rsc7_version(path: str) -> int | None:
    """Return the RSC7 version, or None when the file is not an RSC7 resource."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return None
    if len(head) < 8 or head[:4] != b"RSC7":
        return None
    return struct.unpack_from("<I", head, 4)[0]


@dataclass
class Texture:
    name: str
    width: int
    height: int
    format: str
    mips: int
    bytes: int = 0

    @property
    def expected_mips(self) -> int:
        return max(self.width, self.height).bit_length()

    @property
    def mips_ok(self) -> bool:
        return self.mips >= self.expected_mips


@dataclass
class YtdInfo:
    file: str
    textures: list[Texture]
    error: str = ""
    warning: str = ""

    def find(self, needle: str) -> list[Texture]:
        low = needle.lower()
        return [t for t in self.textures if low in t.name.lower()]


_PLACEHOLDER_LIMIT = 512


def _is_placeholder(path: str) -> bool:
    """True for a stub archive: a valid RSC7 header with no graphics page.

    Some car packs ship an empty `+hi.ytd` beside the real files so the game's
    extra-high block still resolves.  Size alone does not settle it: a real
    dictionary can be under 512 bytes (a single 8x8 block with no mips, e.g.
    `mp_m_niko_01/lowr_diff_000_a_uni` at 186 bytes), so the header flags have to
    say the graphics segment is empty as well.
    """
    try:
        if os.path.getsize(path) > _PLACEHOLDER_LIMIT:
            return False
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return False
    if len(head) < 16 or head[:4] != b"RSC7":
        return False
    try:
        _load_reader()
        from fivefury import resource       # noqa: PLC0415 - after _load_reader
        header = resource.read_rsc7_header(head)
        return int(resource.get_resource_size_from_flags(header.graphics_flags)) == 0
    except Exception:                        # noqa: BLE001 - never mask the real error
        return False


def _read_error(exc: BaseException, path: str = "") -> str:
    """Turn a parser failure into one readable line."""
    text = str(exc).strip() or exc.__class__.__name__
    text = text.splitlines()[0][:300]
    if path and _is_placeholder(path):
        return ("placeholder archive (%d bytes, no texture data); game files keep an "
                "empty +hi.ytd next to cars that only ship .yft / .ytd / _hi.yft"
                % os.path.getsize(path))
    return text


def inspect(paths: Iterable[str], core_dir: str = "", ps1: str = DEFAULT_PS1,
            legacy: bool = False) -> list[YtdInfo]:
    """Return one YtdInfo per archive; `error` is set when a file cannot be read.

    `core_dir` and `ps1` are kept for CLI/GUI compatibility but are unused: the
    reader picks the generation from the RSC7 header, so `legacy` only drives the
    warning that tells a caller their flag disagrees with the file.
    """
    paths = [os.path.abspath(p) for p in paths]
    if not paths:
        return []
    read_ytd = _load_reader()
    out: list[YtdInfo] = []
    for path in paths:
        warning = ""
        version = rsc7_version(path)
        if legacy and version == YTD_VERSION_GEN9:
            kind = "gen9 (159/5)" if version == YTD_VERSION_GEN9 else f"version {version}"
            warning = (f"this archive is {kind} but was parsed with --legacy; "
                       f"the reader always follows the header, so values are gen9")
        try:
            archive = read_ytd(path)
        except Exception as exc:                              # noqa: BLE001
            out.append(YtdInfo(file=path, textures=[], error=_read_error(exc, path),
                               warning=warning))
            continue
        textures = [Texture(name=t.name, width=t.width, height=t.height,
                            format=_format_name(t.format), mips=t.mip_count,
                            bytes=len(t.data))
                    for t in archive.textures]
        out.append(YtdInfo(file=path, textures=textures, error="", warning=warning))
    return out


def format_table(infos: list[YtdInfo], show_mips_problem: bool = False) -> str:
    lines = []
    for info in infos:
        name = os.path.basename(info.file)
        if info.error:
            lines.append(f"{name}: {info.error}")
            continue
        if info.warning:
            lines.append(f"{name}: warning: {info.warning}")
        bad = sum(1 for t in info.textures if not t.mips_ok)
        head = f"{name}: {len(info.textures)} texture(s)"
        if bad:
            head += f", {bad} with incomplete mips"
        lines.append(head)
        lines.append(f"  {'name':32s} {'size':>10s} {'format':8s} {'mips':>4s}")
        for t in info.textures:
            flag = " *" if show_mips_problem and not t.mips_ok else ""
            lines.append(f"  {t.name:32s} {t.width:5d}x{t.height:<4d} {t.format:8s} "
                         f"{t.mips:3d}/{t.expected_mips}{flag}")
    return "\n".join(lines)
