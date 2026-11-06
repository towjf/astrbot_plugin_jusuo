"""居所助手 —— 王者荣耀世界「居所助手」数据查询插件。

数据来源于 jusuo.playmmo.cn（Supabase 公开只读接口），支持：
菜地作物高倍收购、牧场动物产物收购、物品清单与行情走势。

所有命令都必须以 / 开头才触发；不带 / 的消息一律当普通聊天处理。
"""

from __future__ import annotations

import asyncio
import time

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image
from astrbot.api.star import Context, Star, register

from .core import params
from .core.api import DEFAULT_ANON_KEY, DEFAULT_BASE_URL, JusuoAPI, JusuoAPIError
from .core.image import render_card
from .core.text import card_to_text
from .core.view import (
    entry_card,
    help_rows_card,
    market_card,
)

VERSION = "1.5.1"

HELP_ITEMS = [
    {
        "cmd": "/菜地 [物品] [单价|售价] [页数]",
        "what": "菜地作物高倍收购",
        "how": "默认售价优先、第 1 页。例：/菜地 草莓 → 只看名字含草莓的；/菜地 草莓 单价 2 → 单价排序第 2 页。",
    },
    {
        "cmd": "/牧场 [物品] [单价|售价] [页数]",
        "what": "牧场动物产物收购",
        "how": "规则同 /菜地。例：/牧场 羊毛 单价 → 只看羊毛类，按单价排序。",
    },
    {
        "cmd": "/物品列表",
        "what": "菜地 + 牧场的物品清单",
        "how": "把当前在售的作物与牧场产物名字全部列出来，只有名字。",
    },
    {
        "cmd": "/行情 [菜地|牧场] [小时]",
        "what": "近 N 小时行情峰值",
        "how": "默认菜地、24 小时。例：/行情 牧场 → 牧场产物近 24 小时峰值；/行情 菜地 48 → 近 48 小时。",
    },
]

def _raw_text(event: AstrMessageEvent) -> str | None:
    """用户发出的原始文本（未被唤醒前缀处理过）。"""
    obj = getattr(event, "message_obj", None)
    raw = getattr(obj, "message_str", None)
    if raw is not None:
        return str(raw)
    return getattr(event, "message_str", None)


def _has_slash(event: AstrMessageEvent) -> bool:
    """命令必须带 / 触发，不带斜杠就当普通聊天。"""
    return params.has_slash(_raw_text(event))


def _tokens(event: AstrMessageEvent) -> list[str]:
    """取出命令之后的参数列表。"""
    return params.tokens(getattr(event, "message_str", None))


@register(
    "astrbot_plugin_jusuo",
    "AstrBot",
    "王者荣耀世界居所助手：菜地/牧场高倍收购、物品清单与行情查询",
    VERSION,
)
class JusuoPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.api = JusuoAPI(
            base_url=self.config.get("supabase_url") or DEFAULT_BASE_URL,
            anon_key=self.config.get("anon_key") or DEFAULT_ANON_KEY,
            timeout=float(self.config.get("timeout") or 15),
            cache_ttl=int(self.config.get("cache_ttl") or 90),
        )

    async def initialize(self):
        """插件加载时打一行日志，方便在 AstrBot 日志里确认命令已注册。"""
        logger.info(
            f"[居所助手] 已加载 v{VERSION}，命令：/菜地 /牧场 /物品列表 /行情 /居所帮助 /居所测试"
        )

    async def terminate(self):
        await self.api.close()

    # ------------------------------------------------------------------ 渲染

    async def _send_card(self, event: AstrMessageEvent, card: dict):
        """出图：本地 Pillow 直接绘制（快、离线），失败退纯文本。"""
        if not self.config.get("use_image", True):
            return event.plain_result(card_to_text(card))
        try:
            data = await asyncio.to_thread(render_card, card)
            return event.chain_result([Image.fromBytes(data)])
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[居所助手] 本地绘制失败，改用纯文本: {exc}")
        return event.plain_result(card_to_text(card))

    async def _send_help(self, event: AstrMessageEvent):
        if not self.config.get("use_image", True):
            return event.plain_result("\n".join(self._help_text()))
        try:
            data = await asyncio.to_thread(
                render_card, help_rows_card(HELP_ITEMS, "所有命令都必须以 / 开头")
            )
            return event.chain_result([Image.fromBytes(data)])
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[居所助手] 帮助图绘制失败，改用纯文本: {exc}")
        return event.plain_result("\n".join(self._help_text()))

    @staticmethod
    def _help_text() -> list[str]:
        lines = ["【居所助手 命令一览】", "命令必须带 / 才触发"]
        for item in HELP_ITEMS:
            lines.append(f"{item['cmd']}\n  {item['what']} · {item['how']}")
        return lines

    # ------------------------------------------------------------------ 命令
    #
    # 两个要点：
    # 1. 必须「先 yield 结果、后 stop_event()」。若先 stop_event() 再 yield，
    #    调度器会在 yield 处发现事件已停止，跳过 RespondStage，消息就发不出去。
    # 2. 每个命令先用 _has_slash 拦一道：不带 / 的消息当普通聊天，交给 LLM。

    @filter.command("/菜地", alias={"菜地", "／菜地"})
    async def cmd_residence(self, event: AstrMessageEvent):
        """菜地作物高倍收购。"""
        if not _has_slash(event):
            return
        yield await self._entries_result(event, source="residence")
        event.stop_event()

    @filter.command("/牧场", alias={"牧场", "／牧场"})
    async def cmd_ranch(self, event: AstrMessageEvent):
        """牧场动物产物收购。"""
        if not _has_slash(event):
            return
        yield await self._entries_result(event, source="ranch")
        event.stop_event()

    @filter.command("/行情", alias={"行情", "／行情"})
    async def cmd_market(self, event: AstrMessageEvent):
        """近 N 小时行情峰值。"""
        if not _has_slash(event):
            return
        source = "crop"
        hours = int(self.config.get("market_hours") or 24)
        hours = max(6, min(hours, 168))
        for token in _tokens(event):
            if token in {"牧场", "ranch"}:
                source = "ranch"
            elif token in {"菜地", "crop"}:
                source = "crop"
            elif token.isdigit():
                hours = max(6, min(int(token), 168))
        label = "菜地" if source == "crop" else "牧场产物"
        try:
            matrix = await self.api.market_matrix(
                source=source, metric="price", hours=hours
            )
        except JusuoAPIError as exc:
            yield event.plain_result(f"居所助手取数失败：{exc}")
            event.stop_event()
            return
        card = market_card(
            matrix,
            source_label=label,
            metric="price",
            hours=hours,
            limit=int(self.config.get("max_items") or 10),
        )
        yield await self._send_card(event, card)
        event.stop_event()

    @filter.command("/居所帮助", alias={"居所帮助", "／居所帮助"})
    async def cmd_help(self, event: AstrMessageEvent):
        """命令一览。"""
        if not _has_slash(event):
            return
        yield await self._send_help(event)
        event.stop_event()

    @filter.command("/物品列表", alias={"物品列表", "／物品列表"})
    async def cmd_list(self, event: AstrMessageEvent):
        """菜地 + 牧场在售物品清单（只要名字）。"""
        if not _has_slash(event):
            return
        try:
            crops = await self.api.residence_entries(limit=500)
            ranch = await self.api.ranch_entries(limit=500)
            presets = await self.api.ranch_presets()
        except JusuoAPIError as exc:
            yield event.plain_result(f"居所助手取数失败：{exc}")
            event.stop_event()
            return

        crop_names = sorted({e.get("crop_name") for e in crops if e.get("crop_name")})
        ranch_names = sorted(
            {
                presets.get(e.get("product_preset_id"))
                for e in ranch
                if presets.get(e.get("product_preset_id"))
            }
        )

        lines = ["【菜地】" + ("、".join(crop_names) if crop_names else "暂无")]
        lines.append("【牧场】" + ("、".join(ranch_names) if ranch_names else "暂无"))
        yield event.plain_result("\n".join(lines))
        event.stop_event()

    @filter.command("/居所测试", alias={"居所测试", "／居所测试"})
    async def cmd_selftest(self, event: AstrMessageEvent):
        """自检：接口通不通、出图开没开。"""
        if not _has_slash(event):
            return
        lines = ["【居所助手自检】"]
        started = time.perf_counter()
        try:
            entries = await self.api.residence_entries(limit=5)
            cost = (time.perf_counter() - started) * 1000
            lines.append(f"数据接口：正常（样本 {len(entries)} 条，{cost:.0f}ms）")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"数据接口：失败 —— {exc}")
        lines.append(
            "出图方式：本地 Pillow 绘制（失败自动改纯文本）"
            if self.config.get("use_image", True)
            else "出图方式：纯文本（配置里关闭了 use_image）"
        )
        lines.append(f"插件版本：v{VERSION}")
        yield event.plain_result("\n".join(lines))
        event.stop_event()

    # ------------------------------------------------------------------ 内部

    async def _entries_result(self, event: AstrMessageEvent, source: str):
        """菜地 / 牧场共用的取数与出图逻辑，返回可直接 yield 的结果。"""
        args = params.parse_entries_args(_tokens(event))
        item_keyword, sort_mode = args.item_keyword, args.sort_mode
        page, min_mult, min_level = args.page, args.min_mult, args.min_level
        if sort_mode is None:
            sort_mode = str(self.config.get("default_sort_mode") or "sale").lower()
            if sort_mode not in {"unit", "sale"}:
                sort_mode = "sale"
        if min_mult is None and self.config.get("default_min_multiplier"):
            min_mult = float(self.config["default_min_multiplier"]) or None
        if min_level is None and self.config.get("default_min_level"):
            min_level = int(self.config["default_min_level"]) or None

        page_size = int(self.config.get("max_items") or 10)
        command_name = "/菜地" if source == "residence" else "/牧场"

        try:
            if source == "residence":
                entries = await self.api.residence_entries(
                    limit=int(self.config.get("fetch_limit") or 300)
                )
                prices = await self.api.unit_prices()
                card = entry_card(
                    entries,
                    prices,
                    title="菜地 · 高倍收购",
                    name_key="crop_name",
                    level_key="residence_level",
                    level_label="居所",
                    price_category="crop",
                    min_mult=min_mult,
                    min_level=min_level,
                    page_size=page_size,
                    page=page,
                    sort_mode=sort_mode,
                    hide_limited=bool(self.config.get("hide_limited", True)),
                    item_keyword=item_keyword,
                )
            else:
                entries = await self.api.ranch_entries(
                    limit=int(self.config.get("fetch_limit") or 300)
                )
                prices = await self.api.unit_prices()
                presets = await self.api.ranch_presets()
                for entry in entries:
                    entry["product_name"] = presets.get(
                        entry.get("product_preset_id"), "未知产物"
                    )
                card = entry_card(
                    entries,
                    prices,
                    title="牧场 · 高倍收购",
                    name_key="product_name",
                    level_key="animal_stall_level",
                    level_label="摊位",
                    price_category="ranch",
                    min_mult=min_mult,
                    min_level=min_level,
                    page_size=page_size,
                    page=page,
                    sort_mode=sort_mode,
                    hide_limited=bool(self.config.get("hide_limited", True)),
                    item_keyword=item_keyword,
                )
        except JusuoAPIError as exc:
            return event.plain_result(f"居所助手取数失败：{exc}")

        logger.info(
            f"[居所助手] {source} {sort_mode} p{page}：{len(card.get('rows') or [])} 条展示"
        )
        return await self._send_card(event, card)
