from pathlib import Path
from collections.abc import Callable
from collections.abc import Iterable

from .io import load_json
from .dedup import require_timestamps
from .dedup import deduplicate_records
from .dedup import require_valid_pull_groups
from .models import Record
from .layouts import is_arc_pool_type
from .constants import S_CLASS
from .constants import POOL_TYPES
from .constants import GIFT_ROLL_POINTS

type LoadProgressCallback = Callable[[Path, int, int], None]


def load_records(json_paths: list[Path], progress: LoadProgressCallback | None = None) -> list[Record]:
    records: list[Record] = []
    for index, json_path in enumerate(json_paths, start=1):
        if progress is not None:
            progress(json_path, index, len(json_paths))
        if not json_path.exists():
            raise ValueError(f'JSON file not found: {json_path}')
        records.extend(load_json(json_path))
    return records


def prepare_export_records(
    json_paths: list[Path],
    progress: LoadProgressCallback | None = None,
) -> tuple[list[Record], int]:
    records = load_records(json_paths, progress=progress)
    raw_record_count = len(records)
    require_timestamps(records)
    records = deduplicate_records(records)
    require_valid_pull_groups(records)
    return records, raw_record_count


def records_by_pool(records: list[Record]) -> dict[str, list[Record]]:
    grouped: dict[str, list[Record]] = {}
    for record in records:
        grouped.setdefault(record.pool_type, []).append(record)
    return {pool_type: grouped[pool_type] for pool_type in ordered_pool_types(grouped)}


def ordered_pool_types(pool_types: Iterable[str]) -> list[str]:
    pool_type_list = list(pool_types)
    ordered = [pool_type for pool_type in POOL_TYPES if pool_type in pool_type_list]
    ordered.extend(pool_type for pool_type in pool_type_list if pool_type not in POOL_TYPES)
    return ordered


def split_item_type_name(value: str) -> tuple[str, str]:
    item_type, separator, item_name = value.partition('·')
    if not separator:
        return '', value
    return item_type, item_name


def pulls_since_last_s_character(records: list[Record]) -> list[int | None]:
    return pulls_since_last_s(records, is_s_class_character)


def pulls_since_last_s_target(records: list[Record]) -> list[int | None]:
    return pulls_since_last_s(records, is_s_class_target)


def pulls_since_last_s(
    records: list[Record],
    is_s_class_record: Callable[[Record], bool],
) -> list[int | None]:
    values: list[int | None] = []
    counter = 0

    for record in records:
        if record.roll_points == GIFT_ROLL_POINTS:
            values.append(None)
            continue

        counter += 1
        values.append(counter)

        if is_s_class_record(record):
            counter = 0

    return values


def total_pull_counts(records: list[Record]) -> list[int | None]:
    values: list[int | None] = []
    total = 0

    for record in records:
        if record.roll_points == GIFT_ROLL_POINTS:
            values.append(None)
            continue

        total += 1
        values.append(total)

    return values


def is_s_class_character(record: Record) -> bool:
    return record.rarity == S_CLASS and record.item_name.startswith('角色·')


def is_s_class_target(record: Record) -> bool:
    if record.rarity != S_CLASS:
        return False
    if is_arc_pool_type(record.pool_type):
        return True
    return is_s_class_character(record)
