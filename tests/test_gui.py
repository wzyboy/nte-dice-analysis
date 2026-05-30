from pathlib import Path

import pytest

from nte_dice_analysis.gui import default_output_dir


def test_default_output_dir_uses_documents_location() -> None:
    assert default_output_dir('C:/Users/player/Documents') == Path(
        'C:/Users/player/Documents/nte-dice-analysis',
    )


def test_default_output_dir_falls_back_to_home_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, 'home', lambda: Path('C:/Users/player'))

    assert default_output_dir('') == Path('C:/Users/player/Documents/nte-dice-analysis')
