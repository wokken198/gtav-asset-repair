# gtav-asset-repair — user guide

**A note from the author:** I put this together in a week, building one feature a day. I'm stopping
feature development for now, unless a breaking issue comes up.

If this tool helped you out, a link back to <https://github.com/wokken198/gtav-asset-repair> would be
much appreciated. The license requires you retain the copyright notice; linking back is just a kind
gesture, not required.

This guide is for people who just unzipped the folder and want to get on with modding. The Chinese
edition is [README.cn.md](README.cn.md).

No Python, no install, no admin rights, and **no external tool** — archive reading and writing run on
the bundled engine.

---

## 1. Quick start

1. **Unzip the whole folder.** Do not drag `gtav-asset-repair.exe` out on its own — it needs the
   `_internal` folder sitting next to it.
2. Double-click `gtav-asset-repair.exe` (or `Run.bat` if Windows blocks it).
3. Pick a page on the left. Language and theme are at the top right and the window remembers both.

---

## 2. What runs on what

| Page | What it does | Writes |
|---|---|---|
| **Normal maps (DDS)** | Builds tangent-space normal maps from badge/emblem `.dds` files | `<input folder>\normals\…_n.dds` |
| **Textures (YTD)** — *Analyze* | Reads archive headers and estimates savings | report panel only |
| **Textures (YTD)** — *Compress* | Rescales textures inside `.ytd` | `<name>_lite.ytd` next to the source, plus `_lite_report.txt` |
| **Mip check (YTD/DDS)** — *Check* | Reports textures whose mip chain is too short | report table |
| **Mip check** — *Fix selected* | Rebuilds the archive with full mip chains | `<name>_fullmips.ytd` (or in place, keeping `.bak`) |
| **Ped repair (YMT)** — *Check* | Compares each `.ymt` with its `.ydd` | report panel |
| **Ped repair** — *Fix selected* | Repairs the `.ymt` of the ticked peds | `.ymt` rewritten, `.bak` kept |
| **Defragment (RPF)** | Gives the space freed by compression back to disk | `.rpf` rewritten, `.bak` kept |
| **Convert Gen8→9** | Rewrites Legacy assets in the Enhanced layout | mirror tree under the output folder |

---

## 3. Using the pages

### 3.1 Normal maps

1. `Add files` or `Add folder`.
2. Tune **Strength** (how deep the relief is), **Blur** (how smooth), **Alpha weight** (how much the
   alpha silhouette counts as height). The toolbar `?` explains each one and shows the vanilla range.
3. `Generate`.

Output is written next to each source file, in a `normals` subfolder. Existing normal maps
(`*_n.dds`) are skipped.

### 3.2 Textures (YTD)

1. `Add YTD`.
2. Pick a long-edge limit (1024 / 1536 / 2048).
3. Choose one of the three options (`--mode` on the CLI):
   - **Option 1 · Snap to tier** (`--mode tier`) — long edge snaps to the nearest tier below.
   - **Option 2 · Ceiling** (`--mode cap`) — anything above the limit is scaled down; smaller textures are left
     alone. This is the safe default.
   - **Option 3 · Reformat** (`--mode agg`) — ceiling plus format swaps (uncompressed → DXT5, opaque DXT5 → DXT1).
     Smaller files, but **verify in game**.
4. `Analyze` shows what you would save without writing anything. `Compress` writes `<name>_lite.ytd`
   and a short report next to it.

Textures under 1024 px, `script_rt_*` render targets, normal maps and spec maps are never reformatted.

### 3.3 Mip check

`Check` lists every texture whose mip chain is shorter than it should be. Short chains shimmer and
moiré at distance.

Select the rows you want and press `Fix selected`. The filter menu can tick everything, tick only
large problems, or skip hair/alpha.

### 3.4 Ped repair

Add a folder that holds `.ydd` + `.ymt` pairs. `Check` marks every ped green (drawables and texture
counts match) or red (the `.ymt` declares more parts than the `.ydd` ships). Red rows are ticked
automatically; click a row to untick it. `Fix selected` only touches ticked rows and keeps a `.bak`.

A repaired ped is re-read before the app reports success, so a broken write is reported instead of
being kept.

### 3.5 Defragment (RPF)

Add the `.rpf` you edited, press `Defragment`. The file is rewritten with the freed blocks reclaimed
and a `.bak` kept. Useful after compression: FiveM and the game stream faster when the archive is
not full of holes.

### 3.6 Convert Gen8 → Gen9

1. Pick the **input folder** (your Legacy mod, e.g. a saved vehicle or ped).
2. Pick the **output folder**. Leave it empty and the app writes to `<input>-gen9` next to your
   source folder.
3. Press **Convert**. The report pane lists every file as it finishes; **Stop** interrupts between
   files — files already written stay written.

**What it converts**

| Type | What happens |
|---|---|
| `.ytd` | Rebuilt in the gen9 layout: new page table, gen9 texture descriptors, `script_rt_*` render-target flags preserved |
| `.ydd` | Rebuilt: gen9 drawable layout, legacy structural VFTs kept for Sollumz-style packs |
| `.yft` | Rebuilt: gen9 fragment runtime tables, gen9 material defaults, octants kept as shipped |
| `.ymt` / `.yld` | Copied byte for byte (the format is identical in both editions) |
| anything else | Listed as skipped, nothing written |

**Three things to know**

- **Convert the whole set.** A vehicle is usually three files — `car.yft`, `car_hi.yft`, `car.ytd`.
  Converting only `car.yft` leaves half the car in the Legacy layout and the brake calipers and
  steering wheel fly around in game.
- **Files that are already gen9 are skipped**, so running the tool twice is safe.
- **No size limit.** There is no hard cap on how large a converted fragment may be: a 34 MB system
  segment loads fine.

Conversion rebuilds each asset in the gen9 layout, which is what keeps `script_rt_*` render-target
flags intact. Lose that flag and the car still spawns, but the dashboard render target fails and the
game crashes a few seconds later.

A 13 MB body file takes about 8 seconds; one car (body, `_hi` and paint) around 15.

---

## 4. Command line

The same engine, for batch work:

```
gtav-asset-repair normals <src> [--out DIR] [--strength 4.5] [--blur 1.2]
gtav-asset-repair lite <ytd…> [--mode cap|tier|agg] [--cap 1024] [--inplace]
gtav-asset-repair mips check <ytd|dds…>
gtav-asset-repair mips fix   <ytd…> [--out DIR | --inplace]
gtav-asset-repair ped check <folder|ydd|ymt…> [--json report.json]
gtav-asset-repair ped fix   <folder…> [--apply]
gtav-asset-repair ytd list  <ytd…> [--legacy]
gtav-asset-repair scale     <dds…> --out DIR --long-edge 1536
gtav-asset-repair audit     <ped.ymt.xml> [--json report.json]
gtav-asset-repair pack      --xml a.ytd.xml --build DIR --out a.ytd
gtav-asset-repair gen8to9   <src> [dst] [--dry-run] [--json]
```

Most commands accept `--json` for machine-readable output. `--work DIR` moves every default output
under one folder, which is handy for scripts.

---

## 5. Backups and rollback

Any command that rewrites a file you own keeps a `.bak` beside it the first time (`foo.ytd` →
`foo.ytd.bak`). An existing `.bak` is never overwritten, so the first backup is the pristine one.

To roll back: delete the rewritten file and rename `foo.ytd.bak` → `foo.ytd`. The GUI also shows this
reminder in the lower left corner, permanently.

---

## 6. Troubleshooting

**`WinError 5` / access denied.** The folder is read-only or the file is locked by another tool
(OpenIV, CodeWalker, a running game). Close the tool, or copy the file somewhere writable. Desktop
root folders are often protected by Windows itself — pick a folder you can write to.

**The exe does nothing when double-clicked.** Either you took the exe out of its folder (unzip again
and keep the structure), or Windows SmartScreen blocked it. Right-click the exe → *More info* →
*Run anyway*, or use the supplied `Run.bat`.

**A converted car crashes the moment it spawns.** Check that the car's `.ytd` was converted too, and
that any `script_rt_*` texture inside it went through a converter that preserves render-target flags.

**Only the brake calipers / steering wheel fly around.** Only the main `.yft` was converted;
`_hi.yft` is still the Legacy file. Convert the whole pack together.

**A ped stays red after "Fix selected".** The repaired `.ymt` did not read back cleanly, so it was
not kept.

**Mip check flags nearly every texture in a mod.** Many mods ship a single mip level. Flagging is
correct; whether to fix them is your call.

**Compression seems too gentle on some files.** Textures under 1024 px, `script_rt_*`, normal maps
and specular maps are skipped on purpose; the report says why for each.

---

## 7. Feedback

Bug reports and questions: <https://github.com/wokken198/gtav-asset-repair/issues>

Please include the file type, the page or command, and the last few lines of the log panel — that is
usually enough to pinpoint it.

MIT licensed. No game assets are included; everything reads from your own install.
