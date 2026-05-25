from pathlib import Path

from PIL import Image

from .ocr import ocr_table
from .ocr import detect_pool_type
from .models import Record
from .models import OcrEngine
from .models import PipelineOptions
from .visual import draw_debug_image
from .records import tokens_to_records


def process_image(
    image_path: Path,
    ocr: OcrEngine,
    options: PipelineOptions,
    known_items: list[str],
) -> list[Record]:
    image = Image.open(image_path).convert('RGB')
    table_box = options.table_crop.to_pixels(image.size)
    table_image = image.crop(table_box)
    pool_type = detect_pool_type(image, ocr, options)

    if options.debug_dir:
        options.debug_dir.mkdir(parents=True, exist_ok=True)
        table_image.save(options.debug_dir / f'{image_path.stem}_table.png')

    tokens = ocr_table(table_image, ocr, options)
    records = tokens_to_records(table_image, image_path, pool_type, tokens, options, known_items)

    if options.debug_dir:
        draw_debug_image(
            table_image,
            tokens,
            options,
            options.debug_dir / f'{image_path.stem}_boxes.png',
        )

    return records
