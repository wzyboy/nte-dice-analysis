from collections.abc import Callable

from PIL import Image

from nte_dice_analysis.models import PipelineOptions
from nte_dice_analysis.visual import detect_rarity_class
from nte_dice_analysis.visual import connected_components
from nte_dice_analysis.constants import A_CLASS
from nte_dice_analysis.constants import B_CLASS
from nte_dice_analysis.constants import S_CLASS


def test_detect_rarity_class_uses_item_name_cell_color(
    options_factory: Callable[..., PipelineOptions],
) -> None:
    options = options_factory(row_boundaries=(0.0, 1.0))

    gold = Image.new('RGB', (100, 20), 'white')
    gold.paste((220, 170, 80), (22, 0, 50, 20))
    assert detect_rarity_class(gold, 0, options) == S_CLASS

    purple = Image.new('RGB', (100, 20), 'white')
    purple.paste((190, 80, 220), (22, 0, 50, 20))
    assert detect_rarity_class(purple, 0, options) == A_CLASS

    gray = Image.new('RGB', (100, 20), (120, 120, 120))
    assert detect_rarity_class(gray, 0, options) == B_CLASS


def test_connected_components_returns_typed_components() -> None:
    image = Image.new('RGB', (5, 5), 'black')
    image.putpixel((0, 0), (255, 255, 255))
    image.putpixel((1, 0), (255, 255, 255))
    image.putpixel((4, 4), (255, 255, 255))

    components = connected_components(image, lambda rgb: rgb == (255, 255, 255))

    assert sorted((component.area, component.width, component.height) for component in components) == [
        (1, 1, 1),
        (2, 2, 1),
    ]
