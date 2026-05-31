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
from nte_dice_analysis.gui_workflow import SimpleConfig
from nte_dice_analysis.gui_workflow import ProgressEvent
from nte_dice_analysis.gui_workflow import RecognizeConfig
from nte_dice_analysis.gui_workflow import run_crop
from nte_dice_analysis.gui_workflow import run_export
from nte_dice_analysis.gui_workflow import run_simple
from nte_dice_analysis.gui_workflow import run_recognize
from nte_dice_analysis.gui_workflow import load_existing_analysis

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


class SimpleOcr:
    def __init__(self) -> None:
        self.image_sizes: list[tuple[int, int]] = []

    def predict(self, image: object) -> list[OcrPrediction]:
        size = getattr(image, 'shape')
        width, height = int(size[1]), int(size[0])
        self.image_sizes.append((width, height))
        if height < 300:
            return [
                {
                    'rec_texts': [POOL_TYPES[1]],
                    'rec_scores': [0.99],
                },
            ]

        return [
            {
                'rec_texts': ['1', 'UnknownItem', 'x1', TIMESTAMP_TEXT],
                'rec_scores': [0.95, 0.95, 0.95, 0.95],
                'rec_boxes': [
                    (200, 180, 300, 200),
                    (700, 180, 900, 200),
                    (1350, 180, 1450, 200),
                    (1800, 180, 2200, 200),
                ],
            },
        ]


def test_run_crop_writes_named_table_crop(tmp_path: Path) -> None:
    source = tmp_path / 'source.png'
    Image.new('RGB', (100, 80), 'white').save(source)
    fake_ocr = PoolTypeOcr()
    progress_events: list[ProgressEvent] = []

    result = run_crop(
        CropConfig(
            paths=[source],
            table_crop='10,20,50,60',
            pool_crop='70,10,90,30',
        ),
        ocr_factory=lambda options: fake_ocr,
        progress=progress_events.append,
    )

    assert len(result.written_paths) == 1
    assert result.skipped_paths == []
    assert result.written_paths[0].exists()
    assert Image.open(result.written_paths[0]).size == (40, 40)
    assert fake_ocr.image_sizes == [(20, 20)]
    assert any(event.message == f'Cropping {source} (1/1)' for event in progress_events)
    assert any(event.current == 1 and event.total == 1 for event in progress_events)


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
    progress_events: list[ProgressEvent] = []

    result = run_recognize(
        RecognizeConfig(
            paths=[table],
            pool_type=POOL_TYPES[1],
            row_boundaries='0,0.5,1',
        ),
        ocr_factory=lambda options: TableOcr(),
        progress=progress_events.append,
    )

    json_out = table.with_suffix('.json')
    assert result.written_paths == [json_out]
    assert result.written_record_count == 1
    assert len(result.records) == 1
    assert load_json(json_out)[0].obtained_at == '2026-05-07 03:04:05'
    assert any(event.message == f'Recognizing {table} (1/1)' for event in progress_events)
    assert any(event.current == 1 and event.total == 1 for event in progress_events)


def test_run_recognize_accepts_explicit_row_boundaries(tmp_path: Path) -> None:
    table = tmp_path / 'table.png'
    Image.new('RGB', (1000, 100), 'white').save(table)

    result = run_recognize(
        RecognizeConfig(
            paths=[table],
            pool_type=POOL_TYPES[1],
            row_boundaries='0,0.5,1',
        ),
        ocr_factory=lambda options: TableOcr(),
    )

    assert result.written_record_count == 1
    assert result.records[0].page_row == 1


def test_run_recognize_rejects_missing_timestamp(tmp_path: Path) -> None:
    table = tmp_path / 'table.png'
    Image.new('RGB', (1000, 100), 'white').save(table)

    with pytest.raises(ValueError, match='missing obtained_at'):
        run_recognize(
            RecognizeConfig(
                paths=[table],
                pool_type=POOL_TYPES[1],
                row_boundaries='0,0.5,1',
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
            row_boundaries='0,0.5,1',
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
    progress_events: list[ProgressEvent] = []

    result = run_export(
        ExportConfig(
            paths=[json_in],
            xlsx_out=xlsx_out,
            png_out=png_out,
        ),
        progress=progress_events.append,
    )

    assert xlsx_out.exists()
    assert png_out.exists()
    assert result.raw_record_count == 1
    assert result.exported_record_count == 1
    assert result.summary
    assert any(event.message == f'Loading {json_in} (1/1)' for event in progress_events)
    assert any(event.current == 1 and event.total == 1 for event in progress_events)


def test_run_export_deduplicates_json_inputs(
    tmp_path: Path,
    record_factory: Callable[..., Record],
) -> None:
    first_json = tmp_path / 'page1.json'
    second_json = tmp_path / 'page2.json'
    xlsx_out = tmp_path / 'records.xlsx'
    png_out = tmp_path / 'records.png'
    write_json(first_json, [record_factory(source_image='page1.png', confidence=0.1)])
    write_json(second_json, [record_factory(source_image='page2.png', confidence=0.9)])

    result = run_export(
        ExportConfig(
            paths=[first_json, second_json],
            xlsx_out=xlsx_out,
            png_out=png_out,
        ),
    )

    assert xlsx_out.exists()
    assert png_out.exists()
    assert result.raw_record_count == 2
    assert result.exported_record_count == 1
    assert len(result.records) == 1
    assert result.records[0].confidence == 0.9


def test_run_export_creates_output_parent_directories(
    tmp_path: Path,
    record_factory: Callable[..., Record],
) -> None:
    json_in = tmp_path / 'records.json'
    xlsx_out = tmp_path / 'exports' / 'nested' / 'records.xlsx'
    png_out = tmp_path / 'exports' / 'nested' / 'records.png'
    write_json(json_in, [record_factory()])

    run_export(
        ExportConfig(
            paths=[json_in],
            xlsx_out=xlsx_out,
            png_out=png_out,
        ),
    )

    assert xlsx_out.exists()
    assert png_out.exists()


def test_run_export_surfaces_validation_errors(
    tmp_path: Path,
    record_factory: Callable[..., Record],
) -> None:
    json_in = tmp_path / 'records.json'
    write_json(json_in, [record_factory(obtained_at='')])

    with pytest.raises(ValueError, match='missing obtained_at'):
        run_export(ExportConfig(paths=[json_in], xlsx_out=tmp_path / 'records.xlsx', png_out=None))


def test_load_existing_analysis_loads_json_files(
    tmp_path: Path,
    record_factory: Callable[..., Record],
) -> None:
    first_json = tmp_path / 'page1.json'
    second_json = tmp_path / 'page2.json'
    write_json(first_json, [record_factory(source_image='page1.png', confidence=0.1)])
    write_json(second_json, [record_factory(source_image='page2.png', confidence=0.9)])

    result = load_existing_analysis(tmp_path)

    assert result.json_paths == [first_json, second_json]
    assert result.raw_record_count == 2
    assert result.exported_record_count == 1
    assert len(result.records) == 1
    assert result.records[0].confidence == 0.9
    assert result.summary


def test_load_existing_analysis_ignores_missing_and_empty_directories(tmp_path: Path) -> None:
    missing_result = load_existing_analysis(tmp_path / 'missing')
    empty_result = load_existing_analysis(tmp_path)

    assert missing_result.json_paths == []
    assert missing_result.raw_record_count == 0
    assert missing_result.exported_record_count == 0
    assert missing_result.records == []
    assert empty_result.json_paths == []
    assert empty_result.raw_record_count == 0
    assert empty_result.exported_record_count == 0
    assert empty_result.records == []


def test_run_simple_creates_intermediates_and_final_outputs(tmp_path: Path) -> None:
    source = tmp_path / 'source.png'
    out_dir = tmp_path / 'out'
    Image.new('RGB', (3840, 2160), 'white').save(source)
    fake_ocr = SimpleOcr()
    progress_events: list[ProgressEvent] = []

    result = run_simple(
        SimpleConfig(paths=[source], out_dir=out_dir),
        ocr_factory=lambda options: fake_ocr,
        progress=progress_events.append,
    )

    table = out_dir / f'source.table.{POOL_TYPES[1]}.png'
    json_out = table.with_suffix('.json')
    assert table.exists()
    assert json_out.exists()
    assert (out_dir / 'records.xlsx').exists()
    assert (out_dir / 'records.png').exists()
    assert result.table_paths == [table]
    assert result.json_paths == [json_out]
    assert result.xlsx_path == out_dir / 'records.xlsx'
    assert result.png_path == out_dir / 'records.png'
    assert result.raw_record_count == 1
    assert result.exported_record_count == 1
    assert len(result.records) == 1
    assert load_json(json_out)[0].obtained_at == '2026-05-07 03:04:05'
    assert len(fake_ocr.image_sizes) == 2
    progress_messages = [event.message for event in progress_events]
    assert f'Cropping {source} (1/1)' in progress_messages
    assert f'Recognizing {table} (1/1)' in progress_messages
    assert any(event.current == 1 and event.total == 1 for event in progress_events)


def test_run_simple_reuses_intermediates_and_rewrites_final_outputs(tmp_path: Path) -> None:
    source = tmp_path / 'source.png'
    out_dir = tmp_path / 'out'
    Image.new('RGB', (3840, 2160), 'white').save(source)

    run_simple(
        SimpleConfig(paths=[source], out_dir=out_dir),
        ocr_factory=lambda options: SimpleOcr(),
    )
    xlsx_out = out_dir / 'records.xlsx'
    png_out = out_dir / 'records.png'
    xlsx_out.write_text('old', encoding='utf-8')
    png_out.write_bytes(b'old')

    result = run_simple(
        SimpleConfig(paths=[source], out_dir=out_dir),
        ocr_factory=lambda options: pytest.fail('OCR should not be initialized'),
    )

    assert result.raw_record_count == 1
    assert xlsx_out.read_bytes() != b'old'
    assert png_out.read_bytes() != b'old'


def test_run_simple_exports_all_json_files_in_output_dir(
    tmp_path: Path,
    record_factory: Callable[..., Record],
) -> None:
    source = tmp_path / 'source.png'
    out_dir = tmp_path / 'out'
    existing_json = out_dir / 'existing.json'
    Image.new('RGB', (3840, 2160), 'white').save(source)
    out_dir.mkdir()
    write_json(existing_json, [record_factory(source_image='existing.png')])
    progress_events: list[ProgressEvent] = []

    result = run_simple(
        SimpleConfig(paths=[source], out_dir=out_dir),
        ocr_factory=lambda options: SimpleOcr(),
        progress=progress_events.append,
    )

    table = out_dir / f'source.table.{POOL_TYPES[1]}.png'
    json_out = table.with_suffix('.json')
    assert result.json_paths == [existing_json, json_out]
    assert result.raw_record_count == 2
    assert result.exported_record_count == 2
    assert len(result.records) == 2
    assert any('loaded 2 records from 2 JSON files' in event.message for event in progress_events)


def test_run_simple_rejects_missing_screenshots(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match='select at least one screenshot'):
        run_simple(SimpleConfig(paths=[], out_dir=tmp_path / 'out'))

    empty = tmp_path / 'empty'
    empty.mkdir()
    with pytest.raises(ValueError, match='no full screenshots found'):
        run_simple(SimpleConfig(paths=[empty], out_dir=tmp_path / 'out'))
