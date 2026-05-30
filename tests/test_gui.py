import logging
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtCore import QUrl

from nte_dice_analysis.gui import SELF_TEST_IMPORTS
from nte_dice_analysis.gui import RecordsTableModel
from nte_dice_analysis.gui import run_self_test
from nte_dice_analysis.gui import default_log_dir
from nte_dice_analysis.gui import open_local_file
from nte_dice_analysis.gui import default_output_dir
from nte_dice_analysis.gui import open_existing_path
from nte_dice_analysis.gui import configure_file_logging
from nte_dice_analysis.constants import OUTPUT_FIELDS
from nte_dice_analysis.gui_strings import GUI_TEXT
from nte_dice_analysis.gui_strings import OUTPUT_FIELD_LABELS


def test_gui_strings_use_simplified_chinese_core_labels() -> None:
    assert GUI_TEXT.simple_tab == '简单'
    assert GUI_TEXT.advanced_tab == '高级'
    assert GUI_TEXT.crop_tab == '裁剪'
    assert GUI_TEXT.recognize_tab == '识别'
    assert GUI_TEXT.export_tab == '导出'
    assert GUI_TEXT.run_analysis == '开始分析'
    assert GUI_TEXT.open_xlsx == '打开 XLSX'
    assert GUI_TEXT.open_png == '打开 PNG'
    assert GUI_TEXT.open_folder == '打开文件夹'
    assert GUI_TEXT.open_log_file == '打开日志文件'


def test_records_table_model_uses_gui_field_labels() -> None:
    model = RecordsTableModel()

    assert set(OUTPUT_FIELD_LABELS) == set(OUTPUT_FIELDS)
    assert [model.headerData(index, Qt.Orientation.Horizontal) for index in range(model.columnCount())] == [
        OUTPUT_FIELD_LABELS[field] for field in OUTPUT_FIELDS
    ]


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


def test_open_local_file_creates_and_opens_path(tmp_path: Path) -> None:
    log_path = tmp_path / 'logs' / 'nte-dice-analysis.log'
    opened_paths: list[str] = []

    def fake_opener(url: QUrl) -> bool:
        opened_paths.append(url.toLocalFile())
        return True

    assert open_local_file(log_path, opener=fake_opener)
    assert log_path.exists()
    assert [Path(path) for path in opened_paths] == [log_path]


def test_open_existing_path_requires_existing_path(tmp_path: Path) -> None:
    existing_path = tmp_path / 'records.xlsx'
    missing_path = tmp_path / 'missing.xlsx'
    opened_paths: list[str] = []

    def fake_opener(url: QUrl) -> bool:
        opened_paths.append(url.toLocalFile())
        return True

    existing_path.write_text('placeholder', encoding='utf-8')

    assert open_existing_path(existing_path, opener=fake_opener)
    assert not open_existing_path(missing_path, opener=fake_opener)
    assert [Path(path) for path in opened_paths] == [existing_path]


def test_run_self_test_imports_and_initializes_ocr() -> None:
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

    assert (
        run_self_test(
            importer=fake_importer,
            ocr_factory=fake_ocr_factory,
            emit=messages.append,
        )
        == 0
    )
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
