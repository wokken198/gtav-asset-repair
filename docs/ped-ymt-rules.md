# ped ymt / ydd rules

Derived from 41 vanilla peds (`a_f_y_*`, `a_m_y_*`) exported with CodeWalker.
Use this file as the source of truth for `src/gtav_asset_repair/ped.py`.

## Where the fields live

```xml
<CPedVariationInfo>
  <availComp>0 255 1 2 3 255 255 255 4 255 255 255</availComp>   <!-- 12 entries -->
  <aComponentData3>
    <Item>
      <numAvailTex value="4" />
      <aDrawblData3>
        <Item>
          <propMask value="0" />
          <numAlternatives value="1" />
          <aTexData>
            <Item><texId value="1" /><distribution value="255" /></Item>
            <Item><texId value="2" /><distribution value="255" /></Item>
          </aTexData>
          <clothData>…</clothData>
        </Item>
      </aDrawblData3>
    </Item>
  </aComponentData3>
  <compInfos>
    <Item>
      <pedXml_compIdx value="0" />      <!-- index into availComp, NOT list position -->
      <pedXml_drawblIdx value="0" />    <!-- index inside that component's aDrawblData3 -->
      <pedXml_vfxComps>PV_COMP_HEAD</pedXml_vfxComps>
      …
    </Item>
  </compInfos>
</CPedVariationInfo>
```

## The four invariants

1. `numAvailTex` of a component == sum of `len(aTexData)` over that component's drawables.
2. `len(compInfos)` == number of drawables that actually carry textures.
3. Every `(pedXml_compIdx, pedXml_drawblIdx)` points at a real drawable, no duplicates.
   `compIdx` is the **availComp index** (0..11); the component objects are only the
   non-255 entries of `availComp`, in order.
4. Number of textured drawables in the ymt == number of drawables in the ydd.

## Traps that cost a day each

- `aTexData` length (2, 6) is **not** the ydd drawable texture count (10, 15): the ydd
  number is the shader parameter count. Comparing them marks every vanilla ped broken.
- Drawable names are hashes. CodeWalker prints `hash_976FBF04` when it cannot resolve
  (976FBF04 = head_000, 4BD0197A = hair, A1286BE2 = head_001); mods may use arbitrary
  names such as `Yukino_THICC` and may repeat them. Never match by name.
- `availComp` maps slot index -> ped component id (0 head, 1 berd, 2 hair, 3 uppr, …),
  `255` means "no component here"; `aComponentData3` lists only the non-255 slots.
- Dangling component (`availComp = 255` but the component still has drawables) is not
  vanilla and makes random-outfit menus read a null pointer.
- Read `availComp` **slot -> component**, never the other way. The n-th entry of
  `aComponentData3` sits in the n-th *occupied* slot (`[0,255,1,2,3,…]` -> slots 0,2,3,4),
  not in `availComp[n]`. Getting this backwards shifts every name after the first gap
  (Mai came out as 255/1/2 instead of 2/3/4) and still passes every count check, because
  the counts never look at the slot — only the reported component name is wrong.
- `texId` in `aTexData` is a **variant selector**, not a texture-slot index: one drawable
  can carry several skin variants (e.g. `[1,1,1,2,2,2]` = three white-skin maps, then three
  black-skin maps). Measured over 59 peds (41 vanilla + 18 add-on): the value is always in
  `{0,1,2,3,4,10}`, and `distribution` is 255 in 1072 of 1080 rows, so *it* is not the
  selector. Which value maps to which suffix (`0=uni 1=whi 2=bla 3=chi 4=lat 10=pak`) comes
  from community docs and is **not verified entry by entry** — ydd drawable order and the
  ymt `aComponentData3` order do not line up, so pairing them positionally fails. Do not
  add a hard whitelist check on this: it would fire zero times on vanilla and would turn a
  harmless unknown value into a `ped check` failure that `ped fix` cannot repair. The
  repair path never rewrites `texId` anyway.
- "This ped ships N outfits" is **not** `aSelectionSets`/`numAlternatives` — those are 0 and
  empty in all 59 samples. It is simply the number of entries in that component's
  `aDrawblData3` (Kasumi's 16 extra heads are 17 entries under slot 0).

## Baseline check

```
python - <<'PY'
# see _t_van_scan.py in the workspace: audits every *.ydd/*.ymt pair in a folder
PY
```

Current baseline: 41/41 vanilla peds pass, 24/35 user mod peds pass (the 11 failures all
report "ymt declares N drawables, the ydd has M").

## Which CodeWalker build (legacy note)

`ped check`, `ped fix` and `ped align` no longer touch CodeWalker: they parse and
re-write CPedVariationInfo through the vendored fivefury reader
(`src/gtav_asset_repair/vendor/fivefury/`, public domain). Only `pack` still needs
`CodeWalker.Core.dll`.

This section is kept because it is the reason for that move, and because the same
trap returns the moment anyone reintroduces an XML round trip. Verified 2026-11-24
against `素材不要动/ped_gen9/HarleySS` (same result on the gen8 sample):

| Build | Read | Write |
|---|---|---|
| `CodeWalker30_dev48` (4.5 MB, 2026-03-18) | ok | **corrupts** — 4 components / 7 drawables / compInfos 7 come back as 9 / 18 / 15, and the re-exported XML grows 7172 → 15070 chars |
| the 10 MB build bundled inside ModDrop (2026-10-26) | ok | byte-identical round trip |

A corrupted pack was caught, not shipped: `fix_pair()`'s verify step re-exported the
packed file and `audit()` reported e.g. `compInfos has 15 entries for 7 drawable(s)`.
The binary path has no such window — the repaired tree is written by the same library
that parsed it, and the bytes are audited again before the original is replaced, with
the previous file kept as `<name>.bak`.

`probe_core(folder, sample_ymt)` is still available for the `pack` path: it runs
parse → compile → parse and returns `badwrite` for a build that cannot write; "can
read" no longer counts as usable. `cw.py` accepts any folder that ships
`CodeWalker.Core.dll` (not only ones named "CodeWalker", so a bundling app such as
ModDrop is found) and prefers the newest build by DLL mtime.
