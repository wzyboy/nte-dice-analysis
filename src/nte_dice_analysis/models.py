from typing import Self
from typing import Protocol
from pathlib import Path
from dataclasses import dataclass

from .constants import CSV_FIELDS

type OcrPrediction = dict[str, list[object]]


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
    device: str
    table_crop: CropBox
    pool_crop: CropBox
    row_count: int
    row_top: float
    row_bottom: float
    min_score: float
    debug_dir: Path | None
    det_model_dir: Path
    rec_model_dir: Path

    @classmethod
    def from_args(cls, args: object) -> Self:
        return cls(
            device=getattr(args, 'device'),
            table_crop=CropBox.parse(getattr(args, 'table_crop')),
            pool_crop=CropBox.parse(getattr(args, 'pool_crop')),
            row_count=getattr(args, 'row_count'),
            row_top=getattr(args, 'row_top'),
            row_bottom=getattr(args, 'row_bottom'),
            min_score=getattr(args, 'min_score'),
            debug_dir=getattr(args, 'debug_dir'),
            det_model_dir=getattr(args, 'det_model_dir'),
            rec_model_dir=getattr(args, 'rec_model_dir'),
        )

    def row_metrics(self, image_size: tuple[int, int]) -> tuple[float, float, float]:
        _, height = image_size
        row_area_top = self.row_top * height
        row_area_bottom = self.row_bottom * height
        row_height = (row_area_bottom - row_area_top) / self.row_count
        return row_area_top, row_area_bottom, row_height

    def row_bounds(self, image_size: tuple[int, int], row_index: int) -> tuple[int, int]:
        row_area_top, _, row_height = self.row_metrics(image_size)
        y0 = round(row_area_top + row_index * row_height)
        y1 = round(row_area_top + (row_index + 1) * row_height)
        return y0, y1


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

    def to_output_row(self) -> dict[str, str]:
        row = {
            'pool_type': self.pool_type,
            'source_image': str(self.source_image),
            'page_row': str(self.page_row),
            'roll_points': self.roll_points,
            'item_name': self.item_name,
            'rarity': self.rarity,
            'item_name_raw': self.item_name_raw,
            'quantity': self.quantity,
            'obtained_at': self.obtained_at,
            'obtained_at_raw': self.obtained_at_raw,
            'confidence': f'{self.confidence:.3f}' if self.confidence is not None else '',
        }
        return {field: row[field] for field in CSV_FIELDS}

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

        return cls(
            pool_type=row.get('pool_type', ''),
            source_image=Path(row.get('source_image', '')),
            page_row=page_row,
            roll_points=row.get('roll_points', ''),
            item_name=row.get('item_name', ''),
            rarity=row.get('rarity', ''),
            item_name_raw=row.get('item_name_raw', ''),
            quantity=row.get('quantity', ''),
            obtained_at=row.get('obtained_at', ''),
            obtained_at_raw=row.get('obtained_at_raw', ''),
            confidence=confidence,
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
