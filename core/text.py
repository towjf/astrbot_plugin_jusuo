"""纯文本兜底输出。"""

from __future__ import annotations


def card_to_text(card: dict, limit: int = 12) -> str:
    lines: list[str] = [f"【{card.get('title') or '居所助手'}】"]
    subtitle = card.get("subtitle")
    if subtitle:
        lines.append(subtitle)
    rows = card.get("rows") or []
    if not rows:
        lines.append(card.get("empty_text") or "暂无数据")
    for row in rows[:limit]:
        parts = [f"{row.get('rank')}. {row.get('name')}"]
        if row.get("mult"):
            parts.append(row["mult"])
        if row.get("price"):
            label = row.get("price_label") or ""
            parts.append(f"{label} {row['price']}".strip())
        lines.append(" ".join(parts))
        extra = list(row.get("meta") or [])
        if row.get("uid"):
            extra.insert(0, f"UID：{row['uid']}")
        if row.get("time"):
            extra.append(row["time"])
        if extra:
            lines.append("   " + " · ".join(extra))
        if row.get("desc"):
            lines.append(f"   {row['desc']}")
    stamp = card.get("stamp")
    if stamp:
        lines.append(f"— {stamp} · {card.get('footer') or ''} · {card.get('source') or ''}")
    return "\n".join(lines)
