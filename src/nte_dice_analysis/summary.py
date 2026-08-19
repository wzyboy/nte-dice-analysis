import hashlib
import colorsys
from functools import partial
from dataclasses import dataclass
from collections.abc import Callable

from .io import load_known_items
from .models import Record
from .layouts import is_arc_pool_type
from .constants import A_CLASS
from .constants import B_CLASS
from .constants import S_CLASS
from .known_items import KnownItems
from .export_records import records_by_pool
from .export_records import is_s_class_target
from .export_records import pulls_since_last_s
from .export_records import is_bonus_pull_record
from .export_records import split_item_type_name

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
    average_all_s_pulls: float | None = None


def format_text_summary(records: list[Record], known_items: KnownItems | None = None) -> str:
    return '\n\n'.join(
        format_pool_text_summary(summary) for summary in summarize_records(records, known_items=known_items)
    )


def format_pool_text_summary(summary: PoolSummary) -> str:
    target_name = '弧盘' if is_arc_pool_type(summary.pool_type) else '角色'
    history = ' '.join(f'{item.name}[{item.pulls}]' for item in summary.s_history)
    if not history:
        history = '无'
    if is_arc_pool_type(summary.pool_type):
        return '\n'.join(
            [
                summary.pool_type,
                f'一共 {summary.total_pulls} 抽 已累计 {summary.current_pity} 抽未出限定 S-Class 弧盘',
                f'S-Class 弧盘历史记录（限定）: {history}',
                'S-Class 弧盘平均出货次数: '
                f'限定 {format_average(summary.average_s_pulls)} / '
                f'全部 {format_average(summary.average_all_s_pulls)}',
            ],
        )
    return '\n'.join(
        [
            summary.pool_type,
            f'一共 {summary.total_pulls} 抽 已累计 {summary.current_pity} 抽未出 S-Class {target_name}',
            f'S-Class {target_name}历史记录: {history}',
            f'S-Class {target_name}平均出货次数: {format_average(summary.average_s_pulls)}',
        ],
    )


def summarize_records(records: list[Record], known_items: KnownItems | None = None) -> list[PoolSummary]:
    effective_known_items = load_known_items() if known_items is None else known_items
    grouped = records_by_pool(records)
    if not grouped:
        return [summarize_pool('Records', [], known_items=effective_known_items)]
    return [
        summarize_pool(pool_type or 'unknown pool', pool_records, known_items=effective_known_items)
        for pool_type, pool_records in grouped.items()
    ]


def summarize_pool(
    pool_type: str,
    records: list[Record],
    known_items: KnownItems | None = None,
) -> PoolSummary:
    effective_known_items = load_known_items() if known_items is None else known_items
    oldest_first = list(reversed(records))
    pull_records = [record for record in oldest_first if not is_bonus_pull_record(record)]
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
    all_s_history = s_class_history(oldest_first, is_s_class_target)
    is_arc_pool = is_arc_pool_type(pool_type)
    is_summary_target = is_s_class_target
    if is_arc_pool:
        is_summary_target = partial(is_limited_s_arc, known_items=effective_known_items)
    s_history = s_class_history(oldest_first, is_summary_target)
    return PoolSummary(
        pool_type=pool_type,
        total_pulls=total_pulls,
        date_start=date_values[0] if date_values else None,
        date_end=date_values[-1] if date_values else None,
        current_pity=current_pity_count(oldest_first, is_summary_target),
        rarity_stats=rarity_stats,
        s_history=s_history,
        average_s_pulls=average_history_pulls(s_history),
        average_all_s_pulls=average_history_pulls(all_s_history) if is_arc_pool else None,
    )


def percentage(count: int, total: int) -> float:
    if total == 0:
        return 0
    return count / total * 100


def current_pity_count(
    records_oldest_first: list[Record],
    is_s_class_record: Callable[[Record], bool] = is_s_class_target,
) -> int:
    current = 0
    for record in records_oldest_first:
        if is_bonus_pull_record(record):
            continue
        if is_s_class_record(record):
            current = 0
        else:
            current += 1
    return current


def s_class_history(
    records_oldest_first: list[Record],
    is_s_class_record: Callable[[Record], bool] = is_s_class_target,
) -> list[SClassHistoryItem]:
    history: list[SClassHistoryItem] = []
    pulls_since_last_s_values = pulls_since_last_s(records_oldest_first, is_s_class_record)
    for record, pulls_since in zip(records_oldest_first, pulls_since_last_s_values, strict=True):
        if pulls_since is None or not is_s_class_record(record):
            continue
        item_name = summary_item_name(record)
        history.append(SClassHistoryItem(name=item_name or record.item_name, pulls=pulls_since))
    return history


def average_history_pulls(history: list[SClassHistoryItem]) -> float | None:
    if not history:
        return None
    return sum(item.pulls for item in history) / len(history)


def is_limited_s_arc(record: Record, known_items: KnownItems) -> bool:
    return (
        is_arc_pool_type(record.pool_type)
        and record.rarity == S_CLASS
        and known_items.is_limited_s_item(record.pool_type, record.item_name)
    )


def summary_item_name(record: Record) -> str:
    if is_arc_pool_type(record.pool_type):
        return record.item_name
    _, item_name = split_item_type_name(record.item_name)
    return item_name


def history_color(value: str) -> RGBColor:
    digest = hashlib.sha256(value.encode('utf-8')).digest()
    hue = int.from_bytes(digest[:2], 'big') / 65535
    saturation = 0.72
    value_brightness = 0.78
    red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value_brightness)
    return round(red * 255), round(green * 255), round(blue * 255)


def format_average(value: float | None) -> str:
    if value is None:
        return '无'
    return f'{value:.2f}'.rstrip('0').rstrip('.')
