# gtatools

[![tests](https://github.com/wokken198/gtav-toolkit/actions/workflows/tests.yml/badge.svg)](https://github.com/wokken198/gtav-toolkit/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/wokken198/gtav-toolkit?label=release&color=2ea44f)](https://github.com/wokken198/gtav-toolkit/releases/latest)

Small, focused helpers for GTA V (Legacy and Enhanced / gen9) texture and ped-variation work. Six commands, one CLI:

| command | what it does |
|---|---|
| `gtatools normals` | badge diffuse map → tangent-space normal map (DDS) + contact sheet |
| `gtatools audit` | CPedVariationInfo (`.ymt`) consistency check against vanilla's rules |
| `gtatools scale` | DDS rescaling that keeps pixel format and mip depth |
| `gtatools pack` | build a `.ytd` from a CodeWalker XML + a folder of DDS |
| `gtatools ytd list` | read-only dump of a texture dictionary (name, size, format, mips) |
| `gtatools mips check` | flag incomplete mip chains in `.ytd` / `.dds` files |

No game assets are included; everything reads from your own install.

![flat diffuse on the left, the same texture lit with a generated normal map on the right](docs/images/hero.png)

## What it does to a real pack

| pass | before | after | delta |
|---|---|---|---|
| 386 vehicles, 796 badge textures (rebuilt at 256, DXT5, full mips) | 386.9 MB | 373.2 MB | −13.7 MB |
| badge payload only | 65.4 MB | 44.1 MB | **−33%** |
| a 16-texture 2048² ped `.ytd`, rescaled to 1536 | 16.6 MB | 10.6 MB | **−36%** |
| 190 oversized DDS, long edge 2048 → 1536 | 820.8 MB | 521.4 MB | −36% |

Zero failures across those batches, and a pack → export → compare round trip came back
byte-identical on the sampled files.

## Game versions

`normals` and `scale` are version-agnostic: they take DDS files and the rules they encode (DXT1/5,
BC7/BC5, full mip chains, dimensions rounded to 4) are the same in Legacy and Enhanced.

`pack` is where the two games differ:

- **Enhanced (gen9)** archives are RSC7 version 5. That is the default; add `--original` to restore
  the `script_rt_*` render-target descriptors that CodeWalker's XML export drops.
- **Legacy** archives are RSC7 version 13. Pass `--legacy`. Those `G9_*` descriptor fields do not
  exist there, so `--original` is not needed for them.
- Legacy `.ydd` XML round trips silently lose meshes (the exporter writes `<Data2>`, the importer
  reads `<Data>`), so merge legacy peds from the binary files rather than from XML.

## Docs

Start at [docs/README.md](docs/README.md) for a one-table map of the repository: which page to read for
the CLI, for the DeepSeek Harness bundle, for the market index, and for the pitfalls below. The bundle's
internals are described in [dsh-plugin/docs/DETAIL.md](dsh-plugin/docs/DETAIL.md).

## Install

```bash
pip install -e .
```

Python 3.9+, `numpy`, `Pillow`. Two optional dependencies, needed only by the commands that use them:

- **texconv.exe** (DirectXTex) — required by `normals` and `scale`; on `PATH`, in the working directory
  tree, or passed with `--texconv` / `GTA_TOOLS_TEXCONV`.
- **CodeWalker.Core.dll** (dev48+) plus Windows PowerShell — required by `pack`; located through
  `--core-dir`, `GTA_TOOLS_CW`, or the common-install probe described below.

## normals

```bash
gtatools normals <src> --out out --sheet sheet.png
# defaults: --strength 6.5 --blur 1.2 --fmt DXT5 --max-mips 12
```

For every `*badge*.dds` that is not already a normal map:

1. decode with texconv → RGBA
2. height = `0.7 * percentile-normalised luma + 0.3 * alpha`, then Gaussian blur (`--blur`)
3. gradient → normal, slope scaled by `--strength`
4. margin (alpha ≈ 0) forced to `(128,128,255)` — otherwise the atlas cell border keeps a slope and
   shows up as a faint rectangle around the engraving
5. encode with a full mip chain (`--max-mips` caps it)

Tuning: flat decals 8–10, chrome / baked-specular art 4–5, text-only art 6–7.

![diffuse to height field to normal map to lit result](docs/images/pipeline.png)

## audit

```bash
gtatools audit ped.ymt.xml --json report.json
```

Checks against what vanilla peds actually do:

- `numAvailTex(component) == sum(aTexData)` over that component's drawables
- `compInfos` has exactly one entry per `(slot, drawable)`; the key is the **slot index inside
  `availComp`**, not the component's position in `aComponentData3`
- `texId` is a race suffix (`0 uni, 1 whi, 2 bla, 3 chi, 4 lat, 5 ara, 10 pak`), not a texture slot
- dangling components (declared in the .ymt but with no drawable in the .ydd) and count mismatches

Exit code `2` when problems are found, so it can gate a build.

## scale

```bash
gtatools scale <paths...> --out resized --long-edge 1536 --min-edge 1025
# --min-edge skips anything whose long edge is already <= that value
```

- decodes with texconv, resizes RGB and alpha **separately** — Pillow's RGBA Lanczos premultiplies
  alpha and darkens semi-transparent art — then re-encodes in the original format
- target size is rounded to a multiple of 4; mip count is preserved but capped to the new chain
- unsupported formats are skipped and reported, never half-written
- an output tree mirroring the inputs is built under `--out`

## pack

```bash
gtatools pack --xml vehshare.ytd.xml --build build_dir --out vehshare.ytd \
              --original vanilla_vehshare.ytd
```

`--original` copies `G9_UsageData / G9_Flags / UsageData / UsageFlags / ExtraFlags` from an existing
archive, matched by texture name. This matters: CodeWalker's XML export does not carry the gen9
render-target descriptor bits, and losing them breaks scripted render targets (dashboard dials and
similar) — the archive still loads, the game crashes when the target is drawn.

`--legacy` writes gen9=off (version 165 assets). `--core-dir` overrides the CodeWalker location; when
it is omitted the CLI probes `GTA_TOOLS_CW`, `CODEWALKER_DIR`, common install paths, and the working
directory's parents.

## ytd list

```bash
gtatools ytd list car.ytd --only badge
gtatools ytd list cars/*.ytd --json
```

Reads a texture dictionary and prints one line per texture: name, size, format, mips. `--only` filters
by substring. `--json` alone prints JSON to stdout, `--json out.json` writes a file — the same convention
`audit` and `mips check` use. Needs CodeWalker (`CodeWalker.Core.dll`); nothing is written. Exit code `2`
if an archive cannot be read.

## mips check

```bash
gtatools mips check extracted/                 # .ytd and .dds side by side
gtatools mips check a.dds b.dds --all
```

Mip chains are the one defect you cannot see in a still screenshot: a 256×128 texture needs 9 levels
(`floor(log2(256)) + 1`), and a file that ships 1 level aliases into a shimmering mess as soon as the
camera moves. This subcommand reports `mips/expected` per texture; `.dds` files are parsed in pure
Python, `.ytd` files go through CodeWalker. Exit code `2` when anything is incomplete, so it can gate
a build. See [docs/why-mips.md](docs/why-mips.md) for the long version.

## Use it as a DeepSeek Harness plugin

`dsh-plugin/` is an installable DSH bundle that exposes the same six operations as agent tools
(`gta_badge_normal`, `gta_ymt_audit`, `gta_ytd_scale`, `gta_ytd_pack`, `gta_ytd_list`, `gta_mips_check`).
The Python package is vendored inside, so nothing needs to be pip-installed.

### Prerequisites

| need | why |
|---|---|
| DeepSeek Harness (recent build) | the bundle manifest (`dsh.bundle.patch`) |
| Windows | `normals` and `scale` shell out to `texconv.exe`; `pack` shells out to CodeWalker's .NET assembly |
| Python 3.9+ with `numpy` and `Pillow` | DeepSeek Harness already ships one and the bundle probes for it — usually nothing to install |
| `texconv.exe` (DirectXTex) | only `normals` and `scale` |
| `CodeWalker.Core.dll` (dev48+) | only `pack` |

### Install from a checkout

```bash
git clone https://github.com/wokken198/gtav-toolkit
```

Then in DeepSeek Harness: **Plugins → Add plugin**, and point it at `gtav-toolkit/dsh-plugin`.
The bundle is named `dsh-gta-tools`.

### Install from a pinned commit

Pass this as the `target` of `install_bundle`, replacing `<commit>` with a commit of this repository:

```text
git+https://github.com/wokken198/gtav-toolkit.git#<commit>&path:/dsh-plugin
```

### Install from npm (only if you publish it yourself)

```bash
cd dsh-plugin
npm publish          # or: npm publish --access public  for a scoped name
```

Users then install `dsh-gta-tools@<version>`.

There is no central store to submit to: the DSH plugin market only reads index URLs a user adds under
Settings, so a checkout, a pinned commit, or an npm package is the distribution channel.

Environment variables (optional; set before launching DSH):

| variable | meaning |
|---|---|
| `GTA_TOOLS_PYTHON` | python executable; when unset the plugin probes `python3`, `python`, then the Python bundled with DeepSeek Harness |
| `GTA_TOOLS_TEXCONV` | path to `texconv.exe`; when unset it is looked up on `PATH` and in the working directory's parents |
| `GTA_TOOLS_CW` | CodeWalker folder holding `CodeWalker.Core.dll`; when unset the plugin probes `GTA_TOOLS_CW`/`CODEWALKER_DIR`, common install locations, Desktop, and the working directory's parents. `gta_ytd_pack`, `gta_ytd_list` and `gta_mips_check` need it |

### After installing

1. The Plugins list shows **GTA V texture tools**.
2. Smoke test from any session — ask the agent to run `gta_ytd_scale` on a folder of DDS with a small
   target size, `gta_ytd_list` on a `.ytd`, or `gta_ymt_audit` on an exported ped `.ymt.xml`. A table
   with no errors means the Python side is wired up.
3. Tool names: `gta_badge_normal`, `gta_ymt_audit`, `gta_ytd_scale`, `gta_ytd_pack`, `gta_ytd_list`,
   `gta_mips_check`.

### Troubleshooting

- **`ModuleNotFoundError: numpy`** — the bundle probes `python3`, `python`, then the interpreter
  bundled with DeepSeek Harness, and skips any candidate that cannot import `numpy`/`PIL`. If a system
  Python is picked anyway (for example before an update), point `GTA_TOOLS_PYTHON` at the bundled one,
  or `pip install numpy pillow` for the system interpreter.
- **`FileNotFoundError: texconv`** — put `texconv.exe` on `PATH`, in the working directory tree, or set
  `GTA_TOOLS_TEXCONV`.
- **`pack` cannot find CodeWalker** — it prints `codewalker: <path>` on success and exits `2` with a hint
  when nothing was found. Set `GTA_TOOLS_CW` to the folder that holds `CodeWalker.Core.dll`.

Node and CodeWalker are not bundled: `pack` shells out to CodeWalker's .NET assembly on Windows.

## Known pitfalls this repo encodes

- **XML → `.ytd` round trip is lossy** for `script_rt_*` textures; always pack with `--original` when you have a
  reference archive.
- **CodeWalker's DDS export flattens A8R8G8B8 to 8 bpp grayscale**, so exported channel statistics lie
  for mask-style textures (plate fonts, glyph atlases); read `TextureData.FullData` if it matters.
- **Legacy (gen8) vertex data** is exported as `<Data2>` while the importer only reads `<Data>` —
  round-tripping a legacy `.ydd` through XML silently drops its meshes. Merge legacy peds from binary.
- `.ymt` `availComp` appears either as spaced decimals or one hex blob; both forms are parsed here.
- Patch-DLC override order follows `dlclist.xml`, not the `<order>` element in `setup2.xml`: a texture
  shipped in a later-loading pack wins even when an earlier pack declares the same name.
- Pillow ≥12 premultiplies alpha when resizing RGBA, which darkens translucent art: scale channels
  separately.

## Tests

```bash
python -m unittest discover -s tests -v
```

11 tests, covering DDS header parsing (DXT5 / DX10 BC7 / A8R8G8B8 / rejection), the normal-map maths
(flat in → flat out, margin flattening, luma direction) and the ymt audit rules (consistent, wrong
`numAvailTex`, missing `compInfo`, hex `availComp`).

## Layout

```
src/gtatools/       cli.py, dds.py, normals.py, ymt.py, cw.py
tests/              test_core.py
resources/          pack_ytd.ps1
dsh-plugin/         DSH bundle (index.js, locale/, vendor/gtatools, icon.svg)
market/             market index entry
docs/               docs/README.md and docs/images/ artwork
.github/            tests workflow
```

## Building on this

You are welcome to put a UI, a GUI wrapper, or a fork on top of this code — a
standalone desktop app for badge work is an obvious next step, and this repository
is meant to be the engine for it.

If you reuse the code, **keep the copyright notice and say where it came from**,
e.g.:

> Badge handling based on [gtav-toolkit](https://github.com/wokken198/gtav-toolkit)
> by wokken198, MIT licensed.

That attribution requirement is the one thing the MIT license already asks for
(keep the notice); the link back is courtesy, and it is how people find the
original when they need the CLI or the fixes. Forking, renaming, adding a GUI,
using only the normal-map maths, or wrapping the CLI in your own app are all fine.

Not fine: shipping the bundled `dsh-plugin/`, or a copy of this code, without the
notice; or redistributing game assets (`.dds`, `.ytd`, `.ydd`, `.ymt`, brand art)
as if they were yours — none of those are in this repository to begin with.

## License

MIT for the code. Game-derived assets are not covered and are not shipped here.
