import os
import struct
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from gtav_asset_repair import cli, dds, normals, ymt, ytd  # noqa: E402

TMP = os.path.join(HERE, "_tmp")
os.makedirs(TMP, exist_ok=True)


def scratch(name):
    """Workspace scratch dir; never deleted (sandbox denies chmod on cleanup)."""
    d = os.path.join(TMP, name)
    os.makedirs(d, exist_ok=True)
    return d


def make_dds(path, width, height, mips, fourcc=b"DXT5", masks=None):
    hdr = bytearray(148 if fourcc == b"DX10" else 128)
    hdr[0:4] = b"DDS "
    struct.pack_into("<I", hdr, 4, 124)
    struct.pack_into("<II", hdr, 12, height, width)
    struct.pack_into("<I", hdr, 28, mips)
    if masks:
        struct.pack_into("<I", hdr, 76, 32)
        struct.pack_into("<I", hdr, 80, 0x41)
        struct.pack_into("<I", hdr, 88, 32)
        struct.pack_into("<IIII", hdr, 92, *masks)
    else:
        struct.pack_into("<I", hdr, 84, int.from_bytes(fourcc, "little"))
    if fourcc == b"DX10":
        struct.pack_into("<I", hdr, 128, 98)
    with open(path, "wb") as f:
        f.write(bytes(hdr) + b"\x00" * 16)


class TestDds(unittest.TestCase):
    def test_read_dxt5_header(self):
        p = os.path.join(scratch("dds1"), "a.dds")
        make_dds(p, 512, 256, 10)
        h = dds.read_header(p)
        self.assertEqual((h.width, h.height, h.mips), (512, 256, 10))
        self.assertEqual(h.label, "BC3_UNORM")
        self.assertEqual(h.offset, 128)

    def test_read_dx10_bc7(self):
        p = os.path.join(scratch("dds2"), "b.dds")
        make_dds(p, 256, 128, 1, fourcc=b"DX10")
        h = dds.read_header(p)
        self.assertEqual(h.label, "BC7")
        self.assertEqual(h.offset, 148)

    def test_read_a8r8g8b8(self):
        p = os.path.join(scratch("dds3"), "c.dds")
        make_dds(p, 256, 128, 1, fourcc=b"\x00" * 4,
                 masks=(0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000))
        h = dds.read_header(p)
        self.assertEqual(h.label, "A8R8G8B8")
        self.assertEqual(h.texconv_fmt, "B8G8R8A8_UNORM")

    def test_rejects_unknown(self):
        p = os.path.join(scratch("dds4"), "d.dds")
        make_dds(p, 64, 64, 1, fourcc=b"XXXX")
        with self.assertRaises(ValueError):
            dds.read_header(p)


class TestNormals(unittest.TestCase):
    def test_flat_input_gives_flat_normal(self):
        rgba = np.ones((16, 16, 4), np.float32)
        n = normals.normal_from_height(normals.height_field(rgba, blur=0), strength=6.5)
        self.assertEqual(n.shape, (16, 16, 3))
        self.assertTrue(np.all(n[..., 2] > 200))
        self.assertTrue(np.all((n[..., 0] > 120) & (n[..., 0] < 136)))

    def test_margin_is_flat(self):
        rgba = np.zeros((16, 16, 4), np.float32)
        rgba[6:10, 6:10] = 1.0
        n = normals.normal_from_height(normals.height_field(rgba, blur=0), strength=6.5)
        self.assertEqual(tuple(n[0, 0]), (128, 128, 255))

    def test_green_points_up_in_texture_space(self):
        """A ridge that rises towards the bottom of the image must encode G < 128.

        Shipped badges follow this (sentinel_badges_n / serrano_decals_bump match
        sign(-gy) on ~78% of pixels); the opposite sign renders the emboss as a
        groove, which is the bug this locks down.
        """
        rise = np.tile(np.linspace(0.0, 1.0, 16, dtype=np.float32)[:, None], (1, 16))
        n = normals.normal_from_height(rise, strength=4.0, flat_margin=False)
        g = n[8, :, 1].astype(np.float32)
        self.assertLess(float(g.mean()), 128.0, "G must fall as height rises downwards")
        self.assertGreater(float(n[8, :, 2].astype(np.float32).mean()), 200.0)

    def test_height_prefers_bright_inside_mask(self):
        rgba = np.zeros((8, 8, 4), np.float32)
        rgba[..., 3] = 1.0
        rgba[2:4, :, :3] = 1.0
        h = normals.height_field(rgba, blur=0)
        self.assertGreater(h[2:4].mean(), h[6:].mean())


YMT_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<CPedVariationInfo>
 <availComp>{avail}</availComp>
 <aComponentData3 itemType="CPVComponentData">
  <Item>
   <numAvailTex value="{num}" />
   <aDrawblData3 itemType="CPVDrawblData">
{drawbles}
   </aDrawblData3>
  </Item>
 </aComponentData3>
 <compInfos itemType="CComponentInfo">
{infos}
 </compInfos>
</CPedVariationInfo>
"""

DRAWBLE = ("    <Item>\n     <aTexData itemType=\"CPVTextureData\">\n"
           "      <Item><texId value=\"1\" /><distribution value=\"255\" /></Item>\n"
           "     </aTexData>\n    </Item>")


def info(slot=0, drawbl=0):
    return (f"  <Item><pedXml_compIdx value=\"{slot}\" />"
            f"<pedXml_drawblIdx value=\"{drawbl}\" /></Item>")


class TestYmtAudit(unittest.TestCase):
    def write(self, name, avail, num, drawbles, infos):
        p = os.path.join(scratch("ymt"), name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(YMT_TEMPLATE.format(avail=avail, num=num,
                                        drawbles="\n".join(drawbles), infos="\n".join(infos)))
        return p

    def test_consistent(self):
        p = self.write("ok.xml", "0 255", 2, [DRAWBLE, DRAWBLE], [info(0, 0), info(0, 1)])
        res = ymt.audit_xml(p)
        self.assertTrue(res.ok, res.problems)
        self.assertEqual(res.drawble_total, 2)

    def test_wrong_num_avail_tex(self):
        p = self.write("bad_num.xml", "0 255", 5, [DRAWBLE, DRAWBLE], [info(0, 0), info(0, 1)])
        res = ymt.audit_xml(p)
        self.assertFalse(res.ok)
        self.assertTrue(any("numAvailTex" in x for x in res.problems))

    def test_missing_comp_info(self):
        p = self.write("bad_infos.xml", "0 255", 2, [DRAWBLE, DRAWBLE], [info(0, 0)])
        res = ymt.audit_xml(p)
        self.assertFalse(res.ok)
        self.assertTrue(any("missing entry" in x for x in res.problems))

    def test_hex_avail(self):
        self.assertEqual(ymt.parse_avail("00FF0102"), [0, 255, 1, 2])
        self.assertEqual(ymt.parse_avail("0 255 1"), [0, 255, 1])


class TestYtd(unittest.TestCase):
    def test_expected_mips(self):
        cases = [((256, 128), 9), ((256, 256), 9), ((512, 256), 10), ((4, 4), 3), ((648, 324), 10)]
        for (w, h), want in cases:
            self.assertEqual(ytd.Texture("t", w, h, "DXT5", 1).expected_mips, want)

    def test_mips_ok(self):
        self.assertTrue(ytd.Texture("t", 256, 128, "DXT5", 9).mips_ok)
        self.assertFalse(ytd.Texture("t", 256, 128, "DXT5", 8).mips_ok)
        self.assertFalse(ytd.Texture("t", 256, 128, "DXT5", 1).mips_ok)

    def test_find_and_table(self):
        info = ytd.YtdInfo("x/banshee.ytd", [
            ytd.Texture("banshee_badges", 256, 128, "DXT5", 9),
            ytd.Texture("generic_leather2_n", 256, 256, "ATI2", 7),
        ])
        self.assertEqual([t.name for t in info.find("badge")], ["banshee_badges"])
        table = ytd.format_table([info])
        self.assertIn("2 texture(s), 1 with incomplete mips", table)
        self.assertIn("generic_leather2_n", table)

    def test_error_is_reported(self):
        info = ytd.YtdInfo("broken.ytd", [], error="not an RSC7 file")
        self.assertIn("not an RSC7 file", ytd.format_table([info]))

    def test_rsc7_version(self):
        p = os.path.join(scratch("rsc7"), "v.ytd")
        with open(p, "wb") as fh:
            fh.write(b"RSC7" + struct.pack("<I", 5) + b"\x00" * 8)
        self.assertEqual(ytd.rsc7_version(p), 5)
        q = os.path.join(scratch("rsc7"), "plain.bin")
        with open(q, "wb") as fh:
            fh.write(b"nope")
        self.assertIsNone(ytd.rsc7_version(q))

    def test_warning_shows_in_table(self):
        info = ytd.YtdInfo("a.ytd", [ytd.Texture("t", 256, 128, "DXT5", 9)],
                           warning="this archive is gen9")
        self.assertIn("warning: this archive is gen9", ytd.format_table([info]))


if __name__ == "__main__":
    unittest.main()


class WorkDirTest(unittest.TestCase):
    def test_work_before_and_after_subcommand(self):
        parser = cli.build_parser()
        a = parser.parse_args(["--work", "D:/x", "normals", "in"])
        self.assertEqual(a.work, "D:/x")
        b = parser.parse_args(["normals", "in", "--work", "D:/y"])
        self.assertEqual(b.work, "D:/y")

    def test_work_path_defaults(self):
        old = cli.WORK
        try:
            cli.WORK = r"D:\mods\NEW"
            self.assertTrue(cli.work_path("normals").startswith(cli.WORK))
            self.assertEqual(str(cli.work_path("normals")).find("normals") > 0, True)
            cli.WORK = ""
            self.assertEqual(cli.work_path("packed", "a.ytd").find("packed") > 0, True)
        finally:
            cli.WORK = old

    def test_pack_out_is_optional(self):
        parser = cli.build_parser()
        a = parser.parse_args(["pack", "--xml", "a.ytd.xml", "--build", "b"])
        self.assertEqual(a.out, "")

class PedLegacyTest(unittest.TestCase):
    def _fake(self, version):
        import struct
        from tempfile import NamedTemporaryFile

        fh = NamedTemporaryFile(suffix=".ydd", delete=False)
        fh.write(b"RSC7" + struct.pack("<I", version) + b"\0" * 32)
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        return fh.name

    def test_detects_gen8(self):
        from gtav_asset_repair.ped import legacy_for

        self.assertTrue(legacy_for(self._fake(165)))

    def test_detects_gen9(self):
        from gtav_asset_repair.ped import legacy_for

        self.assertFalse(legacy_for(self._fake(159)))

    def test_missing_header_is_not_legacy(self):
        from tempfile import NamedTemporaryFile

        from gtav_asset_repair.ped import legacy_for

        fh = NamedTemporaryFile(suffix=".ydd", delete=False)
        fh.write(b"nope")
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        self.assertFalse(legacy_for(fh.name))

