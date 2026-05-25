from PIL import Image

from nte_dice_analysis.visual import hsv
from nte_dice_analysis.visual import is_gold_pixel
from nte_dice_analysis.visual import is_purple_pixel
from nte_dice_analysis.visual import connected_components


def test_color_classifiers_detect_expected_hues() -> None:
    assert is_gold_pixel(220, 170, 80)
    assert is_purple_pixel(190, 80, 220)
    assert not is_gold_pixel(120, 120, 120)
    assert hsv(255, 0, 0) == (0.0, 1.0, 255)


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
