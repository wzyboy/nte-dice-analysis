import os
import re
import ast
import logging
from io import BytesIO
from pathlib import Path
from datetime import datetime
from collections.abc import Callable

import pytest
from PIL import Image
from PySide6.QtGui import QFontMetrics
from PySide6.QtCore import Qt
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget
from PySide6.QtWidgets import QGridLayout
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QScrollArea
from PySide6.QtWidgets import QApplication

import nte_dice_analysis.gui as gui_module
from nte_dice_analysis.io import write_json
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
from nte_dice_analysis.gui import copy_existing_file
from nte_dice_analysis.gui import default_output_dir
from nte_dice_analysis.gui import open_existing_path
from nte_dice_analysis.gui import dashboard_date_text
from nte_dice_analysis.gui import configure_file_logging
from nte_dice_analysis.gui import dashboard_average_html
from nte_dice_analysis.gui import dashboard_history_html
from nte_dice_analysis.gui import dashboard_summary_html
from nte_dice_analysis.gui import copy_image_to_clipboard
from nte_dice_analysis.gui import default_export_dialog_path
from nte_dice_analysis.gui import dashboard_grid_column_count
from nte_dice_analysis.models import Record
from nte_dice_analysis.summary import RarityStat
from nte_dice_analysis.summary import PoolSummary
from nte_dice_analysis.summary import SClassHistoryItem
from nte_dice_analysis.constants import OUTPUT_FIELDS
from nte_dice_analysis.gui_strings import GUI_TEXT
from nte_dice_analysis.gui_strings import WARNING_TEXT
from nte_dice_analysis.gui_strings import OUTPUT_FIELD_LABELS
from nte_dice_analysis.gui_workflow import CropResult
from nte_dice_analysis.gui_workflow import ExportResult
from nte_dice_analysis.gui_workflow import SimpleResult
from nte_dice_analysis.gui_workflow import ProgressEvent
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


def test_dashboard_grid_column_count_wraps_cards_by_width() -> None:
    assert dashboard_grid_column_count(0, 1200) == 0
    assert dashboard_grid_column_count(3, 1680) == 3
    assert dashboard_grid_column_count(3, 1200) == 2
    assert dashboard_grid_column_count(3, 360) == 1
    assert dashboard_grid_column_count(2, 1680) == 2


def test_pie_chart_reserves_space_for_right_edge_labels() -> None:
    qt_app()

    widget = gui_module.PieChartWidget()
    widget.resize(560, 520)
    stats = [
        RarityStat(
            rarity='S-Class',
            label='S-Class',
            count=5,
            percent=12.5,
            color=(245, 158, 11),
        ),
        RarityStat(
            rarity='A-Class',
            label='A-Class',
            count=5,
            percent=12.5,
            color=(124, 58, 237),
        ),
        RarityStat(
            rarity='B-Class',
            label='B-Class',
            count=30,
            percent=75,
            color=(156, 163, 175),
        ),
    ]
    widget.set_stats(stats)

    total = sum(stat.count for stat in stats)
    metrics = QFontMetrics(widget.label_font())
    pie_rect = widget.pie_rect_for(widget.rect(), total, metrics)
    a_class_row = next(row for row in widget.label_rows(pie_rect, total) if row.stat.rarity == 'A-Class')
    label_width = widget.label_width(a_class_row.lines, metrics)
    single_line_width = metrics.horizontalAdvance('A-Class 12.50%')
    label_x = widget.label_text_x(a_class_row, pie_rect, label_width)

    assert a_class_row.lines == ('A-Class', '12.50%')
    assert label_width < single_line_width
    assert pie_rect.width() > widget.width() - 2 * (
        single_line_width + gui_module.PIE_LABEL_GAP + gui_module.PIE_LABEL_EDGE_PADDING
    )
    assert a_class_row.side == 'right'
    assert label_x >= pie_rect.right() + gui_module.PIE_LABEL_GAP
    assert label_x + label_width <= widget.width() - gui_module.PIE_LABEL_EDGE_PADDING


def test_main_window_uses_responsive_results_grid(
    monkeypatch: pytest.MonkeyPatch,
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
        assert isinstance(window.results_grid, gui_module.DashboardResultsGridWidget)
        assert isinstance(window.results_grid.layout(), QGridLayout)

        scroll_area = window.centralWidget().findChild(QScrollArea, 'ResultsScrollArea')
        assert scroll_area is not None
        assert scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    finally:
        window.close()
        window.deleteLater()


def test_update_analysis_cards_populates_responsive_grid_for_three_pools(
    monkeypatch: pytest.MonkeyPatch,
    record_factory: Callable[..., Record],
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
        records = [
            record_factory(pool_type=pool_type, source_image=f'pool-{index}.png')
            for index, pool_type in enumerate(gui_module.POOL_TYPES)
        ]

        window.update_analysis_cards(records)

        cards = window.results_grid.findChildren(gui_module.AnalysisCardWidget)
        assert window.results_grid.card_count == 3
        assert len(cards) == 3
        assert isinstance(window.results_grid.layout(), QGridLayout)
        assert not hasattr(window, 'results_layout')
    finally:
        window.close()
        window.deleteLater()


def test_results_grid_reflows_after_show_and_keeps_three_up_gaps_tight(
    monkeypatch: pytest.MonkeyPatch,
    record_factory: Callable[..., Record],
) -> None:
    app = qt_app()

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
        records = [
            record_factory(pool_type=pool_type, source_image=f'pool-{index}.png')
            for index, pool_type in enumerate(gui_module.POOL_TYPES)
        ]

        window.update_analysis_cards(records)
        window.show()
        app.processEvents()
        app.processEvents()

        cards = sorted(
            window.results_grid.findChildren(gui_module.AnalysisCardWidget),
            key=lambda card: card.mapTo(window.results_grid, card.rect().topLeft()).x(),
        )
        positions = [card.mapTo(window.results_grid, card.rect().topLeft()) for card in cards]
        gaps = [
            positions[index + 1].x() - (positions[index].x() + cards[index].width()) for index in range(len(cards) - 1)
        ]

        assert window.results_grid.column_count == 3
        assert window.width() == MAIN_WINDOW_INITIAL_WIDTH
        assert {position.y() for position in positions} == {positions[0].y()}
        assert max(gaps) <= 48
    finally:
        window.close()
        window.deleteLater()


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
        assert GUI_TEXT.export_image in dashboard_button_texts
        assert GUI_TEXT.export_table in dashboard_button_texts
        action_bar = window.centralWidget().findChild(QWidget, 'ActionBar')
        assert action_bar is not None
        action_bar_button_texts = [button.text() for button in action_bar.findChildren(QPushButton)]
        assert GUI_TEXT.copy_as_image not in action_bar_button_texts
        assert GUI_TEXT.export_image not in action_bar_button_texts
        assert GUI_TEXT.export_table not in action_bar_button_texts
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


def test_copy_existing_file_copies_to_nested_destination(tmp_path: Path) -> None:
    source = tmp_path / 'records.xlsx'
    destination = tmp_path / 'exports' / 'chosen.xlsx'
    source.write_bytes(b'workbook bytes')

    assert copy_existing_file(source, destination)
    assert destination.read_bytes() == b'workbook bytes'


def test_copy_existing_file_rejects_missing_source(tmp_path: Path) -> None:
    source = tmp_path / 'missing.xlsx'
    destination = tmp_path / 'exports' / 'chosen.xlsx'

    assert not copy_existing_file(source, destination)
    assert not destination.exists()


def test_default_export_dialog_path_uses_home_desktop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, 'home', lambda: tmp_path / 'home')
    timestamp = datetime(2026, 5, 31, 14, 5, 6)

    assert default_export_dialog_path('records.png', timestamp) == (
        tmp_path / 'home' / 'Desktop' / 'NTE_Dice_Analysis_2026-05-31_14-05-06.png'
    )
    assert default_export_dialog_path('records.xlsx', timestamp) == (
        tmp_path / 'home' / 'Desktop' / 'NTE_Dice_Analysis_2026-05-31_14-05-06.xlsx'
    )


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
        assert window.results_grid.card_count == 1
        assert any(
            isinstance(widget, gui_module.AnalysisCardWidget) for widget in window.results_grid.findChildren(QWidget)
        )

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


def test_main_window_analyze_without_selection_refreshes_existing_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    record_factory: Callable[..., Record],
) -> None:
    qt_app()
    json_path = tmp_path / 'existing.json'
    xlsx_path = tmp_path / 'records.xlsx'
    png_path = tmp_path / 'records.png'
    write_json(json_path, [record_factory()])
    xlsx_path.write_bytes(b'old workbook')
    png_path.write_bytes(b'old image')

    monkeypatch.setattr(gui_module, 'default_output_dir', lambda: tmp_path)
    monkeypatch.setattr(gui_module, 'default_log_dir', lambda: tmp_path / 'logs')

    window = MainWindow()
    try:
        warnings: list[str] = []
        started_buttons: list[QPushButton] = []
        progress_events: list[ProgressEvent] = []

        def fake_start_task(
            task: Callable[[Callable[[ProgressEvent], None]], object],
            button: QPushButton,
            on_result: Callable[[object], None],
            progress_bar: object,
            log_edit: object,
        ) -> None:
            started_buttons.append(button)
            result = task(progress_events.append)
            on_result(result)

        monkeypatch.setattr(window, 'show_warning', warnings.append)
        monkeypatch.setattr(window, 'start_task', fake_start_task)

        window.run_simple_task()

        output_paths = [
            Path(window.output_list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(window.output_list.count())
        ]
        progress_messages = [event.message for event in progress_events]
        assert warnings == []
        assert started_buttons == [window.btn_analyze]
        assert any(f'Writing {xlsx_path}' in message for message in progress_messages)
        assert any(f'Writing {png_path}' in message for message in progress_messages)
        assert xlsx_path.read_bytes() != b'old workbook'
        assert png_path.read_bytes() != b'old image'
        assert window.records_model.rowCount() == 1
        assert window.results_grid.card_count == 1
        assert window._latest_png_path == png_path
        assert window._existing_analysis_json_paths == [json_path]
        assert output_paths == [xlsx_path, png_path]
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


def test_main_window_exports_simple_png_as(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qt_app()
    source = tmp_path / 'records.png'
    destination = tmp_path / 'exports' / 'chosen.png'
    default_dialog_path = tmp_path / 'Desktop' / 'NTE_Dice_Analysis_2026-05-31_14-05-06.png'
    Image.new('RGB', (2, 3), 'purple').save(source)
    save_dialog_calls: list[tuple[object, str, str, str]] = []

    def fake_get_save_file_name(parent: object, caption: str, directory: str, file_filter: str) -> tuple[str, str]:
        save_dialog_calls.append((parent, caption, directory, file_filter))
        return str(destination), file_filter

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
    monkeypatch.setattr(gui_module.QFileDialog, 'getSaveFileName', fake_get_save_file_name)
    monkeypatch.setattr(gui_module, 'default_export_dialog_path', lambda _filename: default_dialog_path)

    window = MainWindow()
    try:
        window.export_simple_png_as()

        assert save_dialog_calls == [
            (
                window,
                GUI_TEXT.select_output_file,
                str(default_dialog_path),
                GUI_TEXT.file_filter_png,
            ),
        ]
        with Image.open(destination) as image:
            assert image.size == (2, 3)
        assert window.statusBar().currentMessage() == GUI_TEXT.export_image_succeeded.format(path=destination)
    finally:
        window.close()
        window.deleteLater()


def test_main_window_exports_simple_xlsx_as(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qt_app()
    source = tmp_path / 'records.xlsx'
    destination = tmp_path / 'exports' / 'chosen.xlsx'
    default_dialog_path = tmp_path / 'Desktop' / 'NTE_Dice_Analysis_2026-05-31_14-05-06.xlsx'
    source.write_bytes(b'workbook bytes')
    save_dialog_calls: list[tuple[object, str, str, str]] = []

    def fake_get_save_file_name(parent: object, caption: str, directory: str, file_filter: str) -> tuple[str, str]:
        save_dialog_calls.append((parent, caption, directory, file_filter))
        return str(destination), file_filter

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
    monkeypatch.setattr(gui_module.QFileDialog, 'getSaveFileName', fake_get_save_file_name)
    monkeypatch.setattr(gui_module, 'default_export_dialog_path', lambda _filename: default_dialog_path)

    window = MainWindow()
    try:
        window.export_simple_xlsx_as()

        assert save_dialog_calls == [
            (
                window,
                GUI_TEXT.select_output_file,
                str(default_dialog_path),
                GUI_TEXT.file_filter_xlsx,
            ),
        ]
        assert destination.read_bytes() == b'workbook bytes'
        assert window.statusBar().currentMessage() == GUI_TEXT.export_table_succeeded.format(path=destination)
    finally:
        window.close()
        window.deleteLater()


def test_main_window_warns_when_simple_export_source_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qt_app()
    warnings: list[str] = []
    save_dialog_calls: list[object] = []

    def fake_get_save_file_name(*_args: object) -> tuple[str, str]:
        save_dialog_calls.append(_args)
        return str(tmp_path / 'exports' / 'chosen.png'), GUI_TEXT.file_filter_png

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
    monkeypatch.setattr(gui_module.QFileDialog, 'getSaveFileName', fake_get_save_file_name)

    window = MainWindow()
    try:
        monkeypatch.setattr(window, 'show_warning', warnings.append)

        window.export_simple_png_as()

        assert warnings == [WARNING_TEXT.output_missing.format(path=tmp_path / 'records.png')]
        assert save_dialog_calls == []
    finally:
        window.close()
        window.deleteLater()


def test_main_window_does_nothing_when_simple_export_is_cancelled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    qt_app()
    source = tmp_path / 'records.png'
    destination = tmp_path / 'exports' / 'chosen.png'
    warnings: list[str] = []
    Image.new('RGB', (2, 3), 'orange').save(source)

    def fake_get_save_file_name(*_args: object) -> tuple[str, str]:
        return '', ''

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
    monkeypatch.setattr(gui_module.QFileDialog, 'getSaveFileName', fake_get_save_file_name)

    window = MainWindow()
    try:
        monkeypatch.setattr(window, 'show_warning', warnings.append)

        window.export_simple_png_as()

        assert warnings == []
        assert not destination.exists()
        assert window.statusBar().currentMessage() == GUI_TEXT.ready
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
