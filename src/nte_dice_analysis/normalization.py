import re
import difflib
from collections.abc import Sequence

from .constants import POOL_TYPES


def clean_text(value: str) -> str:
    return re.sub(r'\s+', '', value.strip())


def normalize_pool_type(value: str) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ''

    if cleaned in POOL_TYPES:
        return cleaned

    match = max(
        POOL_TYPES,
        key=lambda pool_type: difflib.SequenceMatcher(None, cleaned, pool_type).ratio(),
    )
    score = difflib.SequenceMatcher(None, cleaned, match).ratio()
    return match if score >= 0.75 else ''


def normalize_quantity(value: str) -> str:
    match = re.search(r'\d+', value)
    return match.group(0) if match else clean_text(value)


def normalize_item_name(value: str, known_items: Sequence[str]) -> str:
    cleaned = clean_text(value)
    if not cleaned or not known_items:
        return cleaned

    comparable = comparable_item_text(cleaned)
    match = max(
        known_items,
        key=lambda item: difflib.SequenceMatcher(
            None,
            comparable,
            comparable_item_text(item),
        ).ratio(),
    )
    score = difflib.SequenceMatcher(None, comparable, comparable_item_text(match)).ratio()
    if score >= 0.82:
        return match

    single_substitution_match = find_single_substitution_match(comparable, known_items)
    return single_substitution_match if single_substitution_match else cleaned


def find_single_substitution_match(comparable: str, known_items: Sequence[str]) -> str:
    candidates = [item for item in known_items if character_distance(comparable, comparable_item_text(item)) == 1]
    return candidates[0] if len(candidates) == 1 else ''


def character_distance(left: str, right: str) -> int:
    if len(left) != len(right):
        return max(len(left), len(right))
    return sum(left_char != right_char for left_char, right_char in zip(left, right, strict=True))


def comparable_item_text(value: str) -> str:
    return clean_text(value).translate(str.maketrans({'-': '·', '■': '·', '▪': '·', '”': '·'}))


def normalize_datetime(value: str) -> str:
    compact = clean_text(value)
    parsed = parse_chinese_datetime(compact)
    if parsed is None:
        return compact

    year, month, day, hour, minute, second = parsed
    return f'{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}'


def parse_chinese_datetime(value: str) -> tuple[int, int, int, int, int, int] | None:
    date_match = re.search(r'(?P<year>\d{4})年(?P<tail>.*)', value)
    if not date_match:
        return None

    year = int(date_match.group('year'))
    tail = date_match.group('tail')

    full_date_match = re.match(r'(?P<month>\d{1,2})月(?P<day>\d{1,2})日(?P<tail>.*)', tail)
    if full_date_match:
        month = int(full_date_match.group('month'))
        day = int(full_date_match.group('day'))
        parsed_time = parse_time(full_date_match.group('tail'))
        if valid_month_day(month, day) and parsed_time is not None:
            return year, month, day, *parsed_time

    month_match = re.match(r'(?P<month>\d{1,2})月(?P<tail>.*)', tail)
    if month_match:
        month = int(month_match.group('month'))
        parsed_day_time = parse_day_time(month_match.group('tail'))
        if parsed_day_time is not None:
            day, hour, minute, second = parsed_day_time
            if valid_month_day(month, day):
                return year, month, day, hour, minute, second

    parsed_compact = parse_compact_date_time(tail)
    if parsed_compact is None:
        return None

    month, day, hour, minute, second = parsed_compact
    return year, month, day, hour, minute, second


def parse_time(value: str) -> tuple[int, int, int] | None:
    time_match = re.search(
        r'(?P<hour>\d{1,3}):(?P<minute>\d{2}):(?P<second>\d{2})',
        value,
    )
    if time_match:
        hour_text = time_match.group('hour')[-2:]
        minute_text = time_match.group('minute')
        second_text = time_match.group('second')
    else:
        compact_time_match = re.search(r'(?P<hour_minute>\d{4}):(?P<second>\d{2})', value)
        if not compact_time_match:
            return None
        hour_minute = compact_time_match.group('hour_minute')
        hour_text = hour_minute[:2]
        minute_text = hour_minute[2:]
        second_text = compact_time_match.group('second')

    hour = int(hour_text)
    minute = int(minute_text)
    second = int(second_text)
    return hour, minute, second


def parse_day_time(value: str) -> tuple[int, int, int, int] | None:
    for day_length in (2, 1):
        day_text = value[:day_length]
        if not day_text.isdecimal():
            continue

        parsed_time = parse_time(value[day_length:])
        if parsed_time is None:
            continue

        day = int(day_text)
        if not 1 <= day <= 31:
            continue

        hour, minute, second = parsed_time
        return day, hour, minute, second

    return None


def parse_compact_date_time(value: str) -> tuple[int, int, int, int, int] | None:
    standard_time_match = re.fullmatch(
        r'(?P<head>\d+):(?P<minute>\d{2}):(?P<second>\d{2})',
        value,
    )
    if standard_time_match:
        parsed = parse_compact_standard_time(standard_time_match)
        if parsed is not None:
            return parsed

    compact_time_match = re.fullmatch(r'(?P<head>\d+):(?P<second>\d{2})', value)
    if not compact_time_match:
        return None

    head = compact_time_match.group('head')
    if len(head) < 6:
        return None

    month_day = parse_compact_month_day(head[:-4])
    if month_day is None:
        return None

    month, day = month_day
    hour = int(head[-4:-2])
    minute = int(head[-2:])
    second = int(compact_time_match.group('second'))
    return month, day, hour, minute, second


def parse_compact_standard_time(match: re.Match[str]) -> tuple[int, int, int, int, int] | None:
    head = match.group('head')
    for hour_length in (2, 1, 3):
        if len(head) <= hour_length:
            continue

        month_day = parse_compact_month_day(head[:-hour_length])
        if month_day is None:
            continue

        month, day = month_day
        hour = int(head[-hour_length:][-2:])
        minute = int(match.group('minute'))
        second = int(match.group('second'))
        return month, day, hour, minute, second

    return None


def parse_compact_month_day(value: str) -> tuple[int, int] | None:
    candidates: list[tuple[int, int]] = []
    for month_length in (1, 2):
        day_length = len(value) - month_length
        if day_length not in (1, 2):
            continue

        month = int(value[:month_length])
        day = int(value[month_length:])
        if valid_month_day(month, day):
            candidates.append((month, day))

    if len(candidates) != 1:
        return None

    return candidates[0]


def valid_month_day(month: int, day: int) -> bool:
    return 1 <= month <= 12 and 1 <= day <= 31
