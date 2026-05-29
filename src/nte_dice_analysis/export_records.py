from pathlib import Path
from collections import defaultdict

from .io import load_json
from .dedup import require_timestamps
from .dedup import deduplicate_records
from .dedup import require_valid_pull_groups
from .models import Record
from .constants import S_CLASS
from .constants import GIFT_ROLL_POINTS


def load_records(json_paths: list[Path]) -> list[Record]:
    records: list[Record] = []
    for json_path in json_paths:
        if not json_path.exists():
            raise ValueError(f'JSON file not found: {json_path}')
        records.extend(load_json(json_path))
    return records


def prepare_export_records(
    json_paths: list[Path],
    *,
    deduplicate: bool,
) -> tuple[list[Record], int]:
    records = load_records(json_paths)
    raw_record_count = len(records)
    require_timestamps(records)

    if deduplicate:
        records = deduplicate_records(records)

    require_valid_pull_groups(records)
    return records, raw_record_count


def records_by_pool(records: list[Record]) -> dict[str, list[Record]]:
    grouped: dict[str, list[Record]] = defaultdict(list)
    for record in records:
        grouped[record.pool_type].append(record)
    return dict(grouped)


def split_item_type_name(value: str) -> tuple[str, str]:
    item_type, separator, item_name = value.partition('·')
    if not separator:
        return '', value
    return item_type, item_name


def pulls_since_last_s_character(records: list[Record]) -> list[int | None]:
    values: list[int | None] = []
    counter = 0

    for record in records:
        if record.roll_points == GIFT_ROLL_POINTS:
            values.append(None)
            continue

        counter += 1
        values.append(counter)

        if is_s_class_character(record):
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
