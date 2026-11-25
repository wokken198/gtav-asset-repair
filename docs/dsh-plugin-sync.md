# Syncing `dsh-plugin/vendor` before a release

The DSH plugin does not import the package from `src/` — `index.js` spawns
`python -m gtav_asset_repair.cli` with `PYTHONPATH` pointing at its own
`dsh-plugin/vendor/`, so the plugin ships a **frozen copy** of the Python package.
That copy is pinned by hand and is currently at 0.7.0. Everything landed since then
(ped repair without CodeWalker, the YTD writer, the vendored fivefury) is missing
from it, which means a user who installs the plugin from the market still gets the
old behaviour: `ped fix` demands a CodeWalker folder.

This file records what has to be copied, what it costs, and how to prove the copy
works. It is a pre-release step, not a live sync — do not run it on every edit.

## What is out of date (measured 2026-11-25)

| file | `src/` | plugin copy |
| --- | --- | --- |
| `cli.py` | 29,467 B | 27,662 B |
| `cw.py` | 4,134 B | 3,764 B |
| `gui.py` | 97,355 B | 97,099 B |
| `gui_pages.py` | 66,401 B | 65,553 B |
| `lite.py` | 31,261 B | 26,982 B |
| `ped.py` | 27,784 B | 23,813 B |
| `ytd.py` | 6,910 B | 6,162 B |
| `ytd_write.py` | 21,112 B | **missing entirely** |
| `vendor/fivefury/` | 11 MB | **missing entirely** |
| `vendor/trimesh/` (stubs) | 3 files | **missing entirely** |

Unchanged and already in sync: `__init__.py`, `dds.py`, `normals.py`, `ymt.py`.
No files exist only in the plugin copy.

## What the copy has to become

```
dsh-plugin/vendor/gtav_asset_repair/
  *.py                     (all modules from src/, including ytd_write.py)
  vendor/fivefury/         459 .py + _native_abi3.pyd + data/ + drawable/ + ydr/
  vendor/trimesh/          three stub files, __version__ = "0.0.0-stub"
```

`dsh-plugin` goes from 280 KB to roughly **11.5 MB** unpacked. That is the single
decision this document exists to put in front of the release, so state it plainly:

- **Option A — ship it.** Zero install steps, works offline, no `pip`. The npm
  tarball carries 11 MB of Unlicense source plus one prebuilt `.pyd`.
- **Option B — keep the plugin thin and have it call the packaged `.exe`.** The
  plugin then depends on the user having installed the desktop build; the market
  entry becomes a launcher. Smaller, but two install paths to keep working.
- **Option C — download fivefury on first use.** Rejected: `pip install` is
  unusable under the DSH sandbox on this machine (`Permission denied` on
  `pip-unpack-*`), and a silent download failure is exactly the class of bug
  `AGENTS.md` §2 forbids.

Recommendation: **A**, because the plugin's whole value is "no external tools".
11 MB is a one-time cost per install; a broken first-run is permanent irritation.

## Two new preconditions the copy brings

1. **Python ≥ 3.11.** fivefury declares `Requires-Python: >=3.11`, and the plugin
   picks whatever `python`/`python3` it finds (`index.js:18 pythonCandidates`) or
   the DSH runtime's interpreter. `pyproject.toml` currently allows 3.9. Either
   raise it to `>=3.11` or keep the fallback to the desktop `.exe`.
2. **VC++ runtime.** `_native_abi3.pyd` imports `MSVCP140.dll`,
   `MSVCP140_ATOMIC_WAIT.dll`, `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll`. The DSH
   runtime's `python` folder ships only the `VCRUNTIME140*` pair, so a machine
   without the redistributable fails at import. Detect it in `index.js` before the
   first spawn and print the known fix instead of a raw `ImportError`.

## How to sync (script to write: `packaging/sync_plugin.py`)

1. Copy every `src/gtav_asset_repair/*.py` over the plugin copy, skipping
   `__pycache__`.
2. Copy `src/gtav_asset_repair/vendor/` wholesale (fivefury + trimesh stubs).
3. Bump `dsh-plugin/package.json` `version` to match `pyproject.toml`.
4. Re-check `package.json` `files`: `vendor` is listed, `resources/pack_ytd.ps1` is
   listed but only `pack` without `--original` needs it now — keep or drop it with
   the same decision that decides `cw.py`'s fate.
5. Refuse to finish if `src/` has a `DIFF` the script did not copy (protects against
   a half-synced tree).

## How to prove the copy works

Run these against `dsh-plugin/vendor` as `PYTHONPATH`, not against `src/`:

```
python -m gtav_asset_repair.cli ytd list  <a gen9 ytd>          -> 32 textures
python -m gtav_asset_repair.cli ped check <41-ped folder>       -> 41 ok
python -m gtav_asset_repair.cli audit     <a .ymt.xml>          -> no problems
python -m unittest discover -s tests -q                         -> 78 tests OK
```

The four numbers above are the release gate. `ytd list` is the one that proves the
`.pyd` loads outside the packaged `.exe`; if it raises `ImportError: DLL load
failed`, the VC runtime precondition is what bit.

## When

Not now. The Python side still has one unverified path (`stride` on scaled gen8
YTDs, waiting on the in-game pass). Syncing the plugin before that settles means
shipping the same uncertainty twice, and the market entry is the copy that users
cannot patch. Order: finish the gen8 pass → decide `cw.py` → sync → bump → publish.
