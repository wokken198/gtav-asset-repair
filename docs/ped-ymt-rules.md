# ped ymt / ydd rules

Derived from 41 vanilla peds (`a_f_y_*`, `a_m_y_*`) exported with CodeWalker.
Use this file as the source of truth for `src/gtatools/ped.py`.

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

## Baseline check

```
python - <<'PY'
# see _t_van_scan.py in the workspace: audits every *.ydd/*.ymt pair in a folder
PY
```

Current baseline: 41/41 vanilla peds pass, 24/35 user mod peds pass (the 11 failures all
report "ymt declares N drawables, the ydd has M").
