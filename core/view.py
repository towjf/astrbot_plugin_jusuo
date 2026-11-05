"""把接口数据整理成卡片视图模型（绘制层只消费这份数据）。"""

from __future__ import annotations

from datetime import UTC, datetime

from .format import (
    estimate_price,
    fmt_count,
    fmt_money,
    fmt_multiplier,
    fmt_remaining,
    multiplier_tone,
    now_text,
    parse_dt,
)

SOURCE = "禁鬼有型&居所助手"
FOOTER = "数据来源jusuo.playmmo.cn"


def _empty_card(title: str, text: str) -> dict:
    return {
        "title": title,
        "subtitle": "",
        "stamp": now_text(),
        "chips": [],
        "rows": [],
        "empty_text": text,
        "footer": FOOTER,
        "source": SOURCE,
    }


def _base_card(title: str, subtitle: str, chips: list[dict]) -> dict:
    return {
        "title": title,
        "subtitle": subtitle,
        "stamp": now_text(),
        "chips": chips,
        "rows": [],
        "empty_text": "暂无符合条件的记录，试试放宽倍率或等级要求。",
        "footer": FOOTER,
        "source": SOURCE,
    }


def _row(
    rank: int,
    name: str,
    *,
    uid: str = "",
    mult: float | None = None,
    tags: list[dict] | None = None,
    meta: list[str] | None = None,
    desc: str = "",
    price: str = "",
    price_label: str = "",
    time: str = "",
    soon: bool = False,
) -> dict:
    return {
        "rank": rank,
        "name": name,
        "uid": str(uid or ""),
        "mult": fmt_multiplier(mult) if mult is not None else "",
        "tone": multiplier_tone(mult),
        "tags": tags or [],
        "meta": meta or [],
        "desc": desc,
        "price": price,
        "price_label": price_label,
        "time": time,
        "soon": soon,
    }


def _too_soon(expires_at: str | None, now: datetime, horizon_minutes: int = 60) -> bool:
    """一小时内过期的条目高亮提醒。"""
    dt = parse_dt(expires_at)
    if not dt:
        return False
    return 0 < (dt - now).total_seconds() <= horizon_minutes * 60


def _time_text(expires_at: str | None, now: datetime) -> str:
    remaining = fmt_remaining(expires_at, now)
    return "已过期" if remaining == "已过期" else f"剩余 {remaining}"


def _parse_created(value: str | None) -> str:
    dt = parse_dt(value)
    if not dt:
        return ""
    return dt.astimezone().strftime("%m-%d")


# ---------------------------------------------------------------- 居所 / 牧场


def entry_card(
    entries: list[dict],
    prices: dict[str, dict[str, float]],
    *,
    title: str,
    name_key: str,
    level_key: str,
    level_label: str,
    price_category: str,
    min_mult: float | None,
    min_level: int | None,
    page_size: int,
    page: int = 1,
    sort_mode: str = "sale",
    hide_limited: bool,
    item_keyword: str = "",
) -> dict:
    """居所作物 / 牧场产物共用的收购条目卡片（支持排序与翻页）。

    sort_mode:
        "sale" → 按售价（整批预估总价）优先；
        "unit" → 按单价（每件预估价格）优先。
    """
    now = datetime.now(UTC)
    unit_prices = prices.get(price_category, {})
    candidates: list[dict] = []

    for entry in entries:
        multiplier = entry.get("price_multiplier")
        level = entry.get(level_key)
        if min_mult is not None and (multiplier or 0) < min_mult:
            continue
        if min_level is not None and (level or 0) < min_level:
            continue
        if hide_limited and entry.get("is_limit_reached"):
            continue
        name = entry.get(name_key) or "未知物品"
        if item_keyword and item_keyword.lower() not in str(name).lower():
            continue
        quantity = entry.get("quantity") or 0
        total_price = entry.get("sale_price") or estimate_price(
            unit_prices.get(name),
            level,
            multiplier,
            quantity,
            entry.get("guild_maxed"),
        )
        unit_price = (
            round(total_price / quantity)
            if (total_price and quantity and quantity > 0)
            else None
        )
        candidates.append(
            {
                "entry": entry,
                "mult": float(multiplier or 0),
                "total": float(total_price or 0) if total_price else 0.0,
                "unit": float(unit_price or 0) if unit_price else 0.0,
            }
        )

    if sort_mode == "unit":
        candidates.sort(key=lambda c: (-c["unit"], -c["total"], -c["mult"]))
        sort_label = "单价优先"
    else:
        candidates.sort(key=lambda c: (-c["total"], -c["unit"], -c["mult"]))
        sort_label = "售价优先"

    total = len(candidates)
    pages = max(1, -(-total // page_size)) if total else 1
    page = min(max(1, page), pages)
    offset = (page - 1) * page_size
    page_items = candidates[offset : offset + page_size]

    chips = [{"text": sort_label, "gold": True}, {"text": f"第 {page}/{pages} 页"}]
    if item_keyword:
        chips.append({"text": f"物品：{item_keyword}"})
    if min_mult is not None:
        chips.append({"text": f"倍率 ≥ {fmt_multiplier(min_mult)}"})
    if min_level is not None:
        chips.append({"text": f"{level_label} ≥ {min_level}"})

    if total:
        subtitle = (
            f"共 {total} 条在售记录，按{sort_label}排序；"
            f"本页 {len(page_items)} 条（第 {offset + 1}-{offset + len(page_items)} 条）。"
        )
    else:
        subtitle = "当前没有符合条件的在售记录，试试去掉倍率/等级限制。"

    card = _base_card(title, subtitle, chips)

    for index, item in enumerate(page_items, start=offset + 1):
        entry = item["entry"]
        tags: list[dict] = []
        if entry.get("is_limit_reached"):
            tags.append({"text": "已限购", "warn": True})
        if entry.get("guild_maxed"):
            tags.append({"text": "满贡献"})
        if (entry.get("like_count") or 0) >= 10:
            tags.append({"text": f"赞 {entry.get('like_count')}"})

        # 右侧一律显示「预计售价」（整批总价）；两种排序模式只是顺序不同
        price_text = fmt_money(item["total"]) if item["total"] else ""

        meta = [f"数量 {fmt_count(entry.get('quantity'))}"]
        if item["unit"]:
            meta.append(f"单价 {fmt_money(item['unit'])}")
        meta.append(f"{level_label} Lv.{entry.get(level_key) or '-'}")
        meta.append(f"商人 {entry.get('merchant_name') or '-'}")

        card["rows"].append(
            _row(
                index,
                entry.get(name_key) or "未知物品",
                uid=entry.get("uid") or "",
                mult=item["mult"],
                tags=tags,
                meta=meta,
                price=price_text,
                time=_time_text(entry.get("expires_at"), now),
                soon=_too_soon(entry.get("expires_at"), now),
            )
        )
    return card


# ---------------------------------------------------------------- 行情


def market_card(
    matrix: dict,
    *,
    source_label: str,
    metric: str,
    hours: int,
    limit: int,
) -> dict:
    hours_axis = matrix.get("hours") or []
    items = matrix.get("items") or []
    cells = matrix.get("cells") or {}

    best: dict[int, tuple[float, int, dict]] = {}
    for key, cell in cells.items():
        try:
            hour_index, item_index = (int(part) for part in str(key).split(":"))
        except (ValueError, TypeError):
            continue
        value = cell.get("value") or 0
        if value <= 0:
            continue
        current = best.get(item_index)
        if current is None or value > current[0]:
            best[item_index] = (float(value), hour_index, cell.get("entry") or {})

    ranked = sorted(best.items(), key=lambda kv: -kv[1][0])
    total = len(ranked)
    ranked = ranked[:limit]

    metric_label = "最高估价" if metric == "price" else "最高数量"
    card = _base_card(
        f"行情 · {source_label}{metric_label}",
        f"近 {hours} 小时内共 {total} 种物品有记录，按{metric_label}排序展示前 {len(ranked)} 种。",
        [{"text": f"近 {hours} 小时", "gold": True}, {"text": "按物品取峰值"}],
    )

    for index, (item_index, (value, hour_index, entry)) in enumerate(ranked, start=1):
        name = entry.get("item_name") or (
            items[item_index] if item_index < len(items) else "未知物品"
        )
        when = hours_axis[hour_index] if hour_index < len(hours_axis) else ""
        meta = []
        if entry.get("quantity"):
            meta.append(f"数量 {fmt_count(entry.get('quantity'))}")
        if entry.get("stall_level"):
            meta.append(f"摊位 Lv.{entry.get('stall_level')}")
        if when:
            meta.append(f"时间 {when}")
        card["rows"].append(
            _row(
                index,
                name,
                uid=entry.get("uid") or "",
                mult=entry.get("price_multiplier"),
                meta=meta,
                price=fmt_money(value) if metric == "price" else fmt_count(value),
                price_label="百工币" if metric == "price" else "件",
            )
        )
    if not ranked:
        card["empty_text"] = "近几小时内没有该来源的成交记录。"
    return card


# ---------------------------------------------------------------- 单价表


def price_card(
    residence_entries: list[dict],
    ranch_entries: list[dict],
    prices: dict[str, dict[str, float]],
    *,
    page: int = 1,
    page_size: int = 10,
    hide_limited: bool = True,
) -> dict:
    """单价表：按物品取「预计售价」（整批预估总价）的峰值，而不是基础单价。"""
    now = datetime.now(UTC)
    best: dict[tuple[str, str], dict] = {}

    def scan(entries: list[dict], category: str, label: str, name_key: str, level_key: str):
        unit_prices = prices.get(category, {})
        for entry in entries:
            if hide_limited and entry.get("is_limit_reached"):
                continue
            name = entry.get(name_key) or "未知物品"
            quantity = entry.get("quantity") or 0
            total = entry.get("sale_price") or estimate_price(
                unit_prices.get(name),
                entry.get(level_key),
                entry.get("price_multiplier"),
                quantity,
                entry.get("guild_maxed"),
            )
            if not total:
                continue
            unit = round(total / quantity) if quantity else 0
            key = (label, name)
            current = best.get(key)
            if current is None or total > current["total"]:
                best[key] = {
                    "label": label,
                    "name": name,
                    "total": float(total),
                    "unit": float(unit),
                    "mult": float(entry.get("price_multiplier") or 0),
                    "level": entry.get(level_key),
                    "level_label": "居所" if category == "crop" else "摊位",
                    "quantity": quantity,
                    "merchant": entry.get("merchant_name") or "-",
                    "uid": entry.get("uid") or "",
                    "expires_at": entry.get("expires_at"),
                }

    scan(residence_entries, "crop", "作物", "crop_name", "residence_level")
    scan(ranch_entries, "ranch", "牧场", "product_name", "animal_stall_level")

    ranked = sorted(best.values(), key=lambda item: -item["total"])
    total_items = len(ranked)
    pages = max(1, -(-total_items // page_size)) if total_items else 1
    page = min(max(1, page), pages)
    offset = (page - 1) * page_size
    page_items = ranked[offset : offset + page_size]

    card = _base_card(
        "单价表 · 各物品预计售价",
        f"每种物品当前在售的最高「预计售价」（整批总价），共 {total_items} 种；"
        f"本页 {len(page_items)} 种（第 {offset + 1}-{offset + len(page_items)} 种）。",
        [{"text": "按预计售价排序", "gold": True}, {"text": f"第 {page}/{pages} 页"}],
    )
    card["footer"] = f"{FOOTER} · 翻页：/单价 N"
    card["empty_text"] = "当前没有在售记录可以估算售价。"

    for index, item in enumerate(page_items, start=offset + 1):
        card["rows"].append(
            _row(
                index,
                item["name"],
                uid=item["uid"],
                mult=item["mult"],
                tags=[{"text": item["label"]}],
                meta=[
                    f"数量 {fmt_count(item['quantity'])}",
                    f"单价 {fmt_money(item['unit'])}",
                    f"{item['level_label']} Lv.{item['level'] or '-'}",
                    f"商人 {item['merchant']}",
                ],
                price=fmt_money(item["total"]),
                time=_time_text(item["expires_at"], now),
                soon=_too_soon(item["expires_at"], now),
            )
        )
    return card


# ---------------------------------------------------------------- 帮助


def help_rows_card(items: list[dict], subtitle: str = "") -> dict:
    """帮助卡片的 Pillow 版：把命令铺成行，供本地兜底渲染。"""
    card = _base_card(
        "居所助手 · 命令一览",
        subtitle or "命令后面用空格跟参数，例：/菜地 草莓 单价 2。",
        [{"text": f"共 {len(items)} 条命令", "gold": True}],
    )
    for index, item in enumerate(items, start=1):
        card["rows"].append(
            _row(
                index,
                item["cmd"],
                meta=[item["what"]],
                desc=item["how"],
            )
        )
    return card


def error_card(title: str, message: str) -> dict:
    return _empty_card(title, message)
