"""Deduplicate OCR records from overlapping NTE pull-history screenshots.

Assumptions:
- A timestamp is required; a missing timestamp means OCR/cropping failed.
- Within a pool, a timestamp identifies exactly one pull event.
- A valid event is 1 pull, 1 pull plus one gift, or 10 pulls plus one gift.
- Arc research uses 10 records with the same timestamp and has no dice points or gifts.
- Dedup uses exact normalized row content only. Fuzzy OCR correction happens before
  records reach this module.
"""

import re
from pathlib import Path

from .models import Record
from .layouts import is_arc_pool_type
from .constants import GIFT_ROLL_POINTS


def deduplicate_records(records: list[Record]) -> list[Record]:
    """Merge exact overlapping fragments while preserving reverse chronological order."""
    require_timestamps(records)

    fragments_by_group: dict[tuple[str, str], list[list[Record]]] = {}
    group_order: list[tuple[str, str]] = []

    for page in records_to_pages(records):
        for fragment in timestamp_fragments(page):
            group_key = record_group_key(fragment[0])
            if group_key not in fragments_by_group:
                fragments_by_group[group_key] = []
                group_order.append(group_key)
            fragments_by_group[group_key].append(fragment)

    deduped: list[Record] = []
    for group_key in sorted(group_order, key=dedup_group_sort_key, reverse=True):
        deduped.extend(merge_group_fragments(group_key, fragments_by_group[group_key]))
    return deduped


def record_group_key(record: Record) -> tuple[str, str]:
    return record.pool_type, record.obtained_at


def dedup_group_sort_key(group_key: tuple[str, str]) -> tuple[int, str, str]:
    pool_type, timestamp = group_key
    timestamp_type, timestamp_value = timestamp_sort_key(timestamp)
    return timestamp_type, timestamp_value, pool_type


def timestamp_sort_key(timestamp: str) -> tuple[int, str]:
    if re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', timestamp):
        return 1, timestamp
    return 0, timestamp


def require_timestamps(records: list[Record]) -> None:
    errors = missing_timestamp_errors(records)
    if errors:
        details = '\n'.join(f'- {error}' for error in errors)
        raise ValueError(f'records have missing timestamps:\n{details}')


def missing_timestamp_errors(records: list[Record]) -> list[str]:
    errors: list[str] = []
    for record in records:
        if not record.obtained_at:
            errors.append(f'{record.source_image}, row {record.page_row}: missing obtained_at')
    return errors


def records_to_pages(records: list[Record]) -> list[list[Record]]:
    pages: list[list[Record]] = []
    current_source: Path | None = None
    current_page: list[Record] = []

    for record in records:
        source = record.source_image
        if current_source is not None and source != current_source:
            pages.append(sorted(current_page, key=page_row_number))
            current_page = []
        current_source = source
        current_page.append(record)

    if current_page:
        pages.append(sorted(current_page, key=page_row_number))

    return pages


def page_row_number(record: Record) -> int:
    return record.page_row


def timestamp_fragments(page: list[Record]) -> list[list[Record]]:
    fragments: list[list[Record]] = []
    current_group_key: tuple[str, str] | None = None
    current_fragment: list[Record] = []

    for record in page:
        group_key = record_group_key(record)
        if current_group_key is not None and group_key != current_group_key:
            fragments.append(current_fragment)
            current_fragment = []
        current_group_key = group_key
        current_fragment.append(record)

    if current_fragment:
        fragments.append(current_fragment)

    return fragments


def merge_fragments(fragments: list[list[Record]]) -> list[Record]:
    merged: list[Record] = []
    for fragment in fragments:
        merged = merge_fragment(merged, fragment)
    return merged


def merge_group_fragments(
    group_key: tuple[str, str],
    fragments: list[list[Record]],
) -> list[Record]:
    pool_type, _ = group_key
    if is_arc_pool_type(pool_type):
        return merge_arc_fragments(fragments)
    return merge_fragments(fragments)


def merge_arc_fragments(fragments: list[list[Record]]) -> list[Record]:
    merged: list[Record] = []
    indexes_by_key: dict[tuple[str, ...], int] = {}

    for fragment in fragments:
        for record in fragment:
            key = arc_exact_record_key(record)
            existing_index = indexes_by_key.get(key)
            if existing_index is None:
                indexes_by_key[key] = len(merged)
                merged.append(record)
            else:
                merged[existing_index] = better_record(merged[existing_index], record)

    return merged


def arc_exact_record_key(record: Record) -> tuple[str, ...]:
    return (
        str(record.source_image),
        str(record.page_row),
        record.pool_type,
        record.obtained_at,
        record.roll_points,
        record.item_name,
        record.rarity,
        record.quantity,
        record.research_type,
    )


def merge_fragment(
    records: list[Record],
    fragment: list[Record],
) -> list[Record]:
    if not records:
        return list(fragment)

    record_keys = [record_match_key(record) for record in records]
    fragment_keys = [record_match_key(record) for record in fragment]

    subsequence_at = find_subsequence(record_keys, fragment_keys)
    if subsequence_at is not None and (len(fragment) > 1 or len(records) == 1):
        merged = list(records)
        for offset, record in enumerate(fragment):
            index = subsequence_at + offset
            merged[index] = better_record(merged[index], record)
        return merged

    containing_at = find_subsequence(fragment_keys, record_keys)
    if containing_at is not None and (len(records) > 1 or len(fragment) == 1):
        merged = list(fragment)
        for offset, record in enumerate(records):
            index = containing_at + offset
            merged[index] = better_record(merged[index], record)
        return merged

    max_overlap = min(len(records), len(fragment))
    for overlap in range(max_overlap, 0, -1):
        if record_keys[-overlap:] == fragment_keys[:overlap] and reliable_overlap(
            record_keys, fragment_keys, overlap, record_keys[-1]
        ):
            merged = list(records)
            for offset, record in enumerate(fragment[:overlap]):
                index = len(merged) - overlap + offset
                merged[index] = better_record(merged[index], record)
            merged.extend(fragment[overlap:])
            return merged

    for overlap in range(max_overlap, 0, -1):
        if record_keys[:overlap] == fragment_keys[-overlap:] and reliable_overlap(
            record_keys, fragment_keys, overlap, record_keys[0]
        ):
            merged = list(fragment[:-overlap])
            for offset, record in enumerate(records[:overlap]):
                merged.append(better_record(fragment[-overlap + offset], record))
            merged.extend(records[overlap:])
            return merged

    return [*records, *fragment]


def find_subsequence(
    haystack: list[tuple[str, ...]],
    needle: list[tuple[str, ...]],
) -> int | None:
    if not needle or len(needle) > len(haystack):
        return None

    for index in range(len(haystack) - len(needle) + 1):
        if haystack[index : index + len(needle)] == needle:
            return index
    return None


def reliable_overlap(
    record_keys: list[tuple[str, ...]],
    fragment_keys: list[tuple[str, ...]],
    overlap: int,
    key: tuple[str, ...],
) -> bool:
    if overlap >= 2:
        return True

    return record_keys.count(key) == 1 and fragment_keys.count(key) == 1


def record_match_key(record: Record) -> tuple[str, ...]:
    return record.roll_points, record.item_name, record.rarity, record.quantity, record.research_type


def better_record(
    existing: Record,
    candidate: Record,
) -> Record:
    if confidence_value(candidate) > confidence_value(existing):
        return candidate
    return existing


def confidence_value(record: Record) -> float:
    return record.confidence or 0.0


def require_valid_pull_groups(records: list[Record]) -> None:
    require_timestamps(records)
    errors = pull_group_errors(records)
    if errors:
        details = '\n'.join(f'- {error}' for error in errors)
        raise ValueError(f'invalid pull groups:\n{details}')


def pull_group_errors(records: list[Record]) -> list[str]:
    errors: list[str] = []
    groups: dict[tuple[str, str], list[Record]] = {}
    for record in records:
        groups.setdefault(record_group_key(record), []).append(record)

    for (pool_type, timestamp), group in groups.items():
        if not timestamp:
            continue

        pool_label = pool_type or '<unknown pool>'
        if not pool_type:
            errors.append(f'{timestamp}: missing pool_type ({group_sources(group)})')
            continue

        if is_arc_pool_type(pool_type):
            errors.extend(arc_research_group_errors(pool_label, timestamp, group))
            continue

        gift_count = sum(record.roll_points == GIFT_ROLL_POINTS for record in group)
        pull_count = len(group) - gift_count
        if gift_count in {0, 1} and pull_count == 1:
            continue
        if gift_count == 1 and pull_count == 10:
            continue

        errors.append(
            f'{pool_label} {timestamp}: expected 1 pull, 1 pull + {GIFT_ROLL_POINTS}, '
            f'or 10 pulls + {GIFT_ROLL_POINTS}; found {pull_count} pulls and '
            f'{gift_count} gifts ({group_sources(group)})',
        )

    return errors


def arc_research_group_errors(pool_label: str, timestamp: str, group: list[Record]) -> list[str]:
    errors: list[str] = []
    gift_count = sum(record.roll_points == GIFT_ROLL_POINTS for record in group)
    dice_point_count = sum(bool(record.roll_points) and record.roll_points != GIFT_ROLL_POINTS for record in group)
    if gift_count:
        errors.append(
            f'{pool_label} {timestamp}: arc research does not support gifts; found {gift_count} gifts '
            f'({group_sources(group)})',
        )
    if dice_point_count:
        errors.append(
            f'{pool_label} {timestamp}: arc research does not support dice points; '
            f'found {dice_point_count} records with dice points ({group_sources(group)})',
        )
    if len(group) != 10:
        errors.append(
            f'{pool_label} {timestamp}: expected 10 arc research records; found {len(group)} ({group_sources(group)})',
        )
    return errors


def group_sources(records: list[Record]) -> str:
    return ', '.join(f'{record.source_image}, row {record.page_row}' for record in records)
