import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from gtatools import lite  # noqa: E402


def entry(name="tex", width=2048, height=2048, mips=12, fmt="D3DFMT_DXT5", usage=""):
    return lite.Entry(name=name, file=name + ".dds", width=width, height=height, mips=mips,
                      format=fmt, usage=usage)


class TargetSizeTest(unittest.TestCase):
    def test_under_min_side_is_untouched(self):
        for mode in lite.MODES:
            self.assertIsNone(lite.target_size(512, 512, mode, 1024))

    def test_exactly_min_side_is_eligible_for_cap(self):
        self.assertIsNone(lite.target_size(1024, 1024, "cap", 1024))
        self.assertEqual(lite.target_size(2048, 2048, "cap", 1024), (1024, 1024))

    def test_cap_only_shrinks_above_limit(self):
        self.assertIsNone(lite.target_size(2048, 1024, "cap", 2048))
        self.assertEqual(lite.target_size(4096, 2048, "cap", 2048), (2048, 1024))
        self.assertEqual(lite.target_size(3000, 1500, "cap", 2048), (2048, 1024))

    def test_tier_falls_to_the_next_lower_tier(self):
        self.assertEqual(lite.target_size(2000, 1000, "tier", 2048), (1536, 768))
        self.assertEqual(lite.target_size(3000, 1500, "tier", 2048), (2048, 1024))
        self.assertEqual(lite.target_size(1200, 600, "tier", 2048), (1024, 512))

    def test_tier_keeps_exact_tiers_and_only_rounds_down(self):
        self.assertIsNone(lite.target_size(1536, 768, "tier", 2048))
        self.assertIsNone(lite.target_size(2048, 1024, "tier", 2048))
        self.assertIsNone(lite.target_size(1024, 512, "tier", 2048))
        self.assertEqual(lite.target_size(1025, 512, "tier", 2048), (1024, 512))
        self.assertEqual(lite.target_size(1537, 768, "tier", 2048), (1536, 768))
        self.assertEqual(lite.target_size(2049, 1024, "tier", 2048), (2048, 1024))

    def test_sizes_stay_multiple_of_four(self):
        for width, height in ((4093, 2047), (1537, 777), (2049, 1023)):
            got = lite.target_size(width, height, "cap", 1024)
            self.assertEqual(got[0] % 4, 0)
            self.assertEqual(got[1] % 4, 0)


class PlanTest(unittest.TestCase):
    def test_small_textures_are_skipped_in_every_mode(self):
        steps = lite.plan([entry(width=512, height=512)], "agg", 1024)
        self.assertTrue(steps[0].skip)
        self.assertIn("below", steps[0].reason)

    def test_resize_rebuilds_the_mip_chain(self):
        steps = lite.plan([entry(width=2048, height=2048, mips=12)], "cap", 1024)
        step = steps[0]
        self.assertEqual((step.new_width, step.new_height, step.new_mips), (1024, 1024, 11))

    def test_single_mip_stays_single(self):
        steps = lite.plan([entry(width=2048, height=2048, mips=1)], "cap", 1024)
        self.assertEqual(steps[0].new_mips, 1)

    def test_aggressive_uses_cap_rule(self):
        steps = lite.plan([entry(width=2048, height=2048, mips=12)], "agg", 2048)
        self.assertTrue(steps[0].skip)

    def test_normal_maps_keep_their_format(self):
        steps = lite.plan([entry(name="body_n", fmt="D3DFMT_DXT5")], "agg", 1024,
                          pixels={"body_n": (False, True)})
        self.assertFalse(steps[0].reformat)

    def test_uncompressed_becomes_dxt5(self):
        steps = lite.plan([entry(name="body", fmt="D3DFMT_A8R8G8B8")], "agg", 1024,
                          pixels={"body": (True, False)})
        self.assertEqual(steps[0].new_format, "D3DFMT_DXT5")

    def test_opaque_dxt5_becomes_dxt1(self):
        steps = lite.plan([entry(name="body", fmt="D3DFMT_DXT5")], "agg", 1024,
                          pixels={"body": (False, False)})
        self.assertEqual(steps[0].new_format, "D3DFMT_DXT1")

    def test_alpha_blocks_the_dxt1_swap(self):
        steps = lite.plan([entry(name="body", fmt="D3DFMT_DXT5")], "agg", 1024,
                          pixels={"body": (True, False)})
        self.assertFalse(steps[0].reformat)

    def test_spec_like_names_keep_their_format(self):
        steps = lite.plan([entry(name="body_spec", fmt="D3DFMT_DXT5")], "agg", 1024,
                          pixels={"body_spec": (False, False)})
        self.assertFalse(steps[0].reformat)


if __name__ == "__main__":
    unittest.main()
