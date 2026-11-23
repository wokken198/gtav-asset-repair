# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.0] - 2026-11-24

**The project, the command and the window are now all called `gtav-asset-repair`.**

This is a breaking change for anyone who scripted the old command.

### Changed

- Command renamed: `gtatools ...` → `gtav-asset-repair ...` (and `gtav-asset-repair-gui`).
  The old `gtatools` entry point is gone on purpose — one name only.
- Python package: `gtatools` → `gtav_asset_repair` (underscores because a Python import name cannot
  contain a hyphen; the distribution, the CLI, the exe and the window all use `gtav-asset-repair`).
- Window title and the nav brand now read `gtav-asset-repair`; the executable is
  `gtav-asset-repair.exe`.
- DeepSeek Harness bundle: `dsh-gta-tools` → `dsh-gtav-asset-repair`. Tool names keep their `gta_*`
  prefix, so existing agent scripts still call the same functions.
- Repository renamed to `github.com/wokken198/gtav-asset-repair` (old links redirect).

### Migration

```bash
pip install -e .
gtav-asset-repair normals <src> --out <out>
```

If you drive the GUI, re-download the portable build: the old exe still works but its footer link and
title point at the old name.

## [0.6.3] - 2026-11-24

### Added
- Stop button on the texture, mip and ped pages: the run stops after the file it is on, and
  everything already written stays written.
- The footer carries a standing warning - back up the originals, verify in game after an aggressive
  pass - plus a clickable link to the issue tracker.

### Fixed
- Two pages could run at the same time and fight over the same files; a single job now owns the
  pipeline and the second page says so instead of starting.
- Picking a ped could not be undone: the list repainted rows by deleting and re-inserting them, which
  dropped the selection and left the counter at zero. Rows are now updated in place against a
  separate picked set, so tick / untick / count / button state all agree.
- Mode cards drew a square focus ring outside their rounded background, which showed up as stray
  colour while clicking between them.

### Changed
- The three compression modes stack the way they are meant to read: mode 1 full width on top, the
  narrow long-edge column on the left, modes 2 and 3 stacked on the right at the same height.
- Defaults are English + light for a first run, so a fresh install opens in the language most users
  of the listing will read.
- Switching language no longer rebuilds pages, so lists, reports and picked files survive it.

## [0.6.2] - 2026-11-24

### Changed
- Second visual pass: a faint 24 px grid behind the content, so cards read as panels on a surface
  instead of floating text; the nav rows are now rounded pills with an icon, a green rail and a
  circled active state; secondary buttons rest on a pale green tint and deepen toward the accent on
  hover; preview thumbnails keep a 32 px inner margin instead of touching the tile edge.
- Corner radius is 8 px for cards and buttons (was 12 / 10), which squares the panels up.
- Nav labels lost their parenthesised second line ("Normal maps (DDS)" instead of a wrapped
  two-liner) so the English column no longer overflows the pill.
- First visual pass, aimed at the flat "dialog box" look: cards are rounded panels with a hairline
  border, buttons are rounded pills with hover / pressed / disabled states, the language and theme
  pickers are real switches with a sliding knob, and the footer status is a coloured dot plus text.
- Card backgrounds are drawn on a canvas rather than a flat frame, so the 16 px inner padding and the
  corner radius survive resizing and both themes.

### Fixed
- `Card.paint()` called `Canvas.lower()` with no argument, which is the *canvas item* command and
  raised `TclError: wrong # args` on every repaint (the log filled with it). The widget is now lowered
  with the raw `lower` Tcl command instead.
- `PillButton` recursively re-entered its own `configure()` from `_draw()` (`RecursionError`), and
  stored its width in `self._w`, which collides with tkinter's internal widget-path attribute
  (`invalid command name "88"`). Widths now live in `self._pw` and redraws are guarded.

## [0.6.1] - 2026-11-23

### Added
- The MIP page explains what it is doing with `script_rt_*`: a permanent line under the report says
  those render targets are skipped on purpose, and a circled help button spells out why (their mip
  chain follows the render-target size, so forcing extra levels blurs or breaks the live picture).

### Changed
- The left navigation keeps a fixed 212 px width in both languages; English entries move the file
  type onto a second line (`Normal map generate` / `(DDS)`), so switching language no longer slides
  the column left and right.
- The `?` affordance is now a circled question-mark button instead of a bare character, and it
  follows the light/dark theme.
- The page subtitle reserves two lines, so the header height is identical in Chinese and English.
- `PED repair` is now `Ped YMT repair` (`PED YMT 修复` in Chinese) in the navigation and page title.

### Fixed
- English UI: the theme switch collapsed to 24 px and the navigation clipped once the labels grew;
  the switches are packed before the title block and the nav column is measured from its longest
  entry (232 -> 255 px before the fixed-width change).
- The packaged build on 125% DPI scaling cut the fixed-width panels: the window, navigation,
  parameter card and preview height now scale with `tk scaling`, and the process declares per-monitor
  DPI awareness before the window is created.

## [0.6.0] - 2026-11-23

### Added
- **Legacy (gen8) ped support**: `ped check` / `ped fix` pick the CodeWalker loader from the
  `.ydd` header (RSC7 v165 = Legacy, v159 = Enhanced), so addon peds exported for the old game
  are audited and repaired without a flag. `ped check --json` reports a `legacy` field and the
  human output tags those rows `gen8`.
- `--legacy` switches on `ped_export.ps1` / `ymt_pack.ps1`, and `ped.legacy_for()` as the single
  place that decides which loader a pair needs.
- Documentation assets: `docs/sample/` (three self-drawn 256 px badges plus a README) and
  `docs/images/sample-compare.png`, so the normal-map effect can be judged without game assets.
- README sections `Scope: what this is, and what it is not`, a support matrix per area,
  `Safety rules the tools follow`, `Try it in one minute` and `Performance notes`.

### Changed
- Project positioning is now **Enhanced & Legacy**: window title, tagline, bundle description and
  README all say so instead of implying Enhanced-only.
- `ped fix` refuses to write when the local CodeWalker build shuffles `.ymt` components, naming
  the build instead of producing a broken file (dev48 writes both generations incorrectly;
  ModDropV-class builds are fine).

### Fixed
- `legacy_for()` treated a missing or truncated header as Enhanced by accident; it now has an
  explicit test for that case.
- README still claimed the ped tools were Enhanced-only after the loader switch landed.
- The packaged build declares DPI awareness through its manifest, so on a 125% display the
  fixed-width panels were laid out at 96 dpi widths inside a scaled window and got clipped;
  the window now scales its base sizes by Tk's scaling factor.

## [0.5.1] - 2026-11-23

### Added
- `gtatools ped check` — audit every `.ydd` / `.ymt` pair and report the ones whose
  declared drawables or texture counts disagree with the geometry (`--json` writes a report).
- `gtatools ped fix` — repair those pairs (`--apply`; a `.bak` is kept next to each file).
- DSH bundle: `gta_ytd_lite`, `gta_ped_check` and `gta_ped_fix`, so the GUI's two new pages are
  reachable from an agent session as well (nine tools in total).

### Changed
- GUI: texture compression and mip repair now write **in place** and keep the previous file as
  `.bak`; the CLI still defaults to a separate `_lite` / `_mips` file and takes `--inplace`.
- Page copy rewritten for all four pages (Chinese and English), including what each tool fixes
  and the `.bak` behaviour; the same wording heads the README.

### Fixed
- CLI crashed with `UnicodeEncodeError` on a GBK console whenever an error message contained a
  character the console could not encode.
- Corrupt archives with an `RSC7` header reached CodeWalker and surfaced a raw PowerShell error;
  the header and version are now validated first and the message says what is wrong.
- PowerShell output is decoded as UTF-8 with a GBK fallback instead of showing `?` on Chinese
  Windows, and the script-path prefix is stripped from error text.
- The page subtitle ran past the window edge once the copy got longer; it now wraps.

## [0.5.0] - 2026-11-22

### Added
- GUI: MIP check page for `.dds` and `.ytd` - lists every texture whose mip chain is
  shorter than the size demands.
- GUI: texture compression page for `.ytd` - Cap / Tier / Aggressive modes, a long-edge
  limit, a plan table, `lite.ytd` plus `lite_report.txt` next to the input.
- `lite` command in the CLI: `gtatools lite file.ytd --mode cap --cap 1024`.
- `resources/ytd_export.ps1`: exports a dictionary through CodeWalker to an XML plus DDS
  files, used by both the page and the CLI.
- `src/gtav_asset_repair/lite.py`: sizing rules, format policy, XML rewrite, texconv resizing and a
  read-back self check of the written archive.

### Changed
- The sidebar is now three features - Normal map (DDS), Mip check (DDS), Texture
  compression (YTD) - instead of four entries, and the YTD list viewer folded into the
  MIP check.
- Log lines stay English and one line per file, including the full output path.

### Fixed
- PowerShell variable names are case-insensitive: the export script no longer shadows its
  own `$Ytd` parameter and passes the dictionary object through as `$dict`.
- XML entries written as `<Width value="256" />` are parsed as well as `<Width>256</Width>`.
- The aggressive mode falls back to the Cap rule instead of the Tier rule.

## [0.4.1] - 2026-11-22

### Added

- A help bubble on the parameters card: every slider explains what it does, what
  vanilla car badges measure, and which value this tool recommends.
- Three-pane preview: the source texture, the generated normal map, and a shaded
  result, side by side.
- Scratch files live in `%TEMP%\gtav_asset_repair\run-<id>` (with `%LOCALAPPDATA%`, the exe
  folder and the input folder as fallbacks) and are deleted as soon as they are used.

### Changed

- The language and theme toggles in the header are fixed-width slider switches, so
  switching EN/ZH no longer shifts the neighbouring control.
- File card buttons are ordered `Add files · Add folder · Remove` with `Clear` on the
  far right.
- Log lines are English only, one line per file, and name the full output path.
- The default strength is now 4.5 — slightly above what vanilla badges measure
  (median slope 0.7-2°, bevels 25-35°) instead of the previous 6.5.

### Fixed

- `texconv.exe` is located inside the frozen bundle and next to the exe, so a
  packaged build starts even when the working directory is elsewhere.
- Child processes no longer flash a console window during preview or generation.
- A result that cannot be written next to the input falls back to `_n_2.dds`,
  `_n_3.dds` … and finally to the user profile, instead of failing the file.
- The worker thread no longer reads Tk variables, which raised
  `RuntimeError: main thread is not in main loop` on some machines.

## [0.4.0] - 2026-11-22

### Added

- A desktop GUI (`python -m gtav_asset_repair.gui`): pick files or a folder, tune strength,
  blur, alpha weight, format, resize and mip depth, preview the result, run a batch
  with progress and cancel, and write `normals\<name>_n.dds` next to each input.
- English / Chinese and light / dark themes, remembered in `%APPDATA%\gtav_asset_repair\gui.json`.
- `gtav_asset_repair-gui` console entry point, `packaging/gui_entry.py` for PyInstaller, and
  `resources/gtav_asset_repair.ico`.
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
  plus the repository layout and the rule that `src/gtav_asset_repair` and `dsh-plugin/vendor/gtav_asset_repair` stay
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
