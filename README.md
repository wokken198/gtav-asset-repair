# gtatools

Small, focused helpers for GTA V (Enhanced / gen9) texture and ped-variation work.

Three tools, all driven by one CLI:

| command | what it does |
|---|---|
| `gtatools normals` | badge diffuse map -> tangent-space normal map (DDS), with a preview contact sheet |
| `gtatools audit` | CPedVariationInfo (`.ymt`) consistency check against the rules vanilla peds follow |
| `gtatools scale` | DDS rescaling that keeps pixel format and mip depth |
| `gtatools pack` | build a YTD from a CodeWalker XML + a folder of DDS, optionally restoring render-target descriptors |

No game assets are included; everything reads from your own install.

## Install

```bash
pip install -e .
# texconv.exe (DirectXTex) must be on PATH, or pass --texconv
# CodeWalker.Core.dll (dev48+) is only needed for `pack`
```

Python 3.9+, numpy, Pillow.

## normals

```bash
gtatools normals "D:\extracted\badges" --out out --sheet sheet.png --strength 6.5 --blur 1.2 --fmt DXT5
```

For every `*badge*.dds` that is not already a normal map:

1. decode with texconv, read as RGBA
2. height = `0.7 * percentile-normalised luma + 0.3 * alpha`, then Gaussian blur
3. gradient -> normal, slope scaled by `--strength`
4. margin (alpha ~0) forced to `(128,128,255)` — otherwise the atlas cell border keeps a slope and shows up as a faint rectangle around engraved text
5. encode to `--fmt` with a full mip chain

Tuning: flat decals 8-10, chrome/baked specular art 4-5, text-only art 6-7.

## audit

```bash
gtatools audit ped.ymt.xml --json report.json
```

Checks:

- `numAvailTex(component) == sum(aTexData)` over that component's drawables
- `compInfos` has one entry per `(slot, drawable)`; the key is the slot index inside `availComp`, **not** the component's position in `aComponentData3`
- `texId` is a race suffix (`0 uni, 1 whi, 2 bla, 3 chi, 4 lat, 5 ara, 10 pak`), not a texture slot
- flags missing entries and entry-count mismatches

Exit code is 2 when problems are found, so it can gate a build.

## scale

```bash
gtatools scale "D:\textures" --out resized --long-edge 1536 --min-edge 1025
```

- decodes with texconv, resizes RGB and alpha **separately** (Pillow's RGBA Lanczos premultiplies alpha, which darkens semi-transparent art), re-encodes in the original format
- target size is rounded to a multiple of 4, mip count is kept (capped to the new size's chain)
- unsupported formats are skipped and reported, never half-written

## Pack

```bash
gtatools pack --xml vehshare.ytd.xml --build build_dir --out vehshare.ytd \
              --core-dir C:\CodeWalker --original vanilla_vehshare.ytd
```

`--original` copies `G9_UsageData / G9_Flags / UsageData / UsageFlags / ExtraFlags` from an existing archive by texture name. This matters: CodeWalker's XML round-trip does not carry the gen9 render-target descriptor bits, and losing them breaks scripted render targets (dashboard dials etc.) — the archives look fine, the game crashes when the target is drawn.

`--legacy` writes gen9=off (version 165 assets).

## Use it as a DeepSeek Harness plugin

`dsh-plugin/` is an installable DSH bundle that exposes the same four operations as agent tools
(`gta_badge_normal`, `gta_ymt_audit`, `gta_ytd_scale`, `gta_ytd_pack`), with the Python package vendored
inside so nothing else needs to be pip-installed.

```bash
# from a checkout
# Plugins > Add plugin > pick the dsh-plugin directory
```

Environment variables (set before launching DSH):

| variable | meaning |
|---|---|
| `GTA_TOOLS_PYTHON` | python executable; when unset the plugin probes `python3`, `python`, then the Python bundled with DeepSeek Harness |
| `GTA_TOOLS_TEXCONV` | path to `texconv.exe`; when unset texconv is looked up on `PATH` and in the working directory's parents |
| `GTA_TOOLS_CW` | CodeWalker folder holding `CodeWalker.Core.dll`; when unset the plugin probes `GTA_TOOLS_CW`/`CODEWALKER_DIR`, common install locations (`C:\CodeWalker30_dev48`, Desktop, Desktop\GM, Downloads) and the working directory's parents. Only `gta_ytd_pack` needs it |

Node and CodeWalker are not bundled: the pack path shells out to CodeWalker's .NET assembly on Windows.

Publishing the plugin to npm (needs a free package name, scope it if taken):

```bash
cd dsh-plugin
npm publish          # or: npm publish --access public  for a scoped name
```

Users then install it from the plugin market, or by pointing **Add plugin** at the package directory.

## Known pitfalls this repo encodes

- **XML -> YTD is lossy** for `script_rt_*` textures; always pack with `--original` when you have a reference archive.
- **CodeWalker's DDS export flattens A8R8G8B8 to 8bpp grayscale**, so do not trust exported channel statistics for mask-style textures (e.g. plate fonts); read `TextureData.FullData` if it matters.
- **Legacy (gen8) vertex data** is exported as `<Data2>` but the importer only reads `<Data>` — round-tripping legacy `.ydd` through XML silently drops meshes. Merge legacy peds from binary, not XML.
- `availComp` is written either as spaced decimals or one hex blob; both are parsed here.
- Patch-style DLC override order follows `dlclist.xml`, not `setup2.xml`'s `<order>`; a texture added in a later-loading pack wins even if an earlier pack ships the same name.

## Tests

```bash
python -m unittest discover -s tests -v
```

Covers DDS header parsing (DXT5 / DX10 BC7 / A8R8G8B8 / rejection), the normal map maths (flat in -> flat out, margin flattening, luma direction) and the ymt audit rules (consistent / wrong numAvailTex / missing compInfo / hex availComp).

## License

MIT for the code. Game-derived assets are not covered and are not shipped here.
