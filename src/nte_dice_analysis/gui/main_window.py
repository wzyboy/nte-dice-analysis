import sys
import logging
from pathlib import Path
from dataclasses import dataclass
from collections.abc import Callable

from PySide6.QtGui import QCloseEvent
from PySide6.QtCore import Qt
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QFrame
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QStyle
from PySide6.QtWidgets import QDialog
from PySide6.QtWidgets import QWidget
from PySide6.QtWidgets import QCheckBox
from PySide6.QtWidgets import QComboBox
from PySide6.QtWidgets import QGroupBox
from PySide6.QtWidgets import QLineEdit
from PySide6.QtWidgets import QSplitter
from PySide6.QtWidgets import QTableView
from PySide6.QtWidgets import QTabWidget
from PySide6.QtWidgets import QFileDialog
from PySide6.QtWidgets import QFormLayout
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QHeaderView
from PySide6.QtWidgets import QListWidget
from PySide6.QtWidgets import QMainWindow
from PySide6.QtWidgets import QMessageBox
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QScrollArea
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QProgressBar
from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtWidgets import QListWidgetItem

from .app import LOG_FILE_NAME
from .app import MAIN_WINDOW_INITIAL_WIDTH
from .app import MAIN_WINDOW_INITIAL_HEIGHT
from .app import app_icon
from ..models import Record
from .widgets import WorkerTask
from .widgets import WorkflowWorker
from .widgets import RecordsTableModel
from .widgets import double_spin
from .widgets import progress_bar
from .widgets import optional_path
from .widgets import selected_paths
from .widgets import default_log_dir
from .widgets import open_local_file
from .widgets import fail_progress_bar
from .widgets import copy_existing_file
from .widgets import default_output_dir
from .widgets import open_existing_path
from .widgets import reset_progress_bar
from .widgets import apply_progress_event
from .widgets import complete_progress_bar
from .widgets import copy_image_to_clipboard
from .widgets import default_export_dialog_path
from ..capture import CaptureError
from ..capture import new_capture_session_dir
from ..capture import capture_foreground_window_png
from ..summary import summarize_records
from .dashboard import DASHBOARD_STYLESHEET
from .dashboard import DashboardResultsGridWidget
from ..constants import POOL_TYPES
from ..constants import DEFAULT_POOL_CROP
from ..constants import DEFAULT_TABLE_CROP
from ..constants import DEFAULT_ROW_BOUNDARIES
from ..gui_strings import GUI_TEXT
from ..gui_strings import WARNING_TEXT
from ..gui_workflow import CropConfig
from ..gui_workflow import CropResult
from ..gui_workflow import ExportConfig
from ..gui_workflow import ExportResult
from ..gui_workflow import SimpleConfig
from ..gui_workflow import SimpleResult
from ..gui_workflow import ProgressEvent
from ..gui_workflow import RecognizeConfig
from ..gui_workflow import RecognizeResult
from ..gui_workflow import ExistingAnalysisResult
from ..gui_workflow import run_crop
from ..gui_workflow import run_export
from ..gui_workflow import run_simple
from ..gui_workflow import run_recognize
from ..gui_workflow import load_existing_analysis
from .capture_hotkeys import CaptureHotkeyThread
from ..check_known_items_cli import format_missing_item_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdvancedGroup:
    group: QGroupBox
    body: QWidget


class AdvancedSettingsDialog(QDialog):
    def __init__(self, parent: QWidget, main_window: 'MainWindow') -> None:
        super().__init__(parent)
        self.setWindowTitle(GUI_TEXT.advanced_dialog_title)
        self.resize(MAIN_WINDOW_INITIAL_WIDTH, MAIN_WINDOW_INITIAL_HEIGHT)

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(main_window.build_crop_tab(), GUI_TEXT.crop_tab)
        self.tabs.addTab(main_window.build_recognize_tab(), GUI_TEXT.recognize_tab)
        self.tabs.addTab(main_window.build_export_tab(), GUI_TEXT.export_tab)

        upper = QWidget()
        upper_layout = QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.addWidget(self.tabs)
        upper_layout.addWidget(main_window.advanced_progress)

        self.lower_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.lower_splitter.addWidget(main_window.grouped(GUI_TEXT.records, main_window.records_table))
        self.lower_splitter.addWidget(main_window.grouped(GUI_TEXT.log, main_window.log_edit))
        self.lower_splitter.addWidget(main_window.build_outputs_panel())
        self.lower_splitter.setSizes([640, 360, 260])

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(upper)
        self.splitter.addWidget(self.lower_splitter)
        self.splitter.setSizes([430, 330])
        layout.addWidget(self.splitter)

        self.close_button = QPushButton(GUI_TEXT.close)
        self.close_button.clicked.connect(self.accept)
        layout.addWidget(self.close_button)


class MainWindow(QMainWindow):
    def __init__(self, log_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle('NTE Dice Analysis')
        self.setWindowIcon(app_icon())
        self.resize(MAIN_WINDOW_INITIAL_WIDTH, MAIN_WINDOW_INITIAL_HEIGHT)

        self._thread: QThread | None = None
        self._worker: WorkflowWorker | None = None
        self._active_progress_bar: QProgressBar | None = None
        self._active_log_edit: QPlainTextEdit | None = None
        self._task_failed = False
        self._capture_hotkey_thread: CaptureHotkeyThread | None = None
        self._capture_session_dir: Path | None = None
        self._capture_count = 0
        self._default_output_dir = default_output_dir()
        self._log_path = log_path or default_log_dir() / LOG_FILE_NAME
        self._advanced_dialog: AdvancedSettingsDialog | None = None
        self._existing_analysis_json_paths: list[Path] = []
        default_png_path = self._default_output_dir / 'records.png'
        self._latest_png_path: Path | None = default_png_path if default_png_path.exists() else None

        self.records_model = RecordsTableModel(self)
        self.records_table = QTableView()
        self.records_table.setModel(self.records_model)
        self.records_table.setAlternatingRowColors(False)
        self.records_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.records_table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.records_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.records_table.horizontalHeader().setStretchLastSection(True)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(1000)
        self.advanced_progress = progress_bar(text_visible=True, styled=False)

        self.output_list = QListWidget()
        self.open_output_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton),
            GUI_TEXT.open_selected,
        )
        self.open_output_button.clicked.connect(self.open_selected_output)

        # Build UI according to new design
        central_widget = QWidget()
        central_widget.setObjectName('DashboardContainer')
        central_widget.setStyleSheet(DASHBOARD_STYLESHEET)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(30, 20, 30, 30)
        main_layout.setSpacing(20)

        # Header
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        app_title = QLabel(GUI_TEXT.app_title)
        app_title.setStyleSheet('font-size: 20px; font-weight: bold; color: #1e293b;')
        app_subtitle = QLabel(GUI_TEXT.app_subtitle)
        app_subtitle.setStyleSheet('font-size: 14px; color: #64748b;')
        title_box.addWidget(app_title)
        title_box.addWidget(app_subtitle)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        self.advanced_mode_button = QPushButton(GUI_TEXT.advanced_mode)
        self.advanced_mode_button.setObjectName('SecondaryButton')
        self.advanced_mode_button.clicked.connect(self.open_advanced_dialog)
        header_layout.addWidget(self.advanced_mode_button)
        main_layout.addLayout(header_layout)

        # Action Bar
        action_bar = QFrame()
        action_bar.setObjectName('ActionBar')
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(15, 10, 15, 10)
        action_layout.setSpacing(15)

        self.btn_add_files = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon), GUI_TEXT.add_files
        )
        self.btn_add_files.setObjectName('SecondaryButton')

        self.btn_add_folder = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon), GUI_TEXT.add_folder
        )
        self.btn_add_folder.setObjectName('SecondaryButton')

        self.btn_capture_game = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon),
            GUI_TEXT.capture_from_game,
        )
        self.btn_capture_game.setObjectName('SecondaryButton')
        self.btn_capture_game.clicked.connect(self.start_capture_mode)

        self.simple_selection_label = QLabel(GUI_TEXT.no_simple_input_selected)
        self.simple_selection_label.setObjectName('SelectedInputLabel')
        self.simple_selection_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.simple_selection_label.setMinimumWidth(180)
        self.simple_selection_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.btn_analyze = QPushButton(GUI_TEXT.analyze)
        self.btn_analyze.setObjectName('PrimaryButton')
        self.btn_analyze.clicked.connect(self.run_simple_task)

        self.btn_copy_as_image = QPushButton(GUI_TEXT.copy_as_image)
        self.btn_copy_as_image.setObjectName('SecondaryButton')
        self.btn_copy_as_image.clicked.connect(self.copy_latest_png_image)

        self.btn_export_image = QPushButton(GUI_TEXT.export_image)
        self.btn_export_image.setObjectName('SecondaryButton')
        self.btn_export_image.clicked.connect(self.export_simple_png_as)

        self.btn_export_table = QPushButton(GUI_TEXT.export_table)
        self.btn_export_table.setObjectName('SecondaryButton')
        self.btn_export_table.clicked.connect(self.export_simple_xlsx_as)

        action_layout.addWidget(self.btn_add_files)
        action_layout.addWidget(self.btn_add_folder)
        action_layout.addWidget(self.btn_capture_game)
        action_layout.addWidget(self.simple_selection_label, 1)
        action_layout.addWidget(self.btn_analyze)
        main_layout.addWidget(action_bar)

        # Progress Bar
        self.simple_progress = progress_bar(text_visible=False, styled=True)
        main_layout.addWidget(self.simple_progress)

        self.simple_inputs = QListWidget()

        self.btn_add_files.clicked.connect(
            lambda: self.add_files(self.simple_inputs, GUI_TEXT.select_screenshots, GUI_TEXT.file_filter_images)
        )
        self.btn_add_folder.clicked.connect(lambda: self.add_folder(self.simple_inputs))

        # Analysis Results Area
        scroll_area = QScrollArea()
        scroll_area.setObjectName('ResultsScrollArea')
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet('background-color: transparent;')

        self.results_grid = DashboardResultsGridWidget()
        scroll_area.setWidget(self.results_grid)
        main_layout.addWidget(scroll_area, 1)

        copy_button_layout = QHBoxLayout()
        copy_button_layout.addStretch(1)
        copy_button_layout.addWidget(self.btn_copy_as_image)
        copy_button_layout.addWidget(self.btn_export_image)
        copy_button_layout.addWidget(self.btn_export_table)
        copy_button_layout.addStretch(1)
        main_layout.addLayout(copy_button_layout)

        # Hidden or secondary UI elements needed for backward compatibility/workers
        self.simple_out_dir = QLineEdit(str(self._default_output_dir))
        self.simple_log_edit = self.log_edit  # Use the same log edit

        self.load_existing_analysis_results()
        self.statusBar().showMessage(GUI_TEXT.ready)

    def open_advanced_dialog(self) -> None:
        if self._advanced_dialog is None:
            self._advanced_dialog = AdvancedSettingsDialog(self, self)
        self._advanced_dialog.exec()

    def load_existing_analysis_results(self) -> None:
        try:
            result = load_existing_analysis(self._default_output_dir)
        except Exception as error:
            message = f'Failed to load existing JSON files from {self._default_output_dir}: {error}'
            logger.exception(message)
            self.append_log(message)
            return

        if not result.json_paths:
            return

        self.handle_existing_analysis_result(result)

    def handle_existing_analysis_result(self, result: ExistingAnalysisResult) -> None:
        self._existing_analysis_json_paths = result.json_paths
        if hasattr(self, 'export_inputs'):
            self.add_paths(self.export_inputs, result.json_paths)
        self.records_model.set_records(result.records)
        self.update_analysis_cards(result.records)
        self.set_outputs(result.json_paths)
        self.append_log(
            f'Loaded {result.raw_record_count} records from {len(result.json_paths)} existing JSON files; '
            f'showing {result.exported_record_count} records',
        )

    def clear_analysis_results(self) -> None:
        self.results_grid.clear_cards()

    def grouped(self, title: str, widget: QWidget) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.addWidget(widget)
        return group

    def build_outputs_panel(self) -> QGroupBox:
        group = QGroupBox(GUI_TEXT.outputs)
        layout = QVBoxLayout(group)
        layout.addWidget(self.output_list)
        layout.addWidget(self.open_output_button)
        return group

    def build_crop_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.crop_inputs = QListWidget()
        layout.addWidget(self.grouped(GUI_TEXT.screenshots, self.crop_inputs))
        layout.addLayout(
            self.path_buttons(
                self.crop_inputs,
                file_caption=GUI_TEXT.select_screenshots,
                file_filter=GUI_TEXT.file_filter_images,
            ),
        )

        self.crop_out_dir = QLineEdit(str(self._default_output_dir))
        layout.addLayout(self.directory_row(GUI_TEXT.output_directory, self.crop_out_dir))

        self.crop_overwrite = QCheckBox(GUI_TEXT.overwrite_existing_table_images)
        layout.addWidget(self.crop_overwrite)

        advanced = self.advanced_group(GUI_TEXT.advanced_crop_settings)
        form = QFormLayout(advanced.body)
        self.crop_table_crop = QLineEdit(DEFAULT_TABLE_CROP)
        self.crop_pool_crop = QLineEdit(DEFAULT_POOL_CROP)
        self.crop_det_model_dir = QLineEdit()
        self.crop_rec_model_dir = QLineEdit()
        form.addRow(GUI_TEXT.table_crop, self.crop_table_crop)
        form.addRow(GUI_TEXT.pool_crop, self.crop_pool_crop)
        form.addRow(GUI_TEXT.detection_model, self.directory_picker(self.crop_det_model_dir))
        form.addRow(GUI_TEXT.recognition_model, self.directory_picker(self.crop_rec_model_dir))
        layout.addWidget(advanced.group)

        self.crop_run_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            GUI_TEXT.run_crop,
        )
        self.crop_run_button.clicked.connect(self.run_crop_task)
        layout.addWidget(self.crop_run_button)
        layout.addStretch(1)
        return tab

    def build_recognize_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.recognize_inputs = QListWidget()
        layout.addWidget(self.grouped(GUI_TEXT.table_images, self.recognize_inputs))
        layout.addLayout(
            self.path_buttons(
                self.recognize_inputs,
                file_caption=GUI_TEXT.select_table_images,
                file_filter=GUI_TEXT.file_filter_images,
            ),
        )

        self.recognize_out_dir = QLineEdit(str(self._default_output_dir))
        self.recognize_debug_dir = QLineEdit()
        self.recognize_known_items = QLineEdit()
        layout.addLayout(self.directory_row(GUI_TEXT.output_directory, self.recognize_out_dir))
        layout.addLayout(self.directory_row(GUI_TEXT.debug_directory, self.recognize_debug_dir))
        layout.addLayout(
            self.file_row(GUI_TEXT.known_items, self.recognize_known_items, GUI_TEXT.file_filter_toml),
        )

        self.recognize_pool_type = QComboBox()
        self.recognize_pool_type.setEditable(True)
        self.recognize_pool_type.addItem('')
        self.recognize_pool_type.addItems(POOL_TYPES)
        pool_row = QHBoxLayout()
        pool_row.addWidget(QLabel(GUI_TEXT.pool_type_override))
        pool_row.addWidget(self.recognize_pool_type)
        layout.addLayout(pool_row)

        self.recognize_overwrite = QCheckBox(GUI_TEXT.overwrite_existing_json_files)
        layout.addWidget(self.recognize_overwrite)

        advanced = self.advanced_group(GUI_TEXT.advanced_ocr_settings)
        form = QFormLayout(advanced.body)
        self.recognize_row_boundaries = QLineEdit(DEFAULT_ROW_BOUNDARIES)
        self.recognize_min_score = double_spin(0.3, 0.0, 1.0, 0.05, 3)
        self.recognize_det_model_dir = QLineEdit()
        self.recognize_rec_model_dir = QLineEdit()
        form.addRow(GUI_TEXT.row_boundaries, self.recognize_row_boundaries)
        form.addRow(GUI_TEXT.min_score, self.recognize_min_score)
        form.addRow(GUI_TEXT.detection_model, self.directory_picker(self.recognize_det_model_dir))
        form.addRow(GUI_TEXT.recognition_model, self.directory_picker(self.recognize_rec_model_dir))
        layout.addWidget(advanced.group)

        self.recognize_run_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            GUI_TEXT.run_ocr,
        )
        self.recognize_run_button.clicked.connect(self.run_recognize_task)
        layout.addWidget(self.recognize_run_button)
        layout.addStretch(1)
        return tab

    def build_export_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.export_inputs = QListWidget()
        self.add_paths(self.export_inputs, self._existing_analysis_json_paths)
        layout.addWidget(self.grouped(GUI_TEXT.json_files, self.export_inputs))
        layout.addLayout(
            self.path_buttons(
                self.export_inputs,
                file_caption=GUI_TEXT.select_json_files,
                file_filter=GUI_TEXT.file_filter_json,
            ),
        )

        self.export_write_xlsx = QCheckBox(GUI_TEXT.write_xlsx)
        self.export_write_xlsx.setChecked(True)
        self.export_xlsx_out = QLineEdit(str(self._default_output_dir / 'records.xlsx'))
        layout.addLayout(
            self.output_file_row(self.export_write_xlsx, self.export_xlsx_out, GUI_TEXT.file_filter_xlsx),
        )

        self.export_write_png = QCheckBox(GUI_TEXT.write_png)
        self.export_write_png.setChecked(True)
        self.export_png_out = QLineEdit(str(self._default_output_dir / 'records.png'))
        layout.addLayout(
            self.output_file_row(self.export_write_png, self.export_png_out, GUI_TEXT.file_filter_png),
        )

        self.export_run_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            GUI_TEXT.run_export,
        )
        self.export_run_button.clicked.connect(self.run_export_task)
        layout.addWidget(self.export_run_button)
        layout.addStretch(1)
        return tab

    def advanced_group(self, title: str) -> AdvancedGroup:
        group = QGroupBox(title)
        group.setCheckable(True)
        group.setChecked(False)
        body = QWidget()
        body.setVisible(False)
        layout = QVBoxLayout(group)
        layout.addWidget(body)
        group.toggled.connect(body.setVisible)
        return AdvancedGroup(group=group, body=body)

    def path_buttons(
        self,
        list_widget: QListWidget,
        *,
        file_caption: str,
        file_filter: str,
    ) -> QHBoxLayout:
        layout = QHBoxLayout()
        add_files = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon), GUI_TEXT.add_files)
        add_folder = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon), GUI_TEXT.add_folder)
        clear = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon), GUI_TEXT.clear)
        add_files.clicked.connect(lambda: self.add_files(list_widget, file_caption, file_filter))
        add_folder.clicked.connect(lambda: self.add_folder(list_widget))
        clear.clicked.connect(list_widget.clear)
        layout.addWidget(add_files)
        layout.addWidget(add_folder)
        layout.addWidget(clear)
        layout.addStretch(1)
        return layout

    def directory_row(self, label: str, line_edit: QLineEdit) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addWidget(QLabel(label))
        layout.addWidget(line_edit)
        browse = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), GUI_TEXT.browse)
        browse.clicked.connect(lambda: self.choose_directory(line_edit))
        layout.addWidget(browse)
        return layout

    def file_row(self, label: str, line_edit: QLineEdit, file_filter: str) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addWidget(QLabel(label))
        layout.addWidget(line_edit)
        browse = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), GUI_TEXT.browse)
        browse.clicked.connect(lambda: self.choose_file(line_edit, file_filter))
        layout.addWidget(browse)
        return layout

    def output_file_row(self, checkbox: QCheckBox, line_edit: QLineEdit, file_filter: str) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addWidget(checkbox)
        layout.addWidget(line_edit)
        browse = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), GUI_TEXT.browse)
        browse.clicked.connect(lambda: self.choose_output_file(line_edit, file_filter))
        layout.addWidget(browse)
        return layout

    def directory_picker(self, line_edit: QLineEdit) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        browse = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), GUI_TEXT.browse)
        browse.clicked.connect(lambda: self.choose_directory(line_edit))
        layout.addWidget(browse)
        return widget

    def add_files(self, list_widget: QListWidget, caption: str, file_filter: str) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, caption, '', file_filter)
        self.add_paths(list_widget, [Path(file) for file in files])

    def add_folder(self, list_widget: QListWidget) -> None:
        directory = QFileDialog.getExistingDirectory(self, GUI_TEXT.select_folder)
        if directory:
            self.add_paths(list_widget, [Path(directory)])

    def add_paths(self, list_widget: QListWidget, paths: list[Path]) -> None:
        existing = {list_widget.item(index).text() for index in range(list_widget.count())}
        for path in paths:
            text = str(path)
            if text in existing:
                continue
            list_widget.addItem(text)
            existing.add(text)
        if paths and getattr(self, 'simple_inputs', None) is list_widget:
            self.update_simple_selection_feedback(paths[-1])

    def update_simple_selection_feedback(self, path: Path) -> None:
        display_path = path.name or str(path)
        self.simple_selection_label.setText(GUI_TEXT.selected_simple_input.format(path=display_path))
        self.simple_selection_label.setToolTip(str(path))

    def choose_directory(self, line_edit: QLineEdit) -> None:
        directory = QFileDialog.getExistingDirectory(self, GUI_TEXT.select_folder, line_edit.text())
        if directory:
            line_edit.setText(directory)

    def choose_file(self, line_edit: QLineEdit, file_filter: str) -> None:
        file, _ = QFileDialog.getOpenFileName(self, GUI_TEXT.select_file, line_edit.text(), file_filter)
        if file:
            line_edit.setText(file)

    def choose_output_file(self, line_edit: QLineEdit, file_filter: str) -> None:
        file, _ = QFileDialog.getSaveFileName(self, GUI_TEXT.select_output_file, line_edit.text(), file_filter)
        if file:
            line_edit.setText(file)

    def run_simple_task(self) -> None:
        if self._capture_hotkey_thread is not None:
            self.show_warning(WARNING_TEXT.task_already_running)
            return

        paths = selected_paths(self.simple_inputs)
        out_dir = optional_path(self.simple_out_dir)
        if out_dir is None:
            self.show_warning(WARNING_TEXT.select_output_folder)
            return

        if not paths:
            self.run_existing_analysis_refresh_task(out_dir)
            return

        config = SimpleConfig(paths=paths, out_dir=out_dir)
        self.start_task(
            lambda progress: run_simple(config, progress=progress),
            self.btn_analyze,
            self.handle_simple_result,
            self.simple_progress,
            self.simple_log_edit,
        )

    def run_existing_analysis_refresh_task(self, out_dir: Path) -> None:
        config = ExportConfig(
            paths=[out_dir],
            xlsx_out=out_dir / 'records.xlsx',
            png_out=out_dir / 'records.png',
        )
        self.start_task(
            lambda progress: run_export(config, progress=progress),
            self.btn_analyze,
            self.handle_existing_analysis_refresh_result,
            self.simple_progress,
            self.simple_log_edit,
        )

    def run_crop_task(self) -> None:
        paths = selected_paths(self.crop_inputs)
        if not paths:
            self.show_warning(WARNING_TEXT.select_screenshot_or_folder)
            return

        config = CropConfig(
            paths=paths,
            out_dir=optional_path(self.crop_out_dir),
            overwrite=self.crop_overwrite.isChecked(),
            table_crop=self.crop_table_crop.text().strip(),
            pool_crop=self.crop_pool_crop.text().strip(),
            det_model_dir=optional_path(self.crop_det_model_dir),
            rec_model_dir=optional_path(self.crop_rec_model_dir),
        )
        self.start_task(
            lambda progress: run_crop(config, progress=progress),
            self.crop_run_button,
            self.handle_crop_result,
            self.advanced_progress,
            self.log_edit,
        )

    def run_recognize_task(self) -> None:
        paths = selected_paths(self.recognize_inputs)
        if not paths:
            self.show_warning(WARNING_TEXT.select_table_image_or_folder)
            return

        pool_type = self.recognize_pool_type.currentText().strip() or None
        config = RecognizeConfig(
            paths=paths,
            out_dir=optional_path(self.recognize_out_dir),
            overwrite=self.recognize_overwrite.isChecked(),
            pool_type=pool_type,
            debug_dir=optional_path(self.recognize_debug_dir),
            row_boundaries=self.recognize_row_boundaries.text().strip(),
            min_score=self.recognize_min_score.value(),
            known_items_path=optional_path(self.recognize_known_items),
            det_model_dir=optional_path(self.recognize_det_model_dir),
            rec_model_dir=optional_path(self.recognize_rec_model_dir),
        )
        self.start_task(
            lambda progress: run_recognize(config, progress=progress),
            self.recognize_run_button,
            self.handle_recognize_result,
            self.advanced_progress,
            self.log_edit,
        )

    def run_export_task(self) -> None:
        paths = selected_paths(self.export_inputs)
        if not paths:
            self.show_warning(WARNING_TEXT.select_json_file_or_folder)
            return

        config = ExportConfig(
            paths=paths,
            xlsx_out=optional_path(self.export_xlsx_out) if self.export_write_xlsx.isChecked() else None,
            png_out=optional_path(self.export_png_out) if self.export_write_png.isChecked() else None,
        )
        self.start_task(
            lambda progress: run_export(config, progress=progress),
            self.export_run_button,
            self.handle_export_result,
            self.advanced_progress,
            self.log_edit,
        )

    def start_task(
        self,
        task: WorkerTask,
        button: QPushButton,
        on_result: Callable[[object], None],
        progress_bar: QProgressBar,
        log_edit: QPlainTextEdit,
    ) -> None:
        if self._thread is not None or self._capture_hotkey_thread is not None:
            self.show_warning(WARNING_TEXT.task_already_running)
            return

        self.clear_log(log_edit)
        self.set_outputs([])
        self.clear_analysis_results()
        self._task_failed = False
        self._active_progress_bar = progress_bar
        self._active_log_edit = log_edit
        reset_progress_bar(progress_bar)
        button.setEnabled(False)
        self.statusBar().showMessage(GUI_TEXT.running)

        thread = QThread(self)
        worker = WorkflowWorker(task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.handle_progress_event)
        worker.result.connect(on_result)
        worker.error.connect(self.handle_worker_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self.finish_task(button, progress_bar))

        self._thread = thread
        self._worker = worker
        thread.start()

    def finish_task(self, button: QPushButton, progress_bar: QProgressBar) -> None:
        button.setEnabled(True)
        self._thread = None
        self._worker = None
        self._active_progress_bar = None
        self._active_log_edit = None
        if self._task_failed:
            fail_progress_bar(progress_bar)
        else:
            complete_progress_bar(progress_bar)
        self.statusBar().showMessage(GUI_TEXT.ready, 3000)

    def start_capture_mode(self) -> None:
        if self._thread is not None or self._capture_hotkey_thread is not None:
            self.show_warning(WARNING_TEXT.task_already_running)
            return
        if sys.platform != 'win32':
            self.show_warning(WARNING_TEXT.capture_windows_only)
            return

        if not self.show_capture_instructions():
            return

        thread = CaptureHotkeyThread(self)
        thread.registered.connect(self.enter_capture_mode)
        thread.capture_requested.connect(self.capture_game_window)
        thread.finish_requested.connect(self.finish_capture_mode)
        thread.error.connect(self.handle_capture_hotkey_error)
        self._capture_hotkey_thread = thread
        self.btn_capture_game.setEnabled(False)
        self.statusBar().showMessage(GUI_TEXT.capture_hotkeys_registering)
        thread.start()

    def show_capture_instructions(self) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(GUI_TEXT.capture_mode_title)
        dialog.setText(GUI_TEXT.capture_mode_instructions)
        start_button = dialog.addButton(GUI_TEXT.start_capture, QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton(GUI_TEXT.cancel, QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        return dialog.clickedButton() is start_button

    def enter_capture_mode(self) -> None:
        try:
            self._capture_session_dir = new_capture_session_dir(self._default_output_dir)
        except OSError as error:
            self.handle_capture_hotkey_error(str(error))
            return

        self._capture_count = 0
        self.append_log(GUI_TEXT.capture_session_started.format(path=self._capture_session_dir))
        self.statusBar().showMessage(GUI_TEXT.capture_mode_running)
        self.showMinimized()

    def capture_game_window(self) -> None:
        session_dir = self._capture_session_dir
        if session_dir is None:
            return

        next_index = self._capture_count + 1
        path = session_dir / f'capture_{session_dir.name}_{next_index:04d}.png'
        try:
            capture_foreground_window_png(path)
        except (CaptureError, OSError) as error:
            message = WARNING_TEXT.capture_failed.format(error=error)
            self.append_log(message)
            self.show_warning(message)
            return

        self._capture_count = next_index
        message = GUI_TEXT.capture_saved.format(path=path)
        self.append_log(message)
        self.statusBar().showMessage(message, 3000)

    def finish_capture_mode(self) -> None:
        session_dir = self._capture_session_dir
        capture_count = self._capture_count
        self.stop_capture_hotkeys()
        self._capture_session_dir = None
        self._capture_count = 0
        self.showNormal()
        self.activateWindow()

        if session_dir is None or capture_count <= 0:
            self.show_warning(WARNING_TEXT.capture_no_images)
            self.statusBar().showMessage(GUI_TEXT.ready, 3000)
            return

        self.simple_inputs.clear()
        self.add_paths(self.simple_inputs, [session_dir])
        message = GUI_TEXT.capture_finished_analyzing.format(count=capture_count)
        self.append_log(message)
        self.statusBar().showMessage(message, 3000)
        self.run_simple_task()

    def handle_capture_hotkey_error(self, error: str) -> None:
        self.stop_capture_hotkeys()
        self._capture_session_dir = None
        self._capture_count = 0
        self.showNormal()
        self.activateWindow()
        self.statusBar().showMessage(GUI_TEXT.ready, 3000)
        self.show_warning(WARNING_TEXT.capture_hotkey_failed.format(error=error))

    def stop_capture_hotkeys(self) -> None:
        thread = self._capture_hotkey_thread
        self._capture_hotkey_thread = None
        if thread is not None:
            thread.stop()
            thread.wait(1000)
        self.btn_capture_game.setEnabled(True)

    def handle_crop_result(self, result: object) -> None:
        crop_result = result
        if not isinstance(crop_result, CropResult):
            return

        paths = [*crop_result.written_paths, *crop_result.skipped_paths]
        self.set_outputs(paths)
        if hasattr(self, 'recognize_inputs'):
            self.add_paths(self.recognize_inputs, paths)
        self.append_log_paths('Cropped table images', crop_result.written_paths)
        self.append_log_paths('Skipped existing files', crop_result.skipped_paths)

    def handle_simple_result(self, result: object) -> None:
        simple_result = result
        if not isinstance(simple_result, SimpleResult):
            return

        self.records_model.set_records(simple_result.records)
        self.update_analysis_cards(simple_result.records)
        self._latest_png_path = simple_result.png_path

        output_paths = [simple_result.xlsx_path, simple_result.png_path]
        self.set_outputs(output_paths)
        self.append_log_paths('Exported files', output_paths)
        if simple_result.summary:
            self.append_log('')
            self.append_log(simple_result.summary)

    def update_analysis_cards(self, records: list[Record]) -> None:
        summaries = summarize_records(records)
        self.results_grid.set_summaries(summaries)

    def handle_recognize_result(self, result: object) -> None:
        recognize_result = result
        if not isinstance(recognize_result, RecognizeResult):
            return

        self.records_model.set_records(recognize_result.records)
        self.update_analysis_cards(recognize_result.records)
        self.set_outputs(recognize_result.json_paths)
        if hasattr(self, 'export_inputs'):
            self.add_paths(self.export_inputs, recognize_result.json_paths)
        self.append_log_paths('JSON files', recognize_result.json_paths)
        for missing_item in recognize_result.missing_known_items:
            self.append_log(
                'Missing known item: '
                f'{format_missing_item_key(missing_item.pool_type, missing_item.item_name)} '
                f'({missing_item.occurrence_count} occurrences)',
            )
            for reference in missing_item.references[:3]:
                self.append_log(f'  {reference}')
            if len(missing_item.references) > 3:
                self.append_log(f'  ... {len(missing_item.references) - 3} more')

    def handle_export_result(self, result: object) -> None:
        export_result = result
        if not isinstance(export_result, ExportResult):
            return

        self.records_model.set_records(export_result.records)
        self.update_analysis_cards(export_result.records)
        if export_result.png_path is not None:
            self._latest_png_path = export_result.png_path
        output_paths = [path for path in [export_result.xlsx_path, export_result.png_path] if path is not None]
        self.set_outputs(output_paths)
        self.append_log_paths('Exported files', output_paths)
        if export_result.summary:
            self.append_log('')
            self.append_log(export_result.summary)

    def handle_existing_analysis_refresh_result(self, result: object) -> None:
        export_result = result
        if not isinstance(export_result, ExportResult):
            return

        self._existing_analysis_json_paths = export_result.json_paths
        if hasattr(self, 'export_inputs'):
            self.add_paths(self.export_inputs, export_result.json_paths)
        self.handle_export_result(export_result)

    def handle_progress_event(self, event: object) -> None:
        if not isinstance(event, ProgressEvent):
            return

        self.append_log(event.message)
        if self._active_progress_bar is not None:
            apply_progress_event(self._active_progress_bar, event)

    def handle_worker_error(self, message: str) -> None:
        self._task_failed = True
        logger.error('Task failed: %s', message)
        self.append_log(message)
        QMessageBox.critical(self, GUI_TEXT.task_failed, message)

    def show_warning(self, message: str) -> None:
        QMessageBox.warning(self, GUI_TEXT.warning_title, message)

    def clear_log(self, log_edit: QPlainTextEdit) -> None:
        log_edit.clear()

    def append_log(self, message: str) -> None:
        if message:
            logger.info(message)
        log_edit = self._active_log_edit or self.log_edit
        log_edit.appendPlainText(message)

    def append_log_paths(self, title: str, paths: list[Path]) -> None:
        if not paths:
            return
        self.append_log(title + ':')
        for path in paths:
            self.append_log(f'  {path}')

    def set_outputs(self, paths: list[Path]) -> None:
        self.output_list.clear()
        for path in paths:
            item = QListWidgetItem(str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.output_list.addItem(item)

    def open_selected_output(self) -> None:
        item = self.output_list.currentItem()
        if item is None:
            self.show_warning(WARNING_TEXT.select_output_first)
            return

        path = Path(item.data(Qt.ItemDataRole.UserRole))
        if not open_existing_path(path):
            self.show_warning(WARNING_TEXT.output_missing.format(path=path))

    def copy_latest_png_image(self) -> None:
        path = self._latest_png_path
        if path is None:
            default_path = self.simple_output_path('records.png')
            if default_path is not None and default_path.exists():
                path = default_path
                self._latest_png_path = path

        if path is None:
            self.show_warning(WARNING_TEXT.copy_image_unavailable)
            return

        if copy_image_to_clipboard(path):
            self.statusBar().showMessage(GUI_TEXT.copy_image_succeeded, 3000)
            return

        self.show_warning(WARNING_TEXT.copy_image_failed.format(path=path))

    def export_simple_png_as(self) -> None:
        self.export_simple_file_as('records.png', GUI_TEXT.file_filter_png, GUI_TEXT.export_image_succeeded)

    def export_simple_xlsx_as(self) -> None:
        self.export_simple_file_as('records.xlsx', GUI_TEXT.file_filter_xlsx, GUI_TEXT.export_table_succeeded)

    def export_simple_file_as(self, filename: str, file_filter: str, success_message: str) -> None:
        source = self.simple_output_path(filename)
        if source is None:
            self.show_warning(WARNING_TEXT.select_output_folder_first)
            return

        if not source.exists() or not source.is_file():
            self.show_warning(WARNING_TEXT.output_missing.format(path=source))
            return

        destination, _ = QFileDialog.getSaveFileName(
            self,
            GUI_TEXT.select_output_file,
            str(default_export_dialog_path(filename)),
            file_filter,
        )
        if not destination:
            return

        destination_path = Path(destination)
        if copy_existing_file(source, destination_path):
            self.statusBar().showMessage(success_message.format(path=destination_path), 3000)
            return

        self.show_warning(WARNING_TEXT.export_file_failed.format(path=destination_path))

    def open_log_file(self) -> None:
        if not open_local_file(self._log_path):
            self.show_warning(WARNING_TEXT.log_open_failed.format(path=self._log_path))

    def open_simple_xlsx(self) -> None:
        path = self.simple_output_path('records.xlsx')
        if path is None:
            self.show_warning(WARNING_TEXT.select_output_folder_first)
            return
        if not open_existing_path(path):
            self.show_warning(WARNING_TEXT.output_missing.format(path=path))

    def open_simple_png(self) -> None:
        path = self.simple_output_path('records.png')
        if path is None:
            self.show_warning(WARNING_TEXT.select_output_folder_first)
            return
        if not open_existing_path(path):
            self.show_warning(WARNING_TEXT.output_missing.format(path=path))

    def open_simple_folder(self) -> None:
        path = optional_path(self.simple_out_dir)
        if path is None:
            self.show_warning(WARNING_TEXT.select_output_folder_first)
            return
        if not open_existing_path(path):
            self.show_warning(WARNING_TEXT.output_folder_missing.format(path=path))

    def simple_output_path(self, filename: str) -> Path | None:
        out_dir = optional_path(self.simple_out_dir)
        if out_dir is None:
            return None
        return out_dir / filename

    def closeEvent(self, event: QCloseEvent) -> None:
        self.stop_capture_hotkeys()
        super().closeEvent(event)
