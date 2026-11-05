"""参数解析测试（纯函数，无需 AstrBot）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import params  # noqa: E402


class TestHasSlash(unittest.TestCase):
    def test_half_width_slash(self):
        self.assertTrue(params.has_slash("/菜地"))

    def test_full_width_slash(self):
        self.assertTrue(params.has_slash("／菜地 草莓"))

    def test_no_slash(self):
        self.assertFalse(params.has_slash("菜地 草莓"))

    def test_at_bot_is_not_enough(self):
        self.assertFalse(params.has_slash("[CQ:at,qq=123] 菜地"))

    def test_unknown_text_is_not_blocked(self):
        self.assertTrue(params.has_slash(None))
        self.assertTrue(params.has_slash(""))


class TestTokens(unittest.TestCase):
    def test_strip_command_word(self):
        self.assertEqual(params.tokens("菜地 草莓 单价 2"), ["草莓", "单价", "2"])

    def test_strip_slash(self):
        self.assertEqual(params.tokens("/菜地 草莓"), ["草莓"])

    def test_full_width_slash(self):
        self.assertEqual(params.tokens("／牧场 羊毛"), ["羊毛"])

    def test_command_only(self):
        self.assertEqual(params.tokens("/菜地"), [])
        self.assertEqual(params.tokens("物品列表"), [])


class TestParseEntriesArgs(unittest.TestCase):
    def test_defaults(self):
        args = params.parse_entries_args([])
        self.assertEqual(args.item_keyword, "")
        self.assertIsNone(args.sort_mode)
        self.assertEqual(args.page, 1)
        self.assertIsNone(args.min_mult)
        self.assertIsNone(args.min_level)

    def test_item_keyword(self):
        args = params.parse_entries_args(["草莓"])
        self.assertEqual(args.item_keyword, "草莓")

    def test_multi_word_keyword(self):
        args = params.parse_entries_args(["荆棘", "草莓"])
        self.assertEqual(args.item_keyword, "荆棘 草莓")

    def test_sort_modes(self):
        self.assertEqual(params.parse_entries_args(["单价"]).sort_mode, "unit")
        self.assertEqual(params.parse_entries_args(["单件"]).sort_mode, "unit")
        self.assertEqual(params.parse_entries_args(["unit"]).sort_mode, "unit")
        self.assertEqual(params.parse_entries_args(["售价"]).sort_mode, "sale")
        self.assertEqual(params.parse_entries_args(["sale"]).sort_mode, "sale")

    def test_page(self):
        self.assertEqual(params.parse_entries_args(["3"]).page, 3)

    def test_zero_page_clamped(self):
        self.assertEqual(params.parse_entries_args(["0"]).page, 1)

    def test_combined(self):
        args = params.parse_entries_args(["草莓", "售价", "2"])
        self.assertEqual(args.item_keyword, "草莓")
        self.assertEqual(args.sort_mode, "sale")
        self.assertEqual(args.page, 2)

    def test_filters(self):
        args = params.parse_entries_args(["倍率2", "等级70"])
        self.assertEqual(args.min_mult, 2.0)
        self.assertEqual(args.min_level, 70)

    def test_filters_x_suffix(self):
        args = params.parse_entries_args(["2.5x", "Lv60"])
        self.assertEqual(args.min_mult, 2.5)
        self.assertEqual(args.min_level, 60)

    def test_latin_word_not_treated_as_level(self):
        args = params.parse_entries_args(["longbow"])
        self.assertIsNone(args.min_level)
        self.assertEqual(args.item_keyword, "longbow")


if __name__ == "__main__":
    unittest.main()
