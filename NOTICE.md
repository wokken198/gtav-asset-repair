# Notice

`gtav-asset-repair` — Copyright (c) 2026 wokken198
<https://github.com/wokken198/gtav-asset-repair>

The code is MIT licensed (see `LICENSE`). In practice that means:

- **You may build on it.** A GUI, a desktop app, a fork, a wrapper that shells out
  to the CLI, or just the normal-map maths inside your own tool — all fine, no
  permission needed.
- **Keep the notice.** If you redistribute the code or a derivative, keep the
  copyright line and the MIT text. That is the only condition the license sets.
- **Link back if you can.** A one-line credit such as

  > Badge handling based on [gtav-asset-repair](https://github.com/wokken198/gtav-asset-repair)
  > by wokken198, MIT licensed.

  is not required by MIT, but it is how people find the original when they need the
  unmodified CLI, the changelog, or the known-pitfalls notes.
- **Do not imply endorsement.** Do not present a fork as an official release of this
  project, and do not ship it under the same name.
- **No game assets.** No `.dds`, `.ytd`, `.ydd`, `.ymt`, brand artwork, or Rockstar
  content is included here, and none of it is covered by this license. If you
  distribute such files, that is your own arrangement with their rights holders.

## Third-party code

### fivefury 0.5.1 — vendored, Unlicense (public domain)

`src/gtav_asset_repair/vendor/fivefury/` is a copy of [fivefury](https://github.com/Hancapo/fivefury)
0.5.1 (`fivefury-0.5.1-cp311-abi3-win_amd64.whl`, sha256 `529142f9ffa08443…`), released under
**The Unlicense** — the upstream `LICENSE` text ships inside the vendored tree. Unlicense
dedicates the work to the public domain, so there is no attribution or notice condition;
the copy is kept verbatim and credited here so the provenance stays traceable.

Two things to know before relying on it:

- **It is frozen on purpose.** Upstream states that 0.5.1 is the last planned feature
  release of the Python implementation (development moved to .NET). This project pins that
  version rather than tracking upstream, and two local behaviours are handled in
  `ytd_write.py` instead of inside the vendored tree: the gen9/legacy texture-header
  fields fivefury does not model, and the non-ASCII texture-name refusal. Nothing in
  `vendor/fivefury/` is patched, so replacing the tree with the original wheel stays safe.
- **`_native_abi3.pyd` is a prebuilt binary.** It ships as a stable-ABI CPython extension
  and cannot be reviewed line by line; its PE imports are `bcrypt`, `python3`, the
  MSVC 2015-2022 runtime and the UCRT. The previous arrangement had the same property and
  worse terms — `CodeWalker.Core.dll` is a closed binary with **no licence file at all**,
  which is exactly why this dependency was replaced.

### texconv (DirectXTex, MIT)

`texconv.exe` is expected to be supplied by the user, alongside the project or on `PATH`.
DirectXTex is MIT licensed; see its repository for the full text.

## CodeWalker interop

CodeWalker is **no longer used**. `ped check/fix`, `ytd list`, `lite`, `fix_mips`
and `pack` all run on the vendored fivefury plus `ytd_write.py`.

- `pack` now requires `--original <the archive the XML came from>`: the texture
  header fields (VFT, descriptor flags, usage, G9 descriptors) only exist in the
  source archive, so packing without it can only guess.
- `cw.py` and the five `resources/*.ps1` bridges were deleted on 2026-11-25.
- The `GTA_LITE_LEGACY_CW` escape hatch was removed: legacy writes are native and
  verified in a legacy install.
