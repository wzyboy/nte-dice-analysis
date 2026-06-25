"""Deduplicate OCR records from overlapping NTE pull-history screenshots.

Assumptions:
- A timestamp is required; a missing timestamp means OCR/cropping failed.
- Within a pool, a timestamp identifies exactly one pull event.
- A valid event is 1 pull, 1 pull plus one gift, or 10 pulls plus one gift,
  plus any random bonus pulls.
- Arc research uses 10 records with the same timestamp and has no dice points or gifts.
- Exact normalized row content is overlap evidence, not a row identity. Fuzzy OCR
  correction happens before records reach this module.
"""

import re
from pathlib import Path
from itertools import product

from .models import Record
from .layouts import is_arc_pool_type
from .constants import GIFT_ROLL_POINTS
from .constants import BONUS_ROLL_POINTS
from .constants import SLEEPING_LAND_ROLL_POINTS


def deduplicate_records(records: list[Record]) -> list[Record]:
    """Reduce timestamp groups while preserving reverse chronological order."""
    require_timestamps(records)

    groups_by_key, group_order = timestamp_groups(deduplicated_records_in_page_order(records))

    deduped: list[Record] = []
    for group_key in sorted(group_order, key=dedup_group_sort_key, reverse=True):
        deduped.extend(deduplicate_timestamp_group(group_key, groups_by_key[group_key]))
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


def deduplicated_records_in_page_order(records: list[Record]) -> list[Record]:
    return [record for page in deduplicate_exact_pages(records_to_pages(records)) for record in page]


def timestamp_groups(records: list[Record]) -> tuple[dict[tuple[str, str], list[Record]], list[tuple[str, str]]]:
    groups_by_key: dict[tuple[str, str], list[Record]] = {}
    group_order: list[tuple[str, str]] = []

    for record in records:
        group_key = record_group_key(record)
        if group_key not in groups_by_key:
            groups_by_key[group_key] = []
            group_order.append(group_key)
        groups_by_key[group_key].append(record)

    return groups_by_key, group_order


def deduplicate_timestamp_group(group_key: tuple[str, str], records: list[Record]) -> list[Record]:
    pool_type, _ = group_key
    if is_arc_pool_type(pool_type):
        return deduplicate_arc_group(records)
    return deduplicate_dice_group(records)


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


def deduplicate_exact_pages(pages: list[list[Record]]) -> list[list[Record]]:
    deduped: list[list[Record]] = []
    indexes_by_key: dict[tuple[tuple[str, ...], ...], int] = {}

    for page in pages:
        key = page_match_key(page)
        existing_index = indexes_by_key.get(key)
        if existing_index is None:
            indexes_by_key[key] = len(deduped)
            deduped.append(page)
        else:
            deduped[existing_index] = merge_duplicate_page(deduped[existing_index], page)

    return deduped


def page_match_key(page: list[Record]) -> tuple[tuple[str, ...], ...]:
    return tuple(
        (
            str(record.page_row),
            record.pool_type,
            record.obtained_at,
            *record_match_key(record),
        )
        for record in page
    )


def merge_duplicate_page(existing: list[Record], candidate: list[Record]) -> list[Record]:
    return [
        better_record(existing_record, candidate_record)
        for existing_record, candidate_record in zip(existing, candidate, strict=True)
    ]


def deduplicate_dice_group(records: list[Record]) -> list[Record]:
    candidates = dice_group_candidates(records)
    valid_candidates = [candidate for candidate in candidates if valid_dice_pull_group(candidate)]
    if valid_candidates:
        return max(valid_candidates, key=valid_dice_candidate_sort_key)

    return min(candidates, key=invalid_dice_candidate_sort_key)


def valid_dice_candidate_sort_key(records: list[Record]) -> tuple[int, float]:
    return len(records), confidence_sum(records)


def invalid_dice_candidate_sort_key(records: list[Record]) -> tuple[int, float]:
    return len(records), -confidence_sum(records)


def confidence_sum(records: list[Record]) -> float:
    return sum(confidence_value(record) for record in records)


def dice_group_candidates(records: list[Record]) -> list[list[Record]]:
    choices_by_bucket = [
        dice_bucket_keep_choices(records, indexes) for indexes in record_indexes_by_match_key(records).values()
    ]
    candidates: list[list[Record]] = []
    for bucket_choices in product(*choices_by_bucket):
        kept_indexes = sorted({index for choice in bucket_choices for index in choice})
        candidates.append([records[index] for index in kept_indexes])
    return unique_record_lists(candidates)


def record_indexes_by_match_key(records: list[Record]) -> dict[tuple[str, ...], list[int]]:
    indexes_by_key: dict[tuple[str, ...], list[int]] = {}
    for index, record in enumerate(records):
        indexes_by_key.setdefault(record_match_key(record), []).append(index)
    return indexes_by_key


def dice_bucket_keep_choices(records: list[Record], indexes: list[int]) -> list[tuple[int, ...]]:
    min_keep_count = minimum_dice_bucket_keep_count(records, indexes)
    choices = [
        best_bucket_indexes(records, indexes, keep_count) for keep_count in range(min_keep_count, len(indexes) + 1)
    ]
    return unique_index_choices(choices)


def minimum_dice_bucket_keep_count(records: list[Record], indexes: list[int]) -> int:
    page_rows_by_source: dict[str, set[int]] = {}
    for index in indexes:
        record = records[index]
        page_rows_by_source.setdefault(str(record.source_image), set()).add(record.page_row)
    return max((len(page_rows) for page_rows in page_rows_by_source.values()), default=0)


def best_bucket_indexes(records: list[Record], indexes: list[int], keep_count: int) -> tuple[int, ...]:
    ranked_indexes = sorted(indexes, key=lambda index: (-confidence_value(records[index]), index))
    return tuple(sorted(ranked_indexes[:keep_count]))


def unique_index_choices(choices: list[tuple[int, ...]]) -> list[tuple[int, ...]]:
    unique_choices: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for choice in choices:
        if choice in seen:
            continue
        seen.add(choice)
        unique_choices.append(choice)
    return unique_choices


def unique_record_lists(candidates: list[list[Record]]) -> list[list[Record]]:
    unique_candidates: list[list[Record]] = []
    seen: set[tuple[tuple[str, ...], ...]] = set()
    for candidate in candidates:
        key = record_list_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)
    return unique_candidates


def record_list_key(records: list[Record]) -> tuple[tuple[str, ...], ...]:
    return tuple(record_identity_key(record) for record in records)


def record_identity_key(record: Record) -> tuple[str, ...]:
    return (
        str(record.source_image),
        str(record.page_row),
        record.pool_type,
        record.obtained_at,
        *record_match_key(record),
    )


def valid_dice_pull_group(group: list[Record]) -> bool:
    gift_count = sum(record.roll_points == GIFT_ROLL_POINTS for record in group)
    sleeping_land_count = sum(record.roll_points == SLEEPING_LAND_ROLL_POINTS for record in group)
    bonus_count = sum(record.roll_points in BONUS_ROLL_POINTS for record in group)
    pull_count = len(group) - bonus_count
    if sleeping_land_count > 1:
        return False
    if gift_count in {0, 1} and pull_count == 1:
        return True
    return gift_count == 1 and pull_count == 10


def deduplicate_arc_group(records: list[Record]) -> list[Record]:
    merged: list[Record] = []
    indexes_by_key: dict[tuple[str, ...], int] = {}

    for record in records:
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
    *,
    allow_single_record_overlap: bool = True,
) -> list[Record]:
    if not records:
        return list(fragment)

    record_keys = [record_match_key(record) for record in records]
    fragment_keys = [record_match_key(record) for record in fragment]

    subsequence_at = find_subsequence(record_keys, fragment_keys)
    if subsequence_at is not None and (len(fragment) > 1 or (len(records) == 1 and allow_single_record_overlap)):
        merged = list(records)
        for offset, record in enumerate(fragment):
            index = subsequence_at + offset
            merged[index] = better_record(merged[index], record)
        return merged

    containing_at = find_subsequence(fragment_keys, record_keys)
    if containing_at is not None and (len(records) > 1 or (len(fragment) == 1 and allow_single_record_overlap)):
        merged = list(fragment)
        for offset, record in enumerate(records):
            index = containing_at + offset
            merged[index] = better_record(merged[index], record)
        return merged

    max_overlap = min(len(records), len(fragment))
    for overlap in range(max_overlap, 0, -1):
        if record_keys[-overlap:] == fragment_keys[:overlap] and reliable_overlap(
            record_keys,
            fragment_keys,
            overlap,
            record_keys[-1],
            allow_single_record_overlap=allow_single_record_overlap,
        ):
            merged = list(records)
            for offset, record in enumerate(fragment[:overlap]):
                index = len(merged) - overlap + offset
                merged[index] = better_record(merged[index], record)
            merged.extend(fragment[overlap:])
            return merged

    for overlap in range(max_overlap, 0, -1):
        if record_keys[:overlap] == fragment_keys[-overlap:] and reliable_overlap(
            record_keys,
            fragment_keys,
            overlap,
            record_keys[0],
            allow_single_record_overlap=allow_single_record_overlap,
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
    *,
    allow_single_record_overlap: bool = True,
) -> bool:
    if overlap >= 2:
        return True

    if not allow_single_record_overlap:
        return False

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
        sleeping_land_count = sum(record.roll_points == SLEEPING_LAND_ROLL_POINTS for record in group)
        bonus_count = sum(record.roll_points in BONUS_ROLL_POINTS for record in group)
        pull_count = len(group) - bonus_count
        if sleeping_land_count > 1:
            errors.append(
                f'{pool_label} {timestamp}: expected at most 1 {SLEEPING_LAND_ROLL_POINTS} bonus; '
                f'found {sleeping_land_count} ({group_sources(group)})',
            )
            continue

        if gift_count in {0, 1} and pull_count == 1:
            continue
        if gift_count == 1 and pull_count == 10:
            continue

        errors.append(
            f'{pool_label} {timestamp}: expected 1 pull, 1 pull + {GIFT_ROLL_POINTS}, '
            f'or 10 pulls + {GIFT_ROLL_POINTS}, plus at most one {SLEEPING_LAND_ROLL_POINTS} bonus; '
            f'found {pull_count} pulls, {gift_count} {GIFT_ROLL_POINTS} gifts, and '
            f'{sleeping_land_count} {SLEEPING_LAND_ROLL_POINTS} bonuses ({group_sources(group)})',
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
