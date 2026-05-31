import math
from pathlib import Path
from dataclasses import dataclass

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

from . import summary as _summary
from .fonts import FontSpec
from .fonts import cjk_font
from .models import Record

COLUMN_WIDTH = 400
COLUMN_GAP = 40
PAGE_MARGIN_X = 38
PAGE_MARGIN_TOP = 34
PAGE_MARGIN_BOTTOM = 34
POOL_TITLE_Y = PAGE_MARGIN_TOP + 24
LEGEND_Y = PAGE_MARGIN_TOP + 70
PIE_TOP = PAGE_MARGIN_TOP + 142
PIE_SIZE = 210
SHAPE_SUPERSAMPLE_SCALE = 4
PNG_OUTPUT_SCALE = 2
DATE_Y = PAGE_MARGIN_TOP + 412
SUMMARY_Y = PAGE_MARGIN_TOP + 452
COUNTS_Y = PAGE_MARGIN_TOP + 492
HISTORY_Y = PAGE_MARGIN_TOP + 584


@dataclass(frozen=True)
class FontSet:
    title: ImageFont.FreeTypeFont | ImageFont.ImageFont
    body: ImageFont.FreeTypeFont | ImageFont.ImageFont
    small: ImageFont.FreeTypeFont | ImageFont.ImageFont


@dataclass(frozen=True)
class TextSegment:
    text: str
    color: _summary.RGBColor


@dataclass
class PieLabel:
    label: str
    edge_x: float
    edge_y: float
    label_x: float
    label_y: float
    side: str


def write_png(path: Path, records: list[Record]) -> None:
    summaries = _summary.summarize_records(records)
    fonts = load_fonts(PNG_OUTPUT_SCALE)
    history_lines = [wrap_history(summary, fonts.body, PNG_OUTPUT_SCALE) for summary in summaries]

    width = (
        scaled(PAGE_MARGIN_X, PNG_OUTPUT_SCALE) * 2
        + len(summaries) * scaled(COLUMN_WIDTH, PNG_OUTPUT_SCALE)
        + (len(summaries) - 1) * scaled(COLUMN_GAP, PNG_OUTPUT_SCALE)
    )
    height = image_height(history_lines, fonts, PNG_OUTPUT_SCALE)
    image = Image.new('RGB', (width, height), _summary.BACKGROUND)
    draw = ImageDraw.Draw(image)

    for index, summary in enumerate(summaries):
        x = scaled(PAGE_MARGIN_X, PNG_OUTPUT_SCALE) + index * scaled(
            COLUMN_WIDTH + COLUMN_GAP,
            PNG_OUTPUT_SCALE,
        )
        draw_pool_summary(image, draw, x, summary, history_lines[index], fonts, PNG_OUTPUT_SCALE)

    image.save(path, format='PNG')


def load_fonts(scale: int = 1) -> FontSet:
    regular = cjk_font()
    return FontSet(
        title=load_font(regular, scaled(27, scale)),
        body=load_font(regular, scaled(18, scale)),
        small=load_font(regular, scaled(16, scale)),
    )


def load_font(spec: FontSpec | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if spec is None:
        return ImageFont.load_default(size=size)
    try:
        font = ImageFont.truetype(str(spec.path), size=size, index=spec.index)
    except OSError:
        return ImageFont.load_default(size=size)
    if spec.variation is not None:
        apply_font_variation(font, spec.variation)
    return font


def apply_font_variation(font: ImageFont.FreeTypeFont, variation: str) -> None:
    try:
        font.set_variation_by_name(variation)
    except (AttributeError, OSError, ValueError):
        return


def image_height(history_lines: list[list[list[TextSegment]]], fonts: FontSet, scale: int = 1) -> int:
    history_line_height = line_height(fonts.body)
    max_history_lines = max((len(lines) for lines in history_lines), default=1)
    return max(
        scaled(820, scale),
        scaled(HISTORY_Y + 82 + PAGE_MARGIN_BOTTOM, scale) + max_history_lines * history_line_height,
    )


def draw_pool_summary(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    summary: _summary.PoolSummary,
    history_lines: list[list[TextSegment]],
    fonts: FontSet,
    scale: int = 1,
) -> None:
    draw_centered_text(
        draw,
        x + scaled(COLUMN_WIDTH, scale) // 2,
        scaled(POOL_TITLE_Y, scale),
        summary.pool_type,
        fonts.title,
        _summary.TEXT_COLOR,
    )
    draw_legend(
        image,
        draw,
        x + scaled(18, scale),
        scaled(LEGEND_Y, scale),
        summary.rarity_stats,
        fonts.body,
        scale,
    )
    draw_pie_chart(
        image,
        x + scaled(COLUMN_WIDTH - PIE_SIZE, scale) // 2,
        scaled(PIE_TOP, scale),
        scaled(PIE_SIZE, scale),
        summary,
        fonts,
        scale,
    )
    draw_centered_text(
        draw,
        x + scaled(COLUMN_WIDTH, scale) // 2,
        scaled(DATE_Y, scale),
        date_range_text(summary),
        fonts.body,
        _summary.TEXT_COLOR,
    )
    draw_centered_segments(
        draw,
        x + scaled(COLUMN_WIDTH, scale) // 2,
        scaled(SUMMARY_Y, scale),
        [
            TextSegment('一共 ', _summary.TEXT_COLOR),
            TextSegment(str(summary.total_pulls), _summary.BLUE_COLOR),
            TextSegment(' 抽 已累计 ', _summary.TEXT_COLOR),
            TextSegment(str(summary.current_pity), _summary.GREEN_COLOR),
            TextSegment(' 抽未出 S-Class 角色', _summary.TEXT_COLOR),
        ],
        fonts.body,
    )
    draw_counts(draw, x, scaled(COUNTS_Y, scale), summary, fonts.body, scale)
    draw_history(draw, x, scaled(HISTORY_Y, scale), summary, history_lines, fonts, scale)


def draw_legend(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    stats: list[_summary.RarityStat],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    scale: int = 1,
) -> None:
    cursor_x = x
    for stat in stats:
        paste_alpha(
            image,
            render_rounded_rectangle_image(
                scaled(38, scale),
                scaled(20, scale),
                scaled(5, scale),
                stat.color,
            ),
            (cursor_x, y + scaled(4, scale)),
        )
        draw.text((cursor_x + scaled(46, scale), y), stat.label, font=font, fill=_summary.TEXT_COLOR)
        cursor_x += scaled(126, scale)


def draw_pie_chart(
    image: Image.Image,
    x: int,
    y: int,
    size: int,
    summary: _summary.PoolSummary,
    fonts: FontSet,
    scale: int = 1,
) -> None:
    total = sum(stat.count for stat in summary.rarity_stats)
    draw = ImageDraw.Draw(image)
    if total == 0:
        paste_alpha(image, render_empty_pie_image(size), (x, y))
        draw_centered_text(
            draw,
            x + size // 2,
            y + size // 2 - scaled(10, scale),
            '无数据',
            fonts.body,
            _summary.MUTED_COLOR,
        )
        return

    paste_alpha(image, render_pie_image(size, summary.rarity_stats), (x, y))
    draw_pie_labels(image, draw, x, y, size, summary, fonts.small, scale)


def render_pie_image(size: int, stats: list[_summary.RarityStat]) -> Image.Image:
    scale = SHAPE_SUPERSAMPLE_SCALE
    scaled_size = size * scale
    image = Image.new('RGBA', (scaled_size, scaled_size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    bbox = (0, 0, scaled_size - 1, scaled_size - 1)
    total = sum(stat.count for stat in stats)
    if total == 0:
        return render_empty_pie_image(size)

    start = -90.0

    for stat in stats:
        if stat.count == 0:
            continue
        extent = 360 * stat.count / total
        draw.pieslice(bbox, start=start, end=start + extent, fill=stat.color + (255,))
        start += extent

    draw.ellipse(bbox, outline=_summary.BACKGROUND + (255,), width=2 * scale)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def render_empty_pie_image(size: int) -> Image.Image:
    scale = SHAPE_SUPERSAMPLE_SCALE
    scaled_size = size * scale
    image = Image.new('RGBA', (scaled_size, scaled_size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    bbox = (0, 0, scaled_size - 1, scaled_size - 1)
    draw.ellipse(bbox, outline=_summary.LEADER_COLOR + (255,), width=2 * scale)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def render_rounded_rectangle_image(
    width: int,
    height: int,
    radius: int,
    color: _summary.RGBColor,
) -> Image.Image:
    scale = SHAPE_SUPERSAMPLE_SCALE
    image = Image.new('RGBA', (width * scale, height * scale), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, width * scale - 1, height * scale - 1),
        radius=radius * scale,
        fill=color + (255,),
    )
    return image.resize((width, height), Image.Resampling.LANCZOS)


def draw_antialiased_line(
    image: Image.Image,
    start: tuple[float, float],
    end: tuple[float, float],
    color: _summary.RGBColor,
    width: int,
) -> None:
    overlay, xy = render_line_image(start, end, width, color)
    paste_alpha(image, overlay, xy)


def render_line_image(
    start: tuple[float, float],
    end: tuple[float, float],
    width: int,
    color: _summary.RGBColor,
) -> tuple[Image.Image, tuple[int, int]]:
    scale = SHAPE_SUPERSAMPLE_SCALE
    padding = max(width * 2, 2)
    left = math.floor(min(start[0], end[0]) - padding)
    top = math.floor(min(start[1], end[1]) - padding)
    right = math.ceil(max(start[0], end[0]) + padding)
    bottom = math.ceil(max(start[1], end[1]) + padding)
    local_width = max(1, right - left + 1)
    local_height = max(1, bottom - top + 1)
    image = Image.new('RGBA', (local_width * scale, local_height * scale), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.line(
        (
            (start[0] - left) * scale,
            (start[1] - top) * scale,
            (end[0] - left) * scale,
            (end[1] - top) * scale,
        ),
        fill=color + (255,),
        width=width * scale,
    )
    return image.resize((local_width, local_height), Image.Resampling.LANCZOS), (left, top)


def paste_alpha(image: Image.Image, overlay: Image.Image, xy: tuple[int, int]) -> None:
    image.paste(overlay.convert('RGB'), xy, overlay.getchannel('A'))


def draw_pie_labels(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    size: int,
    summary: _summary.PoolSummary,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    scale: int = 1,
) -> None:
    total = sum(stat.count for stat in summary.rarity_stats)
    center_x = x + size / 2
    center_y = y + size / 2
    radius = size / 2
    start = -90.0
    label_rows: list[PieLabel] = []

    for stat in summary.rarity_stats:
        if stat.count == 0:
            continue
        extent = 360 * stat.count / total
        middle = math.radians(start + extent / 2)
        edge_x = center_x + math.cos(middle) * radius
        edge_y = center_y + math.sin(middle) * radius
        label_x = center_x + math.cos(middle) * (radius + scaled(36, scale))
        label_y = center_y + math.sin(middle) * (radius + scaled(28, scale))
        label = stat.label
        label_rows.append(
            PieLabel(
                label=label,
                edge_x=edge_x,
                edge_y=edge_y,
                label_x=label_x,
                label_y=label_y,
                side='right' if label_x >= center_x else 'left',
            ),
        )
        start += extent

    adjusted_rows = adjust_label_rows(
        label_rows,
        y - scaled(8, scale),
        y + size + scaled(8, scale),
        line_height(font) + scaled(3, scale),
    )
    for row in adjusted_rows:
        label = row.label
        label_x = row.label_x
        label_y = row.label_y
        label_width = text_width(label, font)
        text_x = label_x if row.side == 'right' else label_x - label_width
        draw_antialiased_line(
            image,
            (row.edge_x, row.edge_y),
            (label_x, label_y),
            _summary.LEADER_COLOR,
            scaled(2, scale),
        )
        draw.text((text_x, label_y - line_height(font) / 2), label, font=font, fill=_summary.TEXT_COLOR)


def adjust_label_rows(
    rows: list[PieLabel],
    min_y: float,
    max_y: float,
    min_gap: int,
) -> list[PieLabel]:
    adjusted: list[PieLabel] = []
    for side in ('left', 'right'):
        side_rows = [copy_pie_label(row) for row in rows if row.side == side]
        side_rows.sort(key=lambda row: row.label_y)
        previous_y: float | None = None
        for row in side_rows:
            label_y = max(min_y, row.label_y)
            if previous_y is not None and label_y - previous_y < min_gap:
                label_y = previous_y + min_gap
            row.label_y = label_y
            previous_y = label_y

        if side_rows and side_rows[-1].label_y > max_y:
            offset = side_rows[-1].label_y - max_y
            for row in side_rows:
                row.label_y = max(min_y, row.label_y - offset)
        adjusted.extend(side_rows)
    return adjusted


def copy_pie_label(label: PieLabel) -> PieLabel:
    return PieLabel(
        label=label.label,
        edge_x=label.edge_x,
        edge_y=label.edge_y,
        label_x=label.label_x,
        label_y=label.label_y,
        side=label.side,
    )


def draw_counts(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    summary: _summary.PoolSummary,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    scale: int = 1,
) -> None:
    current_y = y
    for stat in summary.rarity_stats:
        draw.text(
            (x, current_y),
            f'{stat.label}: {stat.count}   [{format_percent(stat.percent)}]',
            font=font,
            fill=stat.color,
        )
        current_y += line_height(font) + scaled(3, scale)


def draw_history(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    summary: _summary.PoolSummary,
    history_lines: list[list[TextSegment]],
    fonts: FontSet,
    scale: int = 1,
) -> None:
    draw.text((x, y), 'S-Class 角色历史记录:', font=fonts.body, fill=_summary.TEXT_COLOR)
    current_y = y + line_height(fonts.body) + scaled(6, scale)
    for line in history_lines:
        draw_segments(draw, x, current_y, line, fonts.body)
        current_y += line_height(fonts.body) + scaled(3, scale)

    current_y += scaled(14, scale)
    average = _summary.format_average(summary.average_s_pulls)
    draw_segments(
        draw,
        x,
        current_y,
        [
            TextSegment('S-Class 角色平均出货次数为: ', _summary.TEXT_COLOR),
            TextSegment(average, _summary.GREEN_COLOR if average != '无' else _summary.MUTED_COLOR),
        ],
        fonts.body,
    )


def wrap_history(
    summary: _summary.PoolSummary,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    scale: int = 1,
) -> list[list[TextSegment]]:
    if not summary.s_history:
        return [[TextSegment('无', _summary.MUTED_COLOR)]]

    segments = [
        TextSegment(f'{item.name}[{item.pulls}]', _summary.history_color(item.name)) for item in summary.s_history
    ]
    return wrap_segments(segments, scaled(COLUMN_WIDTH, scale), font)


def wrap_segments(
    segments: list[TextSegment],
    max_width: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> list[list[TextSegment]]:
    lines: list[list[TextSegment]] = []
    current: list[TextSegment] = []
    current_width = 0
    space_width = text_width(' ', font)

    for segment in segments:
        segment_width = text_width(segment.text, font)
        next_width = segment_width if not current else current_width + space_width + segment_width
        if current and next_width > max_width:
            lines.append(current)
            current = [segment]
            current_width = segment_width
        else:
            current.append(segment)
            current_width = next_width

    if current:
        lines.append(current)
    return lines


def draw_segments(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    segments: list[TextSegment],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    cursor_x = x
    for index, segment in enumerate(segments):
        if index > 0:
            cursor_x += text_width(' ', font)
        draw.text((cursor_x, y), segment.text, font=font, fill=segment.color)
        cursor_x += text_width(segment.text, font)


def draw_centered_segments(
    draw: ImageDraw.ImageDraw,
    center_x: float,
    y: float,
    segments: list[TextSegment],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    total_width = sum(text_width(segment.text, font) for segment in segments)
    total_width += max(0, len(segments) - 1) * text_width(' ', font)
    draw_segments(draw, center_x - total_width / 2, y, segments, font)


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    center_x: float,
    y: float,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    color: _summary.RGBColor,
) -> None:
    draw.text((center_x - text_width(text, font) / 2, y), text, font=font, fill=color)


def text_width(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    return round(font.getlength(text))


def line_height(font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    left, top, right, bottom = font.getbbox('国Hg')
    return round(bottom - top)


def scaled(value: int, scale: int) -> int:
    return round(value * scale)


def date_range_text(summary: _summary.PoolSummary) -> str:
    if summary.date_start is None or summary.date_end is None:
        return '无记录'
    if summary.date_start == summary.date_end:
        return summary.date_start
    return f'{summary.date_start}  -  {summary.date_end}'


def format_percent(value: float) -> str:
    return f'{value:.2f}%'
