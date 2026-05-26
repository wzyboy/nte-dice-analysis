from collections.abc import Callable

import pytest

from nte_dice_analysis.dedup import merge_fragment
from nte_dice_analysis.dedup import deduplicate_records
from nte_dice_analysis.dedup import validate_pull_groups
from nte_dice_analysis.models import Record
from nte_dice_analysis.constants import GIFT_ROLL_POINTS


def test_merge_fragment_replaces_overlap_with_higher_confidence(
    record_factory: Callable[..., Record],
) -> None:
    first = [
        record_factory(source_image='page1.png', page_row=1, roll_points='1', item_name='角色·薄荷'),
        record_factory(source_image='page1.png', page_row=2, roll_points='2', item_name='角色·哈尼娅'),
    ]
    second = [
        record_factory(
            source_image='page2.png',
            page_row=1,
            roll_points='2',
            item_name='角色·哈尼娅',
            confidence=0.99,
        ),
        record_factory(source_image='page2.png', page_row=2, roll_points='3', item_name='角色·翳'),
    ]

    merged = merge_fragment(first, second)

    assert [record.item_name for record in merged] == ['角色·薄荷', '角色·哈尼娅', '角色·翳']
    assert merged[1].source_image.name == 'page2.png'


def test_deduplicate_records_merges_pages_with_timestamp_overlap(
    record_factory: Callable[..., Record],
) -> None:
    records = [
        record_factory(source_image='page1.png', page_row=1, roll_points='1', item_name='角色·薄荷'),
        record_factory(source_image='page1.png', page_row=2, roll_points='2', item_name='角色·哈尼娅'),
        record_factory(
            source_image='page2.png',
            page_row=1,
            roll_points='2',
            item_name='角色·哈尼娅',
            confidence=0.99,
        ),
        record_factory(source_image='page2.png', page_row=2, roll_points='3', item_name='角色·翳'),
    ]

    deduped = deduplicate_records(records)

    assert [record.item_name for record in deduped] == ['角色·薄荷', '角色·哈尼娅', '角色·翳']
    assert deduped[1].confidence == 0.99


def test_deduplicate_records_rejects_missing_timestamp(
    record_factory: Callable[..., Record],
) -> None:
    records = [record_factory(obtained_at='')]

    with pytest.raises(ValueError, match='records have missing timestamps'):
        deduplicate_records(records)


def test_validate_pull_groups_accepts_single_pull_and_ten_pull_with_gift(
    record_factory: Callable[..., Record],
) -> None:
    single = [record_factory(roll_points='1')]
    ten_with_gift = [record_factory(roll_points=str((index % 6) + 1)) for index in range(10)]
    ten_with_gift.append(record_factory(roll_points=GIFT_ROLL_POINTS))

    assert validate_pull_groups(single) == []
    assert validate_pull_groups(ten_with_gift) == []


def test_validate_pull_groups_warns_on_missing_pool_and_missing_gift(
    record_factory: Callable[..., Record],
) -> None:
    missing_pool = [record_factory(pool_type='', roll_points='1')]
    ten_without_gift = [record_factory(roll_points=str((index % 6) + 1)) for index in range(10)]

    assert validate_pull_groups(missing_pool) == ['2026-01-02 03:04:05: missing pool_type']
    assert validate_pull_groups(ten_without_gift) == [
        '限定棋盘 2026-01-02 03:04:05: found 10 pulls but no 集点赠礼',
    ]
