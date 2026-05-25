from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .constants import COLUMN_BOUNDS
from .geometry import crop_box_to_pixels, normalize_box, parse_crop
from .normalization import clean_text, normalize_pool_type


def resolve_device(device: str) -> str:
    if device != 'auto':
        return device

    try:
        import paddle
    except ImportError:
        return 'cpu'

    if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
        return 'gpu:0'
    return 'cpu'


def create_ocr(args: argparse.Namespace) -> Any:
    os.environ.setdefault('DISABLE_MODEL_SOURCE_CHECK', 'True')

    from paddleocr import PaddleOCR

    device = resolve_device(args.device)
    return PaddleOCR(
        text_detection_model_dir=str(args.det_model_dir),
        text_recognition_model_dir=str(args.rec_model_dir),
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device=device,
    )


def default_model_dir(model_name: str) -> Path:
    return Path.home() / '.paddlex' / 'official_models' / model_name


def detect_pool_type(image: Image.Image, ocr: Any, args: argparse.Namespace) -> str:
    crop = parse_crop(args.pool_crop)
    pool_box = crop_box_to_pixels(crop, image.size)
    pool_image = image.crop(pool_box)
    result = ocr.predict(np.array(pool_image))[0]
    texts = result.get('rec_texts', [])
    scores = result.get('rec_scores', [])

    candidates: list[tuple[float, str]] = []
    for text, score in zip(texts, scores, strict=False):
        raw_text = clean_text(str(text))
        normalized = normalize_pool_type(raw_text)
        if normalized:
            candidates.append((float(score), normalized))

    if not candidates:
        return ''

    return max(candidates, key=lambda candidate: candidate[0])[1]


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


def column_for_x(x_ratio: float) -> str | None:
    for column, (left, right) in COLUMN_BOUNDS.items():
        if left <= x_ratio < right:
            return column
    return None
