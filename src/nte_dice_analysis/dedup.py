from __future__ import annotations

import re

from .constants import GIFT_ROLL_POINTS


def deduplicate_records(records: list[dict[str, str]]) -> list[dict[str, str]]:
    fragments_by_group: dict[tuple[str, str], list[list[dict[str, str]]]] = {}
    group_order: list[tuple[str, str]] = []

    for page in records_to_pages(records):
        for fragment in timestamp_fragments(page):
            group_key = record_group_key(fragment[0])
            if group_key not in fragments_by_group:
                fragments_by_group[group_key] = []
                group_order.append(group_key)
            fragments_by_group[group_key].append(fragment)

    deduped: list[dict[str, str]] = []
    for group_key in sorted(group_order, key=dedup_group_sort_key, reverse=True):
        deduped.extend(merge_fragments(fragments_by_group[group_key]))
    return deduped


def record_group_key(record: dict[str, str]) -> tuple[str, str]:
    return record.get('pool_type', ''), record['obtained_at']


def dedup_group_sort_key(group_key: tuple[str, str]) -> tuple[int, str, str]:
    pool_type, timestamp = group_key
    timestamp_type, timestamp_value = timestamp_sort_key(timestamp)
    return timestamp_type, timestamp_value, pool_type


def timestamp_sort_key(timestamp: str) -> tuple[int, str]:
    if re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', timestamp):
        return 1, timestamp
    return 0, timestamp


def records_to_pages(records: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    pages: list[list[dict[str, str]]] = []
    current_source: str | None = None
    current_page: list[dict[str, str]] = []

    for record in records:
        source = record['source_image']
        if current_source is not None and source != current_source:
            pages.append(sorted(current_page, key=page_row_number))
            current_page = []
        current_source = source
        current_page.append(record)

    if current_page:
        pages.append(sorted(current_page, key=page_row_number))

    return pages


def page_row_number(record: dict[str, str]) -> int:
    try:
        return int(record['page_row'])
    except ValueError:
        return 0


def timestamp_fragments(page: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    fragments: list[list[dict[str, str]]] = []
    current_group_key: tuple[str, str] | None = None
    current_fragment: list[dict[str, str]] = []

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


def merge_fragments(fragments: list[list[dict[str, str]]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for fragment in fragments:
        merged = merge_fragment(merged, fragment)
    return merged


def merge_fragment(
    records: list[dict[str, str]],
    fragment: list[dict[str, str]],
) -> list[dict[str, str]]:
    if not records:
        return [record.copy() for record in fragment]

    record_keys = [record_match_key(record) for record in records]
    fragment_keys = [record_match_key(record) for record in fragment]

    subsequence_at = find_subsequence(record_keys, fragment_keys)
    if subsequence_at is not None and (len(fragment) > 1 or len(records) == 1):
        merged = [record.copy() for record in records]
        for offset, record in enumerate(fragment):
            index = subsequence_at + offset
            merged[index] = better_record(merged[index], record)
        return merged

    containing_at = find_subsequence(fragment_keys, record_keys)
    if containing_at is not None and (len(records) > 1 or len(fragment) == 1):
        merged = [record.copy() for record in fragment]
        for offset, record in enumerate(records):
            index = containing_at + offset
            merged[index] = better_record(merged[index], record)
        return merged

    max_overlap = min(len(records), len(fragment))
    for overlap in range(max_overlap, 0, -1):
        if (
            record_keys[-overlap:] == fragment_keys[:overlap]
            and reliable_overlap(record_keys, fragment_keys, overlap, record_keys[-1])
        ):
            merged = [record.copy() for record in records]
            for offset, record in enumerate(fragment[:overlap]):
                index = len(merged) - overlap + offset
                merged[index] = better_record(merged[index], record)
            merged.extend(record.copy() for record in fragment[overlap:])
            return merged

    for overlap in range(max_overlap, 0, -1):
        if (
            record_keys[:overlap] == fragment_keys[-overlap:]
            and reliable_overlap(record_keys, fragment_keys, overlap, record_keys[0])
        ):
            merged = [record.copy() for record in fragment[:-overlap]]
            for offset, record in enumerate(records[:overlap]):
                merged.append(better_record(fragment[-overlap + offset], record))
            merged.extend(record.copy() for record in records[overlap:])
            return merged

    return [*records, *(record.copy() for record in fragment)]


def find_subsequence(
    haystack: list[tuple[str, str, str]],
    needle: list[tuple[str, str, str]],
) -> int | None:
    if not needle or len(needle) > len(haystack):
        return None

    for index in range(len(haystack) - len(needle) + 1):
        if haystack[index : index + len(needle)] == needle:
            return index
    return None


def reliable_overlap(
    record_keys: list[tuple[str, str, str]],
    fragment_keys: list[tuple[str, str, str]],
    overlap: int,
    key: tuple[str, str, str],
) -> bool:
    if overlap >= 2:
        return True

    return record_keys.count(key) == 1 and fragment_keys.count(key) == 1


def record_match_key(record: dict[str, str]) -> tuple[str, str, str]:
    return record['roll_points'], record['item_name'], record['quantity']


def better_record(
    existing: dict[str, str],
    candidate: dict[str, str],
) -> dict[str, str]:
    if confidence_value(candidate) > confidence_value(existing):
        return candidate.copy()
    return existing.copy()


def confidence_value(record: dict[str, str]) -> float:
    try:
        return float(record['confidence'])
    except ValueError:
        return 0.0


def validate_pull_groups(records: list[dict[str, str]]) -> list[str]:
    warnings: list[str] = []
    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for record in records:
        groups.setdefault(record_group_key(record), []).append(record)

    for (pool_type, timestamp), group in groups.items():
        if not timestamp:
            continue

        pool_label = pool_type or '<unknown pool>'
        if not pool_type:
            warnings.append(f'{timestamp}: missing pool_type')

        gift_count = sum(record['roll_points'] == GIFT_ROLL_POINTS for record in group)
        pull_count = len(group) - gift_count
        if gift_count in {0, 1} and pull_count == 1:
            continue
        if gift_count == 1 and pull_count == 10:
            continue
        if gift_count == 0 and pull_count == 10:
            warnings.append(
                f'{pool_label} {timestamp}: found 10 pulls but no {GIFT_ROLL_POINTS}',
            )
            continue

        warnings.append(
            f'{pool_label} {timestamp}: expected 1 pull or 10 pulls + {GIFT_ROLL_POINTS}, '
            f'found {pull_count} pulls and {gift_count} gifts',
        )

    return warnings
