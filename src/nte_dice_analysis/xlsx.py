from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .constants import A_CLASS, B_CLASS, GIFT_ROLL_POINTS, S_CLASS, XLSX_HEADERS

RARITY_FILLS = {
    S_CLASS: PatternFill(fill_type='solid', fgColor='FCE7A1'),
    A_CLASS: PatternFill(fill_type='solid', fgColor='E9D5FF'),
    B_CLASS: PatternFill(fill_type='solid', fgColor='E5E7EB'),
}
HEADER_FILL = PatternFill(fill_type='solid', fgColor='1F2937')
HEADER_FONT = Font(color='FFFFFF', bold=True)
THIN_BORDER = Border(
    left=Side(style='thin', color='D1D5DB'),
    right=Side(style='thin', color='D1D5DB'),
    top=Side(style='thin', color='D1D5DB'),
    bottom=Side(style='thin', color='D1D5DB'),
)
DETERMINISTIC_XLSX_DATETIME = datetime(2000, 1, 1, 0, 0, 0)
DETERMINISTIC_ZIP_TIMESTAMP = (2000, 1, 1, 0, 0, 0)


def write_xlsx(path: Path, records: list[dict[str, str]]) -> None:
    workbook = Workbook()
    default_sheet = workbook.active
    workbook.remove(default_sheet)

    for pool_type, pool_records in records_by_pool(records).items():
        write_pool_sheet(workbook, pool_type or 'unknown pool', pool_records)

    if not workbook.sheetnames:
        write_pool_sheet(workbook, 'Records', [])

    workbook.properties.created = DETERMINISTIC_XLSX_DATETIME
    workbook.properties.modified = DETERMINISTIC_XLSX_DATETIME
    workbook.save(path)
    normalize_xlsx_archive(path)


def records_by_pool(records: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for record in records:
        grouped[record.get('pool_type', '')].append(record)
    return dict(grouped)


def write_pool_sheet(
    workbook: Workbook,
    pool_type: str,
    records: list[dict[str, str]],
) -> None:
    sheet = workbook.create_sheet(safe_sheet_title(pool_type, workbook.sheetnames))
    sheet.append(XLSX_HEADERS)

    pulls_since_last_s = pulls_since_last_s_character(records)
    for record, pulls_since in zip(records, pulls_since_last_s, strict=True):
        sheet.append(
            [
                record['roll_points'],
                record['item_name'],
                record['rarity'],
                quantity_value(record['quantity']),
                datetime_value(record['obtained_at']),
                pulls_since,
            ],
        )

    style_sheet(sheet, records)


def safe_sheet_title(title: str, existing_titles: list[str]) -> str:
    cleaned = ''.join('_' if char in r'[]:*?/\\' else char for char in title)[:31] or 'Sheet'
    if cleaned not in existing_titles:
        return cleaned

    suffix = 2
    while True:
        suffix_text = f' {suffix}'
        candidate = f'{cleaned[:31 - len(suffix_text)]}{suffix_text}'
        if candidate not in existing_titles:
            return candidate
        suffix += 1


def pulls_since_last_s_character(records: list[dict[str, str]]) -> list[int | None]:
    values: list[int | None] = [None] * len(records)
    counter = 0

    for index in range(len(records) - 1, -1, -1):
        record = records[index]
        if record['roll_points'] == GIFT_ROLL_POINTS:
            values[index] = None
            continue

        counter += 1
        values[index] = counter

        if is_s_class_character(record):
            counter = 0

    return values


def is_s_class_character(record: dict[str, str]) -> bool:
    return record.get('rarity') == S_CLASS and record.get('item_name', '').startswith('角色·')


def quantity_value(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def datetime_value(value: str) -> datetime | str:
    try:
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return value


def style_sheet(sheet, records: list[dict[str, str]]) -> None:
    sheet.freeze_panes = 'A2'
    sheet.sheet_view.showGridLines = False

    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = THIN_BORDER

    for row_index, record in enumerate(records, start=2):
        fill = RARITY_FILLS.get(record.get('rarity'), RARITY_FILLS[B_CLASS])
        for cell in sheet[row_index]:
            cell.fill = fill
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical='center')
        sheet.cell(row=row_index, column=5).number_format = 'yyyy-mm-dd hh:mm:ss'
        sheet.cell(row=row_index, column=6).number_format = '0'

    set_column_widths(sheet)
    sheet.auto_filter.ref = f'A1:{get_column_letter(len(XLSX_HEADERS))}{max(sheet.max_row, 1)}'


def normalize_xlsx_archive(path: Path) -> None:
    with ZipFile(path, 'r') as source:
        entries = [
            (info, normalize_xlsx_entry(info.filename, source.read(info.filename)))
            for info in source.infolist()
        ]

    temp_path = path.with_suffix(f'{path.suffix}.tmp')
    with ZipFile(temp_path, 'w', compression=ZIP_DEFLATED, compresslevel=6) as target:
        for source_info, data in entries:
            info = ZipInfo(source_info.filename, DETERMINISTIC_ZIP_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = source_info.external_attr
            target.writestr(info, data)

    temp_path.replace(path)


def normalize_xlsx_entry(filename: str, data: bytes) -> bytes:
    if filename != 'docProps/core.xml':
        return data

    timestamp = '2000-01-01T00:00:00Z'
    text = data.decode('utf-8')
    text = re.sub(
        r'(<dcterms:created\b[^>]*>).*?(</dcterms:created>)',
        rf'\g<1>{timestamp}\2',
        text,
    )
    text = re.sub(
        r'(<dcterms:modified\b[^>]*>).*?(</dcterms:modified>)',
        rf'\g<1>{timestamp}\2',
        text,
    )
    return text.encode('utf-8')


def set_column_widths(sheet) -> None:
    widths = [14, 28, 12, 10, 22, 12]
    for column_index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(column_index)].width = width
