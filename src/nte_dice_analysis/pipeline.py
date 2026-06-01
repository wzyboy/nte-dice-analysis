from pathlib import Path

from PIL import Image

from .ocr import ocr_table
from .ocr import detect_pool_type
from .models import Record
from .models import CropBox
from .models import OcrEngine
from .models import PipelineOptions
from .visual import draw_debug_image
from .layouts import table_layout_for_pool_type
from .layouts import effective_options_for_pool_type
from .records import tokens_to_records

FULLSCREEN_ASPECT_WIDTH = 16
FULLSCREEN_ASPECT_HEIGHT = 9


def normalize_screenshot_image(image: Image.Image) -> Image.Image:
    width, height = image.size
    target_height = round(width * FULLSCREEN_ASPECT_HEIGHT / FULLSCREEN_ASPECT_WIDTH)
    if height <= target_height:
        return image

    return image.crop((0, height - target_height, width, height))


def uses_normalized_crop(crop: CropBox) -> bool:
    return max(crop.left, crop.top, crop.right, crop.bottom) <= 1


def crop_table_image(
    image_path: Path,
    options: PipelineOptions,
) -> Image.Image:
    image = Image.open(image_path).convert('RGB')
    if uses_normalized_crop(options.table_crop):
        image = normalize_screenshot_image(image)
    table_box = options.table_crop.to_pixels(image.size)
    return image.crop(table_box)


def detect_image_pool_type(
    image_path: Path,
    ocr: OcrEngine,
    options: PipelineOptions,
) -> str:
    image = Image.open(image_path).convert('RGB')
    if uses_normalized_crop(options.pool_crop) or uses_normalized_crop(options.table_crop):
        image = normalize_screenshot_image(image)
    return detect_pool_type(image, ocr, options)


def recognize_table_image(
    table_image_path: Path,
    ocr: OcrEngine,
    options: PipelineOptions,
    known_items: list[str],
    pool_type: str,
) -> list[Record]:
    table_image = Image.open(table_image_path).convert('RGB')
    layout = table_layout_for_pool_type(pool_type)
    effective_options = effective_options_for_pool_type(options, pool_type)
    tokens = ocr_table(table_image, ocr, effective_options, layout.column_bounds)
    records = tokens_to_records(table_image, table_image_path, pool_type, tokens, effective_options, known_items)

    if options.debug_dir:
        options.debug_dir.mkdir(parents=True, exist_ok=True)
        draw_debug_image(
            table_image,
            tokens,
            effective_options,
            options.debug_dir / f'{table_image_path.stem}_boxes.png',
            layout.column_bounds,
        )

    return records
