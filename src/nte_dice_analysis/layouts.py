from dataclasses import dataclass
from collections.abc import Mapping

from .models import PipelineOptions
from .models import parse_row_boundaries
from .constants import ARC_POOL_TYPE
from .constants import COLUMN_BOUNDS
from .constants import ARC_COLUMN_BOUNDS
from .constants import ARC_ROW_BOUNDARIES
from .constants import DEFAULT_ROW_BOUNDARIES

type ColumnBounds = Mapping[str, tuple[float, float]]

DICE_LAYOUT = 'dice_board'
ARC_LAYOUT = 'arc_research'


@dataclass(frozen=True)
class TableLayout:
    name: str
    column_bounds: ColumnBounds
    default_row_boundaries: tuple[float, ...]


DICE_TABLE_LAYOUT = TableLayout(
    name=DICE_LAYOUT,
    column_bounds=COLUMN_BOUNDS,
    default_row_boundaries=parse_row_boundaries(DEFAULT_ROW_BOUNDARIES),
)
ARC_TABLE_LAYOUT = TableLayout(
    name=ARC_LAYOUT,
    column_bounds=ARC_COLUMN_BOUNDS,
    default_row_boundaries=parse_row_boundaries(ARC_ROW_BOUNDARIES),
)


def table_layout_for_pool_type(pool_type: str) -> TableLayout:
    if is_arc_pool_type(pool_type):
        return ARC_TABLE_LAYOUT
    return DICE_TABLE_LAYOUT


def is_arc_pool_type(pool_type: str) -> bool:
    return pool_type == ARC_POOL_TYPE


def effective_options_for_pool_type(options: PipelineOptions, pool_type: str) -> PipelineOptions:
    layout = table_layout_for_pool_type(pool_type)
    if options.row_boundaries != DICE_TABLE_LAYOUT.default_row_boundaries:
        return options
    if layout.default_row_boundaries == options.row_boundaries:
        return options

    return PipelineOptions(
        table_crop=options.table_crop,
        pool_crop=options.pool_crop,
        row_boundaries=layout.default_row_boundaries,
        min_score=options.min_score,
        debug_dir=options.debug_dir,
        det_model_dir=options.det_model_dir,
        rec_model_dir=options.rec_model_dir,
    )
