import os
import sys
from types import SimpleNamespace
from pathlib import Path
from collections.abc import Callable

import pytest
from PIL import Image

from nte_dice_analysis.ocr import ocr_table
from nte_dice_analysis.ocr import create_ocr
from nte_dice_analysis.ocr import column_for_x
from nte_dice_analysis.models import Record
from nte_dice_analysis.models import OcrToken
from nte_dice_analysis.models import OcrPrediction
from nte_dice_analysis.models import PipelineOptions
from nte_dice_analysis.records import joined_text
from nte_dice_analysis.records import tokens_to_records
from nte_dice_analysis.constants import ARC_POOL_TYPE
from nte_dice_analysis.constants import ARC_COLUMN_BOUNDS
from nte_dice_analysis.constants import DEFAULT_DET_MODEL
from nte_dice_analysis.constants import DEFAULT_REC_MODEL
from nte_dice_analysis.constants import LIMITED_POOL_TYPE
from nte_dice_analysis.known_items import KnownItems


class FakeOcr:
    def predict(self, image: object) -> list[OcrPrediction]:
        return [
            {
                'rec_texts': ['角色', '·薄荷', 'x1', '2026年5月7日03:04:05', 'too-low'],
                'rec_scores': [0.95, 0.90, 0.85, 0.80, 0.10],
                'rec_boxes': [
                    (230, 10, 270, 20),
                    (280, 10, 330, 20),
                    (520, 10, 560, 20),
                    (700, 10, 900, 20),
                    (230, 40, 260, 50),
                ],
            },
        ]


def test_create_ocr_uses_official_model_names_by_default(
    monkeypatch: pytest.MonkeyPatch,
    options_factory: Callable[..., PipelineOptions],
) -> None:
    init_kwargs: dict[str, object] = {}

    class FakePaddleOCR:
        def __init__(self, **kwargs: object) -> None:
            init_kwargs.update(kwargs)

    monkeypatch.delenv('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', raising=False)
    monkeypatch.setitem(
        sys.modules,
        'paddleocr',
        SimpleNamespace(PaddleOCR=FakePaddleOCR),
    )

    options = options_factory(det_model_dir=None, rec_model_dir=None)

    create_ocr(options)

    assert init_kwargs['text_detection_model_name'] == DEFAULT_DET_MODEL
    assert init_kwargs['text_detection_model_dir'] is None
    assert init_kwargs['text_recognition_model_name'] == DEFAULT_REC_MODEL
    assert init_kwargs['text_recognition_model_dir'] is None
    assert init_kwargs['device'] == 'cpu'
    assert os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] == 'True'


def test_column_for_x_maps_table_columns() -> None:
    assert column_for_x(0.10) == 'roll_points'
    assert column_for_x(0.30) == 'item_name'
    assert column_for_x(0.60) == 'quantity'
    assert column_for_x(0.80) == 'obtained_at'
    assert column_for_x(1.00) is None


def test_column_for_x_maps_arc_table_columns() -> None:
    assert column_for_x(0.20, ARC_COLUMN_BOUNDS) == 'item_name'
    assert column_for_x(0.50, ARC_COLUMN_BOUNDS) == 'research_type'
    assert column_for_x(0.80, ARC_COLUMN_BOUNDS) == 'obtained_at'
    assert column_for_x(1.00, ARC_COLUMN_BOUNDS) is None


def test_ocr_table_normalizes_predictions(
    options_factory: Callable[..., PipelineOptions],
) -> None:
    image = Image.new('RGB', (1000, 100), 'white')
    options = options_factory(row_boundaries=(0.0, 0.5, 1.0), min_score=0.3)

    tokens = ocr_table(image, FakeOcr(), options)

    assert [token.text for token in tokens] == [
        '角色',
        '·薄荷',
        'x1',
        '2026年5月7日03:04:05',
    ]
    assert [token.column for token in tokens] == [
        'item_name',
        'item_name',
        'quantity',
        'obtained_at',
    ]
    assert {token.row_index for token in tokens} == {0}


def test_ocr_table_maps_arc_layout_columns(
    options_factory: Callable[..., PipelineOptions],
) -> None:
    class ArcOcr:
        def predict(self, image: object) -> list[OcrPrediction]:
            return [
                {
                    'rec_texts': ['行进于时间之外', '奇迹盒盒', '2026年6月1日01:18:32'],
                    'rec_scores': [0.95, 0.90, 0.85],
                    'rec_boxes': [
                        (120, 10, 220, 20),
                        (450, 10, 550, 20),
                        (720, 10, 900, 20),
                    ],
                },
            ]

    image = Image.new('RGB', (1000, 100), 'white')
    options = options_factory(row_boundaries=(0.0, 1.0), min_score=0.3)

    tokens = ocr_table(image, ArcOcr(), options, ARC_COLUMN_BOUNDS)

    assert [(token.text, token.column) for token in tokens] == [
        ('行进于时间之外', 'item_name'),
        ('奇迹盒盒', 'research_type'),
        ('2026年6月1日01:18:32', 'obtained_at'),
    ]


def test_ocr_table_uses_explicit_row_boundaries(
    options_factory: Callable[..., PipelineOptions],
) -> None:
    class BoundaryOcr:
        def predict(self, image: object) -> list[OcrPrediction]:
            return [
                {
                    'rec_texts': ['above', 'first', 'second', 'below'],
                    'rec_scores': [0.95, 0.95, 0.95, 0.95],
                    'rec_boxes': [
                        (230, 10, 270, 20),
                        (230, 30, 270, 40),
                        (230, 70, 270, 80),
                        (230, 98, 270, 100),
                    ],
                },
            ]

    image = Image.new('RGB', (1000, 100), 'white')
    options = options_factory(row_boundaries=(0.20, 0.60, 0.95))

    tokens = ocr_table(image, BoundaryOcr(), options)

    assert [(token.text, token.row_index) for token in tokens] == [
        ('first', 0),
        ('second', 1),
    ]


def test_explicit_row_boundaries_drive_row_bounds(
    options_factory: Callable[..., PipelineOptions],
) -> None:
    options = options_factory(row_boundaries=(0.20, 0.60, 0.95))

    assert options.row_count == 2
    assert options.row_bounds((1000, 100), 0) == (20, 60)
    assert options.row_bounds((1000, 100), 1) == (60, 95)
    assert options.row_index_for_y((1000, 100), 19.99) is None
    assert options.row_index_for_y((1000, 100), 20) == 0
    assert options.row_index_for_y((1000, 100), 60) == 1
    assert options.row_index_for_y((1000, 100), 95) is None


def test_explicit_row_boundaries_must_increase(
    options_factory: Callable[..., PipelineOptions],
) -> None:
    with pytest.raises(ValueError, match='strictly increasing'):
        options_factory(row_boundaries=(0.20, 0.20, 0.95))


def test_tokens_to_records_builds_typed_record(
    options_factory: Callable[..., PipelineOptions],
) -> None:
    image = Image.new('RGB', (1000, 100), 'white')
    options: PipelineOptions = options_factory(row_boundaries=(0.0, 0.5, 1.0))
    tokens = [
        OcrToken('1', 0.95, (10, 10, 20, 20), 0, 'roll_points'),
        OcrToken('角色', 0.90, (230, 10, 270, 20), 0, 'item_name'),
        OcrToken('·薄荷', 0.80, (280, 10, 330, 20), 0, 'item_name'),
        OcrToken('x1', 0.85, (520, 10, 560, 20), 0, 'quantity'),
        OcrToken('2026年5月7日03:04:05', 0.75, (700, 10, 900, 20), 0, 'obtained_at'),
    ]

    records = tokens_to_records(
        image,
        Path('source.png'),
        '限定棋盘',
        tokens,
        options,
        KnownItems({LIMITED_POOL_TYPE: ('角色·薄荷',)}),
    )

    assert records == [
        Record(
            pool_type='限定棋盘',
            source_image=Path('source.png'),
            page_row=1,
            roll_points='1',
            item_name='角色·薄荷',
            rarity='B-Class',
            item_name_raw='角色·薄荷',
            quantity='1',
            obtained_at='2026-05-07 03:04:05',
            obtained_at_raw='2026年5月7日03:04:05',
            confidence=0.75,
        ),
    ]
    assert records[0].to_output_row()['confidence'] == '0.750'


def test_tokens_to_records_builds_arc_research_record(
    options_factory: Callable[..., PipelineOptions],
) -> None:
    image = Image.new('RGB', (1000, 100), 'white')
    options: PipelineOptions = options_factory(row_boundaries=(0.0, 1.0))
    tokens = [
        OcrToken('行进于时间之外', 0.95, (10, 10, 200, 20), 0, 'item_name'),
        OcrToken('奇迹盒盒', 0.90, (430, 10, 520, 20), 0, 'research_type'),
        OcrToken('2026年6月1日01:18:32', 0.85, (700, 10, 900, 20), 0, 'obtained_at'),
    ]

    records = tokens_to_records(
        image,
        Path('source.png'),
        ARC_POOL_TYPE,
        tokens,
        options,
        KnownItems({ARC_POOL_TYPE: ('行进于时间之外',)}),
    )

    assert records == [
        Record(
            pool_type=ARC_POOL_TYPE,
            source_image=Path('source.png'),
            page_row=1,
            roll_points='',
            item_name='行进于时间之外',
            rarity='B-Class',
            item_name_raw='行进于时间之外',
            quantity='',
            obtained_at='2026-06-01 01:18:32',
            obtained_at_raw='2026年6月1日01:18:32',
            confidence=0.85,
            research_type='奇迹盒盒',
        ),
    ]


def test_joined_text_orders_tokens_by_box_position() -> None:
    tokens = [
        OcrToken('B', 0.9, (20, 0, 30, 10), 0, 'item_name'),
        OcrToken('A', 0.9, (10, 0, 20, 10), 0, 'item_name'),
    ]

    assert joined_text(tokens) == 'AB'
