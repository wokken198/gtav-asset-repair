# Changelog

Notable changes only. UI polish, internal fixes and development notes are left out on purpose.

## [Unreleased]

### Changed

- Badge normal maps default to **strength 2.0** (was 4.5), on the Normal maps page and in
  `tools/rebuild_badge_normals.py`. Measured on the vanilla `sultan.ytd` badge, 4.5 sat 4.1× away
  from a flat normal; 2.0 lands at 2.0×. The slider still goes higher if you want a stronger emboss.

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
  existing agent scripts still call the same functions.
- Repository: `github.com/wokken198/gtav-asset-repair` (old links redirect).

## [0.6.3] and earlier

The 0.4–0.6 line built the five pages one at a time — normal maps, YTD compression, MIP repair,
`ped check` / `ped fix` (Legacy-gen8 peds arrived in 0.6.0) — and settled the visual language.
Per-release notes for that period were mostly UI polish and are not repeated here; the tags still
carry them.
