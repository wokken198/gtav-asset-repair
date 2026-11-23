# gtav-asset-repair — user guide

This is the copy of the manual that ships **inside the download**. The README on
GitHub is written for people browsing the source; this one is written for people
who just unzipped the folder and want to get on with modding.

Everything here applies to the portable build: no Python, no install, no admin
rights.

---

## 1. Quick start

1. **Unzip the whole folder.** Do not drag `gtav-asset-repair.exe` out on its own —
   it needs the `_internal` folder that sits next to it.
2. Double-click `gtav-asset-repair.exe`.
3. Optional: point the app at your **CodeWalker** folder (page 2, `Browse` or
   `Detect`). Only the features that read or write archives need it — see the
   table below. If you do not have CodeWalker, the rest still works.

The window remembers language and theme. Both are toggled at the top right.

---

## 2. What runs on what

| Page | What it does | Needs CodeWalker? | Where the result goes |
|---|---|---|---|
| **Normal maps (DDS)** | Builds tangent-space normal maps from badge/emblem `.dds` files | No | `<input folder>\normals\…_n.dds` |
| **Textures (YTD)** — *Analyze* | Reads archive headers and estimates savings | No | report panel only |
| **Textures (YTD)** — *Compress* | Rescales textures inside `.ytd` | **Yes** | `<name>_lite.ytd` next to the source, plus `_lite_report.txt` |
| **Mip check (YTD/DDS)** — *Check* | Reports textures whose mip chain is too short | No | report table |
| **Mip check** — *Fix selected* | Rebuilds the archive with full mip chains | **Yes** | `<name>_fullmips.ytd` (or in place, keeping `.bak`) |
| **Ped repair (YMT)** — *Check* | Compares each `.ymt` with its `.ydd` | **Yes** | report panel |
| **Ped repair** — *Fix selected* | Repairs the `.ymt` of the ticked peds | **Yes** | `.ymt` rewritten, `.bak` kept |

**Why CodeWalker at all?** GTA V archives (`.ytd`) and ped variation files
(`.ymt`) are RSC7 binary containers. CodeWalker is the only maintained library
that writes them correctly. The app does not bundle it — it asks for a copy you
already installed, and it verifies the build can round-trip before touching
anything.

---

## 3. Using the pages

### 3.1 Normal maps

1. `Add files` or `Add folder`.
2. Tune **Strength** (how deep the relief is), **Blur** (how smooth), **Alpha
   weight** (how much the alpha silhouette counts as height). The toolbar `?`
   explains each one and shows the vanilla range.
3. `Generate`.

Output is written next to each source file, in a `normals` subfolder. Existing
normal maps (`*_n.dds`) are skipped so you cannot overwrite your own work by
accident.

### 3.2 Textures (YTD)

1. `Add YTD`.
2. Pick a long-edge limit (1024 / 1536 / 2048).
3. Choose one of the three options:
   - **Option 1 · Snap to tier** — long edge snaps to the nearest tier below.
   - **Option 2 · Ceiling** — anything above the limit is scaled down; smaller
     textures are left alone. This is the safe default.
   - **Option 3 · Reformat** — Ceiling plus format swaps (uncompressed → DXT5,
     opaque DXT5 → DXT1). Smaller files, but **verify in game**.
4. `Analyze` shows what you would save without writing anything. `Compress`
   writes `<name>_lite.ytd` and a short report next to it.

Textures under 1024 px, `script_rt_*` render targets, normal maps and spec maps
are never reformatted — they break if you touch them.

Use **Stop** if you change your mind; files already written stay written.

### 3.3 Mip check

`Check` lists every texture whose mip chain is shorter than it should be. Short
chains shimmer and moiré at distance, and they make the renderer sample a
half-resolution image, which costs more, not less.

Select the rows you want and press `Fix selected`. The filter menu can tick
everything, tick only large problems, or skip hair/alpha.

### 3.4 Ped repair

Add a folder that holds `.ydd` + `.ymt` pairs. `Check` marks every ped green
(drawables and texture counts match) or red (the `.ymt` declares more parts than
the `.ydd` ships). Red rows are ticked automatically; click a row to untick it.
`Fix selected` only touches ticked rows and keeps a `.bak`.

A repaired ped is re-read before the app reports success. If your CodeWalker
build cannot write `.ymt` correctly, the app says so instead of writing a broken
file — pick a newer build.

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
```

Most commands accept `--json` for machine-readable output. `--work DIR` moves
every default output under one folder, which is handy for scripts.

---

## 5. Backups and rollback

Any command that rewrites a file you own keeps a `.bak` beside it the first time
(`foo.ytd` → `foo.ytd.bak`). An existing `.bak` is never overwritten, so the
first backup is the pristine one.

To roll back: delete the rewritten file and rename `foo.ytd.bak` → `foo.ytd`.
The GUI also shows this reminder in the lower left corner, permanently.

---

## 6. Troubleshooting

**`WinError 5` / access denied.**
The folder is read-only, or the file is open in another tool (OpenIV, CodeWalker,
a running game). Close the tool, or copy the folder somewhere writable.

**"not found - pick the CodeWalker folder".**
Only archive-reading features need it. Set the path once on the Textures page;
the other pages reuse it.

**Compression seems too gentle on some files.**
Textures at or below the limit are skipped on purpose, and so are
`script_rt_*`/normal/spec maps. Check the report: skipped rows say why.

**A ped stays red after "Fix selected".**
The app could not confirm the repaired `.ymt` reads back correctly, so it refused
to keep it. Use a newer CodeWalker build.

**Mip check flags nearly every texture in a mod.**
Plenty of mods ship single-mip textures. Flagging them is correct — whether to
fix them is your call (the filter can select only large problems).

**The exe does nothing when double-clicked.**
You moved the exe without `_internal`. Unzip the archive again and keep the
folder structure.

---

## 7. Feedback

Bugs reports and questions: <https://github.com/wokken198/gtav-asset-repair/issues>

Include the file type, the page or command, and the last few lines from the log
panel — that usually pins it down immediately.

MIT licensed. No game assets are included; everything reads from your own
install.
