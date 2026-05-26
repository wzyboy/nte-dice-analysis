from pathlib import Path
from collections.abc import Callable

import pytest

from nte_dice_analysis import cli
from nte_dice_analysis.io import load_json
from nte_dice_analysis.io import write_json
from nte_dice_analysis.models import Record


def make_cli_records(
    record_factory: Callable[..., Record],
    *,
    prefix: str,
    count: int,
    confidence: float = 0.9,
) -> list[Record]:
    return [
        record_factory(
            source_image=f'{prefix}/page{index}.png',
            page_row=1,
            roll_points=str((index % 6) + 1),
            item_name=f'角色·{prefix}{index}',
            obtained_at=f'2026-01-02 03:{index:02}:05',
            confidence=confidence,
        )
        for index in range(count)
    ]


def patch_ocr_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    new_records: list[Record],
) -> None:
    monkeypatch.setattr(cli, 'create_ocr', lambda options: object())
    monkeypatch.setattr(
        cli,
        'process_image',
        lambda image_path, ocr, options, known_items: list(new_records),
    )


def test_cli_merges_existing_json_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    record_factory: Callable[..., Record],
) -> None:
    json_out = tmp_path / 'records.json'
    xlsx_out = tmp_path / 'records.xlsx'
    existing_records = make_cli_records(record_factory, prefix='old', count=10)
    new_records = make_cli_records(record_factory, prefix='new', count=5)
    write_json(json_out, existing_records)
    patch_ocr_pipeline(monkeypatch, new_records)

    cli.main(
        [
            str(tmp_path / 'dir2.png'),
            '--json-out',
            str(json_out),
            '--xlsx-out',
            str(xlsx_out),
        ],
    )

    saved_records = load_json(json_out)
    saved_names = {record.item_name for record in saved_records}
    assert len(saved_records) == 15
    assert saved_names == {record.item_name for record in [*existing_records, *new_records]}
    assert xlsx_out.exists()
    assert 'loaded 10 existing records; OCR produced 5 rows; wrote 15 records' in capsys.readouterr().out


def test_cli_overwrite_ignores_existing_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_factory: Callable[..., Record],
) -> None:
    json_out = tmp_path / 'records.json'
    xlsx_out = tmp_path / 'records.xlsx'
    write_json(json_out, make_cli_records(record_factory, prefix='old', count=3))
    new_records = make_cli_records(record_factory, prefix='new', count=2)
    patch_ocr_pipeline(monkeypatch, new_records)

    cli.main(
        [
            str(tmp_path / 'dir2.png'),
            '--json-out',
            str(json_out),
            '--xlsx-out',
            str(xlsx_out),
            '--overwrite',
        ],
    )

    saved_records = load_json(json_out)
    assert len(saved_records) == 2
    assert {record.item_name for record in saved_records} == {record.item_name for record in new_records}


def test_cli_deduplicates_existing_and_new_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_factory: Callable[..., Record],
) -> None:
    json_out = tmp_path / 'records.json'
    xlsx_out = tmp_path / 'records.xlsx'
    existing_record = record_factory(
        source_image='old/page.png',
        item_name='角色·重叠',
        obtained_at='2026-01-02 03:04:05',
        confidence=0.1,
    )
    better_record = record_factory(
        source_image='new/page.png',
        item_name='角色·重叠',
        obtained_at='2026-01-02 03:04:05',
        confidence=0.9,
    )
    write_json(json_out, [existing_record])
    patch_ocr_pipeline(monkeypatch, [better_record])

    cli.main(
        [
            str(tmp_path / 'dir2.png'),
            '--json-out',
            str(json_out),
            '--xlsx-out',
            str(xlsx_out),
        ],
    )

    assert load_json(json_out) == [better_record]
