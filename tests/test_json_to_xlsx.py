from pathlib import Path
from collections.abc import Callable

import pytest
from openpyxl import load_workbook

from nte_dice_analysis import json_to_xlsx
from nte_dice_analysis.io import write_json
from nte_dice_analysis.models import Record


def test_json_to_xlsx_writes_default_xlsx_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    record_factory: Callable[..., Record],
) -> None:
    json_in = tmp_path / 'records.json'
    write_json(json_in, [record_factory()])

    json_to_xlsx.main([str(json_in)])

    xlsx_out = tmp_path / 'records.xlsx'
    workbook = load_workbook(xlsx_out)
    sheet = workbook['限定棋盘']
    assert sheet['A1'].value == '投掷点数'
    assert sheet['C2'].value == '薄荷'
    assert f'wrote 1 records from {json_in} to {xlsx_out}' in capsys.readouterr().out


def test_json_to_xlsx_allows_explicit_output_path(
    tmp_path: Path,
    record_factory: Callable[..., Record],
) -> None:
    json_in = tmp_path / 'records.json'
    xlsx_out = tmp_path / 'debug.xlsx'
    write_json(json_in, [record_factory()])

    json_to_xlsx.main([str(json_in), '--xlsx-out', str(xlsx_out)])

    assert xlsx_out.exists()


def test_json_to_xlsx_exits_on_malformed_json(tmp_path: Path) -> None:
    json_in = tmp_path / 'records.json'
    json_in.write_text('{', encoding='utf-8')

    with pytest.raises(SystemExit, match='invalid records JSON'):
        json_to_xlsx.main([str(json_in)])
