# Changelog

Notable changes only. UI polish, internal fixes and development notes are left out on purpose.

## [0.7.7] - 2026-11-27

**Gen8 to Gen9 conversion, in the GUI.**

### Added

- **Convert page** — folder in, folder out. Walks every subfolder, mirrors the tree, reports one line
  per file and stops on demand. Files that are already gen9, carry an unsupported extension or fail
  to decode are reported and skipped instead of aborting the run.
- **`gen8to9`** converts a Legacy folder to the Enhanced edition without CodeWalker: `.ytd` gets a
  gen9 layout over the same pixels, `.ydd` and `.yft` are rebuilt against the gen9 runtime tables,
  `.ymt` and `.yld` are copied through because their RSC7 version does not change. All 41 vanilla
  ped drawables and all 24 vanilla vehicle fragments come out channel-identical to their sources.
- **Render-target flags survive.** A converted car used to crash the moment it spawned when its
  texture dictionary carried `script_rt_*` dashboard textures: the converter dropped the high bits of
  `usage_data` and the game could not create the render target. Those textures keep their source flags
  now and get the gen9 render-target descriptor bit.

### Changed

- Badge normal maps default to **strength 2.0** (was 4.5) — on the page, in
  `tools/rebuild_badge_normals.py`, in the library and in `gtav-asset-repair normals --strength`.
  The slider still goes higher.
- Fragments convert about twice as fast: the preparation pass no longer walks every vertex array.
- A `.ydd` whose drawables are plain `YdrDrawable` objects keeps the gen8 structural VFTs. Raising
  them to the gen9 table crashed that pack in game while CodeWalker's untouched output loads; retail
  and streamed ped dictionaries still use the gen9 table.

### Fixed

- Texture compression and mip filling work in the portable build on machines where `%TEMP%` and
  `%LOCALAPPDATA%` are locked down: the scratch directory falls back next to the executable.
- Bad files no longer abort a folder run. A file that cannot be decoded or written is reported with
  its error and the rest of the folder continues.
- A short but real `.ytd` (186 bytes, one texture) is no longer mistaken for a placeholder and
  version-bumped into a broken file.
- The YTD page banner and its summary line follow the interface language, and the banner no longer
  mentions CodeWalker.
- The MIP check page reads loose `.dds` files through their DDS header instead of the dictionary
  reader.

## [0.7.1] - 2026-11-25

**CodeWalker is gone. Every page is pure Python.**

Reading, compressing, MIP repair, ped work and RPF defragging run on a vendored fivefury build plus a
self-contained RPF7 reader. No CodeWalker, no OpenIV, no .NET, no PowerShell.

### Added

- **Defrag (RPF)**: rebuild an archive so the space freed by compression actually reaches disk. A child
  archive is only rebuilt when every entry inside it can be read; archives carrying encrypted children
  are left untouched, and the report says how many were skipped.

### Changed

- `pack` requires `--original`. Without the source archive the texture header fields can only be
  guessed, and guesses write archives the game rejects.
- Legacy (gen8) `.ytd` writes keep the source container flags and put every texture on a 4 KB
  boundary. That is what makes them load in game.
- RPF entries stored uncompressed stay uncompressed — the game uses `stored_size != 0` to decide
  whether to inflate.
- Portable build: 85 MB → 73 MB (zip 34.3 MB).

### Fixed

- Badge normal maps wrote the green channel with the wrong sign, so a generated emboss read as an
  engraved groove in game. **Regenerate any normal map made before this release** — the command and
  the parameters are unchanged.
- Archives larger than 1 GB no longer hang; a 3 GB `.rpf` finishes in about 13 seconds.

### Removed

- `cw.py` and the five PowerShell helpers. Only the Python readers remain.

## [0.7.0] - 2026-11-24

**Everything is called `gtav-asset-repair` now.** Breaking for anyone who scripted the old command.

### Changed

- Command: `gtatools …` → `gtav-asset-repair …`; the old entry point is gone on purpose.
- Python package: `gtatools` → `gtav_asset_repair`; the exe, the window and the bundle follow the new
  name.
- DSH bundle: `dsh-gta-tools` → `dsh-gtav-asset-repair`; tool names keep their `gta_*` prefix, so
  existing scripts still call the same functions.
- Repository: `github.com/wokken198/gtav-asset-repair` (old links redirect).

## [0.6.3] and earlier

The 0.4–0.6 line built the five pages one at a time — normal maps, YTD compression, MIP repair,
`ped check` / `ped fix` (Legacy-gen8 peds arrived in 0.6.0) — and settled the visual language.
Per-release notes for that period were mostly UI polish and are not repeated here; the tags still
carry them.
