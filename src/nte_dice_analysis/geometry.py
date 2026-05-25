from __future__ import annotations

from .models import CropBox


def parse_crop(value: str) -> CropBox:
    return CropBox.parse(value)


def crop_box_to_pixels(
    crop: CropBox,
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    return crop.to_pixels(image_size)


def normalize_box(box: object) -> tuple[float, float, float, float]:
    values = box.tolist() if hasattr(box, 'tolist') else box
    if len(values) == 4 and not isinstance(values[0], list | tuple):
        x0, y0, x1, y1 = values
        return float(x0), float(y0), float(x1), float(y1)

    xs = [point[0] for point in values]
    ys = [point[1] for point in values]
    return float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))
