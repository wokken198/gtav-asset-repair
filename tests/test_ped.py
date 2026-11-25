"""Rules for `ped.audit` / `repair_ymt` / `align_ymt`, without touching a file.

The repair path used to be exercised only by hand against real ped folders, which
meant a broken invariant could ship as long as nobody re-ran the samples. These
tests build the decoded tables in memory instead: same shapes fivefury returns
(`availComp`, `aComponentData3`, `compInfos`), no binary fixture, no CodeWalker.

The four invariants come from `docs/ped-ymt-rules.md`. If a rule changes there,
one of these tests has to change with it -- that is the point.
"""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from gtav_asset_repair import ped  # noqa: E402

COMP = ped._CI_COMP      # "0xD12F579D" -> pedXml_compIdx
DRAWBL = ped._CI_DRAWBL  # "0xFA1F27BF" -> pedXml_drawblIdx

# what fivefury hands back for a healthy 4-component ped (shape of Mai / HarleySS)
HEALTHY_AVAIL = [0, 255, 1, 2, 3, 255, 255, 255, 255, 255, 255, 255]
HEALTHY_DRAWS = [
    ("hash_976FBF04", 10), ("hash_4BD0197A", 10),
    ("hash_A1286BE2", 10), ("hash_5C6D1E77", 10),
    ("hash_C0B2F1E4", 10), (".hash_7F3A9D21", 10), ("hash_2E8B44C0", 10),
]


def _tex(n=1):
    return [{"texId": 0, "distribution": 255, "_meta_name": "CPVTextureData"}
            for _ in range(n)]


def _drawbl(n=1, mask=17):
    return {"propMask": mask, "numAlternatives": 0, "aTexData": _tex(n),
            "clothData": {"ownsCloth": False}}


def _component(draws, declared=None):
    """`draws` is the texture count of each drawable in this component."""
    rows = [_drawbl(n) for n in draws]
    total = sum(draws)
    return {"numAvailTex": total if declared is None else declared,
            "aDrawblData3": rows}


def _info_row(slot, drawbl):
    return {COMP: slot, DRAWBL: drawbl, "flags": 0,
            "pedXml_audioID": 493038497, "pedXml_audioID2": 493038497,
            "pedXml_expressionMods": [0, 0, 0, 0, 0],
            "inclusions": [], "exclusions": [], "pedXml_vfxComps": [],
            "pedXml_flags": 0, "_meta_name_hash": 0, "_meta_name": "0x6F419FC9"}


def _content(avail, comps, info_rows):
    return {"availComp": list(avail),
            "aComponentData3": comps,
            "compInfos": [_info_row(s, d) for s, d in info_rows],
            "propInfo": {"numAvailProps": 0},
            "bHasTexVariations": True,
            "dlcName": ""}


def healthy():
    comps = [_component([3]), _component([1, 1]), _component([3, 3]),
             _component([3, 3])]
    rows = [(0, 0), (2, 0), (2, 1), (3, 0), (3, 1), (4, 0), (4, 1)]
    return _content(HEALTHY_AVAIL, comps, rows)


def audit(content, draws=HEALTHY_DRAWS):
    """Run `ped.audit` over in-memory tables, bypassing the file readers."""
    avail, comps, infos = ped._ymt_tables(content)
    with mock.patch.object(ped, "read_ymt", return_value=(avail, comps, infos)), \
         mock.patch.object(ped, "read_ydd", return_value=list(draws)):
        return ped.audit("stem", "x.ydd", "x.ymt", "x.ydd", "x.ymt")


class TestYmtTables(unittest.TestCase):
    def test_reads_avail_components_and_infos(self):
        avail, comps, infos = ped._ymt_tables(healthy())
        self.assertEqual(avail[:5], [0, 255, 1, 2, 3])
        self.assertEqual(len(comps), 4)
        self.assertEqual([c.declared for c in comps], [3, 2, 6, 6])
        self.assertEqual([c.texture_sum for c in comps], [3, 2, 6, 6])
        self.assertEqual(infos, [(0, 0), (2, 0), (2, 1), (3, 0), (3, 1), (4, 0), (4, 1)])

    def test_slot_comes_from_the_occupied_slots_not_from_avail_at_that_index(self):
        _, comps, _ = ped._ymt_tables(healthy())
        # availComp = [0, 255, 1, 2, 3, ...] -> occupied slots are 0, 2, 3, 4
        self.assertEqual([c.slot for c in comps], [0, 2, 3, 4])

    def test_slot_is_dash_one_when_avail_is_short(self):
        c = _content([0, 255], [_component([1]), _component([2])], [(0, 0)])
        _, comps, _ = ped._ymt_tables(c)
        self.assertEqual(comps[0].slot, 0)
        self.assertEqual(comps[1].slot, -1)

    def test_missing_sections_do_not_raise(self):
        avail, comps, infos = ped._ymt_tables({})
        self.assertEqual((avail, comps, infos), ([], [], []))


class TestInfoPair(unittest.TestCase):
    def test_reads_by_field_name(self):
        self.assertEqual(ped._info_pair(_info_row(3, 1)), (3, 1))

    def test_falls_back_to_position_eight_and_nine(self):
        row = {"a": 0, "b": 0, "c": 0, "d": 0, "e": 0,
               "f": 0, "g": 0, "h": 0, "i": 4, "j": 2}
        self.assertEqual(ped._info_pair(row), (4, 2))


class TestAuditHealthy(unittest.TestCase):
    def test_healthy_ped_has_no_problems(self):
        rep = audit(healthy())
        self.assertTrue(rep.ok, rep.problems)
        self.assertEqual(rep.problems, [])

    def test_healthy_ped_has_no_notes_either(self):
        self.assertEqual(audit(healthy()).notes, [])

    def test_drawable_total_counts_only_textured_rows(self):
        self.assertEqual(audit(healthy()).drawable_total, 7)


class TestAuditInvariantOne(unittest.TestCase):
    """numAvailTex == sum of aTexData over that component's drawables."""

    def test_mismatch_is_a_problem(self):
        c = healthy()
        c["aComponentData3"][0]["numAvailTex"] = 77
        rep = audit(c)
        self.assertFalse(rep.ok)
        # the slot name proves availComp was read slot->component, not the other way
        self.assertTrue(any("head: numAvailTex=77" in p for p in rep.problems), rep.problems)

    def test_per_drawable_count_is_only_a_note(self):
        # some mods store "textures per drawable" here; the game tolerates it
        c = healthy()
        c["aComponentData3"][0]["aDrawblData3"] = [_drawbl(3), _drawbl(3), _drawbl(3)]
        c["aComponentData3"][0]["numAvailTex"] = 3   # per drawable: 3 x 3 = 9 entries
        draws = HEALTHY_DRAWS + [("hash_EXTRA_A", 10), ("hash_EXTRA_B", 10)]
        rep = audit(c, draws=draws)                  # 9 real drawables now
        self.assertTrue(any("is per drawable" in n for n in rep.notes), rep.notes)
        self.assertFalse(any("numAvailTex" in p for p in rep.problems), rep.problems)


class TestAuditInvariantFour(unittest.TestCase):
    """Count of textured drawables in the ymt == number of drawables in the ydd."""

    def test_extra_declared_drawable_is_a_problem(self):
        rep = audit(healthy(), draws=HEALTHY_DRAWS[:6])
        self.assertFalse(rep.ok)
        self.assertIn("ymt declares 7 drawable(s), the ydd has 6", rep.problems)

    def test_missing_declared_drawable_is_a_problem(self):
        rep = audit(healthy(), draws=HEALTHY_DRAWS + [("hash_EXTRA", 10)])
        self.assertFalse(rep.ok)
        self.assertIn("ymt declares 7 drawable(s), the ydd has 8", rep.problems)

    def test_implausible_texture_slot_count_is_a_problem(self):
        draws = [("head", 0)] + HEALTHY_DRAWS[1:]
        rep = audit(healthy(), draws=draws)
        self.assertTrue(any("implausible texture slot count 0" in p for p in rep.problems),
                        rep.problems)

    def test_thirty_two_slots_is_still_plausible(self):
        draws = [("head", 32)] + HEALTHY_DRAWS[1:]
        self.assertTrue(audit(healthy(), draws=draws).ok)


class TestAuditCompInfos(unittest.TestCase):
    def test_row_count_must_match_drawables(self):
        c = healthy()
        del c["compInfos"][-1]
        rep = audit(c)
        self.assertTrue(any("compInfos has 6 entries for 7 drawable(s)" in p
                            for p in rep.problems), rep.problems)

    def test_duplicate_rows_are_a_problem(self):
        c = healthy()
        c["compInfos"][-1] = dict(c["compInfos"][0])
        rep = audit(c)
        self.assertTrue(any("duplicate" in p for p in rep.problems), rep.problems)

    def test_row_for_absent_slot_is_a_problem(self):
        c = healthy()
        c["compInfos"][0] = _info_row(9, 0)
        rep = audit(c)
        self.assertTrue(any("slot #9 which has no component" in p for p in rep.problems),
                        rep.problems)

    def test_drawable_index_outside_component_is_a_problem(self):
        c = healthy()
        c["compInfos"][1] = _info_row(2, 5)   # slot 2 holds two drawables
        rep = audit(c)
        self.assertTrue(any("outside slot #2" in p for p in rep.problems), rep.problems)

    def test_drawable_without_row_is_a_problem(self):
        c = healthy()
        c["compInfos"] = [r for r in c["compInfos"] if ped._info_pair(r) != (4, 1)]
        rep = audit(c)
        self.assertTrue(any("missing slot #4 drawable 1" in p for p in rep.problems),
                        rep.problems)


class TestRepair(unittest.TestCase):
    def test_fixes_numavailtex_and_audit_passes_afterwards(self):
        c = healthy()
        c["aComponentData3"][0]["numAvailTex"] = 77
        rep = audit(c)
        self.assertFalse(rep.ok)
        changes = ped.repair_ymt(c, rep)
        self.assertTrue(changes)
        self.assertEqual(c["aComponentData3"][0]["numAvailTex"], 3)
        self.assertTrue(audit(c).ok)

    def test_adds_missing_compinfos_row_from_a_template(self):
        c = healthy()
        c["compInfos"] = [r for r in c["compInfos"] if ped._info_pair(r) != (4, 1)]
        rep = audit(c)
        self.assertFalse(rep.ok)
        changes = ped.repair_ymt(c, rep)
        self.assertTrue(any("drawable 1" in x for x in changes), changes)
        self.assertIn((4, 1), [ped._info_pair(r) for r in c["compInfos"]])
        self.assertTrue(audit(c).ok)

    def test_clean_ped_changes_nothing(self):
        c = healthy()
        before = [dict(r) for r in c["compInfos"]]
        self.assertEqual(ped.repair_ymt(c, audit(c)), [])
        self.assertEqual(c["compInfos"], before)

    def test_no_template_means_the_row_cannot_be_invented(self):
        c = healthy()
        c["compInfos"] = []
        rep = audit(c)
        self.assertEqual(ped.repair_ymt(c, rep), [])


class TestAlign(unittest.TestCase):
    @staticmethod
    def kasumi():
        avail = [0, 255, 1, 255, 255, 255, 255, 2, 3, 4, 5, 255]
        comps = [_component([1] * 17), _component([1] * 4), _component([1]),
                 _component([1] * 4), _component([1] * 4), _component([1] * 4)]
        rows, slot_of = [], {0: 0, 1: 2, 2: 7, 3: 8, 4: 9, 5: 10}
        for k, comp in enumerate(comps):
            for di in range(len(comp["aDrawblData3"])):
                rows.append((slot_of[k], di))
        return _content(avail, comps, rows)

    def test_trims_to_the_ydd_drawable_count(self):
        c = self.kasumi()
        self.assertEqual(len(c["compInfos"]), 34)
        changes = ped.align_ymt(c, 31)
        self.assertTrue(changes)
        self.assertEqual(len(c["compInfos"]), 31)
        kept = sum(1 for comp in c["aComponentData3"] for d in comp["aDrawblData3"])
        self.assertEqual(kept, 31)

    def test_trims_the_tail_of_the_last_component_first(self):
        c = self.kasumi()
        ped.align_ymt(c, 31)
        self.assertEqual(len(c["aComponentData3"][5]["aDrawblData3"]), 1)
        self.assertEqual(c["aComponentData3"][5]["numAvailTex"], 1)
        self.assertEqual(len(c["aComponentData3"][0]["aDrawblData3"]), 17)

    def test_emptied_component_loses_its_availcomp_slot(self):
        c = self.kasumi()
        ped.align_ymt(c, 0)
        self.assertEqual(c["aComponentData3"][0]["aDrawblData3"], [])
        self.assertEqual(c["availComp"][0], 255)
        self.assertEqual(c["compInfos"], [])

    def test_align_is_idempotent(self):
        c = self.kasumi()
        ped.align_ymt(c, 31)
        self.assertEqual(ped.align_ymt(c, 31), [])
        kept = sum(1 for comp in c["aComponentData3"] for d in comp["aDrawblData3"])
        self.assertEqual(kept, 31)

    def test_kept_rows_are_renumbered_within_their_component(self):
        c = self.kasumi()
        ped.align_ymt(c, 31)   # drops drawables 1..3 of component 5
        pairs = [ped._info_pair(r) for r in c["compInfos"]]
        self.assertIn((10, 0), pairs)
        self.assertNotIn((10, 1), pairs)
        # every kept index must be inside its component's remaining rows
        comp_of = {slot: comp for slot, comp in enumerate(c["availComp"]) if comp != 255}
        for slot, draw in pairs:
            comp = c["aComponentData3"][comp_of[slot]]
            self.assertLess(draw, len(comp["aDrawblData3"]))

    def test_aligned_kasumi_passes_the_audit(self):
        c = self.kasumi()
        ped.align_ymt(c, 31)
        draws = [("hash_%02d" % i, 10) for i in range(31)]
        self.assertTrue(audit(c, draws=draws).ok, audit(c, draws=draws).problems)


class TestParseAvail(unittest.TestCase):
    def test_reads_a_space_separated_list(self):
        text = "0 255 1 2 3 255 255 255 255 255 255 255"
        self.assertEqual(ped.parse_avail(text)[:4], [0, 255, 1, 2])

    def test_reads_a_hex_blob(self):
        self.assertEqual(ped.parse_avail("00ff010203ff"), [0, 255, 1, 2, 3, 255])

    def test_empty_is_empty(self):
        self.assertEqual(ped.parse_avail(""), [])
        self.assertEqual(ped.parse_avail(None), [])


if __name__ == "__main__":
    unittest.main()
