"""CPedVariationInfo (ped .ymt) consistency audit.

Rules are taken from vanilla ped data, not from documentation:

1. numAvailTex(component) == sum of aTexData entries over that component's drawables
2. compInfos has exactly one entry per (slot, drawable) pair; the key is the
   *slot index inside availComp*, not the position of the component in aComponentData3
3. texId is a race suffix (0 uni, 1 whi, 2 bla, 3 chi, 4 lat, 5 ara, 10 pak)
4. a component listed in availComp but absent from the .ydd is a dangling slot -> author error

Note that tag values are stored as attributes in CodeWalker's XML export:
`<numAvailTex value="11" />`, `<pedXml_compIdx value="0" />`.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

SLOTS = {
    0: "head", 1: "berd", 2: "hair", 3: "uppr", 4: "lowr", 5: "hand",
    6: "feet", 7: "teef", 8: "accs", 9: "task", 10: "decl", 11: "jbib",
}
RACE = {0: "uni", 1: "whi", 2: "bla", 3: "chi", 4: "lat", 5: "ara", 10: "pak", 255: "none"}


def _int(node, tag: str) -> int:
    e = node.find(tag) if node is not None else None
    if e is None:
        return 0
    raw = e.get("value") if e.get("value") is not None else (e.text or "")
    try:
        return int(float(str(raw).strip()))
    except ValueError:
        return 0


def parse_avail(text: str | None) -> list[int]:
    """availComp is either spaced decimals or one hex blob ('00FF010203FF...')."""
    text = (text or "").strip()
    if not text:
        return []
    tokens = text.split()
    if len(tokens) == 1 and len(tokens[0]) > 3 and len(tokens[0]) % 2 == 0:
        blob = tokens[0]
        return [int(blob[i:i + 2], 16) for i in range(0, len(blob), 2)]
    return [int(t) for t in tokens]


@dataclass
class ComponentReport:
    slot: int
    slot_name: str
    comp_index: int
    declared: int
    drawbles: list[dict] = field(default_factory=list)

    @property
    def texture_sum(self) -> int:
        return sum(d["tex"] for d in self.drawbles)


@dataclass
class AuditResult:
    components: list[ComponentReport]
    comp_infos: int
    drawble_total: int
    avail: list[int]
    problems: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems


def audit_xml(path: str) -> AuditResult:
    root = ET.parse(path).getroot()
    avail = parse_avail(root.findtext("availComp"))
    comps = root.find("aComponentData3")
    comp_items = [] if comps is None else comps.findall("Item")
    infos = root.find("compInfos")
    info_items = [] if infos is None else infos.findall("Item")

    problems: list[str] = []
    reports: list[ComponentReport] = []

    for comp_index, comp in enumerate(comp_items):
        slot = next((i for i, v in enumerate(avail) if v == comp_index), -1)
        rep = ComponentReport(slot, SLOTS.get(slot, f"slot{slot}"), comp_index, _int(comp, "numAvailTex"))
        dd = comp.find("aDrawblData3")
        for di, drawble in enumerate([] if dd is None else dd.findall("Item")):
            td = drawble.find("aTexData")
            ids = [] if td is None else [_int(t, "texId") for t in td.findall("Item")]
            rep.drawbles.append({"index": di, "tex": len(ids), "texIds": ids})
            bad = [v for v in ids if v not in RACE]
            if bad:
                problems.append(f"{rep.slot_name}[{di}]: texId {bad} is not a known race suffix")
        if rep.declared != rep.texture_sum:
            problems.append(f"{rep.slot_name}: numAvailTex={rep.declared} but drawable textures sum={rep.texture_sum}")
        reports.append(rep)

    pairs = {(_int(it, "pedXml_compIdx"), _int(it, "pedXml_drawblIdx")) for it in info_items}
    drawble_total = sum(len(r.drawbles) for r in reports)
    for rep in reports:
        for d in rep.drawbles:
            if (rep.slot, d["index"]) not in pairs:
                problems.append(f"compInfos missing entry for slot {rep.slot} drawable {d['index']}")
    if len(info_items) != drawble_total:
        problems.append(f"compInfos has {len(info_items)} entries but there are {drawble_total} drawables")

    return AuditResult(reports, len(info_items), drawble_total, avail, problems)


def format_report(result: AuditResult, name: str = "") -> str:
    lines = []
    if name:
        lines.append(f"file: {name}")
    lines.append(f"components: {len(result.components)}  drawables: {result.drawble_total}  compInfos: {result.comp_infos}")
    lines.append("availComp: " + " ".join(str(v) for v in result.avail))
    lines.append("-" * 68)
    for r in result.components:
        tex = [[RACE.get(v, v) for v in d["texIds"]] for d in r.drawbles]
        lines.append(f"{r.slot_name:<6} comp#{r.comp_index:<3} drawables={len(r.drawbles)} "
                     f"numAvailTex={r.declared} sum={r.texture_sum} texIds={tex}")
    lines.append("-" * 68)
    if result.problems:
        lines.append(f"{len(result.problems)} problem(s):")
        lines += ["  - " + p for p in result.problems]
    else:
        lines.append("no problems found")
    return "\n".join(lines)
