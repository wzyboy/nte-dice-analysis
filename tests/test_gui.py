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
from PySide6.QtWidgets import QWidget
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QApplication

import nte_dice_analysis.gui as gui_module
from nte_dice_analysis.gui import SELF_TEST_IMPORTS
from nte_dice_analysis.gui import DASHBOARD_STYLESHEET
from nte_dice_analysis.gui import MAIN_WINDOW_INITIAL_WIDTH
from nte_dice_analysis.gui import MAIN_WINDOW_INITIAL_HEIGHT
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
from nte_dice_analysis.gui import copy_image_to_clipboard
from nte_dice_analysis.png import PoolSummary
from nte_dice_analysis.png import SClassHistoryItem
from nte_dice_analysis.models import Record
from nte_dice_analysis.constants import OUTPUT_FIELDS
from nte_dice_analysis.gui_strings import GUI_TEXT
from nte_dice_analysis.gui_strings import WARNING_TEXT
from nte_dice_analysis.gui_strings import OUTPUT_FIELD_LABELS
from nte_dice_analysis.gui_workflow import CropResult
from nte_dice_analysis.gui_workflow import ExportResult
from nte_dice_analysis.gui_workflow import SimpleResult
from nte_dice_analysis.gui_workflow import RecognizeResult
from nte_dice_analysis.gui_workflow import ExistingAnalysisResult

HAN_RE = re.compile(r'[\u3400-\u9fff]')


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


def test_main_window_keeps_dashboard_styles_out_of_advanced_widgets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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
        assert window.simple_selection_label.text() == GUI_TEXT.no_simple_input_selected
        dashboard_button_texts = [button.text() for button in window.centralWidget().findChildren(QPushButton)]
        assert GUI_TEXT.clear not in dashboard_button_texts
        assert GUI_TEXT.copy_as_image in dashboard_button_texts
        action_bar = window.centralWidget().findChild(QWidget, 'ActionBar')
        assert action_bar is not None
        action_bar_button_texts = [button.text() for button in action_bar.findChildren(QPushButton)]
        assert GUI_TEXT.copy_as_image not in action_bar_button_texts
        assert window.btn_copy_as_image.minimumWidth() >= 320
        dashboard_object_names = [widget.objectName() for widget in window.centralWidget().findChildren(QWidget)]
        assert 'ScreenshotsContainer' not in dashboard_object_names
        selected_path = tmp_path / 'screenshots'
        window.add_paths(window.simple_inputs, [selected_path])
        assert window.simple_selection_label.text() == GUI_TEXT.selected_simple_input.format(path='screenshots')
        assert window.simple_selection_label.toolTip() == str(selected_path)

        dialog = gui_module.AdvancedSettingsDialog(window, window)
        try:
            dialog_button_texts = [button.text() for button in dialog.findChildren(QPushButton)]
            assert GUI_TEXT.clear in dialog_button_texts
            assert dialog.styleSheet() == ''
            assert dialog.close_button.styleSheet() == ''
            assert dialog.size().width() == MAIN_WINDOW_INITIAL_WIDTH
            assert dialog.size().height() == MAIN_WINDOW_INITIAL_HEIGHT
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


def test_copy_image_to_clipboard_copies_png_data(tmp_path: Path) -> None:
    app = qt_app()
    png_path = tmp_path / 'records.png'
    Image.new('RGB', (2, 3), 'red').save(png_path)

    app.clipboard().clear()

    assert copy_image_to_clipboard(png_path)
    image = app.clipboard().image()
    assert not image.isNull()
    assert image.width() == 2
    assert image.height() == 3


def test_copy_image_to_clipboard_rejects_missing_and_unreadable_paths(tmp_path: Path) -> None:
    qt_app()
    unreadable_path = tmp_path / 'records.png'
    unreadable_path.write_text('not a png', encoding='utf-8')

    assert not copy_image_to_clipboard(tmp_path / 'missing.png')
    assert not copy_image_to_clipboard(unreadable_path)


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

        dialog = gui_module.AdvancedSettingsDialog(window, window)
        try:
            assert window.export_inputs.count() == 1
            assert Path(window.export_inputs.item(0).text()) == json_path
        finally:
            dialog.close()
            dialog.deleteLater()
    finally:
        window.close()
        window.deleteLater()


def test_main_window_tracks_existing_default_png_on_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qt_app()
    png_path = tmp_path / 'records.png'
    Image.new('RGB', (2, 3), 'green').save(png_path)

    monkeypatch.setattr(gui_module, 'default_output_dir', lambda: tmp_path)
    monkeypatch.setattr(gui_module, 'default_log_dir', lambda: tmp_path / 'logs')
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
        assert window._latest_png_path == png_path
    finally:
        window.close()
        window.deleteLater()


def test_main_window_copies_simple_result_png(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = qt_app()
    png_path = tmp_path / 'records.png'
    Image.new('RGB', (2, 3), 'blue').save(png_path)

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
        window.handle_simple_result(
            SimpleResult(
                image_paths=[],
                table_paths=[],
                json_paths=[],
                raw_record_count=0,
                exported_record_count=0,
                xlsx_path=tmp_path / 'records.xlsx',
                png_path=png_path,
                summary='',
                records=[],
            ),
        )

        app.clipboard().clear()
        window.copy_latest_png_image()

        assert window._latest_png_path == png_path
        assert not app.clipboard().image().isNull()
        assert window.statusBar().currentMessage() == GUI_TEXT.copy_image_succeeded
    finally:
        window.close()
        window.deleteLater()


def test_main_window_tracks_export_result_png(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qt_app()
    png_path = tmp_path / 'custom-records.png'

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
        window.handle_export_result(
            ExportResult(
                json_paths=[],
                raw_record_count=0,
                exported_record_count=0,
                xlsx_path=None,
                png_path=png_path,
                summary='',
                records=[],
            ),
        )

        assert window._latest_png_path == png_path
    finally:
        window.close()
        window.deleteLater()


def test_main_window_warns_when_latest_png_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qt_app()
    missing_path = tmp_path / 'missing-records.png'
    warnings: list[str] = []

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
        window._latest_png_path = missing_path
        monkeypatch.setattr(window, 'show_warning', warnings.append)

        window.copy_latest_png_image()

        assert warnings == [WARNING_TEXT.copy_image_failed.format(path=missing_path)]
    finally:
        window.close()
        window.deleteLater()


def test_advanced_step_outputs_populate_next_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = qt_app()
    crop_written_path = tmp_path / 'first.table.limited.png'
    crop_skipped_path = tmp_path / 'second.table.standard.png'
    json_path = tmp_path / 'first.table.limited.json'

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
    dialog = gui_module.AdvancedSettingsDialog(window, window)
    try:
        assert app is not None
        window.recognize_inputs.addItem(str(crop_written_path))

        window.handle_crop_result(
            CropResult(
                image_paths=[],
                written_paths=[crop_written_path],
                skipped_paths=[crop_skipped_path],
            ),
        )

        recognize_inputs = [
            Path(window.recognize_inputs.item(index).text()) for index in range(window.recognize_inputs.count())
        ]
        assert recognize_inputs == [crop_written_path, crop_skipped_path]

        window.handle_recognize_result(
            RecognizeResult(
                image_paths=[],
                json_paths=[json_path],
                written_paths=[json_path],
                skipped_paths=[],
                written_record_count=0,
                records=[],
                missing_known_items=[],
            ),
        )

        export_inputs = [Path(window.export_inputs.item(index).text()) for index in range(window.export_inputs.count())]
        assert export_inputs == [json_path]
    finally:
        dialog.close()
        dialog.deleteLater()
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
