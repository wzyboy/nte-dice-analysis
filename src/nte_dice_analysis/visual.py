from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .constants import COLUMN_BOUNDS


def detect_pip_count(
    table_image: Image.Image,
    row_index: int,
    args: argparse.Namespace,
) -> int | None:
    width, height = table_image.size
    scale = min(width / 2480, height / 780)
    row_area_top = args.row_top * height
    row_area_bottom = args.row_bottom * height
    row_height = (row_area_bottom - row_area_top) / args.row_count
    x0 = round(0.02 * width)
    x1 = round(0.20 * width)
    y0 = round(row_area_top + row_index * row_height)
    y1 = round(row_area_top + (row_index + 1) * row_height)
    point_cell = table_image.crop((x0, y0, x1, y1))

    dark_components = connected_components(
        point_cell,
        lambda rgb: rgb[0] < 110 and rgb[1] < 110 and rgb[2] < 110,
    )
    icon_candidates = [
        component
        for component in dark_components
        if component['area'] >= scaled_area(1200, scale)
        and scaled(35, scale) <= component['width'] <= scaled(130, scale)
        and scaled(35, scale) <= component['height'] <= scaled(130, scale)
    ]
    if not icon_candidates:
        return None

    icon = max(icon_candidates, key=lambda component: component['area'])
    icon_image = point_cell.crop((icon['x0'], icon['y0'], icon['x1'] + 1, icon['y1'] + 1))
    margin = scaled(2, scale)
    white_components = connected_components(
        icon_image,
        lambda rgb: rgb[0] > 175 and rgb[1] > 175 and rgb[2] > 175,
    )

    pips = [
        component
        for component in white_components
        if scaled_area(35, scale) <= component['area'] <= scaled_area(500, scale)
        and scaled(5, scale) <= component['width'] <= scaled(30, scale)
        and scaled(5, scale) <= component['height'] <= scaled(30, scale)
        and component['area'] / (component['width'] * component['height']) > 0.55
        and component['x0'] > margin
        and component['y0'] > margin
    ]
    return len(pips) or None


def scaled(value: int, scale: float) -> int:
    return max(1, round(value * scale))


def scaled_area(value: int, scale: float) -> int:
    return max(1, round(value * scale * scale))


def connected_components(
    image: Image.Image,
    predicate: Any,
) -> list[dict[str, int]]:
    pixels = image.load()
    width, height = image.size
    mask = {
        (x, y)
        for y in range(height)
        for x in range(width)
        if predicate(pixels[x, y])
    }

    components: list[dict[str, int]] = []
    while mask:
        start = mask.pop()
        stack = [start]
        xs: list[int] = []
        ys: list[int] = []
        while stack:
            x, y = stack.pop()
            xs.append(x)
            ys.append(y)
            for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if neighbor in mask:
                    mask.remove(neighbor)
                    stack.append(neighbor)

        x0 = min(xs)
        y0 = min(ys)
        x1 = max(xs)
        y1 = max(ys)
        components.append(
            {
                'area': len(xs),
                'x0': x0,
                'y0': y0,
                'x1': x1,
                'y1': y1,
                'width': x1 - x0 + 1,
                'height': y1 - y0 + 1,
            },
        )

    return components


def draw_debug_image(
    table_image: Image.Image,
    tokens: list[dict[str, Any]],
    args: argparse.Namespace,
    output_path: Path,
) -> None:
    debug = table_image.copy()
    draw = ImageDraw.Draw(debug)
    width, height = debug.size

    row_area_top = args.row_top * height
    row_area_bottom = args.row_bottom * height
    row_height = (row_area_bottom - row_area_top) / args.row_count
    for row_index in range(args.row_count + 1):
        y = row_area_top + row_index * row_height
        draw.line((0, y, width, y), fill='blue', width=2)

    for _, (_, right) in COLUMN_BOUNDS.items():
        x = right * width
        draw.line((x, 0, x, height), fill='green', width=2)

    for token in tokens:
        x0, y0, x1, y1 = token['box']
        draw.rectangle((x0, y0, x1, y1), outline='red', width=3)
        draw.text((x0, max(0, y0 - 20)), token['column'], fill='red')

    debug.save(output_path)
