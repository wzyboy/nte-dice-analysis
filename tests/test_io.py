from pathlib import Path
from collections.abc import Callable

import pytest

from nte_dice_analysis.io import load_json
from nte_dice_analysis.io import write_json
from nte_dice_analysis.io import load_known_items
from nte_dice_analysis.models import Record


def test_load_json_returns_empty_list_for_missing_file(tmp_path: Path) -> None:
    assert load_json(tmp_path / 'missing.json') == []


def test_load_json_reads_written_records(
    tmp_path: Path,
    record_factory: Callable[..., Record],
) -> None:
    path = tmp_path / 'records.json'
    records = [record_factory(source_image='debug/page.png', page_row=3, confidence=0.876)]

    write_json(path, records)

    assert load_json(path) == records


def test_load_json_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / 'records.json'
    path.write_text('{', encoding='utf-8')

    with pytest.raises(ValueError, match='invalid records JSON'):
        load_json(path)


def test_load_json_rejects_non_list_json(tmp_path: Path) -> None:
    path = tmp_path / 'records.json'
    path.write_text('{}', encoding='utf-8')

    with pytest.raises(ValueError, match='must contain a list of objects'):
        load_json(path)


def test_load_known_items_uses_packaged_resource_by_default() -> None:
    known_items = load_known_items()

    assert '角色·薄荷' in known_items
    assert '弧盘·「我们。」' in known_items


def test_load_known_items_allows_custom_file(tmp_path: Path) -> None:
    path = tmp_path / 'known_items.txt'
    path.write_text('# comment\n\n自定义·道具\n', encoding='utf-8')

    assert load_known_items(path) == ['自定义·道具']
