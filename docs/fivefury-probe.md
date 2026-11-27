# fivefury probe — can it replace CodeWalker.Core?

**Date:** 2026-11-24
**Candidate tested:** `Hancapo/fivefury` 0.5.1, `fivefury-0.5.1-cp311-abi3-win_amd64.whl`, 3,943,728 B, sha256 `529142f9ffa08443…`, **Unlicense**
**Samples:** `..\素材不要动\` (read-only, never modified). gen8 = `ped_gen8\Mai*`, gen9 = `ped_gen9\*`, `ped_ingame_gen9\*`, `vehicles_gen9\*`.
**Method:** wheel unpacked into `_probe\lib`, `sys.path` injection (pip cannot install in this sandbox: `Permission denied` on its unpack dir). Probes live in `_probe\probe_*.py`.

## Verdict

**For the PED repair path (`ped check` / `ped fix`) fivefury replaces CodeWalker outright — measured end to end, no CodeWalker needed on either side of the comparison.** YMT read agrees with CodeWalker on 16/16 sample peds, YMT write lands on the correct component on both generations, the YMT round-trip is semantically lossless, and a real broken sample (`adare4`: ymt declares 3 drawables, the ydd ships 2) was repaired with fivefury alone and then passed a CodeWalker-based re-audit with **0 problems**. A second repair (`Kasumi`: 34 declared, 31 shipped) also passed, and **the gen9 write path is verified in the running game** — a vanilla ped rewritten by fivefury with no value changed spawns and dresses exactly like the original, and the repaired Kasumi shows precisely the slot behaviour the trim predicted (see *In-game check → Result*). The one gap on the read path is gen8 `.ydd`, closed by patch #3 (10 lines, verified below).

For the *whole* toolkit it still needs the YTD header patches (#1, #2) before `pack` can drop `pack_ytd.ps1`. It is the only candidate that is simultaneously permissively licensed (*Unlicense*), embeddable as a wheel, and actually implements YTD/YMT/YDD for both generations.

What it does *not* give us: a CodeWalker-compatible XML layer. Our `export → scale → pack` pipeline uses `.ytd.xml` / `.ydd.xml` / `.ymt.xml` as the intermediate format; with fivefury the intermediate becomes live objects, so `ytd.py`, `ped.py::export_pair` and `ymt.py` change shape (see *Migration*).

## Round 1 — the six questions, answered

Every answer is 实测 (measured) unless marked 文档 / 推测.

### 1. Can it read a real `.ytd`, and does the texture list match CodeWalker's XML?

**Yes, byte for byte.** The old bridge (`ytd_inspect.ps1` → CodeWalker.Core) and the
vendored fivefury were run on the same archives and their output diffed:

| archive | generation | textures | lines compared | result |
|---|---|---|---|---|
| `ped_gen9/HarleySS.ytd` | gen9 (v5) | 32 | 34 | IDENTICAL |
| `ped_gen8/Mai.ytd` | legacy (v13) | 32 | 34 | IDENTICAL |
| `vehicles_gen9/…/cavalcade3.ytd` | gen9 (v5) | 20 | 22 | IDENTICAL |

Name, width, height, format and mip count all agree; the only mapping needed is
`BC1/BC2/BC3` → the D3D names CodeWalker printed (`DXT1/DXT3/DXT5`). Full sweep: 95 of
95 archives that hold textures read back correctly.

### 2. Can a 2048² texture be scaled to 1024 and written back into the same `.ytd`? Size change?

**Yes.** `lite.make_lite --cap 1024` on `ped_gen9/HarleySS.ytd` (largest texture 4096²):

```
before: 32 textures, max 4096px
after:  32 textures, max 1024px
size: 27301656 -> 6956464 bytes   (-74.5%)
memory 307.5 MB -> 67.5 MB (-78%)
```

11 of 32 textures were rescaled, **no format changed**, all 32 names kept, 6.1 s. The
original file is replaced in place (written to a temp name first, then published
atomically).

### 3. After writing, does re-reading show the right count / RSC7 version / mip levels?

**Yes on all three.** The write path re-reads its own output before publishing (`lite.py`
raises `written archive cannot be read back` if that check fails), and the round-trip
probe compares headers and pixels:

```
HarleySS.ytd:   32 -> 32 textures, rsc7 version 5 -> 5, header field differences {}, pixels 32/32
cavalcade3.ytd: 20 -> 20 textures, rsc7 version 5 -> 5, header field differences {}, pixels 20/20
fix_mips: uppr_diff_000_b_pak 2048x2048 D3DFMT_DXT5 10 -> 12 mips
```

Full sweep: 95 archives, read → write → read, **zero header or pixel differences**.

### 4. Do both generations work through the same path?

**Read: yes. Write: gen9 only** — this is the one real gap left.

- gen9 (v5): read, write, re-read all clean (see above).
- legacy (v13): **read works** (`Mai.ytd`, 32 textures, identical to CodeWalker).
  **Write does not.** `fivefury`'s `_prepare_legacy_ytd` never writes the VFT at
  `0x00`, the byte at `0x04`, or `0x32`. Round-tripping `Mai.ytd` yields
  `0x00: 97eef0b6 -> 0` and `0x32: 0x80 -> 0`. The legacy VFT is a constant
  (`0xB6F0EE97`), not a runtime address, so this is fixable — it is patch #2,
  **not yet implemented**. Until then `lite` / `fix_mips` keep `pack_ytd.ps1` for
  legacy archives.

### 5. Do `script_rt_*` render targets need special handling? Are descriptors lost?

**They are lost by default — this is exactly the bug our `-Original` switch was written
for.** On `vehicles_gen9/…/buffalo.ytd` (46 textures) the unpatched writer produced

```
field differences: {'vft': 46, 'img': 46, 'dflags': 1}
  texture_vft   0xB6F0EE97 -> 0x1406B7940   (runtime address leaked into the file)
  image_flags   0x28 -> 0x00                (silently zeroed)
  descriptor_flags on script_rt_dials_digital: 0x260228 -> 0x260208
                 (the 0x20 render-target bit is dropped)
```

Cause: `GEN9_TEXTURE_RUNTIME_PROFILE` is a hardcoded constant block and
`fivefury/ytd/model.py::Texture` has no field to carry the source values. Fix shipped as
`ytd_write.py`: it dumps the 15 header fields per texture from the source archive,
temporarily replaces `_prepare_gen9_ytd`, then re-reads the written file and fails if any
preserved field drifted. Result on the same archives:

```
field differences: {}   (buffalo 46 textures, HarleySS 32, cavalcade3 20)
```

**Special handling required, and now in place** — verified, not assumed.

### 6. YMT: can it open a `.ymt` read-only and list components / drawable counts?

**Yes — and write works too, which the original questions did not ask for.** `read_ymt` opened
all 41 vanilla peds plus 18 add-on peds and agreed with the CodeWalker XML on `availComp`,
`numAvailTex`, the per-component drawable lists and `compInfos` on **16/16** non-vanilla
pairs. `iter_ped_drawables` yields 7 entries for `HarleySS` / `Mai`, 17 for
`a_f_m_beach_01`, plus 3 props for `HarleySS`.
Write: `save_ymt` round-trips semantically lossless (0 differences, 16/16), lands an
edited `numAvailTex` on the **same** component (the dev48 failure mode does not appear),
and the two real defects (`adare4`, `Kasumi`) were repaired with fivefury alone.
So the fallback path — writing our own YMT serialiser, est. 2–3 days — is **not needed**.

### What the six answers add up to

YTD read (1), gen9 scale-and-write (2, 3), descriptor preservation (5) and YMT read/write
(6) are all demonstrated. The only unanswered item is legacy YTD **write** (4), i.e.
patch #2, which affects `lite` / `fix_mips` on gen8 archives only. `ped check` / `ped fix`
are unaffected because **YMT has no generation split**: RSC7 version 2 with the same header
on both, and CodeWalker's own converter logs `MaiT.ymt - conversion not required, directly
copying file` (实测; 文档: CodeWalker *Convert Assets* 对话框).

## Implementation status (2026-11-24)

Shipped in this working tree, not yet committed or released:

| Cut | Scope | State | Evidence |
|---|---|---|---|
| 1 | `ytd.py::inspect()` reads through the vendored fivefury instead of `ytd_inspect.ps1` | **done** | output identical to the old implementation on three archives — `harley` (gen9, 32 textures) 34/34 lines, `mai` (gen8, 32) 34/34, `cav` (gen9, 20) 22/22, byte for byte. `YtdInfo`/`Texture` unchanged, so the GUI needed no edit. 41 ytd: 0.68 s with 4 workers (was ~25 s and 4 .NET processes) |
| 2 | `ped.py` audits and rewrites CPedVariationInfo directly; `export_pair`, `repair_xml`, `align_xml`, `_reexport` deleted | **done** | `41/41` vanilla baseline, `56/59` over every sample pair — the same three failures as the CodeWalker implementation, all genuine defects (`adare4`, two `Kasumi`). `align_pair` fixes both defects and `fix_pair` repairs a deliberately broken `numAvailTex=77` while leaving healthy files untouched |
| 3 | YTD write (`lite.make_lite` / `fix_mips`) through fivefury, gen9 only | **done for gen9**; gen8 still on CodeWalker | New `ytd_write.py` re-applies the 15 runtime-only header fields from the source archive while serialising; `HarleySS` (32 textures) and `cavalcade3` (20) come back with a **zero-field** header diff and 32/32 resp. 20/20 identical pixels. DDS round trip: 32/32 textures identical, and `make_lite --cap 1024` shrinks 27,301,656 → 6,956,464 B in 6.3 s with all 32 names kept and **no format change** (`fix_mips`: 10 → 12 levels on one texture). Against the old CodeWalker path on the same archive both produce the same texture table (0 differences), fivefury's container is 415 KB smaller because it re-deflates. `legacy` dictionaries still go through `pack_ytd.ps1`: fivefury's legacy writer never writes `0x00` (VFT), `0x04` or `0x32` |

Packaged smoke test (a throwaway console build with the same payload): `ytd list` on a
gen9 archive printed its 32 textures, `ped check` on the 41-ped baseline printed
`41/41 ok`, and `ped check` on the broken `adare4` copy printed the expected problem.

### Full sweep: every archive under `素材不要动` (2026-11-24)

103 texture dictionaries, read → write → read, comparing headers and pixels afterwards:
`95 ok, 7 legacy (not handled), 1 placeholder` in 405 s.  The seven legacy files are
the gen8 ones, which still go through `pack_ytd.ps1`.  The single "failure" is
`vehicles_gen9/Audi TTS/penumbra+hi.ytd`, which is **61 bytes**: a valid RSC7 header
followed by nothing.  Car packs leave an empty `+hi.ytd` beside models that only ship
`.yft` / `.ytd` / `_hi.yft`, so the game's extra-high block still resolves.  `ytd list`
now names that case explicitly (`placeholder archive (61 bytes, no texture data)`)
instead of reporting fivefury's `Unsupported texture dictionary layout`, which reads
like a parser bug.  Nothing is skipped silently: the entry still carries an error.

Every archive that actually holds textures round-trips: 95 of 95.
Two layout traps were found that way, both invisible from source runs: fivefury is a
*top-level* package in the bundle (because `pathex` puts `vendor/` on the path), so its
`.pyd` and its data must land in `_internal/fivefury/` rather than under
`gtav_asset_repair/vendor/`, or `Path(__file__).with_name()` fails at runtime; and the
`str(exc)[:110]` truncation in `cli.py` cut the very path that identified it.

Vendoring: `src/gtav_asset_repair/vendor/fivefury/` (459 modules + `_native_abi3.pyd` 576,000 B + 3.9 MB of `data/*.dat` + two shader XMLs), 11 MB of source. `trimesh` is replaced by a three-file stub (`Trimesh`, `Scene`, `PointCloud`, `MultiMaterial`, `PBRMaterial`, `SimpleMaterial`) because fivefury imports it eagerly at package level and nothing on our paths uses it. Two workarounds live in *our* code so the vendored copy stays upgradeable: the gen8 `.ydd` adler32 tail (patch #3) and the hashed compInfos field names.

`gtav-asset-repair.spec` now collects `_native_abi3.pyd`, `fivefury/data/*`, the two shader XMLs and `MSVCP140.dll`, `MSVCP140_1.dll`, `MSVCP140_2.dll`, `MSVCP140_ATOMIC_WAIT.dll`, `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll` from `%SystemRoot%\System32` (the pyd imports them; PyInstaller does not pull them on its own). The hard-coded `C:/Users/calvi/.../texconv.exe` path is gone.

## Candidates screened (api.github.com, 2026-11-24)

| repo | stars | last push | license | one-line judgement |
|---|---|---|---|---|
| **Hancapo/fivefury** | 19 | 2026-09-12 | **Unlicense** | full YTD/YMT/YDD read+write, gen8+gen9, prebuilt abi3 wheel — **the only viable replacement** |
| Sollumz/szio | 7 | 2026-11-19 | MIT (wrapper) | pure-Python parts are MIT, but every texture/meta binary path goes through `pymateria` — GPL-3.0, not on PyPI → **cannot embed** |
| Hancapo/texfury | 6 | 2026-08-01 | **none** (`license: null`) | image↔DDS/YTD helper; no license file = all rights reserved → **cannot embed** |
| VIRUXE/rage-formats | 3 | 2026-11-15 | Unlicense | Rust, RSC7/drawable/meta parsing, no writer pipeline we need → FFI cost, narrow scope |
| RatPrez/ragekit | 8 | 2026-10-23 | NOASSERTION | C++20, reads+writes the right formats but the licence is "Other", unverified |
| Ryanathlawi/wun-studio | 3 | 2026-09-06 | MIT | `core/ytd_writer.py` only emits **legacy** (`YTD_VERSION = 13`), no gen9, no YMT → reference only |
| dexyfex/CodeWalker | 780 | 2025-04-11 | **none** | what we ship against today; no licence file → cannot redistribute the DLL |

Also checked: no MIT/Unlicense fork of CodeWalker exists (`CODEWALKER-IMPROVED` and `red40_clothing_packer` are `null`/`NOASSERTION`), `6to5m` and `ClothingStudio` are GPL-3.0, PyPI has no `gta`-format package.

## Capability matrix vs our five CodeWalker call sites

| # | today (`resources\*.ps1`) | fivefury | status |
|---|---|---|---|
| 1 | `ytd_inspect.ps1` → `YtdFile.Load`, texture table | `read_ytd()` → `.textures[]` | **measured OK** — gen9 32/55 + gen8 32/32 textures, all fields present |
| 2 | `ytd_export.ps1` → `YtdXml.GetXml` (`.ytd.xml` + DDS) | `read_ytd()` + `defs._build_dds_bytes()` (private) | **DDS yes, XML no** — we would emit our own manifest |
| 3 | `pack_ytd.ps1` → `XmlYtd.GetYtd` + G9 descriptor re-stamp | `save_ytd()` | **works after 2 patches** (one verified: patched output differs from input in **0** header fields) |
| 4 | `ymt_pack.ps1` → `XmlMeta.GetData` | `read_ymt()` / `save_ymt()` | **measured OK, both generations** — read agrees 16/16, write lands on the intended component, round-trip 0 semantic diffs, `adare4` repaired end to end |
| 5 | `ped_export.ps1` → `YddFile/MetaXml.GetXml` | `read_ydd()` / `read_ymt()` → dicts keyed exactly like CodeWalker XML | **gen9 OK, gen8 ydd blocked** by patch #3 |

## Measured results

### YTD read
| file | gen | size | textures | format |
|---|---|---|---|---|
| `ped_gen9\HarleySS.ytd` | 9 | 27,301,656 | 32 | RSC7 ver `0x5` |
| `ped_gen9\MomiNinja.ytd` | 9 | 32,267,210 | 55 | `0x5` |
| `ped_gen8\Mai.ytd` | 8 | 21,448,527 | 32 | `0xD` |
| `ped_gen8\MaiT.ytd` | 8 | 13,775,761 | 32 | `0xD` |

### YTD write (this is where the trouble is)
`save_ytd()` rebuilds the dictionary from scratch (no input bytes kept) and takes the gen9 runtime header fields from a hardcoded profile, so a pure round-trip is **not** faithful:

| file | textures | plain round-trip field diff |
|---|---|---|
| `vehicles_gen9\…\buffalo.ytd` | 46 | `vft` 46 → `0x1406B7940`, `image_flags` 46 → `0`, `descriptor_flags` 1 (`script_rt_dials_digital` `0x260228` → `0x260208`) |
| `ped_gen9\HarleySS.ytd` | 32 | `vft` 32, `image_flags` 32 |
| `ped_gen8\Mai.ytd` (legacy) | 32 | bytes `0x00-0x03` (vft) and `0x04` zeroed, `0x32` `0x80`→`0`, `0x56/0x57` stride rewritten |

After patch #1 (gen9) the same two files round-trip with **`fielddiff = {}`** — 46/46 and 32/32 textures, `extra = []`. See `_probe\probe_patch.py`.

### YMT read/write
`read_ymt` on `Mai.ymt` (975 B), `HarleySS.ymt` (987 B), `a_f_m_beach_01.ymt` (1487 B) → `YmtFormat.RSC`, `YmtContentType.PED_VARIATION`, root `CPedVariationInfo`, content dict keys identical to CodeWalker XML (`availComp`, `aComponentData3`, `compInfos`, `propInfo`, `dlcName`, …).
`save_ymt` → `read_ymt` → `deep_eq`: **0 differences** on all three (sizes 854 / 854 / 1352 B; the RSC7 system flag word changes, nothing semantic). `iter_ped_drawables` returns 7 / 7 / 17, matching the ymt.

### YDD read
gen9: `HarleySS.ydd` 7 drawables (ymt says 7), `a_f_m_beach_01.ydd` 17 (ymt 17), `a_c_chickenhawk.ydd` 3 (ymt 3) — the invariant `#4` of `ped-ymt-rules.md` holds straight out of fivefury.
gen8: all three `Mai*.ydd` raise `ValueError: resource deflate stream contains trailing data` (`fivefury/resource.py:403`) — closed by patch #3: with the 10-line patch all three read **7/7** drawables, matching CodeWalker, and gen9 is unaffected (`_probe/probe_ydd_fix.py`).

## Patches required

### 1. gen9 YTD header fields are hardcoded, not preserved ✅ verified
`fivefury/ytd/model.py:23 class Texture` carries only `name/width/height/format/mip_count/data/mip_offsets/mip_sizes/usage/usage_flags`; `fivefury/ytd/catalog.py:28-40 TextureDescriptor` drops the header even earlier. `fivefury/ytd/__init__.py:294-315` then writes six fields from `GEN9_TEXTURE_RUNTIME_PROFILE`:

```
:294 vft              <- profile.texture_vft   (0x1406B7940)
:296 descriptor_flags <- profile.descriptor_flags (0x00260208)
:300 tile_mode        <- profile.tile_mode     (0xFF)
:302 image_flags      <- profile.image_flags   (0x0)
:312 usage_class      <- profile.usage_class   (0x2)
:314 srv_vft / :315 srv_dimension
```

`probe_patch.py` replaces `_prepare_gen9_ytd` with a table-driven version (values harvested from the input file, keyed by texture name) and gets a **0-field-diff** round trip. That became `src/gtav_asset_repair/ytd_write.py` instead of a fork of fivefury: `dump_headers(raw)` harvests the fields, `_make_prepare(hint)` returns the replacement writer, and `save(dictionary, path, source=raw)` swaps it in for the duration of one `save_ytd` call and restores it in a `finally`. Keeping it in our tree means the vendored copy stays byte-identical to upstream 0.5.1 and can be replaced wholesale on upgrade.

Measured: `HarleySS.ytd` 32 textures and `cavalcade3.ytd` 20 textures, header diff `{}`, pixel data identical, RSC7 version still 5. `save()` without a `source` falls back to `GEN9_TEXTURE_RUNTIME_PROFILE` (correct only for a dictionary built from scratch).

This is exactly what `pack_ytd.ps1 -Original` does with `G9_UsageData/G9_Flags/…` today — the same class of bug, same class of fix.

### 2. legacy YTD header is written as zeros
`_prepare_legacy_ytd` (`fivefury/ytd/__init__.py:165-232`) never writes `0x00` (vft), `0x04`, or `0x32`, and computes stride itself (`:220 _row_pitch`). Measured on `Mai.ytd`: vft `0xB6F0EE97` → `0`, `0x32` `0x80` → `0`. **Fixed and verified in `ytd_write.py`** as a post-pass over the section fivefury produces — no fork, the vendored tree is untouched:

```
$ python _probe/legacy_dump.py 素材不要动/ped_gen8/Mai.ytd _probe/out/legacy_Mai_patched.ytd
source: ... Mai.ytd 21448527 bytes, virtual 8192
output: ... legacy_Mai_patched.ytd 21446773 bytes, virtual 6144
header version: 13 -> 13
textures: 32 -> 32
RESULT: 6 differing byte offsets across 32 textures
  0x28 name_ptr     n=31  ... e.g. hair_diff_000_a_pak: 1342182432 -> 1342182846
  0x29 byte         n=22  ...
  0x70 data_ptr     n=28  ... e.g. hair_diff_000_a_pak: 1660948480 -> 1679866304
  0x71 byte         n=32  ...
  0x72 byte         n=32  ...
  0x73 byte         n=29  ...

$ python _probe/cmp_textures.py 素材不要动/ped_gen8/Mai.ytd _probe/out/legacy_Mai_patched.ytd
source: 32 textures, output: 32
name sets equal: True
metadata differences: 0
pixel differences: 0 / 32
RESULT: identical
```

The only remaining byte differences are `name_ptr` and `data_ptr` — name and pixel
pointers into the rebuilt section, which *must* move because the writer re-lays the
container. Every semantic field (`vft`, `0x04`, `0x32`, `stride`) is preserved, the
RSC7 version stays 13, and CodeWalker reads the result identically to the source:

```
$ ytd_inspect.ps1 -Ytd 素材不要动/ped_gen8/Mai.ytd -CoreDir <ModDropV> -Legacy   # 32 textures
$ ytd_inspect.ps1 -Ytd _probe/out/legacy_Mai_patched.ytd  -CoreDir <ModDropV> -Legacy
# both JSON payloads: identical name/width/height/format/mips/bytes for all 32, "error":""
```

`save()` now routes legacy archives through `_make_prepare_legacy()` and proves the
result with `_verify_legacy()`, which re-reads the file and raises if any of the four
fields drifted — the same read-back rule as gen9.

### 3. gen8 YDD fails on a trailing adler32 ✅ verified
`fivefury/resource.py:394-404` uses raw deflate (`wbits=-15`) *and* demands `unused_data == b""`. Legacy YDD streams carry a 4-byte adler32 after the deflate data. Measured:

```
Mai.ydd   raw inflate → 6,291,456 B, zlib.adler32(out) = 7a9e65c2
          trailing 4 bytes                            = 7a9e65c2   ← identical
Mai.ytd   same path, unused = 0                                ← gen8 YTD has no tail
```

Fix: accept `unused_data <= 4` when the tail equals `adler32(output)`, or let `read_ydd` pass an exact stream length. ~10 lines. This is **not** "fivefury cannot read gen8 ydd" — I verified the tail is a genuine adler32, not a parser artefact of ours.

Patch verified in `_probe/probe_ydd_fix.py` (monkey-patch, read only). Before: 3/3 gen8 `.ydd` raise. After: all six probed files agree with CodeWalker — `Mai`/`MaiS`/`MaiT` 7/7, `HarleySS` 7/7, `adare4` 2/2, `a_f_m_beach_01` 17/17.

## Round 2 — read / write / round-trip on real peds

Script `_probe/probe_ymt_write.py <batch> <stem>` copies the pair into `_probe/cases/<stem>/`, mutates only that copy, and judges every write with **CodeWalker's own XML export** (an implementation independent of fivefury). The source folder is never written.

### gen9 `ped_gen9/adare4` (the one broken sample)

```
=== A. read: fivefury vs our XML ===
  availComp   match: True
  numAvailTex match: True
  drawables   match: True
  compInfos   match: True
=== B. write: numAvailTex 77 on component 0 ===
numAvailTex via fivefury: [77, 1, 1]
numAvailTex via XML     : [77, 1, 1]
landed on component 0   : True
landed on a later comp  : []
compInfos via XML       : [[0, 0], [2, 0], [4, 0]]
drawables via XML       : [[4], [1], [1]]
=== C. round trip: read -> write -> read (no value changed) ===
  format       same: True      numAvailTex  same: True   ([4, 1, 1] -> [4, 1, 1])
  content_type same: True      drawables    same: True   ([[4], [1], [1]] -> [[4], [1], [1]])
  availComp    same: True      compInfos    same: True
  size         1191 -> 1175 B (-16)
  our XML can read it back: True
  RSC7 version ymt 2 -> 2
```

### gen8 `ped_gen8/Mai` (legacy, `-Legacy` auto-detected from the ydd)

```
=== A. read === availComp/numAvailTex/drawables/compInfos  all match
  numAvailTex [3, 2, 6, 6]   drawables [[3], [1, 1], [3, 3], [3, 3]]
  compInfos [(0,0), (2,0), (2,1), (3,0), (3,1), (4,0), (4,1)]
=== B. write numAvailTex=77 on component 0 ===
landed on component 0: True   landed on a later comp: []   size 975 -> 854 B
=== C. round trip === everything same, RSC7 version 2 -> 2, our XML reads it back
```

**The write bug that ruined dev48 does not happen here.** `dev48` re-laid the components (`numAvailTex [3,2,6,6]` became `[0,3,0,2,0,6,0,6,0]`, `compInfos` 7 → 15, XML 7,172 → 15,070 chars). fivefury keeps component 0 at component 0 and leaves `compInfos` untouched.

### The `compInfos` gotcha (cost me one wrong reading)

`compInfos` rows come back keyed by **raw field-name hashes**, because fivefury's schema has no name for 6 of the 10 `CComponentInfo` fields:

```
['0x2FD08CEF', '0xFC507D28', '0x07AE529D', 'flags', '0x817AF4D5',
 '0x72039CC8', '0x6032815C', '0x7E103C8B', '0xD12F579D', '0xFA1F27BF',
 '_meta_name_hash', '_meta_name']
```

The order is stable across four unrelated peds (adare4 / HarleySS / Mai / a_f_m_beach_01) and maps positionally onto the CodeWalker XML fields:

| idx | fivefury key | CodeWalker XML |
|---|---|---|
| 0 | `0x2FD08CEF` | `pedXml_audioID` |
| 1 | `0xFC507D28` | `pedXml_audioID2` |
| 2 | `0x07AE529D` | `pedXml_expressionMods` (5-tuple) |
| 3 | `flags` | `flags` |
| 4 | `0x817AF4D5` | `inclusions` |
| 5 | `0x72039CC8` | `exclusions` |
| 6 | `0x6032815C` | `pedXml_vfxComps` |
| 7 | `0x7E103C8B` | `pedXml_flags` |
| **8** | **`0xD12F579D`** | **`pedXml_compIdx`** |
| **9** | **`0xFA1F27BF`** | **`pedXml_drawblIdx`** |

`jenk_hash`/`joaat` of the field names (`0x756C7982`, `0xA9CBB471`) do **not** match these hashes, so do not try to derive them — index by position, or probe the key set once and assert it. `compIdx` is the **availComp slot number** (0..11), not the `aComponentData3` position.

## Round 3 — regression over every available pair

`_probe/scan_all.py` reads all 16 pairs in `素材不要动\` with fivefury and with CodeWalker, then compares `availComp`, `numAvailTex`, per-component texture counts and `compInfos`.

```
matched 13/16      (all 16 YMT reads match; the 3 misses are gen8 .ydd, patch #3)
ped_gen8       Mai / MaiS / MaiT      ymt ok, ydd FAIL → patch #3
ped_gen9       HarleySS / MomiNinja / Tamaki / adare4            ok / ok
ped_ingame_gen9  a_c_chickenhawk, a_f_m_beach_01, a_f_m_bevhills_01,
                 a_f_m_bodybuild_01, a_f_m_business_02,
                 a_f_y_business_01..04                           ok / ok
```

**Baseline (updated 2026-11-24, same day):** the deleted vanilla set is back — the user dropped `素材不要动\ped_ingame41_gen9\` in (41 peds, flat layout, each with `.ydd`/`.yft`/`.ymt`/`.ytd`, one stray `.yld`). Measured with `_probe/baseline41.py`:

```
41 peds
ok a_f_y_beach_01 ... ok a_f_y_yoga_01
41/41 ok
```

So the audit rules still hold on vanilla and the baseline is usable again. The stronger check is `_probe/roundtrip41.py`: every vanilla `.ymt` read by fivefury and written straight back (no value changed) and then re-audited by CodeWalker:

```
41/41 ok after fivefury round-trip
ymt bytes 55824 -> 50382 (-5442)     # container re-pack, -9.7 %
```

Same drawables and `compInfos` count on all 41; only the byte layout changes. **fivefury's writer does not disturb the structure the game depends on**, at least not as far as XML can tell. Whether the game agrees is the one thing no probe can answer — see *In-game check*.

## End-to-end: repair `adare4` with fivefury only

`_probe/fix_adare4.py`. The sample's `.ymt` claims 3 drawables; its `.ydd` ships 2 (`hash_4BD0197A` = hair, `hash_976FBF04` = head_000).

Picking the ghost component from the file, not by luck:

```
availComp: slot 0 -> component 0, slot 2 -> component 1, slot 4 -> component 2
compInfos: slot 0 audio=none, slot 2 audio=none, slot 4 audio=cloth_lower_pants_tight/shoe_heels
```

Slot 4 is a lower/pants component inherited from the vanilla ymt the mod was derived from; there is no lower drawable in the `.ydd`, so nothing can point at it. Repair = release `availComp[4]`, drop that component, drop its `compInfos` row — **three edits, nothing else touched**.

```
=== before ===  ok: False   1 problem: ymt declares 3 drawable(s), the ydd has 2
after fivefury: availComp [0, 255, 1, 255, 255, ...]
after fivefury: components 2  numAvailTex [4, 1]
after fivefury: compInfos [(0, 0), (2, 0)]
=== after ===   ok: True    0 problems   (verify step re-exported with CodeWalker)
```

That is the whole point of the exercise: fivefury did the read, the mutation and the write, and an independent CodeWalker parse confirmed the result.

## End-to-end: repair `Kasumi` trimmed to the ydd, and what it says about the CodeWalker conversion

Two samples, `素材不要动/ped_gen8/Kasumi` and `素材不要动/ped_gen9/Kasumi`; the gen9 one was produced by converting the gen8 one with CodeWalker.

```
$ python _probe/kasumi.py
core: C:\Users\calvi\Desktop\GM\ModDropV

=== ped_gen8/Kasumi ===   ydd 39414332 B   ymt 1004 B
  availComp   [0, 255, 1, 255, 255, 255, 255, 2, 3, 4, 5, 255]
  numAvailTex [17, 4, 1, 4, 4, 4]   compInfos 34 rows
  check: ok=False  problems=1  ymt declares 34 drawable(s), the ydd has 31

=== ped_gen9/Kasumi ===   ydd 38960385 B   ymt 1004 B
  availComp   [0, 255, 1, 255, 255, 255, 255, 2, 3, 4, 5, 255]
  numAvailTex [17, 4, 1, 4, 4, 4]   compInfos 34 rows
  check: ok=False  problems=1  ymt declares 34 drawable(s), the ydd has 31
```

Both files carry the **identical 1004-byte `.ymt`** (same `availComp`, same `numAvailTex`, same 34 `compInfos` rows) and the **same single problem**. The `.ydd` sizes differ (39414332 vs 38960385) because the conversion rewrote the geometry and the textures, but the `.ymt` was carried over untouched — so the mismatch predates the conversion and **CodeWalker's generation conversion does not repair it**.

Repair, `_probe/fix_kasumi.py`, order-based trimming to the ydd drawable count:

```
ydd 31 drawable(s), ymt 34 -> drop 3
pairs (comp, drawable, slot): [(4, 2, 9), (4, 3, 9), (5, 0, 10), (5, 1, 10), (5, 2, 10), (5, 3, 10)]
  comp 5: dropped 1 drawable(s), numAvailTex -> 3
  comp 5: dropped 1 drawable(s), numAvailTex -> 2
  comp 5: dropped 1 drawable(s), numAvailTex -> 1
after: numAvailTex [17, 4, 1, 4, 4, 1]
after: compInfos   31 rows, last one (10, 0)
=== after ===  ok=True  0 problems   ydd 31 drawables / ymt 31
```

**This one is a structural pass with a stated assumption, not a verified repair.** Drawable names are hashes, so a `.ymt` drawable cannot be matched to a `.ydd` drawable by name; the trim assumes the three missing drawables sit at the tail, which happens to keep the first five components (17 / 4 / 1 / 4 / 4) untouched and shortens only the last one from 4 to 1. If the mod author instead dropped three drawables from an earlier component, this would shift every later drawable by one — exactly the failure mode that made the dev48 build unusable. The 41-vanilla round-trip (§4.4) is order-preserving and therefore unaffected; this repair is not.

What makes the tail assumption plausible here: the difference is 3 and only the last component can absorb it without disturbing the others, and both generations ship the same file. What would settle it: play it (§ In-game check, case B).

## In-game check — what only the game can prove

Everything above is XML-level: it proves the structure is self-consistent and
unchanged. It does **not** prove the game accepts it. Three things can still
go wrong and only the running game shows them:

| symptom | what it means | which test catches it |
|---|---|---|
| crash / freeze when opening the Clothing menu | `availComp` slot ↔ component mapping disagrees with what the menu walks | A, B |
| hair on the waist, torso missing, parts detached | drawable order inside a component is permuted (the dev48 failure mode, one level deeper) | A, B |
| a slot shows in the menu but selecting it does nothing | `compInfos` row points at a drawable that does not exist | B |

### A. Vanilla round-trip (the real safety test)

`_probe/roundtrip41/<stem>/<stem>.ymt` are the 41 vanilla peds written back by
fivefury with **no value changed**. Audit already says 41/41 ok, so if the game
disagrees the XML is lying.

Pick 3–5, not all 41 (a broken write tends to break every file the same way):

```
a_f_y_beach_01    a_f_y_hiker_01    a_f_y_yoga_01
a_f_y_business_01 a_f_y_soucent_02
```

Procedure: back up the originals, drop the rewritten `.ymt` next to the
untouched `.ydd` in a `mods/` copy, spawn each ped, open the Clothing menu,
cycle every slot once. **Pass = the menu opens, every slot applies, the ped
looks identical to vanilla.** A file-identical screenshot comparison is the
strongest form of this test.

### B. The repaired `adare4`

`_probe/cases/adare4/` holds the repaired `.ymt` (slot 4 released, its
component and `compInfos` row removed). Register it as the add-on it already
is, spawn it, and check: head and hair render, **no lower/pants part** (the
`.ydd` has none, that is the whole repair), and `randomize` in the trainer does
not crash. Before the repair, `randomize` is exactly what a dangling component
tends to crash on.

### C. Randomise stress

On any of the above, hold the trainer's "randomise ped" key for 20–30 cycles.
This walks combinations the normal menu rarely hits; a dangling `compInfos`
row usually dies here rather than on a hand-picked outfit.

### Result — verified in game (2026-11-24)

**A passed.** `a_f_y_beach_01` rewritten by fivefury with no value changed spawns
and runs, clothing menu opens, every slot applies, outfit matches vanilla. This
is the one result that matters most: the file's *content* is untouched, so any
defect could only have come from the write path, and there is none. **gen9
write path: accepted by the game.**

**Kasumi passed.** The 16 head variants all present after the repair, every one
usable — the trim left component 0 (17 drawables) completely intact, which is
what the order-based assumption predicted.

**Kasumi's last component (slot 10, `decl`) — the observed behaviour confirms
the tail assumption, and also explains it:**

| | before repair | after repair |
|---|---|---|
| options in the menu | 4 (indices 0–3) | 1 (index 0) |
| rendered content | all four blank | blank |

Four empty slots became one empty slot, and nothing else in the ped moved. That
is exactly what "the `.ydd` ships 1 `decl` drawable, the `.ymt` claimed 4" looks
like from inside the game: the 3 phantom entries were declared-but-absent, so
their slots were empty; the surviving one is a real drawable in the `.ydd`
(`hash_F19DE766`, the last of the 31) that simply has nothing visible to render.
**The trim was correct and it did not shift any other drawable.**

Two related facts worth keeping:

- The gen8 and gen9 `.ydd` files list the **same 31 drawable hash names in the
  same order** (`hash_04F98F7A` … `hash_F19DE766`). The CodeWalker conversion
  rewrote geometry and textures but preserved drawable identity, which is why
  one repair applies identically to both generations.
- **Releasing the whole component is not the right fix here**, tempting as it
  looks: setting `availComp[10] = 255` and dropping component 5 would leave the
  `.ymt` declaring 30 drawables against a `.ydd` that ships 31, and the audit
  would fail on invariant ④. The game would still run it (undeclared drawables
  are simply never loaded), but the file would be structurally inconsistent
  again. The only way to remove the empty slot outright is to delete
  `hash_F19DE766` from the `.ydd` — a model edit, outside the scope of a `.ymt`
  repair and not something this tool should do implicitly.

**Still unverified:** `adare4` (case B) and the gen8 round-trip (`Mai`, case 2 of
the three-priority list) — both are the "release a whole component" and
"legacy write path" cases respectively. `a_f_y_beach_01` covered gen9 write and
Kasumi covered trim-with-surviving-drawable; the legacy path remains unproven in
game, although the gen8 and gen9 containers are the ones the 41-vanilla audit
already treats identically.

### Why the gen8 `.ymt` needs no separate game test

Three independent lines of evidence say the `.ymt` layer has no generation
concept at all:

1. **Header bytes are identical.** `Mai.ymt` (gen8, 975 B) and `HarleySS.ymt`
   (gen9, 987 B) both carry `RSC7 magic 0x37435352, version 2, system_flags
   0x20000, system_span 8192, graphics_flags 0x20000000`. Only the content
   length differs.
2. **The writer has no branch.** `fivefury/meta/__init__.py:219` derives the
   container flags from the *file's own* `resource_version`; there is no
   `if gen9 / else legacy` split on this path. Only YTD has one
   (`_prepare_gen9_ytd` vs `_prepare_legacy_ytd`).
3. **The conversion tool agrees.** CodeWalker's gen8→gen9 conversion copies the
   `.ymt` verbatim — stated by the tool, and visible in the Kasumi pair above,
   where both generations ship a byte-identical 1004-byte `.ymt` while the
   `.ydd` sizes differ by 450 KB.

Consequence for our own code: **`ped check` / `ped fix` do not need to branch on
generation at the `.ymt` level.** Generation only enters through `.ydd` reading
(patch #3) and through `.ytd`. The one residual risk is the recomputed
`system_flags` (`0x20000` → `0x8000004` on the round-tripped file, same
8192-byte span) — a repack consequence of the 975 → 854 byte shrink, not a field
change.

If the gen8 write path is ever tested in game, the clean experiment is two
conversions of the same ped: control = original `Mai.ymt` (975 B), experiment =
the fivefury round-trip (854 B). Because the converter copies `.ymt` byte for
byte, the `.ymt` is then the *only* variable between the two runs — which is
what makes the comparison conclusive. Testing the experiment alone would not
separate a bad write from a bad conversion.




## Packaging impact

The wheel ships `fivefury/_native_abi3.pyd` (576,000 B, machine `0x8664`). Its PE import table:

```
python3.dll (stable ABI → any CPython 3.11+)  ✓
MSVCP140.dll  MSVCP140_ATOMIC_WAIT.dll  VCRUNTIME140.dll  VCRUNTIME140_1.dll
bcrypt.dll  KERNEL32.dll  api-ms-win-crt-*-l1-1-0.dll
```

The current portable zip already contains `MSVCP140.dll`, `VCRUNTIME140*.dll` and `numpy.libs\msvcp140-*.dll`, but **not `MSVCP140_ATOMIC_WAIT.dll`** — that one must be added to the PyInstaller collect list or a clean machine gets `ImportError: DLL load failed`.

`fivefury/_native.py:11` raises on import when the pyd is missing — there is no pure-Python fallback, and the RSC7 page packing lives in the native code (`resource.py:178 _native_backend.resource_pack_block_sizes`). So the native module is mandatory, not optional.

Also `import fivefury` eagerly imports everything, including `trimesh` (`ydr/trimesh/materials.py:8`) — which we do not otherwise need. `_probe/lib/trimesh/` holds empty stubs; for the real product either add `trimesh` to the requirements or vendor the stub.

## Migration cost

| area | change | size |
|---|---|---|
| `ytd.py::inspect` | drop `ytd_inspect.ps1`, call `read_ytd` | ~30 lines |
| `ytd.py::export` | no CodeWalker XML; emit own manifest + DDS (`_build_dds_bytes` or texconv) | 100-150 lines |
| `pack` path | drop `pack_ytd.ps1`, `read_ytd` → mutate → `save_ytd`, header patch | 60-100 lines |
| `ped.py::export_pair` (3 call sites: `check_pair`, `fix_pair`, `align_pair`) | `read_ydd` / `read_ymt` instead of ps1 + XML; `audit()` input changes from ElementTree to dict | 80-120 lines |
| `ymt.py` (130 lines) | audit the fivefury dict instead of `.ymt.xml` — key names are identical | ~small |
| `cw.py` (112 lines) | delete, or keep as opt-in fallback | — |
| tests | `test_*` that build XML fixtures must build dict fixtures; the 41-vanilla baseline needs the .ydd/.ymt set again | medium |

Upside: three PowerShell launches and two XML serialisation passes disappear per ped; `ped check` currently costs one `powershell.exe` cold start *plus* a full ydd/ymt re-export per ped.

## Risks worth stating

1. **Upstream is moving to .NET.** The README says 0.5.1 is the last planned feature release of the Python implementation. A fork we patch is therefore permanent — budget for vendoring it (Unlicense allows that) and for the eventual "switch to the .NET build + a .NET sidecar" decision.
2. **The pyd is a binary blob.** Unlicense removes the *licence* problem, not the *trust* problem: we cannot review 576 KB of prebuilt object code. CodeWalker had the same property (worse: no licence), so this is not a regression, but it should be an explicit note in `NOTICE.md`.
3. **Round-trip is not byte-identical.** Even patched, sizes change (`buffalo` 7,187,987 → 7,102,179 B) because fivefury re-packs pages at its own alignment and compression level. Header fields and pixel data match; the container layout does not. Any workflow that diffs files byte-wise will need a field-level compare (which is what `ped.py` already audits).
4. **No `CodeWalker` XML means "the user can hand-edit the XML" goes away** if that is ever a feature. Today it is not — the XML is an internal stage — so this is a simplification, not a loss.

## Suggested order

1. **Vendor fivefury 0.5.1 into `src/gtav_asset_repair/_vendor/fivefury/`** with patch #3 applied (10 lines, verified). Keep the wheel sha256 and the Unlicense text in `third_party/`, so a future upstream licence change cannot take the shipped code away. — **done**, at `src/gtav_asset_repair/vendor/fivefury/`; the adler32 fix lives in `ped.py::_patch_deflate_tail` so the vendored tree stays pristine.
2. **Move `ped check` / `ped export` to fivefury** — **done**, `ped.py` reads and writes binary ymt/ydd directly; `pack` is no longer part of that path.
3. Patch #1 + #2, then flip `pack` to `read_ytd` → mutate → `save_ytd` — **done for gen9** in `ytd_write.py` + `lite.export_native`/`pack_native`. Still open: **gen8 dictionaries** (`lite.py` keeps the `pack_ytd.ps1` branch for them), a round-trip sweep over all 60 `.ytd` in `素材不要动/`, and an in-game check of a written dictionary.
4. Add `MSVCP140_ATOMIC_WAIT.dll` + `trimesh` to the PyInstaller spec, smoke-test the portable build on a machine without CodeWalker and without VC++ redist installed. — spec updated and the console build runs `ytd list` / `ped check`; the **`lite` path has not been smoke-tested in a packaged build yet**.
5. Re-run the 41-vanilla ped baseline — **done** (`41/41`, still in `素材不要动/ped_ingame41_gen9`).

## Reproduction

```bash
PY="C:/Users/calvi/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe"
"$PY" _probe/probe_patch.py      # gen9 header fidelity, plain vs patched, diff = {}
"$PY" _probe/probe_g9hdr.py      # field distribution across 4 gen9 files
"$PY" _probe/probe_ymt.py        # ymt read / round-trip deep_eq
"$PY" _probe/probe_ydd.py        # gen9 ydd vs ymt drawable counts; gen8 failure
"$PY" _probe/probe_ydd_fix.py    # patch #3: gen8 ydd readable, gen9 unaffected
"$PY" _probe/probe_ymt_write.py ped_gen9 adare4   # §4.3 read / write / round-trip
"$PY" _probe/probe_ymt_write.py ped_gen8 Mai      # same, legacy build
"$PY" _probe/scan_all.py         # §4.4 all 16 pairs, fivefury vs CodeWalker
"$PY" _probe/fix_adare4.py       # end-to-end repair, audit 0 problems
"$PY" _probe/baseline41.py       # vanilla baseline, 41/41 ok
"$PY" _probe/roundtrip41.py      # 41 vanilla ymt rewritten by fivefury, still 41/41 ok
```

Evidence levels: everything in *Measured results*, *§4.3*, *§4.4*, *End-to-end* and *In-game check* is 实测 (commands above, outputs quoted verbatim); patch code shapes are 实测 for #1 and #3 and 推测 for #2; licence/star/date fields are 文档 (api.github.com). The 41-vanilla baseline **was** re-run on this machine — the data lives at
`素材不要动/ped_ingame41_gen9/` (41 `.ymt`, 41 `.ydd`, 41 `.ytd`, 41 `.yft`, 1 `.yld`, unpacked
from `x64v.rpf\models\cdimages\componentpeds_a_f_y.rpf`), and `_probe/baseline41.py` prints
`41/41 ok` against it through the fivefury `ped.audit` path:

```
$ ls 素材不要动/ped_ingame41_gen9/*.ymt | wc -l
41
$ PYTHONPATH=gta-badge-toolkit/src "$PY" _probe/baseline41.py
ok   a_f_y_vinewood_02          drawables  8  compInfos  8
ok   a_f_y_vinewood_03          drawables  8  compInfos  8
ok   a_f_y_vinewood_04          drawables  8  compInfos  8
ok   a_f_y_yoga_01              drawables  6  compInfos  6

41/41 ok
```

An earlier revision of this line said the data no longer exists — that was written before
the user restored the baseline and is wrong.

## Round 4: legacy (gen8) YTD writes work in game

Two rules turned three crashed builds into archives the game loads. Both were
found by measurement, then confirmed in a real legacy install.

**Rule 1 - every texture's data starts on a 0x1000 boundary.**

fivefury concatenates the payloads back to back; the stock archives align every
texture to 4 KB and the game relies on it. Measured on `ped_gen8/Mai.ytd`:

```
source: 32 textures, not 4k-aligned 0
ours  : 32 textures, not 4k-aligned 30
   lowr_spec_000 at 271231648 (% 0x1000 = 2720)
```

The biggest texture (the head normal map) showed it as black speckles across the
face while the rest still looked fine. `ytd_write._align_textures()` lays the
payload back out in source order and rewrites each `data_ptr`; the same check then
reports `not 4k-aligned 0` for `Mai.ytd` (32 textures) and `gtr.ytd` (65).

**Rule 2 - container flags and section sizes stay the source's.**

| | file | system_flags | graphics_flags | sizes |
|---|---|---|---|---|
| source | 21,448,527 | 131072 | 3724804108 | 8192 / 81,788,928 |
| unpatched | 21,446,773 | 50331648 | 3700293621 | 6144 / 77,643,776 |
| CodeWalker | 21,723,575 | 131072 | 3489685528 | 8192 / 83,886,080 |

The unpatched build crashed the game on load. `ytd_write._keep_size()` pads both
sections back to the sizes the source flags describe, keeps the source flags and
raises instead of silently overflowing when the new payload cannot fit.
`lite.pack_native()` passes `keep_size_flags=True` for legacy archives only.

**In-game result (legacy install, 2026-11-25)**

- `05_Mai_aligned` (shrunk 4096 -> 1024, `21,448,527 -> 6,766,450 B`): loads,
  outfit switching works, face and clothes render correctly.
- `06_gtr_aligned` (repacked with no texture changed, `1,906,693 -> 1,879,228 B`):
  loads, car renders, no `ERR_SYS_INVALIDRESOURCE_5`.

CodeWalker's own legacy writer is not a safe fallback either: editing one texture
in `gtr.ytd` with it crashed the game, and restoring the original texture without
restoring the file did not help - the archive had been rewritten.

## CodeWalker is gone (2026-11-25)

| command | backend |
|---|---|
| `ped check` / `ped fix` | fivefury + `ped.py` |
| `ytd list` | fivefury |
| `lite` / `fix_mips` | fivefury + `ytd_write.py` |
| `pack --original` | fivefury + `ytd_write.py` |

`cw.py` and `resources/{pack_ytd,ped_export,ymt_pack,ytd_export,ytd_inspect}.ps1`
were deleted; `pack` without `--original` now errors instead of guessing header
fields; the `GTA_LITE_LEGACY_CW` escape hatch is gone.

Verified after removal: `Ran 78 tests OK`; both baselines `41 PED(s): 41 ok`;
`lite` gen9 `27,301,656 -> 6,956,464`, gen8 `21,448,527 -> 6,766,450`;
`pack --original` `21,451,441 B / 32 texture(s)`; `import gui` works.

## Round 3: the `pack` writer

`gtav-asset-repair pack` was the last command that still required CodeWalker. It now
defaults to the vendored fivefury + `ytd_write`, and CodeWalker is only used when the
caller omits `--original`.

**Method.** Both writers were fed the *same* XML and the *same* DDS folder produced by
`ytd_export.ps1` from the same archive, so the writer is the only variable:

```
A  resources/pack_ytd.ps1 -Xml ... -Build ... -Out cw.ytd -Original <source>   (CodeWalker)
B  read_ytd(source) + lite.pack_native(..., names from the XML)                (ytd_write)
```

| archive | source | A CodeWalker | B ytd_write |
| --- | --- | --- | --- |
| `ped_gen9/HarleySS.ytd` | 27,301,656 B | 27,301,712 B | **26,886,698 B** |
| `ped_gen8/Mai.ytd` | 21,448,527 B | 21,723,575 B | **21,446,773 B** |

**Texture tables.** Both writers reproduce the source table exactly — 32 of 32 names,
widths, heights, formats and mip counts identical (`table diff vs source cw=0 native=0`).
CodeWalker reading our output back (`ytd_inspect.ps1`) returns the same 32 rows as the
source, field for field, with an empty `error` for both generations:

```
_probe\pack_cmp\gen9\cli.ytd: cw rows 32 vs 32  identical=True  err='' ''
_probe\pack_cmp\gen8\cli.ytd: cw rows 32 vs 32  identical=True  err='' ''
```

**Headers — this is where they differ.** Same input, same `-Original` descriptor copy:

- **gen9:** CodeWalker rewrites the VFT of all 32 textures from `0xB6F0EE97` to
  `0x100000000`. The `-Original` pass restores `G9_UsageData / G9_Flags / UsageData /
  UsageFlags / ExtraFlags` but **does not touch VFT**. Our writer: `header diff {}`.
- **gen8:** CodeWalker rewrites VFT to `0` for all 32 textures and flips `0x04` from
  `0` to `1` on all 32. Our writer: `header diff {}`.

Both results were reproduced with **both** CodeWalker builds on this machine —
`CodeWalker30_dev48` (4,572,672 B, `1.0.0+89e335c1`) and the newer `ModDropV` core
(10,170,368 B, `1.0.0+485d56be`) produce byte-identical archives in every row above,
including the same header damage. So the comparison does not depend on which build is
picked; `cw.py` prefers ModDropV only because it sorts by mtime.

On this workload the native writer is strictly closer to the source than CodeWalker's,
and equal on everything else.

**Behaviour shipped:**

- `pack --xml ... --build ... --original <archive>` → native writer, no CodeWalker needed.
  The generation comes from the archive, not from `--legacy`.
- Without `--original` → CodeWalker fallback (a from-scratch dictionary has no source
  headers to copy); if CodeWalker is absent the command says to pass `--original`
  instead of failing on a missing DLL.
- Textures named in the XML but absent from `--original` are reported and skipped:
  `warn  N texture(s) from the XML are not in --original and were skipped: ...`

Verified on the packaged build (`_probe/dist6`): gen9 11.2 s, gen8 9.2 s, same byte sizes
as the source runs, `ytd list` reads both back. `Ran 45 tests OK`.

### Container structure — what actually changes on disk

A matching texture table and a clean header dump do not prove the container the game loads
is unchanged, so the RSC7 layout was compared field by field (`_probe/rsc7_cmp.py`, built
on `fivefury.resource.split_rsc7_sections` / `read_rsc7_header`).

gen9 — every container field is identical; only the deflate stream differs:

```
field                    source      rewritten  same
version                       5              5  yes
system_flags             131072         131072  yes
graphics_flags       1342439960     1342439960  yes
system_size                8192           8192  yes
graphics_size          71303168       71303168  yes
graphics_pages                7              7  yes
```

gen8 — the container is re-laid out, not merely recompressed:

```
system_flags             131072       50331648  NO
graphics_flags       3724804108     3700293621  NO
system_size                8192           6144  NO
graphics_size          81788928       77643776  NO   (-4,145,152)
graphics_pages                5            154  NO
```

The size difference is not lost texture data. The source archive carries **4,146,784 B
(5.07%) of slack** inside its graphics section — space no texture points at:

```
gen8 Mai:      graphics_size=81,788,928  sum(texture data)=77,642,144  slack=4,146,784 (5.07%)
gen9 HarleySS: graphics_size=71,303,168  sum(texture data)=70,736,416  slack=   566,752 (0.79%)
```

`_prepare_gen9_ytd` reproduces the source layout exactly, slack included, which is why
gen9 matches. `_prepare_legacy_ytd` packs the section tightly, so the 5% of unused space is
dropped and the page flags are recomputed — that is the whole of the gen8 difference. The
rewrite is a fixed point: packing our own output again reproduces it byte for byte
(`gen9: pass1 == pass2`, `gen8: pass1 == pass2`), so repeated edits cannot accumulate
drift.

Read as four independent claims: pixel bytes identical (32/32), texture table identical,
runtime fields identical (`header diff {}`), and container identical. The first three hold
for both generations; the fourth holds for gen9 only. Gen8 ships a smaller, differently
paged file with the same contents — whether the engine cares is precisely what the gen8
in-game pass has to answer, and no static check can settle it.

### gen8 checklist for the in-game pass

Queued until a legacy install exists. Each row is one file, one observation and one
failure symptom, so a bad result points at a specific field instead of "something looks
off".

| # | archive | built by | what to watch | if it fails it means |
| --- | --- | --- | --- | --- |
| 1 | `vehicles_gen8/gtr.ytd` | `lite --cap 1024 --inplace` | body paint correct, no scrambled stripes, dials and interior readable | `stride` / dimension mismatch |
| 2 | `ped_gen8/Mai.ytd` | same | face and clothing correct up close, no smeared or greyscale texture | same |
| 3 | `ped_gen8/Mai.ytd` | `pack --xml ... --original Mai.ytd` | appearance identical to the unmodified file | texture order or name-table mismatch |
| 4 | `ped_gen8/Mai.ytd` | `fix_mips` | no shimmering when walking away from the ped | mip chain written but unreadable |
| 5 | any | load, edit again, load again | second load looks identical to the first | non-idempotent write (already ruled out statically) |

Rows 1–2 are the only ones that exercise `stride`, the one field whose meaning is still
unconfirmed: the source stores a quarter of the value fivefury computes (source 32 / 4,
ours 128 / 16), and it is echoed back only when width/height/format are unchanged — so a
scaled texture is exactly the case where the new value reaches the game. That is why the
scaling passes come first.

**Not verified:** no in-game launch of a packed or scaled archive in this round (see the
gen8 checklist above), and `--original` is now effectively required for the
header-preserving path — a behaviour change worth a changelog line.

## Round 2 (2026-11-24)

Working through `REPLY-to-probe.md`. Four items, evidence inline.

1. **41 baseline — run, not inherited.** `ls 素材不要动/ped_ingame41_gen9/*.ymt | wc -l` → `41`;
   `_probe/baseline41.py` → `41/41 ok` (transcript in *Evidence levels* above, where the
   contradictory "data no longer exists" sentence has been replaced). Nothing was left
   worded as "looks like it ran".

2. **legacy YTD write — patch #2 is now 实测, not 推测.** Implemented in `ytd_write.py`
   (`dump_legacy_headers` + `_make_prepare_legacy` + `_verify_legacy`), patching the
   produced section instead of copying fivefury's writer. `ped_gen8/Mai.ytd`:
   header diff after the fix is `name_ptr`/`data_ptr` only (relocation, unavoidable),
   all four semantic fields preserved, **pixels 32/32 identical**, **RSC7 version 13 → 13**,
   and CodeWalker reads the rebuilt archive to a byte-identical texture table.
   Command + output quoted in *2. legacy YTD header is written as zeros* above.

3. **Packaged `lite` — smoke-tested, all four paths pass.** Rebuilt `_probe/cli.spec`
   (PyInstaller 6.22.3, Python 3.12.14), then ran the console binary against fresh
   copies of `ped_gen9/HarleySS.ytd` and `ped_gen8/Mai.ytd`:

   ```
   $ exe ytd list  _probe/lite/gen9/HarleySS.ytd     -> 32 texture(s), 31 with incomplete mips
   $ exe lite --mode cap --cap 1024 --inplace ...gen9 -> 27301656 B -> 6956464 B   6.30 s
   $ exe ytd list  _probe/lite/gen8/Mai.ytd          -> 32 texture(s), 32 with incomplete mips
   $ exe lite --mode cap --cap 1024 --inplace ...gen8 -> 21448527 B -> 6706754 B   6.20 s
   ```

   `_native_abi3.pyd` loads in the packaged build (the `ytd list` path calls
   `read_ytd`), `fivefury/data` and both shader XMLs resolve from `_internal/fivefury/`,
   and `--inplace` keeps `<name>.ytd.bak`.

   Two defects surfaced by this smoke test and fixed:

   - **gen8 `lite` still went through CodeWalker.** `lite.py` keyed its branch on the
     archive version, so a gen8 file called `ytd_export.ps1`, which the console build
     does not ship → `err Mai.ytd: -File ... resources\ytd_export.ps1 does not exist`.
     Since patch #2 covers legacy, the branch is now
     `legacy = version == YTD_VERSION_LEGACY and bool(os.environ.get("GTA_LITE_LEGACY_CW"))`
     — fivefury by default, CodeWalker only on demand. The escape hatch stays because
     legacy `stride` is preserved only while the geometry is unchanged (a shrunk texture
     gets the recomputed value, and that case has no in-game verification yet).
   - **`--inplace` reported the new size twice.** `cli.py` read `os.path.getsize(src)`
     *after* `make_lite` had already rewritten it, so a 21 MB input printed
     `6706754 B -> 6706754 B`. The size is now captured before the call.

4. **Full sweep — `99 ok, 4 refused with a stated reason`, nothing dropped silently.**
   `_probe/roundtrip_ytd.py` now runs every archive through `ytd_write.save`, legacy
   included (its old `legacy (not handled)` branch is gone), 103 files in 431.3 s:

   ```
   99 ok, 0 legacy (not handled), 4 failed in 431.3s
   ```

   The four failures are all *refusals*, not silent damage:

   | archive | reason |
   | --- | --- |
   | `vehicles_gen8/renventon.ytd` | 1 texture name outside ASCII (`coté_n`) |
   | `vehicles_gen9/Audi TTS/penumbra.ytd` | 3 texture names outside ASCII (`disque cotý_n`, `cotý_n`, `disque cotý`) |
   | `vehicles_gen9/Mercedes Benz AMG GTR/feltzer2.ytd` | 1 texture name outside ASCII (`cotý_n`) |
   | `vehicles_gen9/Audi TTS/penumbra+hi.ytd` | 61-byte placeholder, no texture data |

   The non-ASCII finding is new and it is upstream, not ours: fivefury reads the name
   table with `binary.py:139 data[offset:end].decode("ascii", errors="ignore")` and writes
   it with `resource.py:676 value.encode(encoding, errors="ignore")`, so a stored
   `disque cot\\xe9_n` comes back as `disque cot_n` — **the byte is gone before our code
   ever sees the string**. My write-after verify caught it as
   `RuntimeError: written archive does not preserve the source headers: 3 texture(s)
   missing from the written archive` (the names changed, so they no longer match).

   `ytd_write.save()` now refuses such archives up front instead of renaming their
   textures:

   ```
   RuntimeError: this archive stores 3 texture name(s) outside ASCII ('disque cotý_n',
   'cotý_n', 'disque cotý'); fivefury's name table uses ascii+errors=ignore, so rewriting
   it would silently drop those bytes and rename the textures. Refusing to write.
   ```

   That is the honest floor: those four files cannot be rewritten by this stack without
   corrupting their dictionaries, and the tool says so instead of producing a file that
   looks fine until a texture goes missing in game. Everything else — 99 of 103, including
   all six rewriteable gen8 archives — round-trips with zero metadata and zero pixel
   differences.


