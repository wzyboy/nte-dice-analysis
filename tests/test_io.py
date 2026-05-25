from pathlib import Path

from nte_dice_analysis.io import load_known_items


def test_load_known_items_uses_packaged_resource_by_default() -> None:
    known_items = load_known_items()

    assert '角色·薄荷' in known_items
    assert '弧盘·「我们。」' in known_items


def test_load_known_items_allows_custom_file(tmp_path: Path) -> None:
    path = tmp_path / 'known_items.txt'
    path.write_text('# comment\n\n自定义·道具\n', encoding='utf-8')

    assert load_known_items(path) == ['自定义·道具']
