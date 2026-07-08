import re
import difflib
from pathlib import Path
from dataclasses import replace

from PIL import Image

from .ocr import ocr_table
from .ocr import detect_pool_type
from .models import Record
from .models import CropBox
from .models import OcrToken
from .models import OcrEngine
from .models import PipelineOptions
from .visual import draw_debug_image
from .layouts import table_layout_for_pool_type
from .layouts import effective_options_for_pool_type
from .records import joined_text
from .records import tokens_to_records
from .known_items import KnownItems
from .normalization import clean_text
from .normalization import normalize_datetime
from .normalization import normalize_item_name
from .normalization import comparable_item_text

FULLSCREEN_ASPECT_WIDTH = 16
FULLSCREEN_ASPECT_HEIGHT = 9
DATE_COLUMN_UPSCALE = 4
ITEM_NAME_COLUMN_UPSCALE = 2
DATE_COLUMN_BOUNDS = {'obtained_at': (0.0, 1.0)}
ITEM_NAME_COLUMN_BOUNDS = {'item_name': (0.0, 1.0)}
STRICT_CHINESE_DATETIME_RE = re.compile(r'\d{4}年\d{1,2}月\d{1,2}日\d{1,2}:\d{2}:\d{2}')
CANONICAL_DATETIME_RE = re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')


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
    known_items: KnownItems,
    pool_type: str,
) -> list[Record]:
    table_image = Image.open(table_image_path).convert('RGB')
    layout = table_layout_for_pool_type(pool_type)
    effective_options = effective_options_for_pool_type(options, pool_type)
    tokens = ocr_table(table_image, ocr, effective_options, layout.column_bounds)
    records = tokens_to_records(table_image, table_image_path, pool_type, tokens, effective_options, known_items)
    item_name_column_image: Image.Image | None = None
    item_name_column_tokens: list[OcrToken] = []
    if needs_item_name_fallback(records, known_items):
        item_name_column_image, item_name_column_tokens = ocr_upscaled_column(
            table_image,
            ocr,
            effective_options,
            layout.column_bounds['item_name'],
            ITEM_NAME_COLUMN_UPSCALE,
            ITEM_NAME_COLUMN_BOUNDS,
        )
        records = repair_record_item_names(records, item_name_column_tokens, effective_options, known_items)

    date_column_image: Image.Image | None = None
    date_column_tokens: list[OcrToken] = []
    if needs_timestamp_fallback(records):
        date_column_image, date_column_tokens = ocr_upscaled_date_column(
            table_image,
            ocr,
            effective_options,
            layout.column_bounds['obtained_at'],
        )
        records = repair_record_timestamps(records, date_column_tokens, effective_options)

    if options.debug_dir:
        options.debug_dir.mkdir(parents=True, exist_ok=True)
        draw_debug_image(
            table_image,
            tokens,
            effective_options,
            options.debug_dir / f'{table_image_path.stem}_boxes.png',
            layout.column_bounds,
        )
        if date_column_image is not None:
            draw_debug_image(
                date_column_image,
                date_column_tokens,
                effective_options,
                options.debug_dir / f'{table_image_path.stem}_date_column_boxes.png',
                DATE_COLUMN_BOUNDS,
            )
        if item_name_column_image is not None:
            draw_debug_image(
                item_name_column_image,
                item_name_column_tokens,
                effective_options,
                options.debug_dir / f'{table_image_path.stem}_item_name_column_boxes.png',
                ITEM_NAME_COLUMN_BOUNDS,
            )

    return records


def needs_timestamp_fallback(records: list[Record]) -> bool:
    return any(record_needs_timestamp_fallback(record) for record in records)


def record_needs_timestamp_fallback(record: Record) -> bool:
    return not is_canonical_datetime(record.obtained_at) or not is_strict_chinese_datetime(record.obtained_at_raw)


def needs_item_name_fallback(records: list[Record], known_items: KnownItems) -> bool:
    return any(record_needs_item_name_fallback(record, known_items) for record in records)


def record_needs_item_name_fallback(record: Record, known_items: KnownItems) -> bool:
    if not known_items.contains(record.pool_type, record.item_name):
        return True
    return comparable_item_text(record.item_name_raw) != comparable_item_text(record.item_name)


def repair_record_item_names(
    records: list[Record],
    item_name_tokens: list[OcrToken],
    options: PipelineOptions,
    known_items: KnownItems,
) -> list[Record]:
    fallback_by_row = {
        row_index: clean_text(joined_text(tokens_for_row(item_name_tokens, row_index, 'item_name')))
        for row_index in range(options.row_count)
    }
    return [
        repair_record_item_name(record, fallback_by_row.get(record.page_row - 1, ''), known_items) for record in records
    ]


def repair_record_item_name(record: Record, fallback_raw: str, known_items: KnownItems) -> Record:
    if not fallback_raw:
        return record

    pool_known_items = known_items.items_for_pool(record.pool_type)
    fallback_item_name = normalize_item_name(fallback_raw, pool_known_items)
    fallback_is_known = known_items.contains(record.pool_type, fallback_item_name)
    if not fallback_is_known or fallback_item_name != record.item_name:
        return record
    if item_name_similarity(fallback_raw, record.item_name) <= item_name_similarity(
        record.item_name_raw,
        record.item_name,
    ):
        return record
    return replace(record, item_name_raw=fallback_raw)


def item_name_similarity(value: str, known_item: str) -> float:
    return difflib.SequenceMatcher(
        None,
        comparable_item_text(value),
        comparable_item_text(known_item),
    ).ratio()


def ocr_upscaled_date_column(
    table_image: Image.Image,
    ocr: OcrEngine,
    options: PipelineOptions,
    date_column_bounds: tuple[float, float],
) -> tuple[Image.Image, list[OcrToken]]:
    return ocr_upscaled_column(
        table_image,
        ocr,
        options,
        date_column_bounds,
        DATE_COLUMN_UPSCALE,
        DATE_COLUMN_BOUNDS,
    )


def ocr_upscaled_column(
    table_image: Image.Image,
    ocr: OcrEngine,
    options: PipelineOptions,
    column_bounds: tuple[float, float],
    upscale: int,
    result_column_bounds: dict[str, tuple[float, float]],
) -> tuple[Image.Image, list[OcrToken]]:
    width, height = table_image.size
    left, right = column_bounds
    column_image = table_image.crop((round(left * width), 0, round(right * width), height))
    upscaled_image = column_image.resize(
        (column_image.width * upscale, column_image.height * upscale),
        Image.Resampling.BICUBIC,
    )
    return upscaled_image, ocr_table(upscaled_image, ocr, options, result_column_bounds)


def repair_record_timestamps(
    records: list[Record],
    date_column_tokens: list[OcrToken],
    options: PipelineOptions,
) -> list[Record]:
    fallback_by_row = {
        row_index: clean_text(joined_text(tokens_for_row(date_column_tokens, row_index)))
        for row_index in range(options.row_count)
    }
    return [repair_record_timestamp(record, fallback_by_row.get(record.page_row - 1, '')) for record in records]


def tokens_for_row(tokens: list[OcrToken], row_index: int, column: str = 'obtained_at') -> list[OcrToken]:
    return [token for token in tokens if token.row_index == row_index and token.column == column]


def repair_record_timestamp(record: Record, fallback_raw: str) -> Record:
    if not fallback_raw:
        return record

    fallback_obtained_at = normalize_datetime(fallback_raw)
    if not is_canonical_datetime(fallback_obtained_at):
        return record

    original_is_canonical = is_canonical_datetime(record.obtained_at)
    if original_is_canonical and fallback_obtained_at != record.obtained_at:
        return record

    if timestamp_raw_quality(fallback_raw) <= timestamp_raw_quality(record.obtained_at_raw):
        return record

    return replace(record, obtained_at=fallback_obtained_at, obtained_at_raw=fallback_raw)


def timestamp_raw_quality(value: str) -> int:
    cleaned = clean_text(value)
    if is_strict_chinese_datetime(cleaned):
        return 2
    if is_canonical_datetime(normalize_datetime(cleaned)):
        return 1
    return 0


def is_strict_chinese_datetime(value: str) -> bool:
    cleaned = clean_text(value)
    return bool(STRICT_CHINESE_DATETIME_RE.fullmatch(cleaned)) and is_canonical_datetime(normalize_datetime(cleaned))


def is_canonical_datetime(value: str) -> bool:
    return bool(CANONICAL_DATETIME_RE.fullmatch(value))
