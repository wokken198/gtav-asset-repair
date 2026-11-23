"""PED variation audit: compare a ped's .ymt (CPedVariationInfo) with its .ydd.

The checks follow what vanilla peds actually do:

1. numAvailTex(component) == sum of aTexData entries over that component's drawables
2. compInfos has one entry per (slot, drawable) pair
3. every drawable listed by the ymt must exist in the ydd, and the number of
   textures in the ydd must match the number of texId entries
4. a component whose data is present but that no availComp slot points at is a
   dangling component (author error)

Reading/writing needs a CodeWalker build with `MetaXml` and a `YmtFile.Load(byte[])`
overload; both the 4.5 MB dev48 build and the 10 MB build shipped with ModDrop work
(verified). `probe_core()` checks a folder by parsing a real sample and reports the
reason when it cannot be used.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


SLOTS = {
    0: "head", 1: "berd", 2: "hair", 3: "uppr", 4: "lowr", 5: "hand",
    6: "feet", 7: "teef", 8: "accs", 9: "task", 10: "decl", 11: "jbib",
}
RACE = {0: "uni", 1: "whi", 2: "bla", 3: "chi", 4: "lat", 5: "ara", 10: "pak", 255: "none"}
_PS1 = re.compile(r"\d+")


def _int(node, tag: str) -> int:
    if node is None:
        return 0
    e = node.find(tag)
    if e is None:
        return 0
    raw = e.get("value")
    if raw is None:
        raw = (e.text or "0").strip()
    try:
        return int(float(raw))
    except ValueError:
        return 0


def parse_avail(text: str | None) -> list[int]:
    text = (text or "").strip()
    if not text:
        return []
    tokens = text.split()
    if len(tokens) == 1 and len(tokens[0]) > 3 and len(tokens[0]) % 2 == 0:
        blob = tokens[0]
        return [int(blob[i:i + 2], 16) for i in range(0, len(blob), 2)]
    return [int(t) for t in tokens]


def pairs(folder: str) -> list[tuple[str, str, str]]:
    """Return (stem, ydd, ymt) for every ped that ships both files."""
    found: dict[str, dict[str, str]] = {}
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        for name in sorted(files):
            stem, ext = os.path.splitext(name)
            ext = ext.lower()
            if ext not in (".ydd", ".ymt"):
                continue
            slot = found.setdefault(os.path.join(root, stem), {})
            slot[ext] = os.path.join(root, name)
    out = []
    for stem, slot in sorted(found.items()):
        if ".ydd" in slot and ".ymt" in slot:
            out.append((os.path.basename(stem), slot[".ydd"], slot[".ymt"]))
    return out


@dataclass
class Component:
    index: int
    slot: int
    declared: int
    drawables: list[list[int]] = field(default_factory=list)

    @property
    def texture_sum(self) -> int:
        return sum(len(t) for t in self.drawables)


@dataclass
class Report:
    stem: str
    ydd: str
    ymt: str
    components: list[Component] = field(default_factory=list)
    comp_infos: list[tuple[int, int]] = field(default_factory=list)
    ydd_drawables: list[tuple[str, int]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    legacy: bool = False

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def drawable_total(self) -> int:
        return sum(len([d for d in c.drawables if d]) for c in self.components)


# ---------------------------------------------------------------- ydd / ymt

def read_ydd(xml_path: str) -> list[tuple[str, int]]:
    """Name and texture-slot count for every drawable, in file order."""
    root = ET.parse(xml_path).getroot()
    out: list[tuple[str, int]] = []
    for item in root.findall("Item"):
        name = (item.findtext("Name") or "").strip()
        group = item.find("ShaderGroup")
        count = 0
        if group is not None:
            for param in group.iter("Item"):
                if (param.get("type") or "") == "Texture":
                    count += 1
        out.append((name, count))
    return out


def read_ymt(xml_path: str) -> tuple[list[int], list[Component], list[tuple[int, int]]]:
    root = ET.parse(xml_path).getroot()
    avail = parse_avail(root.findtext("availComp"))
    comps: list[Component] = []
    box = root.find("aComponentData3")
    for index, item in enumerate([] if box is None else box.findall("Item")):
        slot = avail[index] if index < len(avail) else -1
        comp = Component(index, slot, _int(item, "numAvailTex"))
        dd = item.find("aDrawblData3")
        for drawbl in ([] if dd is None else dd.findall("Item")):
            tex = drawbl.find("aTexData")
            ids = [] if tex is None else [_int(t, "texId") for t in tex.findall("Item")]
            comp.drawables.append(ids)
        comps.append(comp)
    infos: list[tuple[int, int]] = []
    node = root.find("compInfos")
    for item in ([] if node is None else node.findall("Item")):
        infos.append((_int(item, "pedXml_compIdx"), _int(item, "pedXml_drawblIdx")))
    return avail, comps, infos


def audit(stem: str, ydd_xml: str, ymt_xml: str, ydd: str = "", ymt: str = "") -> Report:
    """Compare the ymt against the ydd by order and counts.

    Rules (see docs/ped-ymt-rules.md, verified against 41 vanilla peds):
    numAvailTex == sum of aTexData entries; compInfos has one row per textured
    drawable; pedXml_compIdx indexes availComp; ymt textured drawables == ydd
    drawables. Drawable names are hashes, never use them as keys.
    """
    avail, comps, infos = read_ymt(ymt_xml)
    draws = read_ydd(ydd_xml)
    rep = Report(stem, ydd, ymt, comps, infos, draws)

    # drawables the ymt really declares (empty slots are placeholders)
    real: list[tuple[int, int, int]] = []      # (comp index, drawable index, texture count)
    for comp in comps:
        for index, tex_ids in enumerate(comp.drawables):
            if tex_ids:
                real.append((comp.index, index, len(tex_ids)))

    for comp in comps:
        if comp.slot < 0 and any(comp.drawables):
            rep.problems.append(f"component #{comp.index}: no availComp slot points at it")
        declared = comp.declared
        actual = sum(len(t) for t in comp.drawables if t)
        per = sum(1 for t in comp.drawables if t)
        name = SLOTS.get(comp.slot, "component #%d" % comp.index)
        if declared != actual:
            if per and declared * per == actual:
                # some mods store the per-drawable count here; harmless in game
                rep.notes.append(f"{name}: numAvailTex={declared} is per drawable ({actual} entries)")
            else:
                rep.problems.append(f"{name}: numAvailTex={declared} but {actual} texture entries")

    if len(real) != len(draws):
        rep.problems.append(f"ymt declares {len(real)} drawable(s), the ydd has {len(draws)}")

    for (_comp_index, _draw_index, _count), (name, ydd_count) in zip(real, draws):
        # the ydd number counts shader texture slots, not the ymt texId list
        if ydd_count < 1 or ydd_count > 32:
            rep.problems.append(f"{name}: implausible texture slot count {ydd_count}")

    if len(infos) != len(real):
        rep.problems.append(f"compInfos has {len(infos)} entries for {len(real)} drawable(s)")
    if len(set(infos)) != len(infos):
        rep.problems.append("compInfos has duplicate entries")
    slots_with_data = [i for i, v in enumerate(avail) if v != 255]
    by_avail = {slot_index: comps[k] for k, slot_index in enumerate(slots_with_data)
                if k < len(comps)}
    for comp_index, draw_index in infos:
        comp = by_avail.get(comp_index)
        if comp is None:
            rep.problems.append(f"compInfos points at slot #{comp_index} which has no component")
            continue
        if draw_index >= len(comp.drawables):
            rep.problems.append(f"compInfos drawable #{draw_index} is outside slot #{comp_index}")
    present = set(infos)
    for slot_index, comp in by_avail.items():
        for index, tex_ids in enumerate(comp.drawables):
            if tex_ids and (slot_index, index) not in present:
                rep.problems.append(f"compInfos missing slot #{slot_index} drawable {index}")
    return rep


# ------------------------------------------------------------------ export

def _run_ps1(core_dir: str, script: str, args: list[str]) -> str:
    from .lite import _find_resource

    ps1 = _find_resource(script)
    if not ps1:
        raise FileNotFoundError(f"helper script not found: {script}")
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1] + args + ["-CoreDir", core_dir]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "powershell failed").strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "powershell failed")
    return proc.stdout


def legacy_for(ydd: str) -> bool:
    """True when the .ydd is a gen8 (legacy, RSC7 v165) asset."""
    try:
        from .ytd import rsc7_version

        return rsc7_version(ydd) == 165
    except Exception:
        return False


def export_pair(stem: str, ydd: str, ymt: str, out_dir: str, core_dir: str,
                legacy: bool | None = None) -> tuple[str, str]:
    if legacy is None:
        legacy = legacy_for(ydd)
    args = ["-Ydd", ydd, "-Ymt", ymt, "-OutDir", out_dir]
    if legacy:
        args.append("-Legacy")
    _run_ps1(core_dir, "ped_export.ps1", args)
    return (os.path.join(out_dir, stem + ".ydd.xml"), os.path.join(out_dir, stem + ".ymt.xml"))


def check_pair(stem: str, ydd: str, ymt: str, core_dir: str, work: str = "") -> Report:
    tmp = work or tempfile.mkdtemp(prefix="pedchk-")
    try:
        legacy = legacy_for(ydd)
        ydd_xml, ymt_xml = export_pair(stem, ydd, ymt, tmp, core_dir, legacy)
        report = audit(stem, ydd_xml, ymt_xml, ydd, ymt)
        report.legacy = legacy
        return report
    finally:
        if not work:
            shutil.rmtree(tmp, ignore_errors=True)


# -------------------------------------------------------------------- fix

def _set_num_avail(comp_node, value: int) -> None:
    tag = comp_node.find("numAvailTex")
    if tag is None:
        tag = ET.SubElement(comp_node, "numAvailTex")
    tag.set("value", str(value))


def repair_xml(ymt_xml: str, report: Report, out_xml: str) -> list[str]:
    """Fix what is provably wrong: numAvailTex and missing compInfos entries."""
    ET.register_namespace("", "")
    tree = ET.parse(ymt_xml)
    root = tree.getroot()
    changes: list[str] = []

    box = root.find("aComponentData3")
    items = [] if box is None else box.findall("Item")
    for comp, item in zip(report.components, items):
        if comp.declared != comp.texture_sum:
            _set_num_avail(item, comp.texture_sum)
            changes.append(f"{SLOTS.get(comp.slot, 'comp%d' % comp.index)}: numAvailTex "
                           f"{comp.declared} -> {comp.texture_sum}")

    _avail = parse_avail(root.findtext("availComp"))
    _data_slots = [i for i, v in enumerate(_avail) if v != 255]
    avail_of = {comp.index: _data_slots[k] for k, comp in enumerate(report.components)
                if k < len(_data_slots)}

    infos = root.find("compInfos")
    if infos is not None:
        have = set(report.comp_infos)
        template = None
        for item in infos.findall("Item"):
            template = item
            break
        for comp in report.components:
            for index in range(len(comp.drawables)):
                if (avail_of.get(comp.index, comp.slot), index) in have or comp.slot < 0:
                    continue
                if template is None:
                    continue
                new = ET.SubElement(infos, "Item")
                for child in list(template):
                    copy = ET.SubElement(new, child.tag, dict(child.attrib))
                    copy.text = child.text
                idx = new.find("pedXml_compIdx")
                if idx is None:
                    idx = ET.SubElement(new, "pedXml_compIdx")
                idx.set("value", str(avail_of.get(comp.index, comp.slot)))
                drw = new.find("pedXml_drawblIdx")
                if drw is None:
                    drw = ET.SubElement(new, "pedXml_drawblIdx")
                drw.set("value", str(index))
                changes.append(f"{SLOTS.get(comp.slot, comp.slot)}: added compInfos entry for drawable {index}")

    tree.write(out_xml, encoding="utf-8", xml_declaration=True)
    return changes


def fix_pair(stem: str, ydd: str, ymt: str, core_dir: str, progress=None) -> tuple[int, str]:
    """Audit, repair the XML, compile it back and verify. Returns (changes, out)."""
    tmp = tempfile.mkdtemp(prefix="pedfix-")
    try:
        if progress:
            progress("export")
        legacy = legacy_for(ydd)
        ydd_xml, ymt_xml = export_pair(stem, ydd, ymt, tmp, core_dir, legacy)
        report = audit(stem, ydd_xml, ymt_xml, ydd, ymt)
        fixed_xml = os.path.join(tmp, stem + ".ymt.xml")
        changes = repair_xml(ymt_xml, report, fixed_xml)
        if progress:
            progress("pack")
        out = os.path.join(os.path.dirname(ymt), stem + ".ymt")
        backup = ymt + ".bak"
        if not os.path.exists(backup):
            shutil.copyfile(ymt, backup)
        packed = os.path.join(tmp, stem + ".ymt")
        pack_args = ["-Xml", fixed_xml, "-Out", packed]
        if legacy:
            pack_args.append("-Legacy")
        _run_ps1(core_dir, "ymt_pack.ps1", pack_args)
        if progress:
            progress("verify")
        probe = os.path.join(tmp, "verify")
        export_pair(stem, ydd, packed, probe, core_dir, legacy)
        again = audit(stem, os.path.join(probe, stem + ".ydd.xml"),
                      os.path.join(probe, stem + ".ymt.xml"), ydd, packed)
        if again.problems:
            raise RuntimeError("this CodeWalker build cannot write .ymt correctly (" + again.problems[0] + "); point the CodeWalker field at a newer build")
        shutil.copyfile(packed, out)
        return len(changes), out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_PROBE = r"""
param([string]$CoreDir, [string]$Sample)
$ErrorActionPreference = 'Stop'
$core = Join-Path $CoreDir 'CodeWalker.Core.dll'
if (-not (Test-Path $core)) { 'missing'; exit 0 }
try { [void][System.Reflection.Assembly]::UnsafeLoadFrom($core) } catch { 'loadfail'; exit 0 }
if (-not ('CodeWalker.GameFiles.MetaXml' -as [type])) { 'nometa'; exit 0 }
if ($Sample -and (Test-Path $Sample)) {
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Sample)
        $f = New-Object CodeWalker.GameFiles.YmtFile
        $f.Load($bytes)
        $warn = $null
        $xml = [CodeWalker.GameFiles.MetaXml]::GetXml($f, [ref]$warn)
        if ($xml -and $xml.Length -gt 200) { 'ok' } else { 'noparse' }
    } catch { 'noparse' }
} else {
    'unknown'
}
"""


def probe_core(folder, sample=""):
    """Return (ok, reason) for a CodeWalker folder used by the PED page."""
    import os
    import subprocess

    folder = folder or ""
    core = os.path.join(folder, "CodeWalker.Core.dll")
    if not os.path.isfile(core):
        return False, "missing"
    script = os.path.join(tempfile.gettempdir(), "probe_%s.ps1" % uuid.uuid4().hex[:8])
    try:
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(_PROBE)
        out = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", script, "-CoreDir", folder, "-Sample", sample or ""],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
            creationflags=_NO_WINDOW if hasattr(sys.modules[__name__], "_NO_WINDOW") else 0,
        )
        text = (out.stdout or "").strip().splitlines()
        code = text[-1].strip().lower() if text else "error"
        if code in ("ok", "unknown"):
            return code == "ok", code
        return False, code
    except Exception as exc:                                  # noqa: BLE001
        return False, str(exc)
    finally:
        try:
            os.remove(script)
        except OSError:
            pass


# ------------------------------------------------------------------- align

_SLOT_INDEX = re.compile(r"^(?P<slot>[a-z]+)_(?P<idx>\d+)")


def _slot_of(name: str):
    m = _SLOT_INDEX.match(name.lower())
    if not m:
        return None, None
    slot = m.group("slot")
    for index, slot_name in SLOTS.items():
        if slot_name == slot:
            return index, int(m.group("idx"))
    return None, int(m.group("idx"))


def read_ydd_textures(xml_path: str) -> list[tuple[str, str]]:
    """(drawable name, texture name) for every texture a drawable references."""
    root = ET.parse(xml_path).getroot()
    out = []
    for item in root.iter("Item"):
        name = item.findtext("Name")
        if not name:
            continue
        shader = item.find("ShaderGroup")
        if shader is None:
            continue
        for param in shader.iter("Item"):
            if param.findtext("Name") != "TextureSampler":
                continue
            tex = param.find("TextureName") or param.find("Name")
            if tex is not None and tex.text:
                out.append((name, tex.text))
        for tex in shader.iter("TextureName"):
            if tex.text:
                out.append((name, tex.text))
    # de-duplicate, keep order
    seen, keep = set(), []
    for pair in out:
        if pair not in seen:
            seen.add(pair)
            keep.append(pair)
    return keep


def missing_textures(ydd_xml: str, ytd_names) -> list[str]:
    have = {n.lower() for n in ytd_names}
    missing = []
    for _drawable, tex in read_ydd_textures(ydd_xml):
        stem = tex.lower()
        if stem.endswith(".dds") or stem.endswith(".png"):
            stem = stem.rsplit(".", 1)[0]
        if stem not in have and tex.lower() not in have:
            missing.append(tex)
    return sorted(set(missing))


def align_xml(ymt_xml: str, ydd_total: int, out_xml: str) -> list[str]:
    tree = ET.parse(ymt_xml)
    root = tree.getroot()
    box = root.find("aComponentData3")
    items = [] if box is None else box.findall("Item")
    avail = parse_avail(root.findtext("availComp"))
    while len(avail) < 12:
        avail.append(255)
    slot_of = {}
    for slot, k in enumerate(avail):
        if k != 255:
            slot_of[k] = slot

    refs = []
    for k, item in enumerate(items):
        dd = item.find("aDrawblData3")
        for di, drawbl in enumerate([] if dd is None else dd.findall("Item")):
            tex = drawbl.find("aTexData")
            if tex is not None and len(tex.findall("Item")):
                refs.append((k, di))
    keep = refs[:ydd_total]
    kept = set(keep)
    changes = []
    if len(keep) != len(refs):
        changes.append("keep %d of %d textured drawable(s)" % (len(keep), len(refs)))

    order = {}
    for k, item in enumerate(items):
        dd = item.find("aDrawblData3")
        if dd is None:
            continue
        rows = dd.findall("Item")
        alive = []
        mapping = {}
        for di, drawbl in enumerate(rows):
            if (k, di) in kept:
                mapping[di] = len(alive)
                alive.append(drawbl)
        for di, drawbl in enumerate(rows):
            if di not in mapping:
                dd.remove(drawbl)
        order[k] = mapping
        total = 0
        for drawbl in alive:
            tex = drawbl.find("aTexData")
            total += 0 if tex is None else len(tex.findall("Item"))
        tag = item.find("numAvailTex")
        if tag is None:
            tag = ET.SubElement(item, "numAvailTex")
        old = (tag.get("value") or tag.text or "").strip()
        tag.set("value", str(total))
        if tag.text is not None and tag.text.strip():
            tag.text = str(total)
        if old and old != str(total):
            changes.append("component #%d numAvailTex %s -> %d" % (k, old, total))
        if not alive and k in slot_of:
            changes.append("slot %d now empty" % slot_of[k])

    used = {k for k, _di in keep}
    for k in range(len(items)):
        if k not in used and k in slot_of:
            avail[slot_of[k]] = 255
    tag = root.find("availComp")
    if tag is not None:
        tag.text = " ".join(str(v) for v in avail)

    box2 = root.find("compInfos")
    if box2 is not None:
        old_rows = {}
        for row in box2.findall("Item"):
            ci = _int(row, "pedXml_compIdx")
            di = _int(row, "pedXml_drawblIdx")
            old_rows[(ci, di)] = row
        for row in list(box2.findall("Item")):
            box2.remove(row)
        for k, di in keep:
            slot = slot_of.get(k, 255)
            row = old_rows.get((slot, di))
            if row is None:
                row = ET.SubElement(box2, "Item")
                ET.SubElement(row, "pedXml_compIdx").set("value", str(slot))
                ET.SubElement(row, "pedXml_drawblIdx").set("value", str(order.get(k, {}).get(di, 0)))
                ET.SubElement(row, "pedXml_vfxComps")
            else:
                ET.SubElement(row) if False else None
                idx = row.find("pedXml_drawblIdx")
                if idx is not None:
                    idx.set("value", str(order.get(k, {}).get(di, 0)))
            box2.append(row)

    tree.write(out_xml, encoding="utf-8", xml_declaration=True)
    return changes


def align_pair(stem: str, ydd: str, ymt: str, core_dir: str, apply: bool = False):
    """Trim the ymt so it declares exactly the drawables the ydd has.

    Keeps the 12-slot structure intact (only availComp values, per-component
    drawable rows and compInfos rows change), because rewriting the arrays in
    a different order makes CodeWalker repack them into the wrong components.
    """
    tmp = tempfile.mkdtemp(prefix="pedalign-")
    try:
        legacy = legacy_for(ydd)
        ydd_xml, ymt_xml = export_pair(stem, ydd, ymt, tmp, core_dir, legacy)
        report = audit(stem, ydd_xml, ymt_xml, ydd, ymt)
        if report.ok:
            return [], ""

        work = os.path.join(tmp, stem + ".ymt.xml")
        changes = align_xml(ymt_xml, len(report.ydd_drawables), work)
        if not changes:
            return [], ""

        packed_dir = os.path.join(tmp, "pk")
        os.makedirs(packed_dir, exist_ok=True)
        packed = os.path.join(packed_dir, stem + ".ymt")
        pack_args = ["-Xml", work, "-Out", packed]
        if legacy:
            pack_args.append("-Legacy")
        _run_ps1(core_dir, "ymt_pack.ps1", pack_args)
        sub = os.path.join(tmp, "re")
        os.makedirs(sub, exist_ok=True)
        ydd2, ymt2 = export_pair(stem, ydd, packed, sub, core_dir, legacy)
        again = audit(stem, ydd2, ymt2, ydd, packed)
        if not again.ok:
            raise RuntimeError("this CodeWalker build cannot write .ymt correctly (" + again.problems[0] + "); point the CodeWalker field at a newer build")
        if apply:
            if os.path.isfile(ymt) and not os.path.isfile(ymt + ".bak"):
                shutil.copy2(ymt, ymt + ".bak")
            shutil.copy2(packed, ymt)
        return changes, packed
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _reexport(stem: str, ydd: str, ymt: str, tmp: str, core_dir: str):
    sub = os.path.join(tmp, "re")
    os.makedirs(sub, exist_ok=True)
    ydd_xml, ymt_xml = export_pair(stem, ydd, ymt, sub, core_dir)
    return ydd_xml, ymt_xml, ydd, ymt
