from pathlib import Path

from PIL import Image

from nte_dice_analysis.models import Record
from nte_dice_analysis.models import CropBox
from nte_dice_analysis.models import OcrPrediction
from nte_dice_analysis.models import PipelineOptions
from nte_dice_analysis.pipeline import crop_table_image
from nte_dice_analysis.pipeline import recognize_table_image
from nte_dice_analysis.pipeline import detect_image_pool_type
from nte_dice_analysis.pipeline import normalize_screenshot_image
from nte_dice_analysis.constants import POOL_TYPES
from nte_dice_analysis.constants import ARC_POOL_TYPE
from nte_dice_analysis.constants import DEFAULT_POOL_CROP
from nte_dice_analysis.constants import DEFAULT_TABLE_CROP
from nte_dice_analysis.constants import STANDARD_POOL_TYPE
from nte_dice_analysis.known_items import KnownItems


class RecordingOcr:
    def __init__(self) -> None:
        self.image_shapes: list[tuple[int, ...]] = []

    def predict(self, image: object) -> list[OcrPrediction]:
        shape = getattr(image, 'shape')
        self.image_shapes.append(tuple(int(value) for value in shape))
        return [
            {
                'rec_texts': [POOL_TYPES[0]],
                'rec_scores': [0.95],
                'rec_boxes': [],
            },
        ]


class ArcMarkerOcr:
    def predict(self, image: object) -> list[OcrPrediction]:
        return [
            {
                'rec_texts': ['研募详情'],
                'rec_scores': [0.95],
                'rec_boxes': [],
            },
        ]


class SequentialOcr:
    def __init__(self, *predictions: OcrPrediction) -> None:
        self.predictions = list(predictions)
        self.image_shapes: list[tuple[int, ...]] = []

    def predict(self, image: object) -> list[OcrPrediction]:
        shape = getattr(image, 'shape')
        self.image_shapes.append(tuple(int(value) for value in shape))
        if not self.predictions:
            raise AssertionError('unexpected OCR call')
        return [self.predictions.pop(0)]


def make_pipeline_options(
    *,
    table_crop: str = '0,0,1,1',
    pool_crop: str = '0,0,1,1',
) -> PipelineOptions:
    return PipelineOptions(
        table_crop=CropBox.parse(table_crop),
        pool_crop=CropBox.parse(pool_crop),
        row_boundaries=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        min_score=0.3,
        debug_dir=None,
        det_model_dir=None,
        rec_model_dir=None,
    )


def save_windowed_screenshot(path: Path) -> None:
    image = Image.new('RGB', (3204, 1847), 'green')
    image.paste('red', (0, 0, 3204, 45))
    image.save(path)


def save_table_image(path: Path) -> None:
    Image.new('RGB', (1000, 100), 'white').save(path)


def table_prediction(obtained_at_values: list[str]) -> OcrPrediction:
    texts: list[str] = []
    scores: list[float] = []
    boxes: list[tuple[int, int, int, int]] = []
    for row_index, obtained_at in enumerate(obtained_at_values):
        y0 = row_index * 20 + 5
        y1 = y0 + 10
        texts.extend(['1', '角色·阿德勒', 'x1', obtained_at])
        scores.extend([0.95, 0.95, 0.95, 0.95])
        boxes.extend(
            [
                (80, y0, 100, y1),
                (250, y0, 360, y1),
                (550, y0, 580, y1),
                (700, y0, 930, y1),
            ],
        )

    return {
        'rec_texts': texts,
        'rec_scores': scores,
        'rec_boxes': boxes,
    }


def date_column_prediction(obtained_at_values: list[str]) -> OcrPrediction:
    texts: list[str] = []
    scores: list[float] = []
    boxes: list[tuple[int, int, int, int]] = []
    for row_index, obtained_at in enumerate(obtained_at_values):
        y0 = row_index * 80 + 20
        y1 = y0 + 30
        texts.append(obtained_at)
        scores.append(0.95)
        boxes.append((80, y0, 900, y1))

    return {
        'rec_texts': texts,
        'rec_scores': scores,
        'rec_boxes': boxes,
    }


def item_name_column_prediction(item_names: list[str]) -> OcrPrediction:
    texts: list[str] = []
    scores: list[float] = []
    boxes: list[tuple[int, int, int, int]] = []
    for row_index, item_name in enumerate(item_names):
        y0 = row_index * 40 + 10
        y1 = y0 + 20
        texts.append(item_name)
        scores.append(0.95)
        boxes.append((20, y0, 500, y1))

    return {
        'rec_texts': texts,
        'rec_scores': scores,
        'rec_boxes': boxes,
    }


def recognize_standard_table(path: Path, ocr: SequentialOcr) -> list[Record]:
    return recognize_table_image(
        path,
        ocr,
        make_pipeline_options(),
        KnownItems({STANDARD_POOL_TYPE: ('角色·阿德勒',)}),
        STANDARD_POOL_TYPE,
    )


def test_normalize_screenshot_image_keeps_fullscreen_image() -> None:
    image = Image.new('RGB', (3840, 2160), 'green')

    normalized = normalize_screenshot_image(image)

    assert normalized is image
    assert normalized.size == (3840, 2160)


def test_normalize_screenshot_image_crops_window_titlebar_from_top() -> None:
    image = Image.new('RGB', (3204, 1847), 'green')
    image.paste('red', (0, 0, 3204, 45))

    normalized = normalize_screenshot_image(image)

    assert normalized.size == (3204, 1802)
    assert normalized.getpixel((0, 0)) == (0, 128, 0)


def test_default_crop_coordinates_use_normalized_windowed_size() -> None:
    normalized = normalize_screenshot_image(Image.new('RGB', (3204, 1847), 'green'))

    table_box = CropBox.parse(DEFAULT_TABLE_CROP).to_pixels(normalized.size)
    pool_box = CropBox.parse(DEFAULT_POOL_CROP).to_pixels(normalized.size)

    assert table_box == (584, 767, 2653, 1418)
    assert pool_box == (865, 604, 2627, 721)


def test_crop_table_image_crops_after_window_titlebar_normalization(tmp_path: Path) -> None:
    image_path = tmp_path / 'windowed.png'
    save_windowed_screenshot(image_path)
    options = make_pipeline_options(table_crop='0.25,0.25,0.75,0.75')

    table_image = crop_table_image(image_path, options)

    assert table_image.size == (1602, 902)
    assert table_image.getpixel((0, 0)) == (0, 128, 0)


def test_detect_image_pool_type_crops_after_window_titlebar_normalization(tmp_path: Path) -> None:
    image_path = tmp_path / 'windowed.png'
    save_windowed_screenshot(image_path)
    options = make_pipeline_options()
    ocr = RecordingOcr()

    pool_type = detect_image_pool_type(image_path, ocr, options)

    assert pool_type == POOL_TYPES[0]
    assert ocr.image_shapes[0] == (1802, 3204, 3)
    assert len(ocr.image_shapes) == 3


def test_detect_image_pool_type_recognizes_arc_research_markers(tmp_path: Path) -> None:
    image_path = tmp_path / 'arc.png'
    Image.new('RGB', (3840, 2160), 'green').save(image_path)
    options = make_pipeline_options()

    pool_type = detect_image_pool_type(image_path, ArcMarkerOcr(), options)

    assert pool_type == ARC_POOL_TYPE


def test_recognize_table_image_repairs_malformed_timestamp_with_date_column_ocr(
    tmp_path: Path,
) -> None:
    table_path = tmp_path / 'table.png'
    save_table_image(table_path)
    ocr = SequentialOcr(
        table_prediction(['2026年62711:48:01']),
        date_column_prediction(['2026年6月27日11:48:01']),
    )

    records = recognize_standard_table(table_path, ocr)

    assert records[0].obtained_at == '2026-06-27 11:48:01'
    assert records[0].obtained_at_raw == '2026年6月27日11:48:01'
    assert ocr.image_shapes == [(100, 1000, 3), (400, 1280, 3)]


def test_recognize_table_image_skips_date_column_ocr_for_strict_timestamp(
    tmp_path: Path,
) -> None:
    table_path = tmp_path / 'table.png'
    save_table_image(table_path)
    ocr = SequentialOcr(table_prediction(['2026年6月27日11:48:01']))

    records = recognize_standard_table(table_path, ocr)

    assert records[0].obtained_at == '2026-06-27 11:48:01'
    assert records[0].obtained_at_raw == '2026年6月27日11:48:01'
    assert ocr.image_shapes == [(100, 1000, 3)]


def test_recognize_table_image_repairs_item_name_with_upscaled_column_ocr(
    tmp_path: Path,
) -> None:
    table_path = tmp_path / 'table.png'
    save_table_image(table_path)
    initial_prediction = table_prediction(['2026年6月27日11:48:01'])
    initial_prediction['rec_texts'][1] = '角色·阿德勤'
    ocr = SequentialOcr(
        initial_prediction,
        item_name_column_prediction(['角色·阿德勒']),
    )

    records = recognize_standard_table(table_path, ocr)

    assert records[0].item_name == '角色·阿德勒'
    assert records[0].item_name_raw == '角色·阿德勒'
    assert ocr.image_shapes == [(100, 1000, 3), (200, 560, 3)]


def test_recognize_table_image_preserves_unknown_item_when_upscaled_ocr_matches_known_item(
    tmp_path: Path,
) -> None:
    table_path = tmp_path / 'table.png'
    save_table_image(table_path)
    initial_prediction = table_prediction(['2026年6月27日11:48:01'])
    initial_prediction['rec_texts'][1] = '完全不像'
    ocr = SequentialOcr(
        initial_prediction,
        item_name_column_prediction(['角色·阿德勒']),
    )

    records = recognize_standard_table(table_path, ocr)

    assert records[0].item_name == '完全不像'
    assert records[0].item_name_raw == '完全不像'


def test_recognize_table_image_keeps_original_when_item_name_retry_disagrees(
    tmp_path: Path,
) -> None:
    table_path = tmp_path / 'table.png'
    save_table_image(table_path)
    initial_prediction = table_prediction(['2026年6月27日11:48:01'])
    initial_prediction['rec_texts'][1] = '角色·阿德勤'
    ocr = SequentialOcr(
        initial_prediction,
        item_name_column_prediction(['角色·埃德嘉']),
    )

    records = recognize_table_image(
        table_path,
        ocr,
        make_pipeline_options(),
        KnownItems({STANDARD_POOL_TYPE: ('角色·阿德勒', '角色·埃德嘉')}),
        STANDARD_POOL_TYPE,
    )

    assert records[0].item_name == '角色·阿德勒'
    assert records[0].item_name_raw == '角色·阿德勤'


def test_recognize_table_image_does_not_replace_strict_existing_timestamp(
    tmp_path: Path,
) -> None:
    table_path = tmp_path / 'table.png'
    save_table_image(table_path)
    ocr = SequentialOcr(
        table_prediction(['2026年62711:48:01', '2026年6月27日11:47:00']),
        date_column_prediction(['2026年6月27日11:48:01', '2026年6月28日11:47:00']),
    )

    records = recognize_standard_table(table_path, ocr)

    assert records[0].obtained_at_raw == '2026年6月27日11:48:01'
    assert records[1].obtained_at == '2026-06-27 11:47:00'
    assert records[1].obtained_at_raw == '2026年6月27日11:47:00'


def test_recognize_table_image_does_not_replace_conflicting_valid_timestamp(
    tmp_path: Path,
) -> None:
    table_path = tmp_path / 'table.png'
    save_table_image(table_path)
    ocr = SequentialOcr(
        table_prediction(['2026年6月2711:48:01']),
        date_column_prediction(['2026年6月28日11:48:01']),
    )

    records = recognize_standard_table(table_path, ocr)

    assert records[0].obtained_at == '2026-06-27 11:48:01'
    assert records[0].obtained_at_raw == '2026年6月2711:48:01'
    assert ocr.image_shapes == [(100, 1000, 3), (400, 1280, 3)]
