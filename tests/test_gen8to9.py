"""gen8 -> gen9 conversion: dispatch rules plus the CodeWalker ground truth.

The dispatch tests run on synthetic headers; the ground-truth tests compare
against the CodeWalker templates under ``素材不要动/`` and are skipped when that
folder is absent (the assets are not part of the repository).
"""
import contextlib
import io
import os
import shutil
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from gtav_asset_repair import gen8to9  # noqa: E402

TMP = os.path.join(HERE, "_tmp")
os.makedirs(TMP, exist_ok=True)

ASSETS = os.path.abspath(os.path.join(HERE, "..", "..", "素材不要动"))
CAR8 = os.path.join(ASSETS, "vehicles_ingame_gen8")
CAR9 = os.path.join(ASSETS, "vehicles_ingame_gen8 - to 9")
PED8 = os.path.join(ASSETS, "ped_ingame41_gen8")
PED9 = os.path.join(ASSETS, "ped_ingame41_gen8 - to 9")
PED_MOD8 = os.path.join(ASSETS, "ped_gen8")
HAVE_CAR = os.path.isfile(os.path.join(CAR8, "sultan.ytd")) and \
    os.path.isfile(os.path.join(CAR9, "sultan.ytd"))
HAVE_PED = os.path.isfile(os.path.join(PED8, "a_f_y_beach_01.ymt")) and \
    os.path.isfile(os.path.join(PED9, "a_f_y_beach_01.ymt"))


def read(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def rsc7(version: int, size: int = 600) -> bytes:
    """A fake RSC7 resource long enough that it is not mistaken for a stub."""
    return b"RSC7" + struct.pack("<I", version) + b"\x00" * (size - 8)


def big_system_rsc7(version: int, system_size: int = 34_078_720) -> bytes:
    """A fake RSC7 whose header claims a system segment that ships and loads.

    34,078,720 B (4160 pages of 8 KiB) is the measured size of a gen9 fragment
    that runs fine in game, so nothing may be refused on segment size alone.
    """
    resource, _defs, _hashing = gen8to9._modules()
    flags = resource.get_resource_flags_from_size_adaptive(system_size, version)
    header = b"RSC7" + struct.pack("<III", version, flags, 0)
    return header + b"\x00" * (600 - len(header))


class TestDispatch(unittest.TestCase):
    def test_ymt_and_yld_are_copied(self):
        for ext, version in ((".ymt", 2), (".yld", 8)):
            raw = rsc7(version)
            out, action = gen8to9.convert_bytes(raw, "a" + ext)
            self.assertEqual(action, "copied")
            self.assertEqual(out, raw)

    def test_passthrough_rejects_unknown_version(self):
        with self.assertRaises(gen8to9.UnsupportedResource):
            gen8to9.convert_bytes(rsc7(3), "a.ymt")

    def test_undecodable_fragment_is_skipped_not_crashed(self):
        """.yft is rebuilt now, so a header-only stub is a decode failure.

        Like .ydd, it must surface as a skip reason with the original error text.
        """
        with self.assertRaises(gen8to9.UnsupportedResource) as cm:
            gen8to9.convert_bytes(rsc7(162), "a.yft")
        self.assertIn(".yft conversion failed", str(cm.exception))

    def test_undecodable_drawable_is_skipped_not_crashed(self):
        """.ydd is supported now, so a header-only stub is a decode failure.

        It must surface as a skip reason carrying the original error text, not as
        an exception that aborts a whole-folder run.
        """
        with self.assertRaises(gen8to9.UnsupportedResource) as cm:
            gen8to9.convert_bytes(rsc7(165), "a.ydd")
        self.assertIn(".ydd conversion failed", str(cm.exception))
        self.assertIn("decompress", str(cm.exception))

    def test_system_segment_size_comes_from_the_header(self):
        """The probe helper reports the declared size without decompressing."""
        self.assertEqual(gen8to9.system_segment_size(big_system_rsc7(162)), 34_078_720)
        self.assertIsNone(gen8to9.system_segment_size(b"not a resource"))

    def test_a_large_system_segment_is_not_refused_on_size(self):
        """34 MiB is known to load in game, so no size gate may stop a rebuild.

        A 32 MiB gate was added and withdrawn on 2026-11-26: a shipped gen9
        fragment with a 34,078,720 B system segment plays fine, and a 64 MiB
        drawable converts.  The only error left for these stubs is the decode.
        """
        for ext, version in ((".yft", 162), (".ydd", 165)):
            with self.assertRaises(gen8to9.UnsupportedResource) as cm:
                gen8to9.convert_bytes(big_system_rsc7(version), "a" + ext)
            message = str(cm.exception)
            self.assertNotIn("system segment", message)
            self.assertIn(f"{ext} conversion failed", message)

    def test_not_rsc7(self):
        with self.assertRaises(gen8to9.UnsupportedResource):
            gen8to9.convert_bytes(b"not a resource", "a.ytd")

    def test_stub_archive_only_gets_its_version(self):
        raw = rsc7(13, size=400)
        out, action = gen8to9.convert_bytes(raw, "x+hi.ytd")
        self.assertEqual(action, "placeholder")
        self.assertEqual(len(out), len(raw))
        self.assertEqual(gen8to9.rsc7_version(out), 5)
        self.assertEqual(out[:4], b"RSC7")

    def test_unknown_extension(self):
        with self.assertRaises(gen8to9.UnsupportedResource):
            gen8to9.convert_bytes(rsc7(1), "a.bin")


@unittest.skipUnless(HAVE_CAR, "素材不要动 vehicle dictionaries not present")
class TestSultanGroundTruth(unittest.TestCase):
    """sultan.ytd is the reference case: byte-identical to CodeWalker's output."""

    def test_byte_identical_to_codewalker(self):
        raw = read(os.path.join(CAR8, "sultan.ytd"))
        expected = read(os.path.join(CAR9, "sultan.ytd"))
        out = gen8to9.convert_ytd(raw)
        self.assertEqual(len(out), len(expected))
        self.assertEqual(out, expected)

    def test_header_and_readback(self):
        raw = read(os.path.join(CAR8, "sultan.ytd"))
        out = gen8to9.convert_ytd(raw)
        self.assertEqual(gen8to9.rsc7_version(out), gen8to9.GEN9_YTD_VERSION)
        _magic, _version, system_flags, graphics_flags = struct.unpack_from(
            "<IIII", out, 0)
        self.assertEqual(system_flags, 0x00020000)      # one 8192 B page
        self.assertEqual(graphics_flags, 0x50000882)    # 196608 B in two pages
        self.assertEqual(gen8to9.readback_problems(raw, out), [])


@unittest.skipUnless(HAVE_PED, "ped baselines not present")
class TestPassthroughGroundTruth(unittest.TestCase):
    """The 45 ped .ymt files convert by copying; .yld does the same."""

    def test_ymt_bytes_are_identical(self):
        for name in ("a_f_y_beach_01.ymt", "a_f_y_beach_01.yld"):
            src = os.path.join(PED8, name)
            if not os.path.isfile(src):
                continue
            raw = read(src)
            out, action = gen8to9.convert_bytes(raw, name)
            self.assertEqual(action, "copied", name)
            self.assertEqual(out, read(os.path.join(PED9, name)), name)


@unittest.skipUnless(HAVE_PED and os.path.isfile(os.path.join(PED8, "a_f_y_beach_01.ydd")),
                     "ped .ydd baselines not present")
class TestYddGroundTruth(unittest.TestCase):
    """A vanilla ped .ydd keeps every mesh, channel and index through the rewrite.

    The ground truth is the gen8 source itself: gen9 reorders and re-encodes the
    container, but nothing in the geometry is allowed to change.
    """

    def test_beach_meshes_match_the_gen8_source(self):
        name = "a_f_y_beach_01.ydd"
        raw = read(os.path.join(PED8, name))
        out, action = gen8to9.convert_bytes(raw, name)
        self.assertEqual(action, "converted")
        self.assertEqual(gen8to9.rsc7_version(out), gen8to9.GEN9_YDD_VERSION)
        self.assertEqual(gen8to9.readback_ydd_problems(raw, out), [])

    @unittest.skipUnless(os.path.isfile(os.path.join(PED_MOD8, "Kasumi.ydd")),
                         "素材不要动/ped_gen8/Kasumi.ydd not present")
    def test_bare_drawable_pack_keeps_its_legacy_vfts(self):
        """Kasumi crashed in game when its structural VFTs were raised to gen9.

        A bare YdrDrawable dictionary (0x40573178) has to keep the gen8 values
        for drawable / model / geometry / buffers / skeleton; only the texture
        VFTs move to gen9.  Verified in game on 2026-11-26.
        """
        name = "Kasumi.ydd"
        raw = read(os.path.join(PED_MOD8, name))
        out, action = gen8to9.convert_bytes(raw, name)
        self.assertEqual(action, "converted")
        system = gen8to9._system_segment(out)
        self.assertEqual(system.count(struct.pack("<I", 0x4068C7F0)), 0)
        self.assertGreater(system.count(struct.pack("<I", 0x40573178)), 0)
        self.assertGreater(system.count(struct.pack("<I", 0x406B77D8)), 0)
        self.assertEqual(gen8to9.readback_ydd_problems(raw, out), [])


@unittest.skipUnless(HAVE_CAR and os.path.isfile(os.path.join(CAR8, "sultan.yft")),
                     "素材不要动 vehicle fragments not present")
class TestYftGroundTruth(unittest.TestCase):
    """A gen8 vehicle fragment keeps every mesh and material through the rebuild."""

    def test_sultan_fragment_has_no_readback_problems(self):
        raw = read(os.path.join(CAR8, "sultan.yft"))
        out, action = gen8to9.convert_bytes(raw, "sultan.yft")
        self.assertEqual(action, "converted")
        self.assertEqual(gen8to9.rsc7_version(out), gen8to9.GEN9_YFT_VERSION)
        self.assertEqual(gen8to9.readback_yft_problems(raw, out), [])

    def test_fragment_carries_the_gen9_joints_table(self):
        """A legacy joints VFT inside a 171 file is the defect this pins down."""
        raw = read(os.path.join(CAR8, "sultan.yft"))
        out = gen8to9.convert_yft(raw)
        yft_api, _hashing = gen8to9._yft_modules()
        yft = yft_api.read_yft(out)
        joints = [obj for obj in gen8to9._walk_yft(yft)
                  if type(obj).__name__ == "YdrJoints"]
        self.assertTrue(joints, "sultan.yft has joints limits")
        self.assertEqual(int(joints[0].vft), gen8to9.GEN9_JOINTS_VFT)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(TMP, "gen8to9_cli")
        os.makedirs(self.dir, exist_ok=True)
        for name, version, size in (("a.ymt", 2, 600), ("b.ydd", 165, 600),
                                    ("c+hi.ytd", 13, 400)):
            with open(os.path.join(self.dir, name), "wb") as fh:
                fh.write(rsc7(version, size))
        self.out = os.path.join(TMP, "gen8to9_cli_out")
        shutil.rmtree(self.out, ignore_errors=True)

    def test_dry_run_writes_nothing(self):
        results = gen8to9.convert_tree(self.dir, self.out, dry_run=True)
        actions = {r.rel: r.action for r in results}
        self.assertEqual(actions["a.ymt"], "copied")
        self.assertEqual(actions["b.ydd"], "skipped")
        self.assertEqual(actions["c+hi.ytd"], "placeholder")
        self.assertFalse(os.path.exists(self.out))

    def test_real_run_keeps_skipped_files_out_of_dst(self):
        results = gen8to9.convert_tree(self.dir, self.out)
        written = {r.rel for r in results if r.action != "skipped"}
        self.assertEqual(written, {"a.ymt", "c+hi.ytd"})
        self.assertTrue(os.path.isfile(os.path.join(self.out, "a.ymt")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "b.ydd")))

    def test_skipped_files_are_not_a_failure_exit(self):
        """A folder with undecodable resources must not fail the whole build."""
        from gtav_asset_repair import cli
        with contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["gen8to9", self.dir, self.out])
        self.assertEqual(code, 0)


RENDER_TARGET_YTD = os.path.join(ASSETS, "vehicles_gen8", "renventon.ytd")
HAVE_RENDER_TARGET = os.path.isfile(RENDER_TARGET_YTD)


def _fivefury(name: str):
    vendor = os.path.join(HERE, "..", "src", "gtav_asset_repair", "vendor")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    import importlib

    return importlib.import_module(name)


def _render_target_flags(blob: bytes) -> dict[str, int]:
    """Return {name: usage_flags} for every script_rt_* texture in a ytd blob."""
    gen8to9._modules()  # loads the native reader before fivefury is importable
    read_ytd = _fivefury("fivefury.ytd").read_ytd
    dictionary = read_ytd(blob)
    return {
        texture.name: texture.usage_flags
        for texture in dictionary.textures
        if texture.name.lower().startswith("script_rt")
    }


@unittest.skipUnless(HAVE_RENDER_TARGET, "素材不要动 render-target vehicle dictionary not present")
class TestRenderTargetTextures(unittest.TestCase):
    """script_rt_* textures are render targets: gen9 keeps their flags.

    Dropping them (the old behaviour) makes the game fail to create the render
    target, which crashes on spawn. CW's converter loses them too; Alchemist
    keeps them.
    """

    def test_script_rt_textures_keep_their_usage_flags(self):
        raw = read(RENDER_TARGET_YTD)
        before = _render_target_flags(raw)
        self.assertTrue(before, "sample is expected to carry a script_rt texture")
        after = _render_target_flags(gen8to9.convert_ytd(raw))
        self.assertEqual(after, before)

    def test_script_rt_textures_keep_the_render_target_bit(self):
        raw = read(RENDER_TARGET_YTD)
        out = gen8to9.convert_ytd(raw)
        gen8to9._modules()
        split = _fivefury("fivefury.resource").split_rsc7_sections
        _header, system, _graphics = split(out)
        # The descriptor flags live at record +0x10; a script_rt record must carry
        # 0x00260228 (plain 0x00260208 plus the render-target bit).
        self.assertGreaterEqual(
            system.count(struct.pack("<I", gen8to9.GEN9_DESCRIPTOR_FLAGS | gen8to9.GEN9_RENDER_TARGET_BIT)),
            1,
        )


if __name__ == "__main__":
    unittest.main()
