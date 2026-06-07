from collections.abc import Callable

import pytest

from nte_dice_analysis.dedup import merge_fragment
from nte_dice_analysis.dedup import pull_group_errors
from nte_dice_analysis.dedup import deduplicate_records
from nte_dice_analysis.dedup import require_valid_pull_groups
from nte_dice_analysis.models import Record
from nte_dice_analysis.constants import ARC_POOL_TYPE
from nte_dice_analysis.constants import GIFT_ROLL_POINTS
from nte_dice_analysis.constants import STANDARD_POOL_TYPE
from nte_dice_analysis.constants import SLEEPING_LAND_ROLL_POINTS


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


def test_deduplicate_records_keeps_identical_rows_when_needed_for_valid_dice_group(
    record_factory: Callable[..., Record],
) -> None:
    timestamp = '2026-06-06 03:09:40'
    records = [
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page1.png',
            page_row=1,
            roll_points=GIFT_ROLL_POINTS,
            item_name='gift',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page1.png',
            page_row=2,
            roll_points='4',
            item_name='smile',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page1.png',
            page_row=3,
            roll_points='2',
            item_name='we',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page1.png',
            page_row=4,
            roll_points=SLEEPING_LAND_ROLL_POINTS,
            item_name='sleeping-land',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page1.png',
            page_row=5,
            roll_points='6',
            item_name='same-visible-row',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page2.png',
            page_row=1,
            roll_points='6',
            item_name='same-visible-row',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page2.png',
            page_row=2,
            roll_points='5',
            item_name='top',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page2.png',
            page_row=3,
            roll_points='5',
            item_name='adler',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page2.png',
            page_row=4,
            roll_points='5',
            item_name='music',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page2.png',
            page_row=5,
            roll_points='4',
            item_name='smile',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page3.png',
            page_row=1,
            roll_points='3',
            item_name='piece',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page3.png',
            page_row=2,
            roll_points='5',
            item_name='music',
            obtained_at=timestamp,
        ),
    ]

    deduped = deduplicate_records(records)

    assert len(deduped) == 12
    assert sum(record.item_name == 'same-visible-row' for record in deduped) == 2
    require_valid_pull_groups(deduped)


def test_deduplicate_records_merges_single_row_overlap_when_needed_for_valid_dice_group(
    record_factory: Callable[..., Record],
) -> None:
    timestamp = '2026-06-06 03:09:40'
    first_page = [
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page1.png',
            page_row=1,
            roll_points=GIFT_ROLL_POINTS,
            item_name='gift',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page1.png',
            page_row=2,
            roll_points='1',
            item_name='pull-1',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page1.png',
            page_row=3,
            roll_points='2',
            item_name='pull-2',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page1.png',
            page_row=4,
            roll_points=SLEEPING_LAND_ROLL_POINTS,
            item_name='sleeping-land',
            obtained_at=timestamp,
        ),
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page1.png',
            page_row=5,
            roll_points='3',
            item_name='overlap',
            obtained_at=timestamp,
        ),
    ]
    second_page = [
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page2.png',
            page_row=1,
            roll_points='3',
            item_name='overlap',
            obtained_at=timestamp,
            confidence=0.99,
        ),
        *[
            record_factory(
                pool_type=STANDARD_POOL_TYPE,
                source_image='page2.png',
                page_row=index + 2,
                roll_points=str(index + 4),
                item_name=f'pull-{index + 4}',
                obtained_at=timestamp,
            )
            for index in range(4)
        ],
    ]
    third_page = [
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page3.png',
            page_row=index + 1,
            roll_points=str(index + 8),
            item_name=f'pull-{index + 8}',
            obtained_at=timestamp,
        )
        for index in range(3)
    ]

    deduped = deduplicate_records([*first_page, *second_page, *third_page])

    assert len(deduped) == 12
    assert sum(record.item_name == 'overlap' for record in deduped) == 1
    require_valid_pull_groups(deduped)


def test_deduplicate_records_preserves_identical_rows_seen_together_on_one_page(
    record_factory: Callable[..., Record],
) -> None:
    timestamp = '2026-06-06 03:09:40'
    records = [
        record_factory(
            pool_type=STANDARD_POOL_TYPE,
            source_image='page1.png',
            page_row=1,
            roll_points=GIFT_ROLL_POINTS,
            item_name='gift',
            obtained_at=timestamp,
        ),
        *[
            record_factory(
                pool_type=STANDARD_POOL_TYPE,
                source_image='page1.png',
                page_row=index + 2,
                roll_points='4',
                item_name='same-visible-row',
                obtained_at=timestamp,
            )
            for index in range(2)
        ],
        *[
            record_factory(
                pool_type=STANDARD_POOL_TYPE,
                source_image='page2.png',
                page_row=index + 1,
                roll_points='4',
                item_name='same-visible-row',
                obtained_at=timestamp,
            )
            for index in range(1)
        ],
        *[
            record_factory(
                pool_type=STANDARD_POOL_TYPE,
                source_image='page3.png',
                page_row=index + 1,
                roll_points=str(index + 1),
                item_name=f'pull-{index}',
                obtained_at=timestamp,
            )
            for index in range(8)
        ],
    ]

    deduped = deduplicate_records(records)

    assert len(deduped) == 11
    assert sum(record.item_name == 'same-visible-row' for record in deduped) == 2
    require_valid_pull_groups(deduped)


def test_deduplicate_records_includes_arc_research_type_in_match_key(
    record_factory: Callable[..., Record],
) -> None:
    first = [
        record_factory(
            pool_type=ARC_POOL_TYPE,
            roll_points='',
            item_name='行进于时间之外',
            quantity='',
            research_type='奇迹盒盒',
        ),
    ]
    second = [
        record_factory(
            pool_type=ARC_POOL_TYPE,
            roll_points='',
            item_name='行进于时间之外',
            quantity='',
            research_type='其他类型',
        ),
    ]

    merged = merge_fragment(first, second)

    assert [record.research_type for record in merged] == ['奇迹盒盒', '其他类型']


def test_deduplicate_records_preserves_repeated_arc_items_across_pages(
    record_factory: Callable[..., Record],
) -> None:
    first = [
        record_factory(
            pool_type=ARC_POOL_TYPE,
            source_image='page1.png',
            page_row=index + 1,
            roll_points='',
            item_name=f'弧盘{index}',
            quantity='',
            research_type='奇迹盒盒',
        )
        for index in range(3)
    ]
    second = [
        record_factory(
            pool_type=ARC_POOL_TYPE,
            source_image='page2.png',
            page_row=index + 1,
            roll_points='',
            item_name=f'弧盘{index % 2}',
            quantity='',
            research_type='奇迹盒盒',
            confidence=0.99,
        )
        for index in range(3)
    ]

    deduped = deduplicate_records([*first, *second])

    assert [record.item_name for record in deduped] == ['弧盘0', '弧盘1', '弧盘2', '弧盘0', '弧盘1', '弧盘0']
    assert [record.source_image.name for record in deduped] == [
        'page1.png',
        'page1.png',
        'page1.png',
        'page2.png',
        'page2.png',
        'page2.png',
    ]


def test_deduplicate_records_merges_exact_duplicate_arc_rows(
    record_factory: Callable[..., Record],
) -> None:
    first = record_factory(
        pool_type=ARC_POOL_TYPE,
        source_image='page1.png',
        page_row=1,
        roll_points='',
        item_name='行进于时间之外',
        quantity='',
        research_type='奇迹盒盒',
    )
    second = record_factory(
        pool_type=ARC_POOL_TYPE,
        source_image='page1.png',
        page_row=1,
        roll_points='',
        item_name='行进于时间之外',
        quantity='',
        research_type='奇迹盒盒',
        confidence=0.99,
    )

    deduped = deduplicate_records([first, second])

    assert deduped == [second]


def test_require_valid_pull_groups_accepts_repeated_arc_items(
    record_factory: Callable[..., Record],
) -> None:
    records = [
        record_factory(
            pool_type=ARC_POOL_TYPE,
            source_image=f'page{index // 5}.png',
            page_row=index % 5 + 1,
            roll_points='',
            item_name=f'弧盘{index % 3}',
            quantity='',
            research_type='奇迹盒盒',
        )
        for index in range(10)
    ]

    deduped = deduplicate_records(records)

    assert len(deduped) == 10
    require_valid_pull_groups(deduped)


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
    single_with_sleeping_land = [
        record_factory(roll_points='1'),
        record_factory(roll_points=SLEEPING_LAND_ROLL_POINTS, item_name='道具·失纬棋子'),
    ]
    ten_with_gift = [record_factory(roll_points=str((index % 6) + 1)) for index in range(10)]
    ten_with_gift.append(record_factory(roll_points=GIFT_ROLL_POINTS))
    ten_with_gift_and_sleeping_land = [record_factory(roll_points=str((index % 6) + 1)) for index in range(10)]
    ten_with_gift_and_sleeping_land.append(record_factory(roll_points=GIFT_ROLL_POINTS))
    ten_with_gift_and_sleeping_land.append(
        record_factory(roll_points=SLEEPING_LAND_ROLL_POINTS, item_name='道具·失纬棋子'),
    )

    assert pull_group_errors(single) == []
    assert pull_group_errors(single_with_gift) == []
    assert pull_group_errors(single_with_sleeping_land) == []
    assert pull_group_errors(ten_with_gift) == []
    assert pull_group_errors(ten_with_gift_and_sleeping_land) == []


def test_require_valid_pull_groups_rejects_missing_pool_and_invalid_counts(
    record_factory: Callable[..., Record],
) -> None:
    missing_pool = [record_factory(pool_type='', roll_points='1')]
    ten_without_gift = [record_factory(page_row=index + 1, roll_points=str((index % 6) + 1)) for index in range(10)]
    ten_with_only_sleeping_land_bonus = [
        record_factory(page_row=index + 1, roll_points=str((index % 6) + 1)) for index in range(10)
    ]
    ten_with_only_sleeping_land_bonus.append(
        record_factory(page_row=11, roll_points=SLEEPING_LAND_ROLL_POINTS, item_name='道具·失纬棋子'),
    )

    with pytest.raises(ValueError, match='missing pool_type'):
        require_valid_pull_groups(missing_pool)

    with pytest.raises(ValueError, match='found 10 pulls, 0 集点赠礼 gifts') as error:
        require_valid_pull_groups(ten_without_gift)
    assert 'page.png, row 1' in str(error.value)
    assert 'page.png, row 10' in str(error.value)

    with pytest.raises(ValueError, match='1 沉眠地 bonuses'):
        require_valid_pull_groups(ten_with_only_sleeping_land_bonus)


def test_require_valid_pull_groups_accepts_exact_arc_multi_pull(
    record_factory: Callable[..., Record],
) -> None:
    records = [
        record_factory(
            pool_type=ARC_POOL_TYPE,
            page_row=index + 1,
            roll_points='',
            item_name=f'弧盘{index}',
            quantity='',
            research_type='奇迹盒盒',
        )
        for index in range(10)
    ]

    require_valid_pull_groups(records)


def test_require_valid_pull_groups_rejects_invalid_arc_groups(
    record_factory: Callable[..., Record],
) -> None:
    nine_records = [
        record_factory(pool_type=ARC_POOL_TYPE, page_row=index + 1, roll_points='', quantity='') for index in range(9)
    ]
    eleven_records = [
        record_factory(pool_type=ARC_POOL_TYPE, page_row=index + 1, roll_points='', quantity='') for index in range(11)
    ]
    gift_record = [
        record_factory(pool_type=ARC_POOL_TYPE, page_row=index + 1, roll_points='', quantity='') for index in range(9)
    ]
    gift_record.append(record_factory(pool_type=ARC_POOL_TYPE, page_row=10, roll_points=GIFT_ROLL_POINTS))
    dice_point_record = [
        record_factory(pool_type=ARC_POOL_TYPE, page_row=index + 1, roll_points='', quantity='') for index in range(9)
    ]
    dice_point_record.append(record_factory(pool_type=ARC_POOL_TYPE, page_row=10, roll_points='1'))

    with pytest.raises(ValueError, match='expected 10 arc research records; found 9'):
        require_valid_pull_groups(nine_records)
    with pytest.raises(ValueError, match='expected 10 arc research records; found 11'):
        require_valid_pull_groups(eleven_records)
    with pytest.raises(ValueError, match='arc research does not support gifts'):
        require_valid_pull_groups(gift_record)
    with pytest.raises(ValueError, match='arc research does not support dice points'):
        require_valid_pull_groups(dice_point_record)
