from pathlib import Path

from PIL import Image

from .ocr import ocr_table
from .ocr import detect_pool_type
from .models import Record
from .models import OcrEngine
from .models import PipelineOptions
from .visual import draw_debug_image
from .records import tokens_to_records


def crop_table_image(
    image_path: Path,
    options: PipelineOptions,
) -> Image.Image:
    image = Image.open(image_path).convert('RGB')
    table_box = options.table_crop.to_pixels(image.size)
    return image.crop(table_box)


def detect_image_pool_type(
    image_path: Path,
    ocr: OcrEngine,
    options: PipelineOptions,
) -> str:
    image = Image.open(image_path).convert('RGB')
    return detect_pool_type(image, ocr, options)


def recognize_table_image(
    table_image_path: Path,
    ocr: OcrEngine,
    options: PipelineOptions,
    known_items: list[str],
    pool_type: str,
) -> list[Record]:
    table_image = Image.open(table_image_path).convert('RGB')
    tokens = ocr_table(table_image, ocr, options)
    records = tokens_to_records(table_image, table_image_path, pool_type, tokens, options, known_items)

    if options.debug_dir:
        options.debug_dir.mkdir(parents=True, exist_ok=True)
        draw_debug_image(
            table_image,
            tokens,
            options,
            options.debug_dir / f'{table_image_path.stem}_boxes.png',
        )

    return records
