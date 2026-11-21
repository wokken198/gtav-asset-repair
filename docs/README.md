# Docs

Where to look, depending on what you are trying to do.

| If you want to | Read |
|---|---|
| understand what the toolkit does, then install it | [README](../README.md) |
| run one command and see what happens | [README § normals](../README.md#normals), then `audit`, `scale`, `pack` |
| install the DeepSeek Harness bundle | [README § Use it as a DeepSeek Harness plugin](../README.md#use-it-as-a-deepseek-harness-plugin) |
| see how the bundle is wired together | [dsh-plugin/docs/DETAIL.md](../dsh-plugin/docs/DETAIL.md) |
| add this repository as a DSH market index | `https://cdn.jsdelivr.net/gh/wokken198/gtav-toolkit@main/market/index.json` |
| avoid the mistakes this repo exists to document | [README § Known pitfalls](../README.md#known-pitfalls-this-repo-encodes) |
| understand why textures shimmer in the distance (missing mip levels) | [why-mips.md](why-mips.md) |
| see what changed in each version | [CHANGELOG.md](../CHANGELOG.md) |

## Repository layout

```
src/gtatools/          the Python package (cli, dds, normals, ymt, cw)
tests/                 unittest suite, no game files required
resources/pack_ytd.ps1 the CodeWalker bridge used by `gtatools pack`
dsh-plugin/            the installable DeepSeek Harness bundle
  vendor/gtatools/     a byte-identical copy of src/gtatools
  docs/DETAIL.md       what each tool does and how it is configured
market/index.json      market index entry (git source, pinned commit)
docs/images/           figures used by the README
```

`src/gtatools` and `dsh-plugin/vendor/gtatools` are kept byte-identical on purpose: the bundle has to work
without `pip install`, so it carries its own copy. Change one, change the other.

## The four commands, in one line each

- `gtatools normals` — badge diffuse → tangent-space normal (DDS), optional contact sheet
- `gtatools audit` — check a `CPedVariationInfo` (`.ymt`) against vanilla's rules
- `gtatools scale` — resize DDS files, keeping pixel format and mip depth
- `gtatools pack` — build a `.ytd` from a CodeWalker XML export plus DDS files

Full flags: `gtatools <command> --help`.

## Not covered here

Game assets. None are in this repository — every command reads from your own install, and the figures in
`docs/images/` are drawn by a script, not extracted from the game.
