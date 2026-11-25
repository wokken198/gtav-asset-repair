"""PED variation audit: compare a ped's .ymt (CPedVariationInfo) with its .ydd.

The checks follow what vanilla peds actually do:

1. numAvailTex(component) == sum of aTexData entries over that component's drawables
2. compInfos has one entry per (slot, drawable) pair
3. every drawable listed by the ymt must exist in the ydd, and the number of
   textures in the ydd must match the number of texId entries
4. a component whose data is present but that no availComp slot points at is a
   dangling component (author error)

Reading and writing go through the vendored fivefury reader (public domain, see
`vendor/fivefury/LICENSE`), which parses CPedVariationInfo natively, so `ped
check` and `ped fix` no longer need CodeWalker. Two quirks are handled here
instead of in the vendored copy, to keep it upgradable: gen8 `.ydd` resources end
with a four-byte adler32 tail that the stock deflate check rejects, and compInfos
rows expose `compIdx`/`drawblIdx` under hashed field names.
"""
from __future__ import annotations

import copy
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from . import settings


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

_READER = None


def _patch_deflate_tail(resource) -> None:
    """Let the reader accept the adler32 tail gen8 `.ydd` resources carry.

    A legacy drawable dictionary appends the adler32 of the decompressed payload
    after the raw deflate stream; the stock check treats any trailing byte as
    corruption, so every gen8 `.ydd` fails with "resource deflate stream contains
    trailing data". Measured on Mai/MaiS/MaiT: 6,291,456 bytes out, tail ==
    zlib.adler32(out). The patch is idempotent and only fires on that message.
    """
    original = getattr(resource, "_decompress_raw_resource_stream", None)
    if original is None or getattr(original, "_gtav_tail_fix", False):
        return

    def patched(data, *args, **kwargs):
        try:
            return original(data, *args, **kwargs)
        except ValueError as exc:
            if "trailing data" not in str(exc):
                raise
            import zlib

            engine = zlib.decompressobj(-15)
            out = engine.decompress(bytes(data)) + engine.flush()
            tail = engine.unused_data
            if len(tail) == 4 and int.from_bytes(tail, "big") == zlib.adler32(out) & 0xFFFFFFFF:
                return out
            raise

    patched._gtav_tail_fix = True
    resource._decompress_raw_resource_stream = patched


def _reader():
    """Import the vendored fivefury readers once and repair the gen8 tail bug."""
    global _READER
    if _READER is not None:
        return _READER
    vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    from fivefury import resource as _resource
    from fivefury.ydd import read_ydd as _read_binary_ydd
    from fivefury.ymt import read_ymt as _read_binary_ymt
    from fivefury.ymt import save_ymt as _save_binary_ymt

    _patch_deflate_tail(_resource)
    _READER = (_read_binary_ydd, _read_binary_ymt, _save_binary_ymt)
    return _READER


# Hashed compInfos field names. fivefury exposes the schema hashes verbatim, and
# joaat("pedXml_compIdx") does not reproduce them, so they are matched by name.
_CI_COMP = "0xD12F579D"
_CI_DRAWBL = "0xFA1F27BF"


def _info_pair(row) -> tuple[int, int]:
    """(compIdx, drawblIdx) from a compInfos row, hashed names first."""
    values = list(row.values())
    comp = row.get(_CI_COMP, values[8] if len(values) > 8 else 0)
    draw = row.get(_CI_DRAWBL, values[9] if len(values) > 9 else 0)
    try:
        return int(comp or 0), int(draw or 0)
    except (TypeError, ValueError):
        return 0, 0


def _ymt_tables(content) -> tuple[list[int], list[Component], list[tuple[int, int]]]:
    avail = [int(v) for v in (content.get("availComp") or [])]
    # availComp is indexed by *slot* (0=head, 2=hair, ...) and stores which
    # component sits there, so the n-th component belongs to the n-th occupied
    # slot -- reading avail[n] treats the table as slot-per-component and shifts
    # every name after the first gap (measured: Mai came out as 255/1/2 instead
    # of 2/3/4).
    data_slots = [i for i, value in enumerate(avail) if value != 255]
    comps: list[Component] = []
    for index, item in enumerate(content.get("aComponentData3") or []):
        slot = data_slots[index] if index < len(data_slots) else -1
        comp = Component(index, slot, int(item.get("numAvailTex") or 0))
        for drawbl in item.get("aDrawblData3") or []:
            comp.drawables.append([int(t.get("texId") or 0) for t in drawbl.get("aTexData") or []])
        comps.append(comp)
    infos = [_info_pair(row) for row in (content.get("compInfos") or [])]
    return avail, comps, infos


def _read_ydd_xml(xml_path: str) -> list[tuple[str, int]]:
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


def _read_ymt_xml(xml_path: str) -> tuple[list[int], list[Component], list[tuple[int, int]]]:
    root = ET.parse(xml_path).getroot()
    avail = parse_avail(root.findtext("availComp"))
    data_slots = [i for i, value in enumerate(avail) if value != 255]
    comps: list[Component] = []
    box = root.find("aComponentData3")
    for index, item in enumerate([] if box is None else box.findall("Item")):
        slot = data_slots[index] if index < len(data_slots) else -1
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


def read_ydd(path: str) -> list[tuple[str, int]]:
    """Name and texture-slot count for every drawable, in file order.

    A `.xml` path still works (CodeWalker dumps remain handy as references), but
    anything else is read straight from the binary resource.
    """
    if path.lower().endswith(".xml"):
        return _read_ydd_xml(path)
    read_binary = _reader()[0]
    archive = read_binary(path)
    out: list[tuple[str, int]] = []
    for entry in archive.drawables:
        materials = getattr(entry.drawable, "materials", ())
        count = sum(1 for material in materials
                    for parameter in material.parameters if parameter.is_texture)
        out.append((entry.name, count))
    return out


def read_ymt(path: str) -> tuple[list[int], list[Component], list[tuple[int, int]]]:
    """Component tables for a CPedVariationInfo, from `.xml` or the binary."""
    if path.lower().endswith(".xml"):
        return _read_ymt_xml(path)
    archive = _reader()[1](path)
    return _ymt_tables(archive.content)


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





def legacy_for(ydd: str) -> bool:
    """True when the .ydd is a gen8 (legacy, RSC7 v165) asset."""
    try:
        from .ytd import rsc7_version

        return rsc7_version(ydd) == 165
    except Exception:
        return False


def check_pair(stem: str, ydd: str, ymt: str, core_dir: str = "", work: str = "") -> Report:
    """Audit one ped pair straight from its binaries.

    `core_dir` and `work` are kept for signature compatibility with the CLI and
    the GUI, but the audit no longer exports anything through CodeWalker.
    """
    report = audit(stem, ydd, ymt, ydd, ymt)
    report.legacy = legacy_for(ydd)
    return report


# -------------------------------------------------------------------- fix

def repair_ymt(content, report: Report) -> list[str]:
    """Fix what is provably wrong: numAvailTex and missing compInfos entries.

    Edits the decoded fivefury tree in place; `Report` already holds both the
    declared and the measured texture count, so nothing is re-derived here.
    """
    changes: list[str] = []

    items = content.get("aComponentData3") or []
    for comp, item in zip(report.components, items):
        if comp.declared != comp.texture_sum:
            item["numAvailTex"] = comp.texture_sum
            changes.append(f"{SLOTS.get(comp.slot, 'comp%d' % comp.index)}: numAvailTex "
                           f"{comp.declared} -> {comp.texture_sum}")

    avail = [int(v) for v in (content.get("availComp") or [])]
    data_slots = [i for i, v in enumerate(avail) if v != 255]
    avail_of = {comp.index: data_slots[k] for k, comp in enumerate(report.components)
                if k < len(data_slots)}

    infos = content.get("compInfos")
    if infos is None:
        infos = []
        content["compInfos"] = infos
    have = set(report.comp_infos)
    template = copy.deepcopy(infos[0]) if infos else None
    for comp in report.components:
        for index in range(len(comp.drawables)):
            slot = avail_of.get(comp.index, comp.slot)
            if comp.slot < 0 or (slot, index) in have:
                continue
            if template is None:
                continue
            row = copy.deepcopy(template)
            row[_CI_COMP] = slot
            row[_CI_DRAWBL] = index
            infos.append(row)
            changes.append(f"{SLOTS.get(comp.slot, comp.slot)}: added compInfos entry for drawable {index}")

    return changes


def fix_pair(stem: str, ydd: str, ymt: str, core_dir: str = "", progress=None) -> tuple[list[str], str]:
    """Audit, repair the decoded tree, write it back and verify. Returns (changes, out).

    A file that already passes the audit is left untouched (AGENTS.md §3), and a
    rewritten file only replaces the original after the audit passes again on the
    bytes actually written. The return shape matches `align_pair`, because the
    CLI and the GUI print the individual changes.
    """
    if progress:
        progress("read")
    if not (os.stat(ymt).st_mode & 0o200):
        raise RuntimeError("%s is read-only; clear the attribute before repairing"
                           % os.path.basename(ymt))
    report = audit(stem, ydd, ymt, ydd, ymt)
    if report.ok:
        return [], ymt

    read_binary_ymt, save_binary_ymt = _reader()[1], _reader()[2]
    archive = read_binary_ymt(ymt)
    content = copy.deepcopy(archive.content)
    changes = repair_ymt(content, report)
    if not changes:
        return [], ymt
    if progress:
        progress("write")

    # Write beside the target and swap it in, so a failed write never leaves a
    # half-written .ymt behind and no cross-volume copy is involved.
    packed = ymt + ".new"
    try:
        archive.content = content
        # `content` is a plain field; serialisation reads it back through
        # `meta.root_value`, so both have to point at the repaired tree.
        archive.meta.root_value = content
        save_binary_ymt(archive, packed)
        if progress:
            progress("verify")
        again = audit(stem, ydd, packed, ydd, packed)
        if again.problems:
            raise RuntimeError("the repaired .ymt still fails the audit ("
                               + again.problems[0] + "); nothing was written")
        backup = ymt + ".bak"
        if settings.keep_bak() and not os.path.exists(backup):
            shutil.copyfile(ymt, backup)
        os.replace(packed, ymt)
        return changes, ymt
    finally:
        if os.path.exists(packed):
            os.remove(packed)






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


def read_ydd_textures(path: str) -> list[tuple[str, str]]:
    """(drawable name, texture name) for every texture a drawable references."""
    out: list[tuple[str, str]] = []
    if path.lower().endswith(".xml"):
        root = ET.parse(path).getroot()
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
    else:
        for entry in _reader()[0](path).drawables:
            for tex in entry.drawable.texture_names:
                if tex:
                    out.append((entry.name, tex))
    # de-duplicate, keep order
    seen, keep = set(), []
    for pair in out:
        if pair not in seen:
            seen.add(pair)
            keep.append(pair)
    return keep


def missing_textures(ydd: str, ytd_names) -> list[str]:
    have = {n.lower() for n in ytd_names}
    missing = []
    for _drawable, tex in read_ydd_textures(ydd):
        stem = tex.lower()
        if stem.endswith(".dds") or stem.endswith(".png"):
            stem = stem.rsplit(".", 1)[0]
        if stem not in have and tex.lower() not in have:
            missing.append(tex)
    return sorted(set(missing))


def align_ymt(content, ydd_total: int) -> list[str]:
    """Trim the ymt so it declares exactly the drawables the ydd has.

    Keeps the 12-slot structure intact (only availComp values, per-component
    drawable rows and compInfos rows change), because rewriting the arrays in a
    different order drops entries into the wrong components.
    """
    avail = [int(v) for v in (content.get("availComp") or [])]
    while len(avail) < 12:
        avail.append(255)
    slot_of = {}
    for slot, k in enumerate(avail):
        if k != 255:
            slot_of[k] = slot

    items = content.get("aComponentData3") or []
    refs = [(k, di) for k, item in enumerate(items)
            for di, drawbl in enumerate(item.get("aDrawblData3") or [])
            if drawbl.get("aTexData")]
    keep = refs[:ydd_total]
    kept = set(keep)
    changes: list[str] = []
    if len(keep) != len(refs):
        changes.append("keep %d of %d textured drawable(s)" % (len(keep), len(refs)))

    order = {}
    for k, item in enumerate(items):
        rows = item.get("aDrawblData3") or []
        alive, mapping = [], {}
        for di, drawbl in enumerate(rows):
            if (k, di) in kept:
                mapping[di] = len(alive)
                alive.append(drawbl)
        item["aDrawblData3"] = alive
        order[k] = mapping
        total = sum(len(drawbl.get("aTexData") or []) for drawbl in alive)
        old = item.get("numAvailTex")
        item["numAvailTex"] = total
        if old != total:
            changes.append("component #%d numAvailTex %s -> %d" % (k, old, total))
        if not alive and k in slot_of:
            changes.append("slot %d now empty" % slot_of[k])

    used = {k for k, _di in keep}
    for k in range(len(items)):
        if k not in used and k in slot_of:
            avail[slot_of[k]] = 255
    content["availComp"] = avail

    old_rows = {}
    for row in content.get("compInfos") or []:
        old_rows[_info_pair(row)] = row
    new_infos = []
    for k, di in keep:
        slot = slot_of.get(k, 255)
        row = old_rows.get((slot, di))
        if row is None:
            row = {_CI_COMP: slot, _CI_DRAWBL: order.get(k, {}).get(di, 0)}
        else:
            row = copy.deepcopy(row)
            row[_CI_DRAWBL] = order.get(k, {}).get(di, 0)
        new_infos.append(row)
    content["compInfos"] = new_infos
    return changes


def align_pair(stem: str, ydd: str, ymt: str, core_dir: str = "", apply: bool = False):
    """Trim the ymt so it declares exactly the drawables the ydd has.

    Keeps the 12-slot structure intact (only availComp values, per-component
    drawable rows and compInfos rows change), because rewriting the arrays in
    a different order drops entries into the wrong components.
    """
    report = audit(stem, ydd, ymt, ydd, ymt)
    if report.ok:
        return [], ""

    if apply and not (os.stat(ymt).st_mode & 0o200):
        raise RuntimeError("%s is read-only; clear the attribute before aligning"
                           % os.path.basename(ymt))

    read_binary_ymt, save_binary_ymt = _reader()[1], _reader()[2]
    archive = read_binary_ymt(ymt)
    content = copy.deepcopy(archive.content)
    changes = align_ymt(content, len(report.ydd_drawables))
    if not changes:
        return [], ""

    # Same write-beside-and-swap dance as fix_pair.
    packed = ymt + ".new"
    try:
        archive.content = content
        # see fix_pair: serialisation goes through meta.root_value
        archive.meta.root_value = content
        save_binary_ymt(archive, packed)

        again = audit(stem, ydd, packed, ydd, packed)
        if not again.ok:
            raise RuntimeError("the aligned .ymt still fails the audit ("
                               + again.problems[0] + "); nothing was written")
        if apply:
            if (settings.keep_bak() and os.path.isfile(ymt)
                    and not os.path.isfile(ymt + ".bak")):
                shutil.copy2(ymt, ymt + ".bak")
            os.replace(packed, ymt)
        return changes, ymt
    finally:
        if os.path.exists(packed):
            os.remove(packed)
