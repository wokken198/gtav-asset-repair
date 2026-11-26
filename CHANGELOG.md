# Changelog

Notable changes only. UI polish, internal fixes and development notes are left out on purpose.

## [0.7.7] - 2026-11-27

### Added

- The portable zip ships two guides instead of one bilingual file: `README.md` for the English
  edition and `README.cn.md` for the Chinese one. Each covers the six pages, the command line, the
  rollback rules and a troubleshooting section that now includes SmartScreen and desktop write denial.
- **GUI Convert page** — a folder-to-folder converter, laid out like the CodeWalker and Alchemist
  dialogs: pick an input folder, get a suggested `<name>-gen9` output folder, press Convert. It walks
  every subfolder, mirrors the directory tree into the output, and reports one line per file in a
  large report panel with a determinate progress bar and a Stop button. Files that are already gen9,
  carry an unsupported extension or fail to decode are reported and skipped instead of aborting the
  run. The page also spells out why this tool rewrites instead of patching, next to the buttons that
  do it.
- **`gen8to9`**: upgrade a Legacy folder to the Enhanced edition without CodeWalker. `.ytd` gets a
  gen9 header over the same pixels (the 18 vehicle dictionaries come out semantically identical,
  and 7 of them byte-identical to CodeWalker's Asset Converter), `.ymt` / `.yld` are copied verbatim
  because their RSC7 version does not change, and `.yft` is reported as skipped instead of being
  written half-converted.
  Verified in game: a converted third-party ped texture dictionary (87 textures, including
  non-power-of-two sizes) loads and draws correctly in the Enhanced edition.
- **`gen8to9` now converts `.ydd`** (165 → 159). The container is rebuilt for gen9 — new vertex
  declarations, gen9 material parameter set, partial-buffer flags `0x00580409` — while geometry and
  skinning are carried over as-is. All 41 vanilla ped drawables come out identical to the gen8 source
  and to CodeWalker's gen9 output across every channel (positions, normals, tangents, UVs, two colour
  sets, blend weights/indices, bone ids, indices, stride, declaration flags). gen8-only material
  parameters with no gen9 slot are dropped, which is what CodeWalker does too; the gen9 hygiene
  parameters it cannot know (`bloodzoneadjust`) come from the shipped gen9 defaults.
  Unlike `.ytd`, the output is not byte-identical to CodeWalker: vertex buffers are re-encoded
  compactly, which is legal but lands on different bytes.
- **`gen8to9` now converts `.yft`** (162 → 171). The fragment is rebuilt against the gen9 runtime
  class tables instead of being skipped: all four container types are now converted. Ground truth was
  the gen9 vehicles that ship with the Enhanced edition, and the result differs from CodeWalker's own
  converter in two places that matter — CodeWalker leaves the legacy class VFTs in place (physics LOD
  `0x406036D8` where retail uses `0x406E02F8`, and five more) and zeroes the gen9-only material
  defaults (`diffusecolor2`, `matDiffuseSpecularRampEnabled`), while this build writes the retail
  values. All 24 vanilla vehicle fragments convert with every mesh channel, material, physics LOD,
  bound and glass pane intact. Collision bounds are int16-quantised in gen9, so their coordinates move
  by at most one quantisation step (~1e-5 model units). Third-party packs whose fragment headers are
  placeholders — resource state 0, junk class VFTs such as `0x4D434850`, a glass pane pointing at a
  non-glass mesh — are normalised to the retail gen9 values rather than refused; the three addon cars
  in the reference corpus (gtr, i8, renventon) convert cleanly that way, where CodeWalker copies the
  junk through untouched.
- **`gen8to9` keeps the gen8 structural VFTs for bare-drawable ped dictionaries.** A `.ydd` whose
  drawables are plain `YdrDrawable` objects (`0x40573178`, common in third-party packs) crashed in
  game when those VFTs were raised to the gen9 table, while the same file with the gen8 values loads
  normally — reproduced on one pack both ways, and CodeWalker's own output (which never touches them)
  loads too. Such dictionaries now keep drawable / shader-group / model / geometry / vertex / index /
  skeleton VFTs at their gen8 values; texture VFTs still move to gen9, and the retail-shaped
  `0x40573158` dictionaries and streamed ped components keep using the gen9 table.
  Verified in game on 2026-11-26, and locked by `test_bare_drawable_pack_keeps_its_legacy_vfts`.
- **`gen8to9` keeps the render-target flags on `script_rt_*` textures.** A converted vehicle crashed
  in game the moment it spawned while the same car with the original (Legacy) texture dictionary was
  fine: the dictionary carries `script_rt_dials_*` dashboard render targets, and the converter used to
  drop the high bits of `usage_data`, leaving `usage_flags` at 0. Dropping them makes the game fail to
  create the render target. Such textures now keep their source `usage_flags` and get the
  render-target bit in their descriptor flags (`0x00260208` → `0x00260228`, matching what Sollumz
  documents for gen9). No earlier sample was affected — none of the 18 vanilla vehicle dictionaries
  carries a `script_rt` texture. Verified in game on the BMW M4 and the Lamborghini Reventon, and
  locked by `TestRenderTargetTextures`.
- **Retracted: `gen8to9` no longer refuses large fragments.** An earlier build skipped any `.yft` or
  `.ydd` whose system segment exceeded 32,768,000 B (4000 pages of 8 KiB), on the theory that the
  gen9 engine caps a single fragment there. That theory was falsified: a shipped Enhanced pack with a
  34,078,720 B (4160-page) system segment loads and spawns in game, larger than the 33 MiB conversions
  that failed. The size check is gone; only `system_segment_size()` remains, as a diagnostic.

### Changed

- A `.ydd` that cannot be decoded (truncated download, unknown payload shape) is reported as a skip
  with the original error text instead of aborting a whole-folder run. Only a file that fails to
  *write* now counts as a failure, so `gen8to9` exits 0 on a folder whose only problem is one bad
  file among hundreds.
- Badge normal maps default to **strength 2.0** (was 4.5), on the Normal maps page and in
  `tools/rebuild_badge_normals.py`. Measured on the vanilla `sultan.ytd` badge, 4.5 sat 4.1× away
  from a flat normal; 2.0 lands at 2.0×. The slider still goes higher if you want a stronger emboss.
  The library default follows: `normals.normal_from_height()` and `gtav-asset-repair normals --strength`
  now also default to 2.0, so a direct API or CLI call no longer silently gets the old 6.5.

### Fixed

- The Textures (YTD) and Mip check pages failed with `no writable scratch directory` on machines
  where `%TEMP%` and `%LOCALAPPDATA%` are locked down. `lite.py` now falls back to a `_tmp` folder
  next to the executable, so compressing and mip filling work in the portable build everywhere.
- The YTD page's legacy-asset banner and its bottom summary line kept the language they were first
  drawn in. Both are rebuilt through `retranslate()` now, and the banner no longer mentions
  CodeWalker — no page needs it any more.
- `gen8to9` fragments convert about twice as fast. The preparation pass walked every vertex array
  (488,110 positions on a 13 MB fragment) only to pin a handful of header values; skipping the vertex
  bulk fields drops preparation from 7.3 s to 0.1 s and the whole file from 17.8 s to 7.9 s. Output
  is byte-identical to the slower build.
- The Convert page rendered blank while the other five pages worked: it is a bare `tk.Frame` and
  never packed itself, unlike the `_Page` subclasses. It claims its slot now.
- A short `.ytd` that really is a texture dictionary is no longer mistaken for a stub. The stub test
  was a 512-byte size cut-off, so a 186-byte Lowrider mouth dictionary — system and graphics segments
  both 8 KiB, one real texture — was "converted" by rewriting its version byte and left broken in
  game. The test is now "RSC7 header present and the graphics segment is empty", which still catches
  the 61-byte placeholder that ships in the reference corpus.
- A `.ytd` that fails to decode (truncated download, junk payload) is reported as a skip with the
  error text. It used to raise a traceback that ended a whole-folder run at the first bad file.
- A file that cannot be written (missing parent path, read-only target) is reported as a failure with
  the OS error instead of a traceback, and no longer aborts the rest of the folder.
- `gen8to9 --json -` writes only JSON to stdout; the human-readable lines move to stderr, so the
  stream can be piped into a JSON parser.
- `gen8to9 --dry-run` says `dry run: no file was written` after the summary, which used to claim
  files had been converted. The `dst` help now spells out both defaults — `<work>/<name>` for a single
  file, `<work>/gen9` for a folder.
- Convert page: switching the language after a run finished (or was stopped) kept redrawing the last
  progress count in the status bar. It now shows the run summary.
- Convert page: the run summary counts stubs, matching the CLI line.
- Convert page: report rows are inserted one slice at a time instead of one row per re-layout, which
  cut the worst main-thread stall during a folder run.
- MIP check page: a loose `.dds` added to the list is read through its DDS header. The page accepted
  `.dds` in its file filter but handed every path to the dictionary reader, so a DDS produced an
  error row or nothing at all; only `.ytd` worked.

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
