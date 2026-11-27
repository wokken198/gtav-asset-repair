# GTA V asset tools

Nine tools for GTA V **Enhanced (gen9)** and **Legacy (gen8)** assets, plus a six-page desktop
window that covers the same ground without a terminal. Everything runs in pure Python — no
CodeWalker installation, no .NET assembly, no PowerShell.

This page covers the bundle itself. Command-line behaviour, the Gen8 → Gen9 conversion rules and
the full flag list live in the [repository README](../../README.md).

## Requirements

- **Python 3.11+** with `numpy` and `Pillow` (resolved automatically when you run from DSH)
- **texconv.exe** (DirectXTex) — only `gta_badge_normal` and `gta_ytd_scale` use it, and only if
  you pass it explicitly or leave it on `PATH`

## Environment variables

| variable | used by | meaning |
|---|---|---|
| `GTA_TOOLS_PYTHON` | all | python executable; defaults to probing `python3`, `python`, then the Python bundled with DSH |
| `GTA_TOOLS_TEXCONV` | normal maps, scale | path to `texconv.exe`; defaults to a `PATH` lookup and the working directory's parents |

## gta_badge_normal

Turns a badge diffuse atlas into a tangent-space normal map. Relief is built from the alpha-weighted
luminance of the diffuse, so engraved lettering keeps its shape; the atlas margin is forced flat so the
texture cell border does not show up as a rectangle around the text.

- `strength` — default 2.0 (matches the desktop window). Raise it for chrome or baked-specular art;
  flat printed decals usually want more, canvas-like art wants less
- `blur` — smooths the height field before differentiating; 1.0-1.4 is typical
- `fmt` — `DXT5`, `DXT1`, `BC5` or `A8R8G8B8`

## gta_ymt_audit

Checks a `CPedVariationInfo` against what vanilla peds actually do:

- `numAvailTex` per component must equal the sum of `aTexData` over that component's drawables
- `compInfos` needs exactly one entry per `(slot, drawable)`
- `availComp` slots that name a component absent from the ydd are reported as dangling
- `texId` is a race suffix, not a texture slot

## gta_ytd_scale

Rescales DDS files while preserving format and mip depth. RGB and alpha are resampled separately,
because resizing RGBA in one pass premultiplies alpha and visibly darkens semi-transparent art.

## gta_ytd_pack

Builds a gen9 YTD from a CodeWalker `ytd.xml` plus a folder of DDS files. Pass `original` to copy the
gen9 render-target descriptor bits by texture name — without that step the archive looks correct in a
viewer but breaks scripted render targets (dashboard dials, camera feeds) in game.

The XML is the *input format*; nothing from CodeWalker has to be installed to run the pack.

## gta_ytd_list

Read-only dump of a texture dictionary: name, size, format and mip count per texture, optionally filtered
by a substring (`only: "badge"`). Handy before editing a `.ytd`, or to confirm what a pack actually ships.

## gta_mips_check

Reports every texture whose mip chain is shorter than `floor(log2(long edge)) + 1` — the defect that makes
a texture shimmer at distance but look fine in a still image. Accepts `.ytd` and `.dds` paths or folders;
`all: true` also lists the healthy ones. See `docs/why-mips.md` for the figures.

## gta_ytd_lite

Shrinks the textures inside a `.ytd` and writes the result back.

| argument | meaning |
|---|---|
| `files[]` | `.ytd` files or folders (scanned recursively) |
| `mode` | `cap` (anything longer than the limit is scaled down to it), `tier` (long edge snaps down to 1024 / 1536 / 2048), `agg` (cap plus format swaps: uncompressed → DXT5, opaque DXT5 → DXT1) |
| `cap` | long-edge limit for `cap` / `agg`: 1024, 1536 or 2048 |
| `inplace` | overwrite the source and keep the previous file as `.bak`; otherwise a `<name>_lite.ytd` is written |
| `out`, `json` | explicit output path, and an optional JSON report |

Textures under 1024 px are skipped, and `script_rt_*`, normal maps and `spec` / `gloss` / `dirt` /
`decal` / `mask` maps keep their format even in aggressive mode — changing those breaks shaders.
The result is re-read before it is published, and nothing is written when the archive would not change.

## gta_ped_check

Audits ped variation files. For every `.ydd` / `.ymt` pair it checks that the `.ymt` declares exactly
the drawables the geometry has: `numAvailTex` equals the `aTexData` sum of the component, one
`compInfos` row per textured drawable, and no dangling slots. Prints one line per ped plus a summary,
writes a JSON report with `json`, and exits non-zero on any mismatch.

A mismatch is what makes a ped spawn with misplaced parts, broken LODs or a crash.

## gta_ped_fix

Repairs those pairs: trims the `.ymt` down to the drawables the `.ydd` ships, or corrects the counts,
then re-reads the packed file to prove it parses back. Dry run unless `apply` is true; a `.bak` stays
next to every file it rewrites. Files that already pass the audit are left untouched.

## Limitations

- Window and CLI assume Windows paths; the library itself is portable.
- There is no Gen9 → Gen8 path: the newer layout carries information the old engine cannot express.
- Encrypted RPF entries are copied as-is — moving them would break the archive.
- Long jobs run until the child process exits; very large batches are better run from the CLI.

## Installing from the market index

The repository publishes an index at
`https://cdn.jsdelivr.net/gh/wokken198/gtav-asset-repair@main/market/index.json`. Add it under
**Plugins → Discover → market settings**, then install `dsh-gtav-asset-repair` from the list. The index entry
pins a commit, so updates arrive only when the index is regenerated — that is deliberate: it keeps the
published bundle reproducible.

## What the desktop window does

`gtav-asset-repair.exe` covers the same ground without a terminal, on six pages:

| page | what it reads | what it writes |
|---|---|---|
| Normal maps | `.dds` | `*_n.dds` next to the source |
| Texture compression | `.ytd` | `<name>_lite.ytd` by default, or in place with a `.bak` |
| Mipmap check & fill | `.dds`, `.ytd` | in place, original kept as `.bak` |
| Ped YMT repair | `.ydd` + `.ymt` pairs | in place, original kept as `.bak` |
| Defragment RPF | `.rpf` | in place, original kept as `.bak` |
| Convert Gen8→9 | `.ytd` / `.ydd` / `.yft` / `.ymt` / `.yld` | a mirrored tree under `<folder>-gen9` |

Two behaviours worth knowing before you file a bug:

- `script_rt_*` render targets are never given extra mip levels; they stay listed as incomplete on
  purpose, because their chain follows the render-target size.
- Converting a vehicle needs the whole set — `car.yft`, `car_hi.yft` and `car.ytd`. Converting only the
  body leaves half the car on the gen8 layout; suspension and steering parts (brake calipers, steering
  wheel) then fly around in game.
