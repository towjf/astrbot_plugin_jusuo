"""格式化与估价公式测试。"""

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.format import (  # noqa: E402
    clip,
    estimate_price,
    fmt_count,
    fmt_money,
    fmt_multiplier,
    fmt_remaining,
    multiplier_tone,
    parse_dt,
)


class TestFmtMoney(unittest.TestCase):
    def test_small(self):
        self.assertEqual(fmt_money(999), "999")

    def test_wan(self):
        self.assertEqual(fmt_money(10_000), "1万")
        self.assertEqual(fmt_money(15_580_000), "1558万")

    def test_yi(self):
        self.assertEqual(fmt_money(123_456_789), "1.23亿")

    def test_none(self):
        self.assertEqual(fmt_money(None), "-")


class TestFmtRemaining(unittest.TestCase):
    now = datetime(2026, 11, 6, 0, 0, tzinfo=UTC)

    def _at(self, **kwargs):
        return (self.now + timedelta(**kwargs)).isoformat()

    def test_hours(self):
        self.assertEqual(fmt_remaining(self._at(hours=5, minutes=12), self.now), "5时12分")

    def test_days(self):
        self.assertEqual(fmt_remaining(self._at(days=1, hours=3), self.now), "1天3时")

    def test_minutes(self):
        self.assertEqual(fmt_remaining(self._at(minutes=43), self.now), "43分")

    def test_expired(self):
        self.assertEqual(fmt_remaining(self._at(minutes=-1), self.now), "已过期")

    def test_bad_input(self):
        self.assertEqual(fmt_remaining(None, self.now), "-")
        self.assertEqual(fmt_remaining("not-a-date", self.now), "-")


class TestEstimatePrice(unittest.TestCase):
    def test_formula(self):
        # 单价 460 ×(1 + (78×5-5)/100) × 1.9 × 2880 ×(1+0.2)
        expected = round(460 * (1 + (78 * 5 - 5) / 100) * 1.9 * 2880 * 1.2)
        self.assertEqual(
            estimate_price(460, 78, 1.9, 2880, guild_maxed=True), expected
        )

    def test_without_guild_bonus(self):
        expected = round(460 * (1 + (78 * 5 - 5) / 100) * 1.9 * 2880)
        self.assertEqual(
            estimate_price(460, 78, 1.9, 2880, guild_maxed=False), expected
        )

    def test_missing_inputs(self):
        self.assertIsNone(estimate_price(None, 78, 1.9, 2880, False))
        self.assertIsNone(estimate_price(460, 78, None, 2880, False))
        self.assertIsNone(estimate_price(460, 78, 1.9, 0, False))


class TestMiscHelpers(unittest.TestCase):
    def test_multiplier_tone(self):
        self.assertEqual(multiplier_tone(2.0), "gold")
        self.assertEqual(multiplier_tone(1.85), "orange")
        self.assertEqual(multiplier_tone(1.2), "green")

    def test_fmt_multiplier(self):
        self.assertEqual(fmt_multiplier(2), "2x")
        self.assertEqual(fmt_multiplier(1.85), "1.85x")

    def test_fmt_count(self):
        self.assertEqual(fmt_count(2880), "2,880")

    def test_clip(self):
        self.assertEqual(clip("短"), "短")
        self.assertTrue(clip("字" * 50, 10).endswith("…"))

    def test_parse_dt(self):
        dt = parse_dt("2026-11-06T01:00:00+00:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, UTC)
        self.assertIsNone(parse_dt("bad"))


if __name__ == "__main__":
    unittest.main()
