"""Minimal DDS header handling + texconv based rescaling.

Only the formats that show up in GTA vehicle/ped texture dictionaries are mapped;
everything else is reported and skipped so a batch never half-writes a bad file.
"""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass

# fourCC -> texconv -f value
FOURCC = {
    b"DXT1": "BC1_UNORM",
    b"DXT3": "BC2_UNORM",
    b"DXT5": "BC3_UNORM",
    b"ATI1": "BC4_UNORM",
    b"BC5U": "BC5_UNORM",
    b"BC4U": "BC4_UNORM",
}
# DXGI format (DX10 header) -> texconv value, plus a display name
DXGI = {
    71: ("BC1_UNORM", "BC1"),
    74: ("BC2_UNORM", "BC2"),
    77: ("BC3_UNORM", "BC3"),
    80: ("BC4_UNORM", "BC4"),
    83: ("BC5_UNORM", "BC5"),
    98: ("BC7_UNORM", "BC7"),
    87: ("B8G8R8A8_UNORM", "A8R8G8B8"),
    28: ("R8G8B8A8_UNORM", "A8R8G8B8"),
    10: ("R16G16B16A16_FLOAT", "A16B16G16R16F"),
}
D3D_MASKS = {
    (0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000): "B8G8R8A8_UNORM",
    (0x000000FF, 0x0000FF00, 0x00FF0000, 0xFF000000): "R8G8B8A8_UNORM",
}


@dataclass
class Header:
    width: int
    height: int
    mips: int
    texconv_fmt: str
    label: str
    offset: int  # where pixel data starts

    @property
    def max_mips(self) -> int:
        return max(self.width, self.height).bit_length()


def read_header(path: str) -> Header:
    with open(path, "rb") as f:
        data = f.read(148)
    if data[:4] != b"DDS ":
        raise ValueError(f"{path}: not a DDS file")
    height, width = struct.unpack_from("<II", data, 12)
    mips = struct.unpack_from("<I", data, 28)[0] or 1
    pf_flags = struct.unpack_from("<I", data, 80)[0]
    fourcc = data[84:88]
    offset = 128
    if fourcc in FOURCC:
        return Header(width, height, mips, FOURCC[fourcc], FOURCC[fourcc], offset)
    if fourcc == b"DX10":
        dxgi = struct.unpack_from("<I", data, 128)[0]
        if dxgi not in DXGI:
            raise ValueError(f"{path}: unsupported DXGI format {dxgi}")
        fmt, label = DXGI[dxgi]
        return Header(width, height, mips, fmt, label, 148)
    if pf_flags & 0x40:  # uncompressed with explicit masks
        masks = struct.unpack_from("<IIII", data, 92)
        if masks in D3D_MASKS:
            return Header(width, height, mips, D3D_MASKS[masks], "A8R8G8B8", offset)
    raise ValueError(f"{path}: unsupported pixel format (flags={pf_flags:#x}, fourcc={fourcc!r})")


TEXCONV_NAMES = ("texconv.exe", "texconv")

if sys.platform == "win32":
    _NO_WINDOW = subprocess.CREATE_NO_WINDOW
    _HIDDEN = subprocess.STARTUPINFO()
    _HIDDEN.dwFlags |= subprocess.STARTF_USESHOWWINDOW
else:
    _NO_WINDOW = 0
    _HIDDEN = None


def _run_hidden(cmd: list[str]) -> None:
    """Run a helper without flashing a console window (packaged builds have none)."""
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
                   creationflags=_NO_WINDOW, startupinfo=_HIDDEN)


def _search_dirs() -> list[str]:
    """Places a bundled texconv can hide: PyInstaller unpack dir, exe dir, cwd and parents."""
    seen, out = set(), []
    for base in (getattr(sys, "_MEIPASS", None),
                 os.path.dirname(os.path.abspath(sys.executable)) if sys.executable else None,
                 os.getcwd()):
        if not base:
            continue
        here = os.path.abspath(base)
        for _ in range(5):
            if here not in seen:
                seen.add(here)
                out.append(here)
            parent = os.path.dirname(here)
            if parent == here:
                break
            here = parent
    return out


def resolve_texconv(texconv: str) -> str:
    """Find texconv: explicit path, PATH, PyInstaller dir, then exe dir / cwd and parents."""
    if texconv and os.path.exists(texconv):
        return texconv
    if texconv:
        found = shutil.which(texconv)
        if found:
            return found
    for name in TEXCONV_NAMES:
        found = shutil.which(name)
        if found:
            return found
    for here in _search_dirs():
        for name in TEXCONV_NAMES:
            candidate = os.path.join(here, name)
            if os.path.exists(candidate):
                return candidate
    raise FileNotFoundError(
        "texconv.exe not found: put it next to this program, on PATH, or set GTA_TOOLS_TEXCONV"
    )


def decode(png_dir: str, dds_paths: list[str], texconv: str) -> None:
    os.makedirs(png_dir, exist_ok=True)
    _run_hidden([resolve_texconv(texconv), "-ft", "png", "-y", "-o", png_dir] + dds_paths)


def encode(png_path: str, fmt: str, mips: int, out_dir: str, texconv: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    _run_hidden([resolve_texconv(texconv), "-f", fmt, "-m", str(mips), "-y", "-o", out_dir, png_path])
    base = os.path.splitext(os.path.basename(png_path))[0]
    out = os.path.join(out_dir, base + ".DDS")
    if not os.path.exists(out):
        for f in os.listdir(out_dir):
            if f.lower() == base.lower() + ".dds":
                return os.path.join(out_dir, f)
        raise FileNotFoundError(f"{png_path}: texconv produced no output")
    return out


def resize_rgba(png_path: str, size: tuple[int, int], dest_png: str) -> None:
    """Resize without the Pillow premultiplied-alpha pitfall: RGB and A are scaled separately."""
    from PIL import Image

    im = Image.open(png_path)
    rgb = im.convert("RGB").resize(size, Image.LANCZOS)
    out = rgb.convert("RGBA")
    if "A" in im.getbands():
        out.putalpha(im.getchannel("A").resize(size, Image.LANCZOS))
    else:
        out.putalpha(255)
    out.save(dest_png)
