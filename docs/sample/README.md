# Sample textures

Three 256x256 badge-like DDS files (DXT5, full mip chain) drawn for this repository -
no game assets, free to use for testing.

```bash
# 1. build normal maps next to the sources
gtatools normals docs/sample --strength 4.5 --fmt DXT5

# 2. find and fill short mip chains
gtatools mips check docs/sample
gtatools mips fix docs/sample --apply      # writes *_mips.ytd / *.dds copies

# 3. shrink a texture dictionary (bring your own .ytd)
gtatools lite "D:\mods\cars" --mode cap --cap 1024 --inplace
```

The GUI does the same: drop the folder on the first page, press Generate.
