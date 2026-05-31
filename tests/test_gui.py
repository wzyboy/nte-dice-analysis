import os
import re
import ast
import logging
from io import BytesIO
from pathlib import Path
from collections.abc import Callable

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

import nte_dice_analysis.gui as gui_module
from nte_dice_analysis.gui import SELF_TEST_IMPORTS
from nte_dice_analysis.gui import DASHBOARD_STYLESHEET
from nte_dice_analysis.gui import MainWindow
from nte_dice_analysis.gui import RecordsTableModel
from nte_dice_analysis.gui import run_self_test
from nte_dice_analysis.gui import app_icon_bytes
from nte_dice_analysis.gui import default_log_dir
from nte_dice_analysis.gui import open_local_file
from nte_dice_analysis.gui import default_output_dir
from nte_dice_analysis.gui import open_existing_path
from nte_dice_analysis.gui import dashboard_date_text
from nte_dice_analysis.gui import configure_file_logging
from nte_dice_analysis.gui import dashboard_average_html
from nte_dice_analysis.gui import dashboard_history_html
from nte_dice_analysis.gui import dashboard_summary_html
from nte_dice_analysis.png import PoolSummary
from nte_dice_analysis.png import SClassHistoryItem
from nte_dice_analysis.models import Record
from nte_dice_analysis.constants import OUTPUT_FIELDS
from nte_dice_analysis.gui_strings import GUI_TEXT
from nte_dice_analysis.gui_strings import OUTPUT_FIELD_LABELS
from nte_dice_analysis.gui_workflow import ExistingAnalysisResult

HAN_RE = re.compile(r'[\u3400-\u9fff]')


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
    assert GUI_TEXT.app_title == '《异环》抽卡记录分析 NTE Dice Analysis'
    assert GUI_TEXT.app_subtitle == '本地识别截图并分析抽卡结果'
    assert GUI_TEXT.more == '更多'
    assert GUI_TEXT.analyze == '分析'
    assert GUI_TEXT.no_data == '无数据'
    assert GUI_TEXT.no_records == '无记录'
    assert GUI_TEXT.none == '无'
    assert GUI_TEXT.records_and_log == '记录与日志'
    assert GUI_TEXT.close == '关闭'


def test_gui_py_has_no_han_string_literals() -> None:
    gui_path = Path(__file__).parents[1] / 'src' / 'nte_dice_analysis' / 'gui.py'
    tree = ast.parse(gui_path.read_text(encoding='utf-8'))

    offenders = [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and HAN_RE.search(node.value)
    ]

    assert offenders == []


def test_dashboard_stylesheet_scopes_dashboard_button_styles() -> None:
    assert 'QMainWindow' not in DASHBOARD_STYLESHEET
    assert 'QPushButton {' not in DASHBOARD_STYLESHEET
    assert 'QPushButton#PrimaryButton,' in DASHBOARD_STYLESHEET
    assert 'QPushButton#SecondaryButton {' in DASHBOARD_STYLESHEET


def test_main_window_keeps_dashboard_styles_out_of_advanced_widgets(monkeypatch: pytest.MonkeyPatch) -> None:
    qt_app()

    monkeypatch.setattr(
        gui_module,
        'load_existing_analysis',
        lambda _out_dir: ExistingAnalysisResult(
            json_paths=[],
            raw_record_count=0,
            exported_record_count=0,
            summary='',
            records=[],
        ),
    )

    window = MainWindow()
    try:
        assert window.styleSheet() == ''
        assert window.centralWidget().styleSheet() == DASHBOARD_STYLESHEET
        assert window.advanced_progress.styleSheet() == ''

        dialog = gui_module.AdvancedSettingsDialog(window, window)
        try:
            assert dialog.styleSheet() == ''
            assert dialog.close_button.styleSheet() == ''
        finally:
            dialog.close()
            dialog.deleteLater()
    finally:
        window.close()
        window.deleteLater()


def pool_summary_factory(
    *,
    date_start: str | None = None,
    date_end: str | None = None,
    s_history: list[SClassHistoryItem] | None = None,
    average_s_pulls: float | None = None,
) -> PoolSummary:
    return PoolSummary(
        pool_type='限定棋盘',
        total_pulls=10,
        date_start=date_start,
        date_end=date_end,
        current_pity=4,
        rarity_stats=[],
        s_history=s_history or [],
        average_s_pulls=average_s_pulls,
    )


def test_dashboard_formatting_helpers_use_empty_fallbacks() -> None:
    summary = pool_summary_factory()

    assert dashboard_date_text(summary) == GUI_TEXT.no_records
    assert dashboard_history_html(summary) == GUI_TEXT.dashboard_history.format(history=GUI_TEXT.none)
    assert GUI_TEXT.none in dashboard_average_html(summary)


def test_dashboard_formatting_helpers_escape_history_names() -> None:
    summary = pool_summary_factory(
        date_start='2026-05-01',
        date_end='2026-05-02',
        s_history=[SClassHistoryItem('娜娜莉<script>', 3)],
        average_s_pulls=3,
    )

    assert dashboard_date_text(summary) == '2026-05-01 - 2026-05-02'
    assert '<span style="color: #2563eb;">10</span>' in dashboard_summary_html(summary)
    history_html = dashboard_history_html(summary)
    assert '娜娜莉&lt;script&gt;[3]' in history_html
    assert '娜娜莉<script>' not in history_html
    assert '3' in dashboard_average_html(summary)


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


def test_app_icon_resource_is_transparent_png() -> None:
    icon = Image.open(BytesIO(app_icon_bytes()))

    assert icon.mode == 'RGBA'
    assert icon.size[0] == icon.size[1]
    assert icon.getchannel('A').getextrema()[0] == 0


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


def test_main_window_loads_existing_analysis_on_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    record_factory: Callable[..., Record],
) -> None:
    app = qt_app()
    json_path = tmp_path / 'records.json'
    record = record_factory()
    loaded_dirs: list[Path] = []

    def fake_load_existing_analysis(out_dir: Path) -> ExistingAnalysisResult:
        loaded_dirs.append(out_dir)
        return ExistingAnalysisResult(
            json_paths=[json_path],
            raw_record_count=1,
            exported_record_count=1,
            summary='summary',
            records=[record],
        )

    monkeypatch.setattr(gui_module, 'default_output_dir', lambda: tmp_path)
    monkeypatch.setattr(gui_module, 'default_log_dir', lambda: tmp_path / 'logs')
    monkeypatch.setattr(gui_module, 'load_existing_analysis', fake_load_existing_analysis)

    window = MainWindow()
    try:
        assert app is not None
        assert loaded_dirs == [tmp_path]
        assert window.records_model.rowCount() == 1
        assert window.output_list.count() == 1
        assert Path(window.output_list.item(0).data(Qt.ItemDataRole.UserRole)) == json_path
        assert 'Loaded 1 records from 1 existing JSON files' in window.log_edit.toPlainText()
        widgets = [window.results_layout.itemAt(index).widget() for index in range(window.results_layout.count())]
        assert any(isinstance(widget, gui_module.AnalysisCardWidget) for widget in widgets)
    finally:
        window.close()
        window.deleteLater()


def qt_app() -> QApplication:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


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
