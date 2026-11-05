"""卡片视图模型测试：排序、分页、筛选、字段透传。"""

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.view import entry_card, market_card  # noqa: E402

PRICES = {"crop": {"荆棘草莓": 460.0, "蝶影莲子": 366.0}, "ranch": {"浅滩羊驼毛": 800.0}}

FAR_FUTURE = (datetime.now(UTC) + timedelta(days=3)).isoformat()


def make_entry(
    name="荆棘草莓",
    quantity=2880,
    multiplier=1.9,
    level=78,
    uid="131809",
    limited=False,
    guild=True,
):
    return {
        "crop_name": name,
        "quantity": quantity,
        "price_multiplier": multiplier,
        "merchant_name": "金糜(工巧家)",
        "residence_level": level,
        "expires_at": FAR_FUTURE,
        "is_limit_reached": limited,
        "guild_maxed": guild,
        "sale_price": None,
        "uid": uid,
    }


def build(entries, **kwargs):
    options = dict(
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
    options.update(kwargs)
    return entry_card(entries, PRICES, **options)


class TestEntryCard(unittest.TestCase):
    def test_sale_sort_orders_by_total(self):
        entries = [
            make_entry(quantity=1000, multiplier=1.9, uid="low"),
            make_entry(quantity=2880, multiplier=1.9, uid="high"),
        ]
        card = build(entries, sort_mode="sale")
        self.assertEqual([r["uid"] for r in card["rows"]], ["high", "low"])

    def test_unit_sort_orders_by_price_per_item(self):
        entries = [
            make_entry(quantity=2880, level=60, uid="big-batch"),
            make_entry(quantity=1000, level=79, uid="small-batch"),
        ]
        card = build(entries, sort_mode="unit")
        self.assertEqual(card["rows"][0]["uid"], "small-batch")

    def test_page_offset_and_rank(self):
        entries = [make_entry(uid=str(i)) for i in range(25)]
        card = build(entries, page=2, page_size=10)
        self.assertEqual(len(card["rows"]), 10)
        self.assertEqual(card["rows"][0]["rank"], 11)
        self.assertIn("第 2/3 页", [c["text"] for c in card["chips"]])

    def test_page_clamped_to_last(self):
        entries = [make_entry(uid=str(i)) for i in range(12)]
        card = build(entries, page=99, page_size=10)
        self.assertEqual(len(card["rows"]), 2)
        self.assertEqual(card["rows"][0]["rank"], 11)

    def test_item_keyword_filter(self):
        entries = [make_entry(), make_entry(name="蝶影莲子", uid="lotus")]
        card = build(entries, item_keyword="莲子")
        self.assertEqual([r["uid"] for r in card["rows"]], ["lotus"])
        self.assertIn("物品：莲子", [c["text"] for c in card["chips"]])

    def test_hide_limited(self):
        entries = [make_entry(uid="ok"), make_entry(uid="limited", limited=True)]
        self.assertEqual(len(build(entries, hide_limited=True)["rows"]), 1)
        self.assertEqual(len(build(entries, hide_limited=False)["rows"]), 2)

    def test_multiplier_filters(self):
        entries = [make_entry(multiplier=1.2), make_entry(multiplier=2.0, uid="顶")]
        self.assertEqual(len(build(entries, min_mult=1.8)["rows"]), 1)
        self.assertEqual(len(build(entries, min_level=90)["rows"]), 0)

    def test_row_carries_uid_and_price(self):
        card = build([make_entry()])
        row = card["rows"][0]
        self.assertEqual(row["uid"], "131809")
        self.assertTrue(row["price"])
        self.assertEqual(row["mult"], "1.9x")
        self.assertEqual(card["footer"], "数据来源jusuo.playmmo.cn")
        self.assertEqual(card["source"], "禁鬼有型&居所助手")

    def test_empty_state(self):
        card = build([], min_mult=9)
        self.assertEqual(card["rows"], [])
        self.assertIn("没有符合条件", card["subtitle"])


class TestMarketCard(unittest.TestCase):
    def test_pick_peak_per_item(self):
        matrix = {
            "hours": ["11-05 10:00", "11-05 11:00"],
            "items": ["荆棘草莓"],
            "cells": {
                "0:0": {"value": 100, "entry": {"item_name": "荆棘草莓", "uid": "a"}},
                "1:0": {"value": 300, "entry": {"item_name": "荆棘草莓", "uid": "b"}},
            },
        }
        card = market_card(matrix, source_label="菜地", metric="price", hours=24, limit=5)
        self.assertEqual(len(card["rows"]), 1)
        self.assertEqual(card["rows"][0]["uid"], "b")
        self.assertIn("菜地", card["title"])


if __name__ == "__main__":
    unittest.main()
