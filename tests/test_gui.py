import logging
from pathlib import Path

import pytest

from nte_dice_analysis.gui import SELF_TEST_IMPORTS
from nte_dice_analysis.gui import run_self_test
from nte_dice_analysis.gui import default_log_dir
from nte_dice_analysis.gui import default_output_dir
from nte_dice_analysis.gui import configure_file_logging


def test_default_output_dir_uses_documents_location() -> None:
    assert default_output_dir('C:/Users/player/Documents') == Path(
        'C:/Users/player/Documents/nte-dice-analysis',
    )


def test_default_output_dir_falls_back_to_home_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, 'home', lambda: Path('C:/Users/player'))

    assert default_output_dir('') == Path('C:/Users/player/Documents/nte-dice-analysis')


def test_default_log_dir_uses_output_logs_folder() -> None:
    assert default_log_dir('C:/Users/player/Documents') == Path(
        'C:/Users/player/Documents/nte-dice-analysis/logs',
    )


def test_configure_file_logging_creates_log_file(tmp_path: Path) -> None:
    log_path = configure_file_logging(str(tmp_path))

    logging.getLogger('nte_dice_analysis.test').info('hello from test')
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert log_path == tmp_path / 'nte-dice-analysis' / 'logs' / 'nte-dice-analysis.log'
    assert log_path.exists()
    assert 'hello from test' in log_path.read_text(encoding='utf-8')


def test_run_self_test_checks_runtime_imports() -> None:
    imported_modules: list[str] = []
    messages: list[str] = []
    ocr_initialized = False

    def fake_importer(module_name: str) -> object:
        imported_modules.append(module_name)
        return object()

    def fake_ocr_factory(options: object) -> object:
        nonlocal ocr_initialized
        ocr_initialized = True
        return object()

    assert run_self_test(importer=fake_importer, ocr_factory=fake_ocr_factory, emit=messages.append) == 0
    assert imported_modules == SELF_TEST_IMPORTS
    assert ocr_initialized
    assert messages[-2] == 'ok: initialized PaddleOCR pipeline'
    assert messages[-1] == 'self-test passed'


def test_run_self_test_reports_import_failure() -> None:
    messages: list[str] = []

    def fake_importer(module_name: str) -> object:
        if module_name == 'paddleocr':
            raise ImportError('missing paddleocr')
        return object()

    assert run_self_test(importer=fake_importer, ocr_factory=lambda options: object(), emit=messages.append) == 1
    assert messages[-1] == 'failed: missing paddleocr'


def test_run_self_test_reports_ocr_initialization_failure() -> None:
    messages: list[str] = []

    def fake_ocr_factory(options: object) -> object:
        raise RuntimeError('missing OCR metadata')

    assert run_self_test(ocr_factory=fake_ocr_factory, emit=messages.append) == 1
    assert messages[-1] == 'failed: missing OCR metadata'
