from typing import Any
from typing import cast
from collections.abc import Sequence

from .models import CropBox


def parse_crop(value: str) -> CropBox:
    return CropBox.parse(value)


def crop_box_to_pixels(
    crop: CropBox,
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    return crop.to_pixels(image_size)


def normalize_box(box: object) -> tuple[float, float, float, float]:
    to_list = getattr(box, 'tolist', None)
    values = to_list() if callable(to_list) else box
    if not isinstance(values, Sequence) or isinstance(values, str | bytes):
        raise ValueError(f'unsupported OCR box: {box!r}')

    if len(values) == 4 and not isinstance(values[0], Sequence):
        x0, y0, x1, y1 = values
        return (
            float(cast(Any, x0)),
            float(cast(Any, y0)),
            float(cast(Any, x1)),
            float(cast(Any, y1)),
        )

    points = []
    for point in values:
        if not isinstance(point, Sequence) or len(point) < 2:
            raise ValueError(f'unsupported OCR box point: {point!r}')
        points.append((float(cast(Any, point[0])), float(cast(Any, point[1]))))

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))
