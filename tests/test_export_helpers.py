from __future__ import annotations

from pathlib import Path
from collections.abc import Callable

from openpyxl import load_workbook

from nte_dice_analysis.xlsx import write_xlsx
from nte_dice_analysis.xlsx import records_by_pool
from nte_dice_analysis.xlsx import safe_sheet_title
from nte_dice_analysis.xlsx import split_item_type_name
from nte_dice_analysis.xlsx import pulls_since_last_s_character
from nte_dice_analysis.models import Record
from nte_dice_analysis.constants import GIFT_ROLL_POINTS


def test_record_output_round_trip(record_factory: Callable[..., Record]) -> None:
    record = record_factory(source_image='debug/page.png', page_row=3, confidence=0.876)

    row = record.to_output_row()
    restored = Record.from_output_row(row)

    assert row['page_row'] == '3'
    assert row['confidence'] == '0.876'
    assert restored == Record(
        pool_type=record.pool_type,
        source_image=Path('debug/page.png'),
        page_row=3,
        roll_points=record.roll_points,
        item_name=record.item_name,
        rarity=record.rarity,
        item_name_raw=record.item_name_raw,
        quantity=record.quantity,
        obtained_at=record.obtained_at,
        obtained_at_raw=record.obtained_at_raw,
        confidence=0.876,
    )


def test_xlsx_grouping_and_sheet_helpers(record_factory: Callable[..., Record]) -> None:
    records = [
        record_factory(pool_type='限定棋盘'),
        record_factory(pool_type='标准棋盘'),
    ]

    assert list(records_by_pool(records)) == ['限定棋盘', '标准棋盘']
    assert split_item_type_name('角色·薄荷') == ('角色', '薄荷')
    assert split_item_type_name('未知') == ('', '未知')
    assert safe_sheet_title('bad[]:*?/\\name', []) == 'bad_______name'
    assert safe_sheet_title('限定棋盘', ['限定棋盘']) == '限定棋盘 2'


def test_pulls_since_last_s_character_counts_from_oldest_record(
    record_factory: Callable[..., Record],
) -> None:
    records = [
        record_factory(page_row=1, roll_points='3', item_name='角色·哈尼娅', rarity='A-Class'),
        record_factory(page_row=2, roll_points='2', item_name='角色·薄荷', rarity='S-Class'),
        record_factory(page_row=3, roll_points='1', item_name='道具·质实骰子', rarity='B-Class'),
        record_factory(page_row=4, roll_points=GIFT_ROLL_POINTS, item_name='道具·赠礼', rarity='B-Class'),
    ]

    assert pulls_since_last_s_character(records) == [1, 2, 1, None]


def test_write_xlsx_creates_pool_sheet(
    tmp_path: Path,
    record_factory: Callable[..., Record],
) -> None:
    path = tmp_path / 'records.xlsx'
    records = [record_factory()]

    write_xlsx(path, records)

    workbook = load_workbook(path)
    sheet = workbook['限定棋盘']
    assert sheet['A1'].value == '投掷点数'
    assert sheet['B2'].value == '角色'
    assert sheet['C2'].value == '薄荷'
