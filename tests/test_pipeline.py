from pathlib import Path

from PIL import Image

from nte_dice_analysis.models import CropBox
from nte_dice_analysis.models import OcrPrediction
from nte_dice_analysis.models import PipelineOptions
from nte_dice_analysis.pipeline import crop_table_image
from nte_dice_analysis.pipeline import detect_image_pool_type
from nte_dice_analysis.pipeline import normalize_screenshot_image
from nte_dice_analysis.constants import POOL_TYPES
from nte_dice_analysis.constants import ARC_POOL_TYPE
from nte_dice_analysis.constants import DEFAULT_POOL_CROP
from nte_dice_analysis.constants import DEFAULT_TABLE_CROP


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
