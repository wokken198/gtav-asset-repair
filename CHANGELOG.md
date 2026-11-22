# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-11-22

### Added

- A desktop GUI (`python -m gtatools.gui`): pick files or a folder, tune strength,
  blur, alpha weight, format, resize and mip depth, preview the result, run a batch
  with progress and cancel, and write `normals\<name>_n.dds` next to each input.
- English / Chinese and light / dark themes, remembered in `%APPDATA%\gtatools\gui.json`.
- `gtatools-gui` console entry point, `packaging/gui_entry.py` for PyInstaller, and
  `resources/gtatools.ico`.
- `--work` / `--scratch` driven output layout shared by the CLI and the GUI.
- `ytd list` and `mips check` gained the same `--json PATH` / stdout behaviour.

### Fixed

- `height_field()` is now alpha-gated (`alpha * (luma_weight * lum + mask_weight)`), so
  transparent regions no longer show up as a rectangular step in the normal map.
- `ytd list --legacy` on a gen9 archive reports a warning instead of silently printing
  zeroed sizes.
- `scale` no longer upscales; targets at or above the source size count as skipped.

### Changed

- Version bumped to 0.4.0; the DSH bundle now exposes six tools.

## [0.3.0] - 2026-11-22

### Added

- `--work DIR` for every command: default outputs go to `<DIR>/normals`, `<DIR>/scaled` and
  `<DIR>/packed`. Explicit `--out` / `--json` still override it, so existing scripts keep working.
- `pack --out` is now optional: omitting it writes `<work>/packed/<xml stem>.ytd`.
- `normals --scratch` (was `--work`) names the folder for decoded PNGs, avoiding a clash with the new
  global flag.

## [0.2.0] - 2026-11-22

### Added

- `gtatools ytd list` — read-only dump of a texture dictionary (name, size, format, mips) through
  CodeWalker, with `--only` and `--json` filters.
- `gtatools mips check` — reports every `.ytd` / `.dds` whose mip chain is shorter than
  `floor(log2(long edge)) + 1`. `.dds` headers are parsed in pure Python; `.ytd` goes through
  CodeWalker. Exit code `2` when something is incomplete, so it can gate a build.
- `resources/ytd_inspect.ps1` — the CodeWalker bridge behind both commands.
- plugin: `gta_ytd_list` and `gta_mips_check` agent tools, so the bundle now mirrors all six CLI
  operations.
- docs: `docs/why-mips.md` explains the shimmer, with a cropped before/after figure and a GIF.

### Fixed

- `ytd list` / `mips check` now warn when `--legacy` disagrees with the archive's RSC7 header instead
  of silently printing zeroed sizes. `ytd.rsc7_version()` exposes the check.

### Changed

- `--json` now means the same thing everywhere: bare `--json` prints JSON to stdout, `--json PATH`
  writes a file. Previously the three commands disagreed.
- `scale` no longer upscales: a target long edge at or above the source size counts as skipped.
- `normals` / `pack` / `audit` report a readable error instead of a traceback when a path is missing;
  `ytd list` exits `2` when any archive could not be read.

## [0.1.1] - 2026-11-20

### Fixed

- `normals` and `scale` produced one mip level too few on power-of-two textures: a 256-wide atlas came
  out with 8 levels instead of 9. The cap now uses the full chain length, so output matches the source
  texture for every size.
- `normals` nested its output one directory too deep when `--src` pointed at a folder: the folder's own
  name was used as an output subdirectory. Output now only mirrors subdirectories that actually exist
  below the given root.

### Added

- `docs/README.md` — a one-table entry point that maps "what you want to do" to the page that covers it,
  plus the repository layout and the rule that `src/gtatools` and `dsh-plugin/vendor/gtatools` stay
  byte-identical.
- README: a `Docs` section pointing at that entry point and at `dsh-plugin/docs/DETAIL.md`; `Layout`
  now lists `market/` and `docs/`.
- `dsh-plugin/docs/DETAIL.md`: an `Installing from the market index` section, and a note that the page
  covers the bundle while command-line behaviour lives in the README.

## [0.1.0] - 2026-11-19

### Added

- `gtatools normals` — badge diffuse to tangent-space normal map, with margin flattening and an optional
  contact sheet.
- `gtatools audit` — `CPedVariationInfo` consistency checks against the rules vanilla peds follow.
- `gtatools scale` — DDS resizing that keeps pixel format and mip depth, resampling RGB and alpha
  separately.
- `gtatools pack` — build a `.ytd` from a CodeWalker XML export, optionally restoring the gen9
  render-target descriptors that the XML does not carry.
- `dsh-plugin/` — the same four operations as DeepSeek Harness tools, with the Python package vendored
  so nothing needs to be installed.
- `market/index.json` — a market index entry that pins a commit.
