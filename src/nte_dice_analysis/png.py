import math
import hashlib
import colorsys
from pathlib import Path
from dataclasses import dataclass

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

from .fonts import FontSpec
from .fonts import cjk_font
from .models import Record
from .constants import A_CLASS
from .constants import B_CLASS
from .constants import S_CLASS
from .constants import GIFT_ROLL_POINTS
from .export_records import records_by_pool
from .export_records import is_s_class_character
from .export_records import split_item_type_name
from .export_records import pulls_since_last_s_character

type RGBColor = tuple[int, int, int]

BACKGROUND = (255, 255, 255)
TEXT_COLOR = (51, 65, 85)
MUTED_COLOR = (148, 163, 184)
BLUE_COLOR = (37, 99, 235)
GREEN_COLOR = (22, 163, 74)
LEADER_COLOR = (203, 213, 225)
S_CLASS_COLOR = (245, 158, 11)
A_CLASS_COLOR = (124, 58, 237)
B_CLASS_COLOR = (156, 163, 175)

RARITY_ORDER = [S_CLASS, A_CLASS, B_CLASS]
RARITY_LABELS = {
    S_CLASS: 'S-Class',
    A_CLASS: 'A-Class',
    B_CLASS: 'B-Class',
}
RARITY_COLORS = {
    S_CLASS: S_CLASS_COLOR,
    A_CLASS: A_CLASS_COLOR,
    B_CLASS: B_CLASS_COLOR,
}
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
class RarityStat:
    rarity: str
    label: str
    count: int
    percent: float
    color: RGBColor


@dataclass(frozen=True)
class SClassHistoryItem:
    name: str
    pulls: int


@dataclass(frozen=True)
class PoolSummary:
    pool_type: str
    total_pulls: int
    date_start: str | None
    date_end: str | None
    current_pity: int
    rarity_stats: list[RarityStat]
    s_history: list[SClassHistoryItem]
    average_s_pulls: float | None


@dataclass(frozen=True)
class TextSegment:
    text: str
    color: RGBColor


@dataclass
class PieLabel:
    label: str
    edge_x: float
    edge_y: float
    label_x: float
    label_y: float
    side: str


def write_png(path: Path, records: list[Record]) -> None:
    summaries = summarize_records(records)
    fonts = load_fonts(PNG_OUTPUT_SCALE)
    history_lines = [wrap_history(summary, fonts.body, PNG_OUTPUT_SCALE) for summary in summaries]

    width = (
        scaled(PAGE_MARGIN_X, PNG_OUTPUT_SCALE) * 2
        + len(summaries) * scaled(COLUMN_WIDTH, PNG_OUTPUT_SCALE)
        + (len(summaries) - 1) * scaled(COLUMN_GAP, PNG_OUTPUT_SCALE)
    )
    height = image_height(history_lines, fonts, PNG_OUTPUT_SCALE)
    image = Image.new('RGB', (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    for index, summary in enumerate(summaries):
        x = scaled(PAGE_MARGIN_X, PNG_OUTPUT_SCALE) + index * scaled(
            COLUMN_WIDTH + COLUMN_GAP,
            PNG_OUTPUT_SCALE,
        )
        draw_pool_summary(image, draw, x, summary, history_lines[index], fonts, PNG_OUTPUT_SCALE)

    image.save(path, format='PNG')


def format_text_summary(records: list[Record]) -> str:
    return '\n\n'.join(format_pool_text_summary(summary) for summary in summarize_records(records))


def format_pool_text_summary(summary: PoolSummary) -> str:
    history = ' '.join(f'{item.name}[{item.pulls}]' for item in summary.s_history)
    if not history:
        history = '无'
    return '\n'.join(
        [
            summary.pool_type,
            f'一共 {summary.total_pulls} 抽 已累计 {summary.current_pity} 抽未出 S-Class 角色',
            f'S-Class 角色历史记录: {history}',
            f'S-Class 角色平均出货次数为: {format_average(summary.average_s_pulls)}',
        ],
    )


def summarize_records(records: list[Record]) -> list[PoolSummary]:
    grouped = records_by_pool(records)
    if not grouped:
        return [summarize_pool('Records', [])]
    return [summarize_pool(pool_type or 'unknown pool', pool_records) for pool_type, pool_records in grouped.items()]


def summarize_pool(pool_type: str, records: list[Record]) -> PoolSummary:
    oldest_first = list(reversed(records))
    pull_records = [record for record in oldest_first if not is_gift_record(record)]
    total_pulls = len(pull_records)
    rarity_counts = {rarity: sum(record.rarity == rarity for record in pull_records) for rarity in RARITY_ORDER}
    rarity_stats = [
        RarityStat(
            rarity=rarity,
            label=RARITY_LABELS[rarity],
            count=rarity_counts[rarity],
            percent=percentage(rarity_counts[rarity], total_pulls),
            color=RARITY_COLORS[rarity],
        )
        for rarity in RARITY_ORDER
    ]
    date_values = [record.obtained_at[:10] for record in oldest_first if record.obtained_at]
    s_history = s_class_history(oldest_first)
    average_s_pulls = sum(item.pulls for item in s_history) / len(s_history) if s_history else None
    return PoolSummary(
        pool_type=pool_type,
        total_pulls=total_pulls,
        date_start=date_values[0] if date_values else None,
        date_end=date_values[-1] if date_values else None,
        current_pity=current_pity_count(oldest_first),
        rarity_stats=rarity_stats,
        s_history=s_history,
        average_s_pulls=average_s_pulls,
    )


def is_gift_record(record: Record) -> bool:
    return record.roll_points == GIFT_ROLL_POINTS


def percentage(count: int, total: int) -> float:
    if total == 0:
        return 0
    return count / total * 100


def current_pity_count(records_oldest_first: list[Record]) -> int:
    current = 0
    for record in records_oldest_first:
        if is_gift_record(record):
            continue
        if is_s_class_character(record):
            current = 0
        else:
            current += 1
    return current


def s_class_history(records_oldest_first: list[Record]) -> list[SClassHistoryItem]:
    history: list[SClassHistoryItem] = []
    pulls_since_last_s = pulls_since_last_s_character(records_oldest_first)
    for record, pulls_since in zip(records_oldest_first, pulls_since_last_s, strict=True):
        if pulls_since is None or not is_s_class_character(record):
            continue
        _, item_name = split_item_type_name(record.item_name)
        history.append(SClassHistoryItem(name=item_name or record.item_name, pulls=pulls_since))
    return history


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
    summary: PoolSummary,
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
        TEXT_COLOR,
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
        TEXT_COLOR,
    )
    draw_centered_segments(
        draw,
        x + scaled(COLUMN_WIDTH, scale) // 2,
        scaled(SUMMARY_Y, scale),
        [
            TextSegment('一共 ', TEXT_COLOR),
            TextSegment(str(summary.total_pulls), BLUE_COLOR),
            TextSegment(' 抽 已累计 ', TEXT_COLOR),
            TextSegment(str(summary.current_pity), GREEN_COLOR),
            TextSegment(' 抽未出 S-Class 角色', TEXT_COLOR),
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
    stats: list[RarityStat],
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
        draw.text((cursor_x + scaled(46, scale), y), stat.label, font=font, fill=TEXT_COLOR)
        cursor_x += scaled(126, scale)


def draw_pie_chart(
    image: Image.Image,
    x: int,
    y: int,
    size: int,
    summary: PoolSummary,
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
            MUTED_COLOR,
        )
        return

    paste_alpha(image, render_pie_image(size, summary.rarity_stats), (x, y))
    draw_pie_labels(image, draw, x, y, size, summary, fonts.small, scale)


def render_pie_image(size: int, stats: list[RarityStat]) -> Image.Image:
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

    draw.ellipse(bbox, outline=BACKGROUND + (255,), width=2 * scale)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def render_empty_pie_image(size: int) -> Image.Image:
    scale = SHAPE_SUPERSAMPLE_SCALE
    scaled_size = size * scale
    image = Image.new('RGBA', (scaled_size, scaled_size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    bbox = (0, 0, scaled_size - 1, scaled_size - 1)
    draw.ellipse(bbox, outline=LEADER_COLOR + (255,), width=2 * scale)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def render_rounded_rectangle_image(width: int, height: int, radius: int, color: RGBColor) -> Image.Image:
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
    color: RGBColor,
    width: int,
) -> None:
    overlay, xy = render_line_image(start, end, width, color)
    paste_alpha(image, overlay, xy)


def render_line_image(
    start: tuple[float, float],
    end: tuple[float, float],
    width: int,
    color: RGBColor,
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
    summary: PoolSummary,
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
            LEADER_COLOR,
            scaled(2, scale),
        )
        draw.text((text_x, label_y - line_height(font) / 2), label, font=font, fill=TEXT_COLOR)


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
    summary: PoolSummary,
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
    summary: PoolSummary,
    history_lines: list[list[TextSegment]],
    fonts: FontSet,
    scale: int = 1,
) -> None:
    draw.text((x, y), 'S-Class 角色历史记录:', font=fonts.body, fill=TEXT_COLOR)
    current_y = y + line_height(fonts.body) + scaled(6, scale)
    for line in history_lines:
        draw_segments(draw, x, current_y, line, fonts.body)
        current_y += line_height(fonts.body) + scaled(3, scale)

    current_y += scaled(14, scale)
    average = format_average(summary.average_s_pulls)
    draw_segments(
        draw,
        x,
        current_y,
        [
            TextSegment('S-Class 角色平均出货次数为: ', TEXT_COLOR),
            TextSegment(average, GREEN_COLOR if average != '无' else MUTED_COLOR),
        ],
        fonts.body,
    )


def wrap_history(
    summary: PoolSummary,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    scale: int = 1,
) -> list[list[TextSegment]]:
    if not summary.s_history:
        return [[TextSegment('无', MUTED_COLOR)]]

    segments = [TextSegment(f'{item.name}[{item.pulls}]', history_color(item.name)) for item in summary.s_history]
    return wrap_segments(segments, scaled(COLUMN_WIDTH, scale), font)


def history_color(value: str) -> RGBColor:
    digest = hashlib.sha256(value.encode('utf-8')).digest()
    hue = int.from_bytes(digest[:2], 'big') / 65535
    saturation = 0.72
    value_brightness = 0.78
    red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value_brightness)
    return round(red * 255), round(green * 255), round(blue * 255)


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
    color: RGBColor,
) -> None:
    draw.text((center_x - text_width(text, font) / 2, y), text, font=font, fill=color)


def text_width(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    return round(font.getlength(text))


def line_height(font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    left, top, right, bottom = font.getbbox('国Hg')
    return round(bottom - top)


def scaled(value: int, scale: int) -> int:
    return round(value * scale)


def date_range_text(summary: PoolSummary) -> str:
    if summary.date_start is None or summary.date_end is None:
        return '无记录'
    if summary.date_start == summary.date_end:
        return summary.date_start
    return f'{summary.date_start}  -  {summary.date_end}'


def format_percent(value: float) -> str:
    return f'{value:.2f}%'


def format_average(value: float | None) -> str:
    if value is None:
        return '无'
    return f'{value:.2f}'.rstrip('0').rstrip('.')
