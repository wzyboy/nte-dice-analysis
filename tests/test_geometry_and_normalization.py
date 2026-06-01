import pytest

from nte_dice_analysis.geometry import parse_crop
from nte_dice_analysis.geometry import crop_box_to_pixels
from nte_dice_analysis.normalization import normalize_datetime
from nte_dice_analysis.normalization import normalize_quantity
from nte_dice_analysis.normalization import normalize_item_name
from nte_dice_analysis.normalization import normalize_pool_type
from nte_dice_analysis.normalization import comparable_item_text
from nte_dice_analysis.normalization import normalize_arc_item_name


def test_parse_crop_supports_normalized_and_pixel_coordinates() -> None:
    normalized = parse_crop('0.1, 0.2, 0.9, 0.8')
    pixels = parse_crop('10,20,90,80')

    assert crop_box_to_pixels(normalized, (1000, 500)) == (100, 100, 900, 400)
    assert crop_box_to_pixels(pixels, (1000, 500)) == (10, 20, 90, 80)


def test_parse_crop_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match='four comma-separated values'):
        parse_crop('0,0,1')

    with pytest.raises(ValueError, match='outside image'):
        crop_box_to_pixels(parse_crop('0.9,0,0.1,1'), (100, 100))


def test_normalize_pool_type_uses_fuzzy_known_values() -> None:
    assert normalize_pool_type(' 限 定 棋 盘 ') == '限定棋盘'
    assert normalize_pool_type('标准棋盤') == '标准棋盘'
    assert normalize_pool_type('弧盘研募') == '弧盘研募'
    assert normalize_pool_type('完全不像') == ''


def test_normalize_item_name_uses_comparable_text() -> None:
    known_items = ['弧盘·「我们。」', '角色·薄荷']

    assert comparable_item_text('弧盘-「我们。」') == '弧盘·「我们。」'
    assert normalize_item_name('角色■薄荷', known_items) == '角色·薄荷'
    assert normalize_item_name('未知道具', known_items) == '未知道具'


def test_normalize_arc_item_name_matches_known_prefixed_names_without_adding_prefix() -> None:
    assert normalize_arc_item_name('行进于时间之外', ['弧盘·行进于时间之外']) == '行进于时间之外'


def test_normalize_quantity_and_datetime() -> None:
    assert normalize_quantity('x 10') == '10'
    assert normalize_quantity('赠礼') == '赠礼'
    assert normalize_datetime('2026年5月7日03:04:05') == '2026-05-07 03:04:05'
    assert normalize_datetime('2026年5月7日0304:05') == '2026-05-07 03:04:05'
    assert normalize_datetime('not a datetime') == 'notadatetime'
