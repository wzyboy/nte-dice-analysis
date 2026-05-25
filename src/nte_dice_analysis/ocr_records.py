from __future__ import annotations

from .cli import main, parse_args
from .constants import (
    COLUMN_BOUNDS,
    CSV_FIELDS,
    DEFAULT_DET_MODEL,
    DEFAULT_POOL_CROP,
    DEFAULT_REC_MODEL,
    DEFAULT_TABLE_CROP,
    GIFT_ROLL_POINTS,
    IMAGE_EXTENSIONS,
    POOL_TYPES,
)
from .dedup import (
    better_record,
    confidence_value,
    deduplicate_records,
    dedup_group_sort_key,
    find_subsequence,
    merge_fragment,
    merge_fragments,
    page_row_number,
    record_group_key,
    record_match_key,
    records_to_pages,
    reliable_overlap,
    timestamp_fragments,
    timestamp_sort_key,
    validate_pull_groups,
)
from .geometry import crop_box_to_pixels, normalize_box, parse_crop
from .io import load_known_items, resolve_image_paths, write_csv, write_json
from .normalization import (
    clean_text,
    comparable_item_text,
    normalize_datetime,
    normalize_item_name,
    normalize_pool_type,
    normalize_quantity,
)
from .ocr import column_for_x, create_ocr, default_model_dir, detect_pool_type, ocr_table, resolve_device
from .pipeline import process_image
from .records import joined_text, normalize_roll_points, tokens_to_records
from .visual import (
    connected_components,
    detect_pip_count,
    draw_debug_image,
    scaled,
    scaled_area,
)


if __name__ == '__main__':
    main()
