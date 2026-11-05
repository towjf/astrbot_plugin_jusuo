"""命令行参数解析（纯字符串处理，不依赖 AstrBot，便于单元测试）。"""

from __future__ import annotations

import re
from typing import NamedTuple

SLASHES = ("/", "／")
"""命令触发用的斜杠：半角与全角。"""

_LEVEL_PATTERN = re.compile(r"^[Ll][Vv]?\d+$")

COMMAND_WORDS = (
    "菜地",
    "牧场",
    "行情",
    "物品列表",
    "居所帮助",
    "居所测试",
)
"""命令首词，用于把 "/菜地 草莓 单价" 与 "菜地 草莓 单价" 都还原成参数列表。"""

SORT_UNIT = {"单价", "单件", "单价优先", "unit"}
SORT_SALE = {"售价", "总价", "售价优先", "sale"}


class EntriesArgs(NamedTuple):
    """`/菜地`、`/牧场` 的解析结果。"""

    item_keyword: str
    """物品关键词，空字符串表示不过滤。"""

    sort_mode: str | None
    """`unit` 单价优先 / `sale` 售价优先 / None 表示用配置里的默认值。"""

    page: int
    """页码，从 1 开始。"""

    min_mult: float | None
    """最低倍率，None 表示不过滤。"""

    min_level: int | None
    """最低等级，None 表示不过滤。"""


def has_slash(raw_text: str | None) -> bool:
    """判断用户原始消息是否以斜杠开头（拿不到原文时不拦截）。"""
    if raw_text is None:
        return True
    text = str(raw_text).strip()
    if not text:
        return True
    return text.startswith(SLASHES)


def tokens(message_str: str | None) -> list[str]:
    """取出命令之后的参数列表。"""
    text = str(message_str or "").strip().lstrip("".join(SLASHES)).strip()
    parts = text.split()
    if parts and parts[0] in COMMAND_WORDS:
        parts = parts[1:]
    return parts


def parse_entries_args(argv: list[str]) -> EntriesArgs:
    """解析 `/菜地`、`/牧场` 的参数。

    支持的写法：
        /菜地                     → 全部物品，售价优先，第 1 页
        /菜地 草莓                 → 只看名字含「草莓」的
        /菜地 草莓 单价            → 单价优先
        /菜地 草莓 售价 2          → 售价优先第 2 页
        /菜地 倍率2 等级70 售价     → 附带过滤条件（可选）
    """
    sort_mode: str | None = None
    page = 1
    min_mult: float | None = None
    min_level: int | None = None
    words: list[str] = []

    for token in argv:
        text = str(token).strip()
        if not text:
            continue
        low = text.lower()

        if low in SORT_UNIT:
            sort_mode = "unit"
            continue
        if low in SORT_SALE:
            sort_mode = "sale"
            continue
        if text.startswith(("倍率", "×")):
            try:
                min_mult = float(text.lstrip("倍率×xX"))
            except ValueError:
                pass
            continue
        if text.startswith("等级"):
            digits = "".join(ch for ch in text if ch.isdigit())
            if digits:
                min_level = int(digits)
            continue
        if _LEVEL_PATTERN.match(text):
            min_level = int(text.lstrip("LlVv"))
            continue
        if text.endswith(("x", "X", "倍")) and text[:-1].replace(".", "").isdigit():
            try:
                min_mult = float(text.rstrip("xX倍"))
            except ValueError:
                pass
            continue
        if text.isdigit():
            page = max(1, int(text))
            continue
        words.append(text)

    return EntriesArgs(" ".join(words).strip(), sort_mode, page, min_mult, min_level)
