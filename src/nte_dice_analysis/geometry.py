from __future__ import annotations

from typing import Any


def parse_crop(value: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in value.split(',')]
    if len(parts) != 4:
        raise ValueError('crop must have four comma-separated values')
    return tuple(float(part) for part in parts)  # type: ignore[return-value]


def crop_box_to_pixels(
    crop: tuple[float, float, float, float],
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    width, height = image_size
    if max(crop) <= 1:
        x0, y0, x1, y1 = (
            round(crop[0] * width),
            round(crop[1] * height),
            round(crop[2] * width),
            round(crop[3] * height),
        )
    else:
        x0, y0, x1, y1 = (round(value) for value in crop)

    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError(f'crop {x0},{y0},{x1},{y1} is outside image {width}x{height}')
    return x0, y0, x1, y1


def normalize_box(box: Any) -> tuple[float, float, float, float]:
    values = box.tolist() if hasattr(box, 'tolist') else box
    if len(values) == 4 and not isinstance(values[0], list | tuple):
        x0, y0, x1, y1 = values
        return float(x0), float(y0), float(x1), float(y1)

    xs = [point[0] for point in values]
    ys = [point[1] for point in values]
    return float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))
