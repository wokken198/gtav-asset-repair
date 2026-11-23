# Implementation notes

Details that matter if you want to change the code or reproduce the numbers. None of this is
required to use the tool.

## Normal maps

Height is `0.7 * percentile-normalised luma + 0.3 * alpha`, then a Gaussian blur, then the gradient
scaled by `--strength`. The atlas margin is forced flat to `(128,128,255)` so a rectangle never shows
around the art.

Measured on vanilla badges: median slope 0.7–2.3°, bevels 25–35°, flat areas 53–71%. The default
`--strength 4.5` lands in that range; flat decals want 8–10, chrome or baked specular 4–5, text-only 6–7.

## Rescaling

RGB and alpha are resized **separately**. Pillow ≥ 12 premultiplies alpha when resizing RGBA, which
darkens translucent art — reading the four channels apart avoids it. Target size rounds to a multiple
of 4; mip depth is preserved but capped to the new chain.

## Repacking

`pack --original` copies `G9_UsageData`, `G9_Flags`, `UsageData`, `UsageFlags` and `ExtraFlags` from an
existing archive, matched by texture name. CodeWalker's XML export does not carry those gen9
render-target bits. The archive still loads without them, but scripted render targets (dashboard
dials and similar) crash when drawn.

XML → `.ytd` is lossy for `script_rt_*` textures in general: always pack with `--original` when you
have a reference archive to copy from.

CodeWalker's DDS export flattens `A8R8G8B8` to 8 bpp grayscale, so exported channel statistics lie
for mask-style textures (plate fonts, glyph atlases). Read `TextureData.FullData` if it matters.

Legacy vertex data exports as `<Data2>` while the importer only reads `<Data>`; a legacy `.ydd`
round-tripped through XML silently loses its meshes. Merge legacy peds from the binary.

## Ped variation files

The key in `compInfos` is the **slot index inside `availComp`**, not the component's position in
`aComponentData3`. `numAvailTex` is the sum of `aTexData` over that component's drawables. `texId` is
a race suffix (0 uni, 1 whi, 2 bla, 3 chi, 4 lat), not a texture slot. Full structure in
[ped-ymt-rules.md](ped-ymt-rules.md).

## Override order

Patch-DLC override order follows `dlclist.xml`, not `setup2.xml`'s `<order>`: a texture shipped in a
later-loading pack wins even when an earlier pack declares the same name.
