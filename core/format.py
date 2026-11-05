"""数值与时间格式化工具。"""

from __future__ import annotations

from datetime import UTC, datetime


def parse_dt(value: str | None) -> datetime | None:
    """解析 Supabase 返回的时间字符串。"""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    # 兼容 "2026-11-08T14:39:43.372+00:00" 与 "...+00"
    if len(text) >= 3 and text[-3] in "+-" and text[-2:].isdigit():
        text = f"{text}:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _trim_decimal(text: str) -> str:
    """去掉小数部分的尾随零：'1558.0' -> '1558'，'1.20' -> '1.2'。"""
    if "." not in text:
        return text
    return text.rstrip("0").rstrip(".")


def fmt_money(value: float | int | None) -> str:
    """百工币金额：1234 -> 1234，12345678 -> 1234.6万。"""
    if value is None:
        return "-"
    number = float(value)
    if number < 0:
        return "-"
    if number >= 100_000_000:
        return f"{_trim_decimal(f'{number / 100_000_000:.2f}')}亿"
    if number >= 10_000:
        return f"{_trim_decimal(f'{number / 10_000:.1f}')}万"
    return f"{number:.0f}"


def fmt_count(value: float | int | None) -> str:
    """普通计数（数量等），带千分位。"""
    if value is None:
        return "-"
    return f"{int(value):,}"


def fmt_multiplier(value: float | None) -> str:
    if value is None:
        return "-"
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return f"{text}x"


def multiplier_tone(value: float | None) -> str:
    """倍率配色档位：gold / orange / green。"""
    if value is None:
        return "green"
    if value >= 2:
        return "gold"
    if value >= 1.8:
        return "orange"
    return "green"


def fmt_remaining(expires_at: str | datetime | None, now: datetime | None = None) -> str:
    """剩余时间：1天3时 / 5时12分 / 43分。"""
    dt = parse_dt(expires_at) if isinstance(expires_at, str) else expires_at
    if dt is None:
        return "-"
    now = now or datetime.now(UTC)
    seconds = (dt - now).total_seconds()
    if seconds <= 0:
        return "已过期"
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}天{hours}时"
    if hours:
        return f"{hours}时{minutes}分"
    return f"{max(1, minutes)}分"


def estimate_price(
    unit_price: float | None,
    level: int | None,
    multiplier: float | None,
    quantity: float | None,
    guild_maxed: bool | None,
) -> float | None:
    """按站点前端的公式估算出售总价（百工币）。"""
    if not unit_price or not multiplier or not quantity:
        return None
    level_value = level if (level and level > 0) else 0
    level_bonus = (level_value * 5 - 5) / 100
    guild_bonus = 0.2 if guild_maxed else 0
    total = (
        float(unit_price)
        * (1 + level_bonus)
        * float(multiplier)
        * float(quantity)
        * (1 + guild_bonus)
    )
    if total <= 0:
        return None
    return round(total)


def clip(text: str | None, length: int = 46) -> str:
    """截断长文本，避免卡片被撑爆。"""
    if not text:
        return ""
    clean = " ".join(str(text).replace("\r", " ").replace("\n", " ").split())
    if len(clean) <= length:
        return clean
    return clean[: length - 1] + "…"


def now_text(prefix: str = "更新") -> str:
    local = datetime.now().astimezone()
    return f"{prefix} {local.strftime('%m-%d %H:%M')}"
