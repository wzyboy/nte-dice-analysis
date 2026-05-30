from pathlib import Path
from collections.abc import Callable

import pytest
from PIL import Image

from nte_dice_analysis.io import load_json
from nte_dice_analysis.io import write_json
from nte_dice_analysis.models import Record
from nte_dice_analysis.models import OcrPrediction
from nte_dice_analysis.constants import POOL_TYPES
from nte_dice_analysis.gui_workflow import CropConfig
from nte_dice_analysis.gui_workflow import ExportConfig
from nte_dice_analysis.gui_workflow import RecognizeConfig
from nte_dice_analysis.gui_workflow import run_crop
from nte_dice_analysis.gui_workflow import run_export
from nte_dice_analysis.gui_workflow import run_recognize

TIMESTAMP_TEXT = '2026\u5e745\u67087\u65e503:04:05'


class PoolTypeOcr:
    def __init__(self) -> None:
        self.image_sizes: list[tuple[int, int]] = []

    def predict(self, image: object) -> list[OcrPrediction]:
        size = getattr(image, 'shape')
        self.image_sizes.append((int(size[1]), int(size[0])))
        return [
            {
                'rec_texts': [POOL_TYPES[1]],
                'rec_scores': [0.99],
            },
        ]


class TableOcr:
    def __init__(self, *, include_timestamp: bool = True, item_name: str = 'UnknownItem') -> None:
        self.include_timestamp = include_timestamp
        self.item_name = item_name

    def predict(self, image: object) -> list[OcrPrediction]:
        texts = [self.item_name, 'x1']
        scores = [0.95, 0.90]
        boxes = [
            (230, 10, 330, 20),
            (520, 10, 560, 20),
        ]
        if self.include_timestamp:
            texts.append(TIMESTAMP_TEXT)
            scores.append(0.85)
            boxes.append((700, 10, 900, 20))
        return [
            {
                'rec_texts': texts,
                'rec_scores': scores,
                'rec_boxes': boxes,
            },
        ]


def test_run_crop_writes_named_table_crop(tmp_path: Path) -> None:
    source = tmp_path / 'source.png'
    Image.new('RGB', (100, 80), 'white').save(source)
    fake_ocr = PoolTypeOcr()

    result = run_crop(
        CropConfig(
            paths=[source],
            table_crop='10,20,50,60',
            pool_crop='70,10,90,30',
        ),
        ocr_factory=lambda options: fake_ocr,
    )

    assert len(result.written_paths) == 1
    assert result.skipped_paths == []
    assert result.written_paths[0].exists()
    assert Image.open(result.written_paths[0]).size == (40, 40)
    assert fake_ocr.image_sizes == [(20, 20)]


def test_run_crop_skips_existing_table_crop(tmp_path: Path) -> None:
    source = tmp_path / 'source.png'
    output = tmp_path / f'source.table.{POOL_TYPES[1]}.png'
    Image.new('RGB', (100, 80), 'white').save(source)
    Image.new('RGB', (40, 40), 'black').save(output)

    result = run_crop(
        CropConfig(paths=[source]),
        ocr_factory=lambda options: pytest.fail('OCR should not be initialized'),
    )

    assert result.written_paths == []
    assert result.skipped_paths == [output]


def test_run_recognize_writes_json_and_returns_records(tmp_path: Path) -> None:
    table = tmp_path / 'table.png'
    Image.new('RGB', (1000, 100), 'white').save(table)

    result = run_recognize(
        RecognizeConfig(
            paths=[table],
            pool_type=POOL_TYPES[1],
            row_count=2,
            row_top=0,
            row_bottom=1,
        ),
        ocr_factory=lambda options: TableOcr(),
    )

    json_out = table.with_suffix('.json')
    assert result.written_paths == [json_out]
    assert result.written_record_count == 1
    assert len(result.records) == 1
    assert load_json(json_out)[0].obtained_at == '2026-05-07 03:04:05'


def test_run_recognize_rejects_missing_timestamp(tmp_path: Path) -> None:
    table = tmp_path / 'table.png'
    Image.new('RGB', (1000, 100), 'white').save(table)

    with pytest.raises(ValueError, match='missing obtained_at'):
        run_recognize(
            RecognizeConfig(
                paths=[table],
                pool_type=POOL_TYPES[1],
                row_count=2,
                row_top=0,
                row_bottom=1,
            ),
            ocr_factory=lambda options: TableOcr(include_timestamp=False),
        )

    assert not table.with_suffix('.json').exists()


def test_run_recognize_reports_missing_known_items(tmp_path: Path) -> None:
    table = tmp_path / 'table.png'
    known_items = tmp_path / 'known_items.txt'
    Image.new('RGB', (1000, 100), 'white').save(table)
    known_items.write_text('KnownItem\n', encoding='utf-8')

    result = run_recognize(
        RecognizeConfig(
            paths=[table],
            pool_type=POOL_TYPES[1],
            row_count=2,
            row_top=0,
            row_bottom=1,
            known_items_path=known_items,
        ),
        ocr_factory=lambda options: TableOcr(item_name='NotListed'),
    )

    assert len(result.missing_known_items) == 1
    assert result.missing_known_items[0].item_name == 'NotListed'
    assert result.missing_known_items[0].occurrence_count == 1


def test_run_export_writes_selected_outputs(
    tmp_path: Path,
    record_factory: Callable[..., Record],
) -> None:
    json_in = tmp_path / 'records.json'
    xlsx_out = tmp_path / 'records.xlsx'
    png_out = tmp_path / 'records.png'
    write_json(json_in, [record_factory()])

    result = run_export(
        ExportConfig(
            paths=[json_in],
            xlsx_out=xlsx_out,
            png_out=png_out,
        ),
    )

    assert xlsx_out.exists()
    assert png_out.exists()
    assert result.raw_record_count == 1
    assert result.exported_record_count == 1
    assert result.summary


def test_run_export_surfaces_validation_errors(
    tmp_path: Path,
    record_factory: Callable[..., Record],
) -> None:
    json_in = tmp_path / 'records.json'
    write_json(json_in, [record_factory(obtained_at='')])

    with pytest.raises(ValueError, match='missing obtained_at'):
        run_export(ExportConfig(paths=[json_in], xlsx_out=tmp_path / 'records.xlsx', png_out=None))
