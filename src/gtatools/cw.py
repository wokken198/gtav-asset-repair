from __future__ import annotations

import os

CORE_DLL = "CodeWalker.Core.dll"


def _has_core(path: str) -> bool:
    return bool(path) and os.path.isfile(os.path.join(path, CORE_DLL))


def _desktop_variants() -> list[str]:
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    desktop = os.path.join(home, "Desktop")
    roots = [desktop, os.path.join(desktop, "GM"), os.path.join(home, "Downloads"), home]
    out: list[str] = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for name in os.listdir(root):
                if "codewalker" in name.lower():
                    out.append(os.path.join(root, name))
        except OSError:
            continue
    return out


def _common_paths() -> list[str]:
    paths = [
        r"C:\CodeWalker30_dev48",
        r"C:\CodeWalker30_dev47",
        r"C:\CodeWalker30",
        r"C:\Tools\CodeWalker30_dev48",
        r"C:\Program Files\CodeWalker30_dev48",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "CodeWalker30_dev48"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "CodeWalker30_dev48"),
    ]
    paths.extend(_desktop_variants())
    return paths


def _ancestors(start: str, depth: int = 4) -> list[str]:
    current = os.path.abspath(start)
    out: list[str] = []
    for _ in range(depth):
        out.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return out


def candidates(start: str = "") -> list[str]:
    """Every CodeWalker folder we can find, newest build first."""
    seen: dict[str, float] = {}
    for value in (os.environ.get("GTA_TOOLS_CW", ""), os.environ.get("CODEWALKER_DIR", "")):
        if _has_core(value):
            seen[os.path.abspath(value)] = os.path.getmtime(os.path.join(value, CORE_DLL))
    for candidate in _common_paths():
        if _has_core(candidate):
            path = os.path.abspath(candidate)
            try:
                seen[path] = os.path.getmtime(os.path.join(path, CORE_DLL))
            except OSError:
                seen[path] = 0.0
    for base in _ancestors(start or os.getcwd()):
        if _has_core(base):
            path = os.path.abspath(base)
            try:
                seen.setdefault(path, os.path.getmtime(os.path.join(path, CORE_DLL)))
            except OSError:
                seen.setdefault(path, 0.0)
    return [p for p, _ in sorted(seen.items(), key=lambda kv: kv[1], reverse=True)]


def find_corewalker(explicit: str = "", start: str = "") -> str | None:
    """Locate a CodeWalker directory containing CodeWalker.Core.dll.

    Order: explicit argument, GTA_TOOLS_CW / CODEWALKER_DIR, common install
    locations, then the working directory and its parents.
    """
    if explicit and _has_core(explicit):
        return os.path.abspath(explicit)

    for env_name in ("GTA_TOOLS_CW", "CODEWALKER_DIR"):
        value = os.environ.get(env_name, "")
        if _has_core(value):
            return os.path.abspath(value)

    found = candidates(start)
    if found:
        return found[0]

    for base in _ancestors(start or os.getcwd()):
        if _has_core(base):
            return base
        try:
            for name in os.listdir(base):
                if "codewalker" in name.lower() and _has_core(os.path.join(base, name)):
                    return os.path.join(base, name)
        except OSError:
            continue
    return None


MISSING_HINT = (
    "CodeWalker not found. Install CodeWalker (dev48 or newer) and either set "
    "GTA_TOOLS_CW to its folder, pass --core-dir, or place it in a standard spot "
    "such as C:\\CodeWalker30_dev48 or the Desktop. Only 'pack' needs it."
)
