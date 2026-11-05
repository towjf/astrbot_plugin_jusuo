"""Pillow 本地兜底渲染（t2i 出图失败时使用），与卡片同一份视图模型。

配色：深蓝底 + 蓝色强调；字号整体调大，PNG 直出保证清晰。
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 960
PADDING = 34

BG_TOP = (11, 25, 43)
BG_BOTTOM = (6, 13, 24)
PANEL_TOP = (24, 45, 73)
BORDER = (45, 80, 122)
TITLE = (244, 250, 255)
TEXT = (219, 233, 248)
MUTED = (144, 169, 196)
DIM = (95, 119, 147)
ACCENT = (125, 211, 252)
CYAN = (34, 211, 238)
RANK_FILL = (30, 58, 92)
RANK_TOP = (56, 189, 248)
DARK_INK = (4, 18, 31)
WARN = (252, 165, 165)

_FONT_CANDIDATES_BOLD = [
    ("C:/Windows/Fonts/msyhbd.ttc", 0),
    ("C:/Windows/Fonts/msyh.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
    ("/System/Library/Fonts/PingFang.ttc", 1),
    ("DejaVuSans-Bold.ttf", 0),
]
_FONT_CANDIDATES = [
    ("C:/Windows/Fonts/msyh.ttc", 0),
    ("C:/Windows/Fonts/msyhl.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
    ("DejaVuSans.ttf", 0),
]

_cache: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key in _cache:
        return _cache[key]
    for path, index in _FONT_CANDIDATES_BOLD if bold else _FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            font = ImageFont.truetype(path, size, index=index)
        except OSError:
            continue
        _cache[key] = font
        return font
    font = ImageFont.load_default(size)
    _cache[key] = font
    return font


def text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    return int(font.getlength(text))


def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        if char == "\n":
            lines.append(current)
            current = ""
            continue
        if text_width(current + char, font) > max_width and current:
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    return lines or [""]


def _gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]):
    width, height = size
    base = Image.new("RGB", (1, height))
    draw = ImageDraw.Draw(base)
    for y in range(height):
        ratio = y / max(1, height - 1)
        draw.point(
            (0, y),
            fill=(
                int(top[0] + (bottom[0] - top[0]) * ratio),
                int(top[1] + (bottom[1] - top[1]) * ratio),
                int(top[2] + (bottom[2] - top[2]) * ratio),
            ),
        )
    return base.resize((width, height), Image.Resampling.BILINEAR)


def render_card(card: dict) -> bytes:
    """把卡片视图模型渲染成 PNG 字节。"""
    return _render(card).getvalue()


def _render(card: dict) -> BytesIO:
    rows: list[dict] = card.get("rows") or []
    title_font = get_font(34, True)
    sub_font = get_font(16)
    name_font = get_font(22, True)
    meta_font = get_font(15)
    desc_font = get_font(15)
    price_font = get_font(25, True)
    small_font = get_font(13)
    badge_font = get_font(15, True)
    rank_font = get_font(16, True)
    uid_value_font = get_font(19, True)
    chip_font = get_font(14, True)

    content_width = WIDTH - PADDING * 2
    inner_width = content_width - 36 - 16 - 16 - 210

    # ---- 预排：行高 ----
    row_layouts = []
    for row in rows:
        lines = []
        if row.get("meta"):
            lines.extend(wrap("    ".join(row["meta"]), meta_font, inner_width))
        desc_lines = wrap(row["desc"], desc_font, inner_width) if row.get("desc") else []
        height = 16 + 28
        if lines:
            height += 8 + 20 * len(lines)
        if desc_lines:
            height += 8 + 20 * len(desc_lines)
        height += 16
        row_layouts.append((row, lines, desc_lines, max(height, 104)))

    sub_lines = (
        wrap(card.get("subtitle") or "", sub_font, content_width)
        if card.get("subtitle")
        else []
    )
    chips = card.get("chips") or []

    header_height = 34 + 36 + 16 + 42 + (8 + 24 * len(sub_lines) if sub_lines else 0)
    if chips:
        header_height += 16 + 34
    height = header_height + 22
    if row_layouts:
        height += sum(layout[3] + 12 for layout in row_layouts)
    else:
        empty_lines = wrap(card.get("empty_text") or "暂无数据", sub_font, content_width - 44)
        height += 36 + 26 * len(empty_lines) + 36
    height += 22 + 24 + 24  # footer

    canvas = _gradient((WIDTH, height), BG_TOP, BG_BOTTOM).convert("RGBA")
    glow = Image.new("RGBA", (WIDTH, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((WIDTH - 460, -360, WIDTH + 260, 200), fill=(56, 130, 246, 60))
    glow_draw.ellipse((-240, -280, 420, 140), fill=(34, 211, 238, 32))
    canvas = Image.alpha_composite(canvas, glow)
    draw = ImageDraw.Draw(canvas)

    y = 34
    # logo
    draw.rounded_rectangle((PADDING, y, PADDING + 36, y + 36), radius=12, fill=CYAN)
    draw.rounded_rectangle((PADDING + 5, y + 5, PADDING + 19, y + 19), radius=7, fill=(99, 102, 241))
    draw.text((PADDING + 48, y + 8), "居 所 助 手", font=chip_font, fill=ACCENT)
    stamp = card.get("stamp") or ""
    if stamp:
        draw.text(
            (WIDTH - PADDING, y + 10),
            stamp,
            font=get_font(14),
            fill=DIM,
            anchor="ra",
        )
    y += 36 + 16

    draw.text((PADDING, y), card.get("title") or "", font=title_font, fill=TITLE)
    y += 42 + 8

    for line in sub_lines:
        draw.text((PADDING, y), line, font=sub_font, fill=MUTED)
        y += 24
    if sub_lines:
        y += 8
    if chips:
        x = PADDING
        y_chip = y + 4
        for chip in chips:
            label = chip.get("text") if isinstance(chip, dict) else str(chip)
            strong = isinstance(chip, dict) and chip.get("gold")
            width = text_width(label, chip_font) + 28
            if strong:
                draw.rounded_rectangle(
                    (x, y_chip, x + width, y_chip + 32), radius=16, fill=CYAN
                )
                draw.text((x + 14, y_chip + 8), label, font=chip_font, fill=DARK_INK)
            else:
                draw.rounded_rectangle(
                    (x, y_chip, x + width, y_chip + 32),
                    radius=16,
                    fill=(26, 48, 78),
                    outline=(52, 90, 134),
                )
                draw.text((x + 14, y_chip + 8), label, font=chip_font, fill=ACCENT)
            x += width + 10
        y += 16 + 34

    y += 22

    # ---- 行 ----
    for row, meta_lines, desc_lines, row_height in row_layouts:
        draw.rounded_rectangle(
            (PADDING, y, WIDTH - PADDING, y + row_height),
            radius=18,
            fill=PANEL_TOP,
            outline=BORDER,
        )
        rank = row.get("rank") or 0
        top = rank <= 3
        draw.rounded_rectangle(
            (PADDING + 18, y + (row_height - 36) // 2, PADDING + 54, y + (row_height - 36) // 2 + 36),
            radius=12,
            fill=RANK_TOP if top else RANK_FILL,
        )
        rank_label = str(rank)
        draw.text(
            (
                PADDING + 18 + (36 - text_width(rank_label, rank_font)) / 2,
                y + (row_height - 36) // 2 + 9,
            ),
            rank_label,
            font=rank_font,
            fill=DARK_INK if top else (188, 217, 255),
        )

        text_x = PADDING + 18 + 36 + 16
        name_y = y + 16
        name = str(row.get("name") or "")
        while text_width(name, name_font) > inner_width and len(name) > 4:
            name = name[:-2] + "…"
        draw.text((text_x, name_y), name, font=name_font, fill=TITLE)
        cursor = text_x + text_width(name, name_font) + 12

        mult = row.get("mult")
        if mult:
            tone = row.get("tone") or "green"
            fill = {
                "gold": CYAN,
                "orange": (96, 165, 250),
                "green": (147, 197, 253),
            }.get(tone, (147, 197, 253))
            ink = DARK_INK if tone == "gold" else (6, 26, 51)
            m_width = text_width(mult, badge_font) + 20
            draw.rounded_rectangle(
                (cursor, name_y + 2, cursor + m_width, name_y + 30), radius=9, fill=fill
            )
            draw.text((cursor + 10, name_y + 6), mult, font=badge_font, fill=ink)
            cursor += m_width + 10

        for tag in row.get("tags") or []:
            label = tag.get("text") if isinstance(tag, dict) else str(tag)
            warn = isinstance(tag, dict) and tag.get("warn")
            color = WARN if warn else MUTED
            t_width = text_width(label, get_font(13)) + 18
            draw.rounded_rectangle(
                (cursor, name_y + 5, cursor + t_width, name_y + 27),
                radius=8,
                fill=(34, 56, 88) if not warn else (72, 42, 52),
                outline=(52, 80, 116) if not warn else (110, 56, 68),
            )
            draw.text((cursor + 9, name_y + 7), label, font=get_font(13), fill=color)
            cursor += t_width + 10

        text_y = name_y + 28 + 8
        for line in meta_lines:
            draw.text((text_x, text_y), line, font=meta_font, fill=MUTED)
            text_y += 20
        for line in desc_lines:
            draw.text((text_x, text_y + 2), line, font=desc_font, fill=DIM)
            text_y += 20

        # 右侧竖排：价格 → UID → 剩余时间（行距按字号逐行排）
        side_right = WIDTH - PADDING - 18
        price = row.get("price")
        if price:
            draw.text(
                (side_right, y + 12),
                price,
                font=price_font,
                fill=ACCENT,
                anchor="ra",
            )
        uid = str(row.get("uid") or "")
        if uid:
            draw.text(
                (side_right, y + 50),
                f"UID：{uid}",
                font=uid_value_font,
                fill=(188, 217, 255),
                anchor="ra",
            )
        when = row.get("time")
        if when:
            color = WARN if row.get("soon") else MUTED
            draw.text(
                (side_right, y + 76),
                when,
                font=get_font(13),
                fill=color,
                anchor="ra",
            )
        y += row_height + 12

    if not row_layouts:
        empty_lines = wrap(card.get("empty_text") or "暂无数据", sub_font, content_width - 44)
        box_height = 26 * len(empty_lines) + 44
        draw.rounded_rectangle(
            (PADDING, y, WIDTH - PADDING, y + box_height),
            radius=18,
            fill=(18, 34, 58),
            outline=BORDER,
        )
        text_y = y + 22
        for line in empty_lines:
            draw.text(
                ((WIDTH - text_width(line, sub_font)) // 2, text_y),
                line,
                font=sub_font,
                fill=MUTED,
            )
            text_y += 26

    # ---- 页脚 ----
    footer_y = height - 24 - 24
    draw.line((PADDING, footer_y, WIDTH - PADDING, footer_y), fill=BORDER, width=1)
    footer_font = get_font(13, True)
    draw.text(
        (PADDING, footer_y + 10), card.get("footer") or "", font=footer_font, fill=MUTED
    )
    source = card.get("source") or ""
    draw.text(
        (WIDTH - PADDING, footer_y + 10),
        source,
        font=footer_font,
        fill=MUTED,
        anchor="ra",
    )

    buffer = BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer


def save_png(card: dict, path: str | Path) -> str:
    data = render_card(card)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return str(path)


def save_image(card: dict, path: str | Path) -> str:
    """按扩展名保存卡片：`.webp` 无损（体积约为 PNG 的 1/5）、`.jpg` 有损，其余写 PNG。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = render_card(card)
    suffix = path.suffix.lower()
    if suffix == ".webp":
        with Image.open(BytesIO(data)) as image:
            image.convert("RGB").save(
                path, format="WEBP", lossless=True, method=6
            )
    elif suffix in {".jpg", ".jpeg"}:
        with Image.open(BytesIO(data)) as image:
            image.convert("RGB").save(
                path, format="JPEG", quality=92, subsampling=0, optimize=True
            )
    else:
        path.write_bytes(data)
    return str(path)
