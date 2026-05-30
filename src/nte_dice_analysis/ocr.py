import os
from types import ModuleType
from typing import cast
from pathlib import Path

import numpy as np
from PIL import Image

from .models import OcrToken
from .models import OcrEngine
from .models import PipelineOptions
from .runtime import CPU_RUNTIME
from .runtime import CUDA_RUNTIME
from .runtime import package_runtime
from .runtime import bundled_model_dir
from .runtime import cuda_unavailable_message
from .geometry import normalize_box
from .constants import COLUMN_BOUNDS
from .constants import DEFAULT_DET_MODEL
from .constants import DEFAULT_REC_MODEL
from .normalization import clean_text
from .normalization import normalize_pool_type


class CudaUnavailableError(RuntimeError):
    pass


def validate_ocr_runtime(paddle_module: ModuleType | object | None = None) -> None:
    if package_runtime() != CUDA_RUNTIME:
        return

    require_cuda_available(paddle_module)


def require_cuda_available(paddle_module: ModuleType | object | None = None) -> None:
    try:
        if paddle_module is None:
            import paddle as paddle_module

        compiled_with_cuda = paddle_module.device.is_compiled_with_cuda()
        cuda_device_count = paddle_module.device.cuda.device_count()
    except Exception as error:
        raise CudaUnavailableError(cuda_unavailable_message(str(error))) from error

    if not compiled_with_cuda:
        raise CudaUnavailableError(cuda_unavailable_message('Paddle is not a CUDA build.'))
    if cuda_device_count <= 0:
        raise CudaUnavailableError(cuda_unavailable_message('No CUDA GPU was detected.'))


def resolve_device(device: str, paddle_module: ModuleType | object | None = None) -> str:
    runtime = package_runtime()
    if runtime == CUDA_RUNTIME:
        if device == CPU_RUNTIME:
            raise CudaUnavailableError(
                'This is the Windows CUDA build, and CPU OCR is disabled for packaged CUDA releases. '
                'Use the CPU build of NTE Dice Analysis for CPU-only OCR.',
            )
        require_cuda_available(paddle_module)
        if device == 'auto':
            return 'gpu:0'
        return device

    if runtime == CPU_RUNTIME and device.startswith('gpu'):
        raise CudaUnavailableError(
            'This is the Windows CPU build, and GPU OCR is not included. '
            'Use the CUDA build of NTE Dice Analysis for NVIDIA GPU OCR.',
        )

    if device != 'auto':
        return device

    try:
        if paddle_module is None:
            import paddle as paddle_module
    except ImportError:
        return 'cpu'

    if paddle_module.device.is_compiled_with_cuda() and paddle_module.device.cuda.device_count() > 0:
        return 'gpu:0'
    return 'cpu'


def create_ocr(options: PipelineOptions) -> OcrEngine:
    os.environ.setdefault('DISABLE_MODEL_SOURCE_CHECK', 'True')
    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', 'True')

    validate_ocr_runtime()

    from paddleocr import PaddleOCR

    device = resolve_device(options.device)
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
            device=device,
        ),
    )


def resolve_model_dir(model_name: str, override: Path | None) -> Path | None:
    if override is not None:
        return override
    return bundled_model_dir(model_name)


def default_model_dir(model_name: str) -> Path:
    return Path.home() / '.paddlex' / 'official_models' / model_name


def detect_pool_type(image: Image.Image, ocr: OcrEngine, options: PipelineOptions) -> str:
    pool_box = options.pool_crop.to_pixels(image.size)
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
    ocr: OcrEngine,
    options: PipelineOptions,
) -> list[OcrToken]:
    result = ocr.predict(np.array(table_image))[0]
    texts = result.get('rec_texts', [])
    scores = result.get('rec_scores', [])
    boxes = result.get('rec_boxes', [])

    tokens: list[OcrToken] = []
    width, height = table_image.size
    row_area_top, row_area_bottom, row_height = options.row_metrics(table_image.size)

    for text, score, box in zip(texts, scores, boxes, strict=False):
        text = str(text).strip()
        score = float(score)
        if not text or score < options.min_score:
            continue

        x0, y0, x1, y1 = normalize_box(box)
        center_x = (x0 + x1) / 2
        center_y = (y0 + y1) / 2
        if center_y < row_area_top or center_y >= row_area_bottom:
            continue

        row_index = int((center_y - row_area_top) // row_height)
        if row_index < 0 or row_index >= options.row_count:
            continue

        column = column_for_x(center_x / width)
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


def column_for_x(x_ratio: float) -> str | None:
    for column, (left, right) in COLUMN_BOUNDS.items():
        if left <= x_ratio < right:
            return column
    return None
