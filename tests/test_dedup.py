from collections.abc import Callable

import pytest

from nte_dice_analysis.dedup import merge_fragment
from nte_dice_analysis.dedup import pull_group_errors
from nte_dice_analysis.dedup import deduplicate_records
from nte_dice_analysis.dedup import require_valid_pull_groups
from nte_dice_analysis.models import Record
from nte_dice_analysis.constants import GIFT_ROLL_POINTS


def test_merge_fragment_replaces_overlap_with_higher_confidence(
    record_factory: Callable[..., Record],
) -> None:
    first = [
        record_factory(source_image='page1.png', page_row=1, roll_points='1', item_name='角色·娜娜莉'),
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

    assert [record.item_name for record in merged] == ['角色·娜娜莉', '角色·哈尼娅', '角色·翳']
    assert merged[1].source_image.name == 'page2.png'


def test_deduplicate_records_merges_pages_with_timestamp_overlap(
    record_factory: Callable[..., Record],
) -> None:
    records = [
        record_factory(source_image='page1.png', page_row=1, roll_points='1', item_name='角色·娜娜莉'),
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

    assert [record.item_name for record in deduped] == ['角色·娜娜莉', '角色·哈尼娅', '角色·翳']
    assert deduped[1].confidence == 0.99


def test_deduplicate_records_rejects_missing_timestamp(
    record_factory: Callable[..., Record],
) -> None:
    records = [record_factory(obtained_at='')]

    with pytest.raises(ValueError, match='records have missing timestamps'):
        deduplicate_records(records)


def test_pull_group_errors_accepts_valid_pull_groups(
    record_factory: Callable[..., Record],
) -> None:
    single = [record_factory(roll_points='1')]
    single_with_gift = [
        record_factory(roll_points='1'),
        record_factory(roll_points=GIFT_ROLL_POINTS, item_name='道具·赠礼'),
    ]
    ten_with_gift = [record_factory(roll_points=str((index % 6) + 1)) for index in range(10)]
    ten_with_gift.append(record_factory(roll_points=GIFT_ROLL_POINTS))

    assert pull_group_errors(single) == []
    assert pull_group_errors(single_with_gift) == []
    assert pull_group_errors(ten_with_gift) == []


def test_require_valid_pull_groups_rejects_missing_pool_and_invalid_counts(
    record_factory: Callable[..., Record],
) -> None:
    missing_pool = [record_factory(pool_type='', roll_points='1')]
    ten_without_gift = [record_factory(page_row=index + 1, roll_points=str((index % 6) + 1)) for index in range(10)]

    with pytest.raises(ValueError, match='missing pool_type'):
        require_valid_pull_groups(missing_pool)

    with pytest.raises(ValueError, match='found 10 pulls and 0 gifts') as error:
        require_valid_pull_groups(ten_without_gift)
    assert 'page.png, row 1' in str(error.value)
    assert 'page.png, row 10' in str(error.value)
