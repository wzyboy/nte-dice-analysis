from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

from .models import Record
from .models import OcrToken
from .models import PipelineOptions
from .visual import detect_pip_count
from .visual import detect_rarity_class
from .constants import COLUMN_BOUNDS
from .constants import GIFT_ROLL_POINTS
from .normalization import clean_text
from .normalization import normalize_datetime
from .normalization import normalize_quantity
from .normalization import normalize_item_name


def tokens_to_records(
    table_image: Image.Image,
    image_path: Path,
    pool_type: str,
    tokens: list[OcrToken],
    options: PipelineOptions,
    known_items: list[str],
) -> list[Record]:
    records: list[Record] = []
    for row_index in range(options.row_count):
        row_tokens = [token for token in tokens if token.row_index == row_index]
        by_column = {column: [token for token in row_tokens if token.column == column] for column in COLUMN_BOUNDS}

        roll_points = normalize_roll_points(
            joined_text(by_column['roll_points']),
            table_image,
            row_index,
            options,
        )

        quantity_raw = joined_text(by_column['quantity'])
        obtained_at_raw = joined_text(by_column['obtained_at'])
        item_name_raw = clean_text(joined_text(by_column['item_name']))
        scores = [token.score for token in row_tokens]

        record = Record(
            pool_type=pool_type,
            source_image=image_path,
            page_row=row_index + 1,
            roll_points=roll_points,
            item_name=normalize_item_name(item_name_raw, known_items),
            rarity=detect_rarity_class(table_image, row_index, options),
            item_name_raw=item_name_raw,
            quantity=normalize_quantity(quantity_raw),
            obtained_at=normalize_datetime(obtained_at_raw),
            obtained_at_raw=clean_text(obtained_at_raw),
            confidence=min(scores) if scores else None,
        )
        if record.item_name or record.obtained_at:
            records.append(record)

    return records


def joined_text(tokens: list[OcrToken]) -> str:
    sorted_tokens = sorted(tokens, key=lambda token: (token.box[0], token.box[1]))
    return ''.join(token.text for token in sorted_tokens)


def normalize_roll_points(
    value: str,
    table_image: Image.Image,
    row_index: int,
    options: PipelineOptions,
) -> str:
    cleaned = clean_text(value)
    pip_count = detect_pip_count(table_image, row_index, options)
    if pip_count:
        return str(pip_count)

    if cleaned == GIFT_ROLL_POINTS:
        return GIFT_ROLL_POINTS

    if re.fullmatch(r'[1-6]', cleaned):
        return cleaned

    return cleaned
