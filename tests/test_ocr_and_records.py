from __future__ import annotations

from pathlib import Path
from collections.abc import Callable

from PIL import Image

from nte_dice_analysis.ocr import ocr_table
from nte_dice_analysis.ocr import column_for_x
from nte_dice_analysis.models import Record
from nte_dice_analysis.models import OcrToken
from nte_dice_analysis.models import OcrPrediction
from nte_dice_analysis.models import PipelineOptions
from nte_dice_analysis.records import joined_text
from nte_dice_analysis.records import tokens_to_records


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


def test_column_for_x_maps_table_columns() -> None:
    assert column_for_x(0.10) == 'roll_points'
    assert column_for_x(0.30) == 'item_name'
    assert column_for_x(0.60) == 'quantity'
    assert column_for_x(0.80) == 'obtained_at'
    assert column_for_x(1.00) is None


def test_ocr_table_normalizes_predictions(
    options_factory: Callable[..., PipelineOptions],
) -> None:
    image = Image.new('RGB', (1000, 100), 'white')
    options = options_factory(row_count=2, row_top=0.0, row_bottom=1.0, min_score=0.3)

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


def test_tokens_to_records_builds_typed_record(
    options_factory: Callable[..., PipelineOptions],
) -> None:
    image = Image.new('RGB', (1000, 100), 'white')
    options: PipelineOptions = options_factory(row_count=2, row_top=0.0, row_bottom=1.0)
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
        ['角色·薄荷'],
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


def test_joined_text_orders_tokens_by_box_position() -> None:
    tokens = [
        OcrToken('B', 0.9, (20, 0, 30, 10), 0, 'item_name'),
        OcrToken('A', 0.9, (10, 0, 20, 10), 0, 'item_name'),
    ]

    assert joined_text(tokens) == 'AB'
