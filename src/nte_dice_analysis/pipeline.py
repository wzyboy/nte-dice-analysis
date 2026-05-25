from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from PIL import Image

from .geometry import crop_box_to_pixels, parse_crop
from .ocr import detect_pool_type, ocr_table
from .records import tokens_to_records
from .visual import draw_debug_image


def process_image(
    image_path: Path,
    ocr: Any,
    args: argparse.Namespace,
    known_items: list[str],
) -> list[dict[str, str]]:
    image = Image.open(image_path).convert('RGB')
    crop = parse_crop(args.table_crop)
    table_box = crop_box_to_pixels(crop, image.size)
    table_image = image.crop(table_box)
    pool_type = detect_pool_type(image, ocr, args)

    if args.debug_dir:
        args.debug_dir.mkdir(parents=True, exist_ok=True)
        table_image.save(args.debug_dir / f'{image_path.stem}_table.png')

    tokens = ocr_table(table_image, ocr, args)
    records = tokens_to_records(table_image, image_path, pool_type, tokens, args, known_items)

    if args.debug_dir:
        draw_debug_image(table_image, tokens, args, args.debug_dir / f'{image_path.stem}_boxes.png')

    return records
