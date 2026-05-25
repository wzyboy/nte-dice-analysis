from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from PIL import Image

from .constants import COLUMN_BOUNDS, GIFT_ROLL_POINTS
from .normalization import clean_text, normalize_datetime, normalize_item_name, normalize_quantity
from .visual import detect_pip_count


def tokens_to_records(
    table_image: Image.Image,
    image_path: Path,
    pool_type: str,
    tokens: list[dict[str, Any]],
    args: argparse.Namespace,
    known_items: list[str],
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for row_index in range(args.row_count):
        row_tokens = [token for token in tokens if token['row_index'] == row_index]
        by_column = {
            column: [token for token in row_tokens if token['column'] == column]
            for column in COLUMN_BOUNDS
        }

        roll_points = normalize_roll_points(
            joined_text(by_column['roll_points']),
            table_image,
            row_index,
            args,
        )

        quantity_raw = joined_text(by_column['quantity'])
        obtained_at_raw = joined_text(by_column['obtained_at'])
        item_name_raw = clean_text(joined_text(by_column['item_name']))
        scores = [token['score'] for token in row_tokens]

        record = {
            'pool_type': pool_type,
            'source_image': str(image_path),
            'page_row': str(row_index + 1),
            'roll_points': roll_points,
            'item_name': normalize_item_name(item_name_raw, known_items),
            'item_name_raw': item_name_raw,
            'quantity': normalize_quantity(quantity_raw),
            'obtained_at': normalize_datetime(obtained_at_raw),
            'obtained_at_raw': clean_text(obtained_at_raw),
            'confidence': f'{min(scores):.3f}' if scores else '',
        }
        if record['item_name'] or record['obtained_at']:
            records.append(record)

    return records


def joined_text(tokens: list[dict[str, Any]]) -> str:
    sorted_tokens = sorted(tokens, key=lambda token: (token['box'][0], token['box'][1]))
    return ''.join(token['text'] for token in sorted_tokens)


def normalize_roll_points(
    value: str,
    table_image: Image.Image,
    row_index: int,
    args: argparse.Namespace,
) -> str:
    cleaned = clean_text(value)
    pip_count = detect_pip_count(table_image, row_index, args)
    if pip_count:
        return str(pip_count)

    if cleaned == GIFT_ROLL_POINTS:
        return GIFT_ROLL_POINTS

    if re.fullmatch(r'[1-6]', cleaned):
        return cleaned

    return cleaned
