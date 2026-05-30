from pathlib import Path

import pytest

from nte_dice_analysis.fonts import FontSpec
from nte_dice_analysis.fonts import qt_cjk_font
from nte_dice_analysis.fonts import unique_paths
from nte_dice_analysis.fonts import font_from_candidates
from nte_dice_analysis.fonts import select_qt_font_family
from nte_dice_analysis.fonts import qt_cjk_font_family_hints


def test_font_from_candidates_prefers_first_existing_candidate(tmp_path: Path) -> None:
    font_dir = tmp_path / 'fonts'
    font_dir.mkdir()
    (font_dir / 'simhei.ttf').touch()
    (font_dir / 'msyh.ttc').touch()

    assert font_from_candidates(
        [
            ('missing.otf', 0, None),
            ('msyh.ttc', 0, None),
            ('simhei.ttf', 0, None),
        ],
        [font_dir],
    ) == FontSpec(path=font_dir / 'msyh.ttc', index=0)


def test_font_from_candidates_finds_nested_font(tmp_path: Path) -> None:
    font_dir = tmp_path / 'fonts'
    nested = font_dir / 'vendor' / 'noto'
    nested.mkdir(parents=True)
    font_path = nested / 'NotoSansSC-VF.ttf'
    font_path.touch()

    assert font_from_candidates(
        [('NotoSansSC-VF.ttf', 0, 'Regular')],
        [font_dir],
    ) == FontSpec(path=font_path, index=0, variation='Regular')


def test_qt_cjk_font_prefers_windows_font_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    import nte_dice_analysis.fonts as fonts

    monkeypatch.setattr(fonts, 'windows_cjk_font', lambda: FontSpec(Path('msyh.ttc'), 0))
    monkeypatch.setattr(fonts, 'noto_sans_cjk_sc_font', lambda: FontSpec(Path('NotoSansSC.otf'), 0))

    assert qt_cjk_font(platform='win32') == FontSpec(Path('msyh.ttc'), 0)
    assert qt_cjk_font(platform='linux') == FontSpec(Path('NotoSansSC.otf'), 0)


def test_select_qt_font_family_prefers_noto_on_non_windows() -> None:
    assert select_qt_font_family(['Microsoft YaHei', 'Noto Sans CJK SC'], platform='linux') == 'Noto Sans CJK SC'
    assert select_qt_font_family(['Arial', 'Microsoft YaHei'], platform='linux') is None
    assert select_qt_font_family(['Noto Sans CJK SC Regular'], platform='linux') == 'Noto Sans CJK SC Regular'
    assert select_qt_font_family(['Arial']) is None
    assert select_qt_font_family([]) is None


def test_select_qt_font_family_prefers_microsoft_yahei_on_windows() -> None:
    assert select_qt_font_family(['Microsoft YaHei', 'Noto Sans CJK SC'], platform='win32') == 'Microsoft YaHei'
    assert select_qt_font_family(['Noto Sans CJK SC', 'Microsoft YaHei UI'], platform='win32') == ('Microsoft YaHei UI')
    assert select_qt_font_family(['Noto Sans CJK SC Regular'], platform='win32') == 'Noto Sans CJK SC Regular'


def test_qt_cjk_font_family_hints_are_platform_specific() -> None:
    assert qt_cjk_font_family_hints('win32')[0] == 'Microsoft YaHei UI'
    assert qt_cjk_font_family_hints('linux')[0] == 'Noto Sans CJK SC'


def test_unique_paths_preserves_first_case_insensitive_occurrence() -> None:
    assert unique_paths([Path('C:/Fonts'), Path('c:/fonts'), Path('D:/Fonts')]) == [
        Path('C:/Fonts'),
        Path('D:/Fonts'),
    ]
