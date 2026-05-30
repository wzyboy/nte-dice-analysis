import os
import sys
import subprocess
from pathlib import Path
from dataclasses import dataclass

type FontCandidate = tuple[str, int, str | None]

NOTO_CJK_SC_REGULAR_FONTS: list[FontCandidate] = [
    ('NotoSansCJK-Regular.ttc', 2, None),
    ('NotoSansCJKsc-Regular.otf', 0, None),
    ('NotoSansSC-Regular.otf', 0, None),
    ('NotoSansSC-VF.ttf', 0, 'Regular'),
    ('NotoSansSC-VariableFont_wght.ttf', 0, 'Regular'),
]
WINDOWS_REGULAR_CJK_FONTS: list[FontCandidate] = [
    ('msyh.ttc', 0, None),
    ('Deng.ttf', 0, None),
    ('simhei.ttf', 0, None),
    ('simsun.ttc', 0, None),
    ('msjh.ttc', 0, None),
]
DEFAULT_QT_CJK_FONT_FAMILY_HINTS = [
    'Noto Sans CJK SC',
    'Noto Sans SC',
]
WINDOWS_QT_CJK_FONT_FAMILY_HINTS = [
    'Microsoft YaHei UI',
    'Microsoft YaHei',
    '微软雅黑',
    'DengXian',
    '等线',
    'SimHei',
    '黑体',
    'SimSun',
    '宋体',
    'Noto Sans CJK SC',
    'Noto Sans SC',
    'Microsoft JhengHei',
]


@dataclass(frozen=True)
class FontSpec:
    path: Path
    index: int
    variation: str | None = None


def cjk_font() -> FontSpec | None:
    return noto_sans_cjk_sc_font() or windows_cjk_font()


def qt_cjk_font(platform: str = sys.platform) -> FontSpec | None:
    if platform.startswith('win'):
        return windows_cjk_font() or noto_sans_cjk_sc_font()
    return cjk_font()


def noto_sans_cjk_sc_font() -> FontSpec | None:
    return fc_match_font('Noto Sans CJK SC:style=Regular') or installed_noto_cjk_sc_font()


def fc_match_font(pattern: str) -> FontSpec | None:
    try:
        completed = subprocess.run(
            ['fc-match', '-f', '%{file}\n%{index}\n%{family}', pattern],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None

    if completed.returncode != 0:
        return None
    file_text, _, remainder = completed.stdout.partition('\n')
    index_text, _, family_text = remainder.partition('\n')
    if not file_text or 'Noto Sans CJK SC' not in family_text:
        return None

    path = Path(file_text)
    if not path.exists():
        return None

    try:
        index = int(index_text)
    except ValueError:
        index = 0
    return FontSpec(path=path, index=index)


def installed_noto_cjk_sc_font() -> FontSpec | None:
    return font_from_candidates(NOTO_CJK_SC_REGULAR_FONTS, font_search_dirs())


def windows_cjk_font() -> FontSpec | None:
    return font_from_candidates(WINDOWS_REGULAR_CJK_FONTS, windows_font_dirs())


def font_from_candidates(candidates: list[FontCandidate], font_dirs: list[Path]) -> FontSpec | None:
    for filename, index, variation in candidates:
        for font_dir in font_dirs:
            direct_path = font_dir / filename
            if direct_path.exists():
                return FontSpec(path=direct_path, index=index, variation=variation)

            try:
                matching_path = next(font_dir.rglob(filename))
            except (OSError, StopIteration):
                continue
            return FontSpec(path=matching_path, index=index, variation=variation)
    return None


def font_search_dirs() -> list[Path]:
    dirs: list[Path] = []

    local_app_data = os.environ.get('LOCALAPPDATA')
    if local_app_data:
        dirs.append(Path(local_app_data) / 'Microsoft' / 'Windows' / 'Fonts')

    dirs.extend(windows_font_dirs())

    xdg_data_home = os.environ.get('XDG_DATA_HOME')
    if xdg_data_home:
        dirs.append(Path(xdg_data_home) / 'fonts')
    else:
        dirs.append(Path.home() / '.local' / 'share' / 'fonts')

    dirs.extend([Path('/usr/local/share/fonts'), Path('/usr/share/fonts')])
    return unique_paths(dirs)


def windows_font_dirs() -> list[Path]:
    roots = [os.environ.get('WINDIR'), os.environ.get('SystemRoot'), 'C:\\Windows']
    return unique_paths([Path(root) / 'Fonts' for root in roots if root])


def unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).casefold()
        if key in seen:
            continue
        unique.append(path)
        seen.add(key)
    return unique


def qt_cjk_font_family_hints(platform: str = sys.platform) -> list[str]:
    if platform.startswith('win'):
        return WINDOWS_QT_CJK_FONT_FAMILY_HINTS
    return DEFAULT_QT_CJK_FONT_FAMILY_HINTS


def select_qt_font_family(families: list[str], platform: str = sys.platform) -> str | None:
    hints = qt_cjk_font_family_hints(platform)
    for hint in hints:
        family = exact_font_family(families, hint)
        if family is not None:
            return family

    for hint in hints:
        family = partial_font_family(families, hint)
        if family is not None:
            return family

    return None


def exact_font_family(families: list[str], hint: str) -> str | None:
    hint_key = hint.casefold()
    for family in families:
        if family.casefold() == hint_key:
            return family
    return None


def partial_font_family(families: list[str], hint: str) -> str | None:
    hint_key = hint.casefold()
    for family in families:
        if hint_key in family.casefold():
            return family
    return None
