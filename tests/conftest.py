from pathlib import Path
from collections.abc import Callable

import pytest

from nte_dice_analysis.models import Record
from nte_dice_analysis.models import CropBox
from nte_dice_analysis.models import PipelineOptions


def make_options(
    *,
    row_count: int = 5,
    row_top: float = 0.0,
    row_bottom: float = 1.0,
    min_score: float = 0.3,
    det_model_dir: Path | None = Path('det'),
    rec_model_dir: Path | None = Path('rec'),
) -> PipelineOptions:
    return PipelineOptions(
        device='cpu',
        table_crop=CropBox.parse('0,0,1,1'),
        pool_crop=CropBox.parse('0,0,1,1'),
        row_count=row_count,
        row_top=row_top,
        row_bottom=row_bottom,
        min_score=min_score,
        debug_dir=None,
        det_model_dir=det_model_dir,
        rec_model_dir=rec_model_dir,
    )


@pytest.fixture
def options_factory() -> Callable[..., PipelineOptions]:
    return make_options


@pytest.fixture
def record_factory() -> Callable[..., Record]:
    return make_record


def make_record(
    *,
    pool_type: str = '限定棋盘',
    source_image: str = 'page.png',
    page_row: int = 1,
    roll_points: str = '1',
    item_name: str = '角色·薄荷',
    rarity: str = 'S-Class',
    quantity: str = '1',
    obtained_at: str = '2026-01-02 03:04:05',
    confidence: float | None = 0.9,
) -> Record:
    return Record(
        pool_type=pool_type,
        source_image=Path(source_image),
        page_row=page_row,
        roll_points=roll_points,
        item_name=item_name,
        rarity=rarity,
        item_name_raw=item_name,
        quantity=quantity,
        obtained_at=obtained_at,
        obtained_at_raw=obtained_at,
        confidence=confidence,
    )
