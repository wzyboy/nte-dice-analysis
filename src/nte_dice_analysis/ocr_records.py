from __future__ import annotations

import argparse
import csv
import difflib
import json
import os
import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


DEFAULT_TABLE_CROP = '0.1823,0.4259,0.8281,0.7870'
DEFAULT_DET_MODEL = 'PP-OCRv5_server_det'
DEFAULT_REC_MODEL = 'PP-OCRv5_server_rec'

COLUMN_BOUNDS = {
    'roll_points': (0.00, 0.22),
    'item_name': (0.22, 0.50),
    'quantity': (0.50, 0.68),
    'obtained_at': (0.68, 1.00),
}

CSV_FIELDS = [
    'source_image',
    'page_row',
    'roll_points',
    'item_name',
    'item_name_raw',
    'quantity',
    'obtained_at',
    'obtained_at_raw',
    'confidence',
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Extract NTE gacha records from table screenshots with PaddleOCR.',
    )
    parser.add_argument('images', nargs='+', type=Path)
    parser.add_argument('--out', type=Path, default=Path('records.csv'))
    parser.add_argument('--json-out', type=Path, default=Path('records.json'))
    parser.add_argument('--debug-dir', type=Path)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--table-crop', default=DEFAULT_TABLE_CROP)
    parser.add_argument('--row-count', type=int, default=5)
    parser.add_argument('--row-top', type=float, default=0.17)
    parser.add_argument('--row-bottom', type=float, default=0.95)
    parser.add_argument('--min-score', type=float, default=0.3)
    parser.add_argument('--known-items', type=Path, default=Path('known_items.txt'))
    parser.add_argument(
        '--det-model-dir',
        type=Path,
        default=default_model_dir(DEFAULT_DET_MODEL),
    )
    parser.add_argument(
        '--rec-model-dir',
        type=Path,
        default=default_model_dir(DEFAULT_REC_MODEL),
    )
    return parser.parse_args(argv)


def default_model_dir(model_name: str) -> Path:
    return Path.home() / '.paddlex' / 'official_models' / model_name


def parse_crop(value: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in value.split(',')]
    if len(parts) != 4:
        raise ValueError('crop must have four comma-separated values')
    return tuple(float(part) for part in parts)  # type: ignore[return-value]


def crop_box_to_pixels(
    crop: tuple[float, float, float, float],
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    width, height = image_size
    if max(crop) <= 1:
        x0, y0, x1, y1 = (
            round(crop[0] * width),
            round(crop[1] * height),
            round(crop[2] * width),
            round(crop[3] * height),
        )
    else:
        x0, y0, x1, y1 = (round(value) for value in crop)

    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError(f'crop {x0},{y0},{x1},{y1} is outside image {width}x{height}')
    return x0, y0, x1, y1


def create_ocr(args: argparse.Namespace) -> Any:
    os.environ.setdefault('DISABLE_MODEL_SOURCE_CHECK', 'True')

    from paddleocr import PaddleOCR

    return PaddleOCR(
        text_detection_model_dir=str(args.det_model_dir),
        text_recognition_model_dir=str(args.rec_model_dir),
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device=args.device,
    )


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

    if args.debug_dir:
        args.debug_dir.mkdir(parents=True, exist_ok=True)
        table_image.save(args.debug_dir / f'{image_path.stem}_table.png')

    tokens = ocr_table(table_image, ocr, args)
    records = tokens_to_records(table_image, image_path, tokens, args, known_items)

    if args.debug_dir:
        draw_debug_image(table_image, tokens, args, args.debug_dir / f'{image_path.stem}_boxes.png')

    return records


def ocr_table(
    table_image: Image.Image,
    ocr: Any,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    result = ocr.predict(np.array(table_image))[0]
    texts = result.get('rec_texts', [])
    scores = result.get('rec_scores', [])
    boxes = result.get('rec_boxes', [])

    tokens: list[dict[str, Any]] = []
    width, height = table_image.size
    row_area_top = args.row_top * height
    row_area_bottom = args.row_bottom * height
    row_height = (row_area_bottom - row_area_top) / args.row_count

    for text, score, box in zip(texts, scores, boxes, strict=False):
        text = str(text).strip()
        score = float(score)
        if not text or score < args.min_score:
            continue

        x0, y0, x1, y1 = normalize_box(box)
        center_x = (x0 + x1) / 2
        center_y = (y0 + y1) / 2
        if center_y < row_area_top or center_y >= row_area_bottom:
            continue

        row_index = int((center_y - row_area_top) // row_height)
        if row_index < 0 or row_index >= args.row_count:
            continue

        column = column_for_x(center_x / width)
        if column is None:
            continue

        tokens.append(
            {
                'text': text,
                'score': score,
                'box': (x0, y0, x1, y1),
                'row_index': row_index,
                'column': column,
            },
        )

    return tokens


def normalize_box(box: Any) -> tuple[float, float, float, float]:
    values = box.tolist() if hasattr(box, 'tolist') else box
    if len(values) == 4 and not isinstance(values[0], list | tuple):
        x0, y0, x1, y1 = values
        return float(x0), float(y0), float(x1), float(y1)

    xs = [point[0] for point in values]
    ys = [point[1] for point in values]
    return float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))


def column_for_x(x_ratio: float) -> str | None:
    for column, (left, right) in COLUMN_BOUNDS.items():
        if left <= x_ratio < right:
            return column
    return None


def tokens_to_records(
    table_image: Image.Image,
    image_path: Path,
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

        roll_points = joined_text(by_column['roll_points'])
        if not roll_points:
            pip_count = detect_pip_count(table_image, row_index, args)
            roll_points = str(pip_count) if pip_count else ''

        quantity_raw = joined_text(by_column['quantity'])
        obtained_at_raw = joined_text(by_column['obtained_at'])
        item_name_raw = clean_text(joined_text(by_column['item_name']))
        scores = [token['score'] for token in row_tokens]

        record = {
            'source_image': str(image_path),
            'page_row': str(row_index + 1),
            'roll_points': clean_text(roll_points),
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


def clean_text(value: str) -> str:
    return re.sub(r'\s+', '', value.strip())


def normalize_quantity(value: str) -> str:
    match = re.search(r'\d+', value)
    return match.group(0) if match else clean_text(value)


def normalize_item_name(value: str, known_items: list[str]) -> str:
    cleaned = clean_text(value)
    if not cleaned or not known_items:
        return cleaned

    match = max(
        known_items,
        key=lambda item: difflib.SequenceMatcher(None, cleaned, item).ratio(),
    )
    score = difflib.SequenceMatcher(None, cleaned, match).ratio()
    return match if score >= 0.82 else cleaned


def normalize_datetime(value: str) -> str:
    compact = clean_text(value)
    match = re.search(
        r'(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日.*?'
        r'(?P<hour>\d{1,2}):(?P<minute>\d{2}):(?P<second>\d{2})',
        compact,
    )
    if not match:
        return compact

    year = int(match.group('year'))
    month = int(match.group('month'))
    day = int(match.group('day'))
    hour = int(match.group('hour'))
    minute = int(match.group('minute'))
    second = int(match.group('second'))
    return f'{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}'


def detect_pip_count(
    table_image: Image.Image,
    row_index: int,
    args: argparse.Namespace,
) -> int | None:
    width, height = table_image.size
    scale = min(width / 2480, height / 780)
    row_area_top = args.row_top * height
    row_area_bottom = args.row_bottom * height
    row_height = (row_area_bottom - row_area_top) / args.row_count
    x0 = round(0.02 * width)
    x1 = round(0.20 * width)
    y0 = round(row_area_top + row_index * row_height)
    y1 = round(row_area_top + (row_index + 1) * row_height)
    point_cell = table_image.crop((x0, y0, x1, y1))

    dark_components = connected_components(
        point_cell,
        lambda rgb: rgb[0] < 110 and rgb[1] < 110 and rgb[2] < 110,
    )
    icon_candidates = [
        component
        for component in dark_components
        if component['area'] >= scaled_area(1200, scale)
        and scaled(35, scale) <= component['width'] <= scaled(130, scale)
        and scaled(35, scale) <= component['height'] <= scaled(130, scale)
    ]
    if not icon_candidates:
        return None

    icon = max(icon_candidates, key=lambda component: component['area'])
    icon_image = point_cell.crop((icon['x0'], icon['y0'], icon['x1'] + 1, icon['y1'] + 1))
    margin = scaled(2, scale)
    white_components = connected_components(
        icon_image,
        lambda rgb: rgb[0] > 175 and rgb[1] > 175 and rgb[2] > 175,
    )

    pips = [
        component
        for component in white_components
        if scaled_area(35, scale) <= component['area'] <= scaled_area(500, scale)
        and scaled(5, scale) <= component['width'] <= scaled(30, scale)
        and scaled(5, scale) <= component['height'] <= scaled(30, scale)
        and component['area'] / (component['width'] * component['height']) > 0.55
        and component['x0'] > margin
        and component['y0'] > margin
    ]
    return len(pips) or None


def scaled(value: int, scale: float) -> int:
    return max(1, round(value * scale))


def scaled_area(value: int, scale: float) -> int:
    return max(1, round(value * scale * scale))


def connected_components(
    image: Image.Image,
    predicate: Any,
) -> list[dict[str, int]]:
    pixels = image.load()
    width, height = image.size
    mask = {
        (x, y)
        for y in range(height)
        for x in range(width)
        if predicate(pixels[x, y])
    }

    components: list[dict[str, int]] = []
    while mask:
        start = mask.pop()
        stack = [start]
        xs: list[int] = []
        ys: list[int] = []
        while stack:
            x, y = stack.pop()
            xs.append(x)
            ys.append(y)
            for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if neighbor in mask:
                    mask.remove(neighbor)
                    stack.append(neighbor)

        x0 = min(xs)
        y0 = min(ys)
        x1 = max(xs)
        y1 = max(ys)
        components.append(
            {
                'area': len(xs),
                'x0': x0,
                'y0': y0,
                'x1': x1,
                'y1': y1,
                'width': x1 - x0 + 1,
                'height': y1 - y0 + 1,
            },
        )

    return components


def draw_debug_image(
    table_image: Image.Image,
    tokens: list[dict[str, Any]],
    args: argparse.Namespace,
    output_path: Path,
) -> None:
    debug = table_image.copy()
    draw = ImageDraw.Draw(debug)
    width, height = debug.size

    row_area_top = args.row_top * height
    row_area_bottom = args.row_bottom * height
    row_height = (row_area_bottom - row_area_top) / args.row_count
    for row_index in range(args.row_count + 1):
        y = row_area_top + row_index * row_height
        draw.line((0, y, width, y), fill='blue', width=2)

    for _, (_, right) in COLUMN_BOUNDS.items():
        x = right * width
        draw.line((x, 0, x, height), fill='green', width=2)

    for token in tokens:
        x0, y0, x1, y1 = token['box']
        draw.rectangle((x0, y0, x1, y1), outline='red', width=3)
        draw.text((x0, max(0, y0 - 20)), token['column'], fill='red')

    debug.save(output_path)


def write_csv(path: Path, records: list[dict[str, str]]) -> None:
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)


def write_json(path: Path, records: list[dict[str, str]]) -> None:
    with path.open('w', encoding='utf-8') as file:
        json.dump(records, file, ensure_ascii=False, indent=2)
        file.write('\n')


def load_known_items(path: Path) -> list[str]:
    if not path.exists():
        return []

    return [
        line.strip()
        for line in path.read_text(encoding='utf-8-sig').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    ]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    ocr = create_ocr(args)
    known_items = load_known_items(args.known_items)

    records: list[dict[str, str]] = []
    for image_path in args.images:
        records.extend(process_image(image_path, ocr, args, known_items))

    write_csv(args.out, records)
    write_json(args.json_out, records)
    print(f'wrote {len(records)} records to {args.out} and {args.json_out}')


if __name__ == '__main__':
    main()
