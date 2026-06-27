from bisect import bisect_right
from typing import Self
from typing import Protocol
from pathlib import Path
from dataclasses import dataclass
from collections.abc import Mapping
from collections.abc import Sequence

from .constants import OUTPUT_FIELDS
from .normalization import clean_text
from .normalization import normalize_datetime

type OcrPrediction = Mapping[str, Sequence[object]]


@dataclass(frozen=True)
class CropBox:
    left: float
    top: float
    right: float
    bottom: float

    @classmethod
    def parse(cls, value: str) -> Self:
        parts = [part.strip() for part in value.split(',')]
        if len(parts) != 4:
            raise ValueError('crop must have four comma-separated values')
        left, top, right, bottom = (float(part) for part in parts)
        return cls(left, top, right, bottom)

    def to_pixels(self, image_size: tuple[int, int]) -> tuple[int, int, int, int]:
        width, height = image_size
        values = (self.left, self.top, self.right, self.bottom)
        if max(values) <= 1:
            x0, y0, x1, y1 = (
                round(self.left * width),
                round(self.top * height),
                round(self.right * width),
                round(self.bottom * height),
            )
        else:
            x0, y0, x1, y1 = (round(value) for value in values)

        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise ValueError(f'crop {x0},{y0},{x1},{y1} is outside image {width}x{height}')
        return x0, y0, x1, y1


@dataclass(frozen=True)
class PipelineOptions:
    table_crop: CropBox
    pool_crop: CropBox
    row_boundaries: tuple[float, ...]
    min_score: float
    debug_dir: Path | None
    det_model_dir: Path | None
    rec_model_dir: Path | None

    def __post_init__(self) -> None:
        boundaries = tuple(float(boundary) for boundary in self.row_boundaries)
        if len(boundaries) < 2:
            raise ValueError('row boundaries must contain at least two values')
        if any(boundary < 0 or boundary > 1 for boundary in boundaries):
            raise ValueError('row boundaries must be ratios from 0 to 1')
        if any(left >= right for left, right in zip(boundaries, boundaries[1:], strict=False)):
            raise ValueError('row boundaries must be strictly increasing')

        object.__setattr__(self, 'row_boundaries', boundaries)

    @classmethod
    def from_args(cls, args: object) -> Self:
        return cls(
            table_crop=CropBox.parse(getattr(args, 'table_crop')),
            pool_crop=CropBox.parse(getattr(args, 'pool_crop')),
            row_boundaries=parse_row_boundaries(getattr(args, 'row_boundaries')),
            min_score=getattr(args, 'min_score'),
            debug_dir=getattr(args, 'debug_dir'),
            det_model_dir=getattr(args, 'det_model_dir'),
            rec_model_dir=getattr(args, 'rec_model_dir'),
        )

    @property
    def row_count(self) -> int:
        return len(self.row_boundaries) - 1

    def row_bounds(self, image_size: tuple[int, int], row_index: int) -> tuple[int, int]:
        if row_index < 0 or row_index >= self.row_count:
            raise ValueError(f'row index {row_index} is outside row count {self.row_count}')

        row_boundaries = self.row_boundary_pixels(image_size)
        y0 = round(row_boundaries[row_index])
        y1 = round(row_boundaries[row_index + 1])
        return y0, y1

    def row_boundary_pixels(self, image_size: tuple[int, int]) -> tuple[float, ...]:
        _, height = image_size
        return tuple(boundary * height for boundary in self.row_boundaries)

    def row_index_for_y(self, image_size: tuple[int, int], y: float) -> int | None:
        row_boundaries = self.row_boundary_pixels(image_size)
        if y < row_boundaries[0] or y >= row_boundaries[-1]:
            return None

        row_index = bisect_right(row_boundaries, y) - 1
        if 0 <= row_index < self.row_count:
            return row_index
        return None


def parse_row_boundaries(value: str) -> tuple[float, ...]:
    parts = [part.strip() for part in value.split(',')]
    if any(not part for part in parts):
        raise ValueError('row boundaries must be comma-separated numbers')
    return tuple(float(part) for part in parts)


@dataclass(frozen=True)
class OcrToken:
    text: str
    score: float
    box: tuple[float, float, float, float]
    row_index: int
    column: str


@dataclass(frozen=True)
class Record:
    pool_type: str
    source_image: Path
    page_row: int
    roll_points: str
    item_name: str
    rarity: str
    item_name_raw: str
    quantity: str
    obtained_at: str
    obtained_at_raw: str
    confidence: float | None
    research_type: str = ''

    def to_output_row(self) -> dict[str, str]:
        row = {
            'pool_type': self.pool_type,
            'source_image': str(self.source_image),
            'page_row': str(self.page_row),
            'roll_points': self.roll_points,
            'item_name': self.item_name,
            'rarity': self.rarity,
            'item_name_raw': self.item_name_raw,
            'research_type': self.research_type,
            'quantity': self.quantity,
            'obtained_at': self.obtained_at,
            'obtained_at_raw': self.obtained_at_raw,
            'confidence': f'{self.confidence:.3f}' if self.confidence is not None else '',
        }
        return {field: row[field] for field in OUTPUT_FIELDS}

    @classmethod
    def from_output_row(cls, row: dict[str, str]) -> Self:
        confidence_text = row.get('confidence', '')
        try:
            confidence = float(confidence_text) if confidence_text else None
        except ValueError:
            confidence = None

        try:
            page_row = int(row.get('page_row', '0'))
        except ValueError:
            page_row = 0

        obtained_at = row.get('obtained_at', '')
        obtained_at_raw = row.get('obtained_at_raw', '')
        normalized_obtained_at_raw = normalize_datetime(obtained_at_raw)
        if obtained_at_raw and normalized_obtained_at_raw != clean_text(obtained_at_raw):
            obtained_at = normalized_obtained_at_raw

        return cls(
            pool_type=row.get('pool_type', ''),
            source_image=Path(row.get('source_image', '')),
            page_row=page_row,
            roll_points=row.get('roll_points', ''),
            item_name=row.get('item_name', ''),
            rarity=row.get('rarity', ''),
            item_name_raw=row.get('item_name_raw', ''),
            quantity=row.get('quantity', ''),
            obtained_at=obtained_at,
            obtained_at_raw=obtained_at_raw,
            confidence=confidence,
            research_type=row.get('research_type', ''),
        )


@dataclass(frozen=True)
class ConnectedComponent:
    area: int
    x0: int
    y0: int
    x1: int
    y1: int
    width: int
    height: int


class OcrEngine(Protocol):
    def predict(self, image: object) -> list[OcrPrediction]: ...
