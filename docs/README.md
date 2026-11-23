# Docs

Where to look, depending on what you are trying to do.

| If you want to | Read |
|---|---|
| understand what the toolkit does, then install it | [README](../README.md) |
| run one command and see what happens | [README § normals](../README.md#normals), then `audit`, `scale`, `pack` |
| use a window instead of the command line | [README → GUI](../README.md#gui) |
| build the Windows exe | [README → GUI](../README.md#gui) |
| install the DeepSeek Harness bundle | [README § Use it as a DeepSeek Harness plugin](../README.md#use-it-as-a-deepseek-harness-plugin) |
| see how the bundle is wired together | [dsh-plugin/docs/DETAIL.md](../dsh-plugin/docs/DETAIL.md) |
| add this repository as a DSH market index | `https://cdn.jsdelivr.net/gh/wokken198/gtav-asset-repair@main/market/index.json` |
| avoid the mistakes this repo exists to document | [README § Known pitfalls](../README.md#known-pitfalls-this-repo-encodes) |
| see what is inside a `.ytd` without opening CodeWalker | [README § ytd list](../README.md#ytd-list) |
| find textures whose mip chain is too short | [README § mips check](../README.md#mips-check), then [why-mips.md](why-mips.md) |
| understand why textures shimmer in the distance (missing mip levels) | [why-mips.md](why-mips.md) |
| see what changed in each version | [CHANGELOG.md](../CHANGELOG.md) |

## Repository layout

```
src/gtav_asset_repair/          the Python package (cli, dds, normals, ymt, ytd, cw)
tests/                 unittest suite, no game files required
packaging/gui_entry.py PyInstaller entry point for the GUI
resources/gtav_asset_repair.ico window icon, generated, brand-free
resources/pack_ytd.ps1 the CodeWalker bridge used by `gtav-asset-repair pack`
resources/ytd_inspect.ps1  the CodeWalker bridge used by `ytd list` and `mips check`
dsh-plugin/            the installable DeepSeek Harness bundle
  vendor/gtav_asset_repair/     a byte-identical copy of src/gtav_asset_repair
  docs/DETAIL.md       what each tool does and how it is configured
market/index.json      market index entry (git source, pinned commit)
docs/images/           figures used by the README
```

`src/gtav_asset_repair` and `dsh-plugin/vendor/gtav_asset_repair` are kept byte-identical on purpose: the bundle has to work
without `pip install`, so it carries its own copy. Change one, change the other.

## The four commands, in one line each

- `gtav-asset-repair normals` — badge diffuse → tangent-space normal (DDS), optional contact sheet
- `gtav-asset-repair audit` — check a `CPedVariationInfo` (`.ymt`) against vanilla's rules
- `gtav-asset-repair scale` — resize DDS files, keeping pixel format and mip depth
- `gtav-asset-repair pack` — build a `.ytd` from a CodeWalker XML export plus DDS files

Full flags: `gtav_asset_repair <command> --help`.

## Not covered here

Game assets. None are in this repository — every command reads from your own install, and the figures in
`docs/images/` are drawn by a script, not extracted from the game.
