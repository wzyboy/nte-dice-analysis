from pathlib import Path
from collections.abc import Callable

import pytest
from PIL import Image
from openpyxl import load_workbook

from nte_dice_analysis import crop_cli
from nte_dice_analysis import recognize_cli
from nte_dice_analysis import merge_xlsx_cli
from nte_dice_analysis.io import load_json
from nte_dice_analysis.io import write_json
from nte_dice_analysis.models import Record
from nte_dice_analysis.models import OcrPrediction


class PoolTypeOcr:
    def __init__(self) -> None:
        self.image_sizes: list[tuple[int, int]] = []

    def predict(self, image: object) -> list[OcrPrediction]:
        size = getattr(image, 'shape')
        self.image_sizes.append((int(size[1]), int(size[0])))
        return [
            {
                'rec_texts': ['标准棋盘'],
                'rec_scores': [0.99],
            },
        ]


class TableOcr:
    def predict(self, image: object) -> list[OcrPrediction]:
        return [
            {
                'rec_texts': ['角色', '·薄荷', 'x1', '2026年5月7日03:04:05'],
                'rec_scores': [0.95, 0.90, 0.85, 0.80],
                'rec_boxes': [
                    (230, 10, 270, 20),
                    (280, 10, 330, 20),
                    (520, 10, 560, 20),
                    (700, 10, 900, 20),
                ],
            },
        ]


def test_crop_cli_writes_named_table_crop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / '2026-05-25_21-06-03_NTE.png'
    Image.new('RGB', (100, 80), 'white').save(source)
    fake_ocr = PoolTypeOcr()
    monkeypatch.setattr(crop_cli, 'create_ocr', lambda options: fake_ocr)

    crop_cli.main(
        [
            str(source),
            '--table-crop',
            '10,20,50,60',
            '--pool-crop',
            '70,10,90,30',
        ],
    )

    output = tmp_path / '2026-05-25_21-06-03_NTE.table.标准棋盘.png'
    assert output.exists()
    assert Image.open(output).size == (40, 40)
    assert fake_ocr.image_sizes == [(20, 20)]


def test_recognize_cli_writes_json_for_cropped_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = tmp_path / '2026-05-25_21-06-03_NTE.table.标准棋盘.png'
    Image.new('RGB', (1000, 100), 'white').save(table)
    monkeypatch.setattr(recognize_cli, 'create_ocr', lambda options: TableOcr())

    recognize_cli.main(
        [
            str(table),
            '--row-count',
            '2',
            '--row-top',
            '0',
            '--row-bottom',
            '1',
        ],
    )

    records = load_json(table.with_suffix('.json'))
    assert len(records) == 1
    assert records[0].pool_type == '标准棋盘'
    assert records[0].source_image == table
    assert records[0].item_name == '角色·薄荷'
    assert records[0].obtained_at == '2026-05-07 03:04:05'


def test_recognize_cli_requires_pool_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = tmp_path / 'cropped.png'
    Image.new('RGB', (1000, 100), 'white').save(table)
    monkeypatch.setattr(recognize_cli, 'create_ocr', lambda options: TableOcr())

    with pytest.raises(SystemExit, match='could not infer pool type'):
        recognize_cli.main([str(table)])


def test_merge_xlsx_cli_deduplicates_json_inputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    record_factory: Callable[..., Record],
) -> None:
    first_json = tmp_path / 'page1.json'
    second_json = tmp_path / 'page2.json'
    xlsx_out = tmp_path / 'records.xlsx'
    first = record_factory(source_image='page1.png', item_name='角色·薄荷', confidence=0.1)
    better = record_factory(source_image='page2.png', item_name='角色·薄荷', confidence=0.9)
    write_json(first_json, [first])
    write_json(second_json, [better])

    merge_xlsx_cli.main([str(first_json), str(second_json), '--xlsx-out', str(xlsx_out)])

    workbook = load_workbook(xlsx_out)
    sheet = workbook['限定棋盘']
    assert sheet.max_row == 2
    assert sheet['C2'].value == '薄荷'
    assert f'loaded 2 records from 2 JSON files; wrote 1 records to {xlsx_out}' in capsys.readouterr().out


def test_merge_xlsx_cli_emits_validation_warnings(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    record_factory: Callable[..., Record],
) -> None:
    json_in = tmp_path / 'records.json'
    records = [record_factory(roll_points=str((index % 6) + 1), item_name=f'角色·{index}') for index in range(10)]
    write_json(json_in, records)

    merge_xlsx_cli.main([str(json_in), '--xlsx-out', str(tmp_path / 'records.xlsx')])

    assert 'warning: 限定棋盘 2026-01-02 03:04:05: found 10 pulls but no 集点赠礼' in capsys.readouterr().err
