import os
import sys
from typing import SupportsFloat
from typing import SupportsIndex
from typing import cast
from pathlib import Path
from collections.abc import Mapping

import numpy as np
from PIL import Image

from .models import OcrToken
from .models import OcrEngine
from .models import PipelineOptions
from .geometry import normalize_box
from .constants import ARC_POOL_TYPE
from .constants import COLUMN_BOUNDS
from .constants import DEFAULT_DET_MODEL
from .constants import DEFAULT_REC_MODEL
from .normalization import clean_text
from .normalization import normalize_pool_type

MODELS_DIR_ENV_VAR = 'NTE_DICE_ANALYSIS_MODELS_DIR'
ARC_POOL_MARKERS = ('研募详情', '弧盘列表', '研募类型', '研募时间', '研募记录')
POOL_TITLE_CROP = (0.42, 0.16, 0.58, 0.23)


def create_ocr(options: PipelineOptions) -> OcrEngine:
    os.environ.setdefault('DISABLE_MODEL_SOURCE_CHECK', 'True')
    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', 'True')

    from paddleocr import PaddleOCR

    det_model_dir = resolve_model_dir(DEFAULT_DET_MODEL, options.det_model_dir)
    rec_model_dir = resolve_model_dir(DEFAULT_REC_MODEL, options.rec_model_dir)
    return cast(
        OcrEngine,
        PaddleOCR(
            text_detection_model_name=DEFAULT_DET_MODEL,
            text_detection_model_dir=str(det_model_dir) if det_model_dir is not None else None,
            text_recognition_model_name=DEFAULT_REC_MODEL,
            text_recognition_model_dir=str(rec_model_dir) if rec_model_dir is not None else None,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device='cpu',
        ),
    )


def resolve_model_dir(model_name: str, override: Path | None) -> Path | None:
    if override is not None:
        return override
    return bundled_model_dir(model_name)


def bundled_model_dir(model_name: str) -> Path | None:
    root = bundled_models_root()
    if root is None:
        return None

    model_dir = root / model_name
    if model_dir.exists():
        return model_dir
    return None


def bundled_models_root() -> Path | None:
    env_root = os.environ.get(MODELS_DIR_ENV_VAR)
    if env_root:
        root = Path(env_root)
        if root.exists():
            return root

    base_dir = packaged_base_dir()
    if base_dir is None:
        return None

    root = base_dir / 'models'
    if root.exists():
        return root
    return None


def packaged_base_dir() -> Path | None:
    base_dir = getattr(sys, '_MEIPASS', None)
    if isinstance(base_dir, str):
        return Path(base_dir)
    return None


def default_model_dir(model_name: str) -> Path:
    return Path.home() / '.paddlex' / 'official_models' / model_name


def detect_pool_type(image: Image.Image, ocr: OcrEngine, options: PipelineOptions) -> str:
    candidates: list[tuple[float, str]] = []
    for region in pool_detection_regions(image, options):
        result = ocr.predict(np.array(region))[0]
        texts = result.get('rec_texts', [])
        scores = result.get('rec_scores', [])

        for text, score in zip(texts, scores, strict=False):
            raw_text = clean_text(str(text))
            normalized = normalize_pool_type(raw_text)
            score_value = ocr_score_to_float(score)
            if normalized:
                candidates.append((score_value, normalized))
            if is_arc_pool_marker(raw_text):
                candidates.append((score_value, ARC_POOL_TYPE))

    if not candidates:
        return ''

    return max(candidates, key=lambda candidate: candidate[0])[1]


def pool_detection_regions(image: Image.Image, options: PipelineOptions) -> list[Image.Image]:
    regions = [image.crop(options.pool_crop.to_pixels(image.size))]

    width, height = image.size
    title_box = (
        round(POOL_TITLE_CROP[0] * width),
        round(POOL_TITLE_CROP[1] * height),
        round(POOL_TITLE_CROP[2] * width),
        round(POOL_TITLE_CROP[3] * height),
    )
    regions.append(image.crop(title_box))

    table_image = image.crop(options.table_crop.to_pixels(image.size))
    table_width, table_height = table_image.size
    regions.append(table_image.crop((0, 0, table_width, round(table_height * 0.22))))
    return regions


def is_arc_pool_marker(value: str) -> bool:
    return any(marker in value for marker in ARC_POOL_MARKERS)


def ocr_table(
    table_image: Image.Image,
    ocr: OcrEngine,
    options: PipelineOptions,
    column_bounds: Mapping[str, tuple[float, float]] = COLUMN_BOUNDS,
) -> list[OcrToken]:
    result = ocr.predict(np.array(table_image))[0]
    texts = result.get('rec_texts', [])
    scores = result.get('rec_scores', [])
    boxes = result.get('rec_boxes', [])

    tokens: list[OcrToken] = []
    width, _ = table_image.size

    for text, score, box in zip(texts, scores, boxes, strict=False):
        text = str(text).strip()
        score = ocr_score_to_float(score)
        if not text or score < options.min_score:
            continue

        x0, y0, x1, y1 = normalize_box(box)
        center_x = (x0 + x1) / 2
        center_y = (y0 + y1) / 2
        row_index = options.row_index_for_y(table_image.size, center_y)
        if row_index is None:
            continue

        column = column_for_x(center_x / width, column_bounds)
        if column is None:
            continue

        tokens.append(
            OcrToken(
                text=text,
                score=score,
                box=(x0, y0, x1, y1),
                row_index=row_index,
                column=column,
            ),
        )

    return tokens


def column_for_x(
    x_ratio: float,
    column_bounds: Mapping[str, tuple[float, float]] = COLUMN_BOUNDS,
) -> str | None:
    for column, (left, right) in column_bounds.items():
        if left <= x_ratio < right:
            return column
    return None


def ocr_score_to_float(value: object) -> float:
    if isinstance(value, str | bytes | bytearray | SupportsFloat | SupportsIndex):
        return float(value)
    raise ValueError(f'unsupported OCR score: {value!r}')
