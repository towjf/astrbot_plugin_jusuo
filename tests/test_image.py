"""绘制层测试：PNG 输出、尺寸、文本兜底。"""

import io
import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.image import render_card  # noqa: E402
from core.text import card_to_text  # noqa: E402
from core.view import entry_card  # noqa: E402

PRICES = {"crop": {"荆棘草莓": 460.0}}


def build(row_count: int = 3) -> dict:
    entries = [
        {
            "crop_name": "荆棘草莓",
            "quantity": 2880,
            "price_multiplier": 1.9,
            "merchant_name": "金糜(工巧家)",
            "residence_level": 78,
            "expires_at": None,
            "is_limit_reached": False,
            "guild_maxed": True,
            "sale_price": None,
            "uid": f"10000{i}",
        }
        for i in range(row_count)
    ]
    return entry_card(
        entries,
        PRICES,
        title="菜地 · 高倍收购",
        name_key="crop_name",
        level_key="residence_level",
        level_label="居所",
        price_category="crop",
        min_mult=None,
        min_level=None,
        page_size=10,
        page=1,
        sort_mode="sale",
        hide_limited=True,
    )


class TestRenderCard(unittest.TestCase):
    def test_returns_png(self):
        data = render_card(build())
        self.assertIsInstance(data, bytes)
        self.assertTrue(data.startswith(b"\x89PNG"))

    def test_dimensions(self):
        image = Image.open(io.BytesIO(render_card(build())))
        self.assertEqual(image.width, 960)
        self.assertGreater(image.height, 300)

    def test_more_rows_are_taller(self):
        small = Image.open(io.BytesIO(render_card(build(1))))
        large = Image.open(io.BytesIO(render_card(build(5))))
        self.assertGreater(large.height, small.height)

    def test_empty_card_does_not_crash(self):
        card = build(0)
        image = Image.open(io.BytesIO(render_card(card)))
        self.assertEqual(image.width, 960)


class TestCardToText(unittest.TestCase):
    def test_contains_uid_and_price(self):
        text = card_to_text(build(1))
        self.assertIn("UID：100000", text)
        self.assertIn("荆棘草莓", text)
        self.assertIn("数据来源jusuo.playmmo.cn", text)

    def test_empty_card_text(self):
        text = card_to_text(build(0))
        self.assertIn("没有符合条件", text)


if __name__ == "__main__":
    unittest.main()
