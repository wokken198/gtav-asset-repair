"""Read a `.ytd` texture dictionary through CodeWalker and print its contents.

The RSC7 container cannot be parsed in pure Python, so this module shells out to
PowerShell + CodeWalker.Core.dll (the same dependency `pack` uses). Everything
here is read-only: no archive is modified.
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
from dataclasses import dataclass, field
from typing import Iterable

from . import cw

DEFAULT_PS1 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "resources", "ytd_inspect.ps1")

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


def inspect(paths: Iterable[str], core_dir: str = "", ps1: str = DEFAULT_PS1,
            legacy: bool = False) -> list[YtdInfo]:
    """Return one YtdInfo per archive; `error` is set when a file cannot be read."""
    paths = [os.path.abspath(p) for p in paths]
    if not paths:
        return []
    core = cw.find_corewalker(core_dir or None, start=os.path.dirname(paths[0]))
    if core is None:
        raise RuntimeError(cw.MISSING_HINT)
    out: list[YtdInfo] = []
    for path in paths:
        warning = ""
        version = rsc7_version(path)
        if version is not None:
            want = YTD_VERSION_LEGACY if legacy else YTD_VERSION_GEN9
            if version != want:
                kind = "gen9 (159/5)" if version == YTD_VERSION_GEN9 else f"version {version}"
                warning = (f"this archive is {kind} but was parsed with "
                           f"{'--legacy' if legacy else 'gen9'}; pass "
                           f"{'--legacy' if not legacy else 'no --legacy'} for real values")
        cmd = ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1,
               "-CoreDir", core, "-Ytd", path]
        if legacy:
            cmd.append("-Legacy")
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        got = 0
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            textures = [Texture(**{k: t[k] for k in ("name", "width", "height", "format", "mips", "bytes")})
                        for t in payload.get("textures", [])]
            out.append(YtdInfo(file=payload.get("path", path), textures=textures,
                               error=payload.get("error", ""), warning=warning))
            got += 1
        if not got:
            msg = (proc.stderr or proc.stdout or "CodeWalker failed").strip().splitlines()
            detail = msg[-1][:300] if msg else "unknown error"
            out.append(YtdInfo(file=path, textures=[], error=detail, warning=warning))
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
