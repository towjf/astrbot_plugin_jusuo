"""离线预览：抓取真实数据 -> 生成本地绘制的卡片图。

用法（插件目录下）：
    python tests/preview.py  # 输出到 docs/images/
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

from core.api import JusuoAPI  # noqa: E402
from core.image import save_png  # noqa: E402
from core.view import entry_card, market_card  # noqa: E402

OUT = PLUGIN_DIR / "docs" / "images"


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    api = JusuoAPI(cache_ttl=0)
    try:
        prices = await api.unit_prices()
        residence = await api.residence_entries()
        ranch = await api.ranch_entries()
        presets = await api.ranch_presets()
        matrix = await api.market_matrix("crop", "price", 24)

        for entry in ranch:
            entry["product_name"] = presets.get(entry.get("product_preset_id"), "未知产物")

        def make_card(entries, source, sort_mode, page=1):
            is_res = source == "residence"
            return entry_card(
                entries,
                prices,
                title="菜地 · 高倍收购" if is_res else "牧场 · 高倍收购",
                name_key="crop_name" if is_res else "product_name",
                level_key="residence_level" if is_res else "animal_stall_level",
                level_label="居所" if is_res else "摊位",
                price_category="crop" if is_res else "ranch",
                min_mult=None,
                min_level=None,
                page_size=10,
                page=page,
                sort_mode=sort_mode,
                hide_limited=True,
            )

        cards = {
            "residence-sale": make_card(residence, "residence", "sale"),
            "residence-unit": make_card(residence, "residence", "unit"),
            "residence-page2": make_card(residence, "residence", "sale", 2),
            "ranch-sale": make_card(ranch, "ranch", "sale"),
            "ranch-unit": make_card(ranch, "ranch", "unit"),
            "market": market_card(
                matrix, source_label="菜地", metric="price", hours=24, limit=8
            ),
        }

        for name, card in cards.items():
            print(f"{name}: {save_png(card, OUT / (name + '-pillow.png'))}")
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
