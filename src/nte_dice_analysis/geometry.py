from typing import SupportsFloat
from typing import SupportsIndex
from collections.abc import Sequence

from .models import CropBox


def parse_crop(value: str) -> CropBox:
    return CropBox.parse(value)


def crop_box_to_pixels(
    crop: CropBox,
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    return crop.to_pixels(image_size)


def coordinate_to_float(value: object) -> float:
    if isinstance(value, str | bytes | bytearray | SupportsFloat | SupportsIndex):
        return float(value)
    raise ValueError(f'unsupported OCR coordinate: {value!r}')


def normalize_box(box: object) -> tuple[float, float, float, float]:
    to_list = getattr(box, 'tolist', None)
    values = to_list() if callable(to_list) else box
    if not isinstance(values, Sequence) or isinstance(values, str | bytes):
        raise ValueError(f'unsupported OCR box: {box!r}')

    if len(values) == 4 and not isinstance(values[0], Sequence):
        x0, y0, x1, y1 = values
        return (
            coordinate_to_float(x0),
            coordinate_to_float(y0),
            coordinate_to_float(x1),
            coordinate_to_float(y1),
        )

    points = []
    for point in values:
        if not isinstance(point, Sequence) or len(point) < 2:
            raise ValueError(f'unsupported OCR box point: {point!r}')
        points.append((coordinate_to_float(point[0]), coordinate_to_float(point[1])))

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))
