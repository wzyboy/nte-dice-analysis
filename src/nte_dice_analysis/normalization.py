import re
import difflib

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


def normalize_item_name(value: str, known_items: list[str]) -> str:
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
    return match if score >= 0.82 else cleaned


def comparable_item_text(value: str) -> str:
    return clean_text(value).translate(str.maketrans({'-': '·', '■': '·', '”': '·'}))


def normalize_datetime(value: str) -> str:
    compact = clean_text(value)
    date_match = re.search(
        r'(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日(?P<tail>.*)',
        compact,
    )
    if not date_match:
        return compact

    tail = date_match.group('tail')
    time_match = re.search(
        r'(?P<hour>\d{1,3}):(?P<minute>\d{2}):(?P<second>\d{2})',
        tail,
    )
    if time_match:
        hour_text = time_match.group('hour')[-2:]
        minute_text = time_match.group('minute')
        second_text = time_match.group('second')
    else:
        compact_time_match = re.search(r'(?P<hour_minute>\d{4}):(?P<second>\d{2})', tail)
        if not compact_time_match:
            return compact
        hour_minute = compact_time_match.group('hour_minute')
        hour_text = hour_minute[:2]
        minute_text = hour_minute[2:]
        second_text = compact_time_match.group('second')

    year = int(date_match.group('year'))
    month = int(date_match.group('month'))
    day = int(date_match.group('day'))
    hour = int(hour_text)
    minute = int(minute_text)
    second = int(second_text)
    return f'{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}'
