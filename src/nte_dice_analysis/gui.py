import os
import sys
import logging
from pathlib import Path
from importlib import import_module
from dataclasses import dataclass
from collections.abc import Callable
from logging.handlers import RotatingFileHandler

from PySide6.QtGui import QFont
from PySide6.QtGui import QColor
from PySide6.QtGui import QFontDatabase
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import Qt
from PySide6.QtCore import QUrl
from PySide6.QtCore import Slot
from PySide6.QtCore import Signal
from PySide6.QtCore import QObject
from PySide6.QtCore import QThread
from PySide6.QtCore import QModelIndex
from PySide6.QtCore import QStandardPaths
from PySide6.QtCore import QAbstractTableModel
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QStyle
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
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QProgressBar
from PySide6.QtWidgets import QDoubleSpinBox
from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtWidgets import QListWidgetItem

from .io import load_known_items
from .ocr import create_ocr
from .fonts import qt_cjk_font
from .fonts import select_qt_font_family
from .models import Record
from .models import CropBox
from .models import PipelineOptions
from .models import parse_row_boundaries
from .constants import A_CLASS
from .constants import B_CLASS
from .constants import S_CLASS
from .constants import POOL_TYPES
from .constants import OUTPUT_FIELDS
from .constants import DEFAULT_POOL_CROP
from .constants import DEFAULT_TABLE_CROP
from .constants import DEFAULT_ROW_BOUNDARIES
from .gui_strings import GUI_TEXT
from .gui_strings import WARNING_TEXT
from .gui_strings import OUTPUT_FIELD_LABELS
from .gui_workflow import CropConfig
from .gui_workflow import CropResult
from .gui_workflow import ExportConfig
from .gui_workflow import ExportResult
from .gui_workflow import SimpleConfig
from .gui_workflow import SimpleResult
from .gui_workflow import ProgressEvent
from .gui_workflow import RecognizeConfig
from .gui_workflow import RecognizeResult
from .gui_workflow import run_crop
from .gui_workflow import run_export
from .gui_workflow import run_simple
from .gui_workflow import run_recognize

type WorkerTask = Callable[[Callable[[ProgressEvent], None]], object]
type Importer = Callable[[str], object]
type Emitter = Callable[[str], None]
type OcrFactory = Callable[[PipelineOptions], object]
type UrlOpener = Callable[[QUrl], bool]

LOG_FILE_NAME = 'nte-dice-analysis.log'
LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'
SELF_TEST_IMPORTS = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PIL.Image',
    'openpyxl',
    'paddleocr',
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdvancedGroup:
    group: QGroupBox
    body: QWidget


class RecordsTableModel(QAbstractTableModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._records: list[Record] = []
        self._rows: list[dict[str, str]] = []

    def set_records(self, records: list[Record]) -> None:
        self.beginResetModel()
        self._records = records
        self._rows = [record.to_output_row() for record in records]
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(OUTPUT_FIELDS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None

        record = self._records[index.row()]
        row = self._rows[index.row()]
        field = OUTPUT_FIELDS[index.column()]

        if role == Qt.ItemDataRole.DisplayRole:
            return row.get(field, '')

        if role == Qt.ItemDataRole.BackgroundRole:
            return rarity_background(record.rarity)

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if field in {'page_row', 'roll_points', 'rarity', 'quantity', 'confidence'}:
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignVCenter

        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            field = OUTPUT_FIELDS[section]
            return OUTPUT_FIELD_LABELS.get(field, field)
        return str(section + 1)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled


def rarity_background(rarity: str) -> QColor:
    if rarity == S_CLASS:
        return QColor('#fef3c7')
    if rarity == A_CLASS:
        return QColor('#f3e8ff')
    if rarity == B_CLASS:
        return QColor('#f1f5f9')
    return QColor('#ffffff')


class WorkflowWorker(QObject):
    progress = Signal(object)
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, task: WorkerTask) -> None:
        super().__init__()
        self._task = task

    @Slot()
    def run(self) -> None:
        try:
            result = self._task(self.progress.emit)
        except SystemExit as error:
            logger.exception('Workflow task stopped')
            self.error.emit(system_exit_message(error))
        except Exception as error:
            logger.exception('Workflow task failed')
            self.error.emit(str(error) or type(error).__name__)
        else:
            self.result.emit(result)
        finally:
            self.finished.emit()


def system_exit_message(error: SystemExit) -> str:
    if error.code is None or error.code == 0:
        return 'operation stopped'
    return str(error.code)


class MainWindow(QMainWindow):
    def __init__(self, log_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle('NTE Dice Analysis')
        self.resize(1180, 820)

        self._thread: QThread | None = None
        self._worker: WorkflowWorker | None = None
        self._active_progress_bar: QProgressBar | None = None
        self._active_log_edit: QPlainTextEdit | None = None
        self._task_failed = False
        self._default_output_dir = default_output_dir()
        self._log_path = log_path or default_log_dir() / LOG_FILE_NAME

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

        self.output_list = QListWidget()
        self.open_output_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton),
            GUI_TEXT.open_selected,
        )
        self.open_output_button.clicked.connect(self.open_selected_output)

        self.mode_tabs = QTabWidget()
        self.mode_tabs.addTab(self.build_simple_tab(), GUI_TEXT.simple_tab)
        self.mode_tabs.addTab(self.build_advanced_tab(), GUI_TEXT.advanced_tab)

        self.setCentralWidget(self.mode_tabs)
        self.statusBar().showMessage(GUI_TEXT.ready)

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

    def build_advanced_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.build_crop_tab(), GUI_TEXT.crop_tab)
        self.tab_widget.addTab(self.build_recognize_tab(), GUI_TEXT.recognize_tab)
        self.tab_widget.addTab(self.build_export_tab(), GUI_TEXT.export_tab)

        self.advanced_progress = QProgressBar()
        reset_progress_bar(self.advanced_progress)

        upper = QWidget()
        upper_layout = QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.addWidget(self.tab_widget)
        upper_layout.addWidget(self.advanced_progress)

        lower_splitter = QSplitter(Qt.Orientation.Horizontal)
        lower_splitter.addWidget(self.grouped(GUI_TEXT.records, self.records_table))
        lower_splitter.addWidget(self.grouped(GUI_TEXT.log, self.log_edit))
        lower_splitter.addWidget(self.build_outputs_panel())
        lower_splitter.setSizes([640, 360, 260])

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(upper)
        splitter.addWidget(lower_splitter)
        splitter.setSizes([430, 330])
        layout.addWidget(splitter)
        return tab

    def build_simple_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.simple_inputs = QListWidget()
        layout.addWidget(self.grouped(GUI_TEXT.screenshots, self.simple_inputs))
        layout.addLayout(
            self.path_buttons(
                self.simple_inputs,
                file_caption=GUI_TEXT.select_screenshots,
                file_filter=GUI_TEXT.file_filter_images,
            ),
        )

        self.simple_out_dir = QLineEdit(str(self._default_output_dir))
        layout.addLayout(self.directory_row(GUI_TEXT.output_folder, self.simple_out_dir))

        self.simple_run_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            GUI_TEXT.run_analysis,
        )
        self.simple_run_button.clicked.connect(self.run_simple_task)

        self.open_log_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon),
            GUI_TEXT.open_log_file,
        )
        self.open_log_button.clicked.connect(self.open_log_file)

        self.open_simple_xlsx_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon),
            GUI_TEXT.open_xlsx,
        )
        self.open_simple_xlsx_button.clicked.connect(self.open_simple_xlsx)

        self.open_simple_png_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon),
            GUI_TEXT.open_png,
        )
        self.open_simple_png_button.clicked.connect(self.open_simple_png)

        self.open_simple_folder_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
            GUI_TEXT.open_folder,
        )
        self.open_simple_folder_button.clicked.connect(self.open_simple_folder)

        button_row = QHBoxLayout()
        button_row.addWidget(self.simple_run_button)
        button_row.addWidget(self.open_simple_xlsx_button)
        button_row.addWidget(self.open_simple_png_button)
        button_row.addWidget(self.open_simple_folder_button)
        button_row.addWidget(self.open_log_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.simple_progress = QProgressBar()
        reset_progress_bar(self.simple_progress)
        layout.addWidget(self.simple_progress)

        self.simple_log_edit = QPlainTextEdit()
        self.simple_log_edit.setReadOnly(True)
        self.simple_log_edit.setMaximumBlockCount(1000)
        layout.addWidget(self.grouped(GUI_TEXT.activity_log, self.simple_log_edit), 1)
        return tab

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
            self.file_row(GUI_TEXT.known_items, self.recognize_known_items, GUI_TEXT.file_filter_text),
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
        paths = selected_paths(self.simple_inputs)
        if not paths:
            self.show_warning(WARNING_TEXT.select_screenshot_or_folder)
            return

        out_dir = optional_path(self.simple_out_dir)
        if out_dir is None:
            self.show_warning(WARNING_TEXT.select_output_folder)
            return

        config = SimpleConfig(paths=paths, out_dir=out_dir)
        self.start_task(
            lambda progress: run_simple(config, progress=progress),
            self.simple_run_button,
            self.handle_simple_result,
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
        if self._thread is not None:
            self.show_warning(WARNING_TEXT.task_already_running)
            return

        self.clear_log(log_edit)
        self.set_outputs([])
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

    def handle_crop_result(self, result: object) -> None:
        crop_result = result
        if not isinstance(crop_result, CropResult):
            return

        paths = [*crop_result.written_paths, *crop_result.skipped_paths]
        self.set_outputs(paths)
        self.append_log_paths('Cropped table images', crop_result.written_paths)
        self.append_log_paths('Skipped existing files', crop_result.skipped_paths)

    def handle_simple_result(self, result: object) -> None:
        simple_result = result
        if not isinstance(simple_result, SimpleResult):
            return

        self.records_model.set_records(simple_result.records)
        output_paths = [simple_result.xlsx_path, simple_result.png_path]
        self.set_outputs(output_paths)
        self.append_log_paths('Exported files', output_paths)
        if simple_result.summary:
            self.append_log('')
            self.append_log(simple_result.summary)

    def handle_recognize_result(self, result: object) -> None:
        recognize_result = result
        if not isinstance(recognize_result, RecognizeResult):
            return

        self.records_model.set_records(recognize_result.records)
        self.set_outputs(recognize_result.json_paths)
        self.append_log_paths('JSON files', recognize_result.json_paths)
        for missing_item in recognize_result.missing_known_items:
            self.append_log(
                f'Missing known item: {missing_item.item_name} ({missing_item.occurrence_count} occurrences)',
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
        output_paths = [path for path in [export_result.xlsx_path, export_result.png_path] if path is not None]
        self.set_outputs(output_paths)
        self.append_log_paths('Exported files', output_paths)
        if export_result.summary:
            self.append_log('')
            self.append_log(export_result.summary)

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


def double_spin(value: float, minimum: float, maximum: float, step: float, decimals: int) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setSingleStep(step)
    spin.setDecimals(decimals)
    spin.setValue(value)
    return spin


def reset_progress_bar(progress_bar: QProgressBar) -> None:
    progress_bar.setRange(0, 1)
    progress_bar.setValue(0)
    progress_bar.setFormat(GUI_TEXT.ready)


def complete_progress_bar(progress_bar: QProgressBar) -> None:
    progress_bar.setRange(0, 1)
    progress_bar.setValue(1)
    progress_bar.setFormat(GUI_TEXT.complete)


def fail_progress_bar(progress_bar: QProgressBar) -> None:
    progress_bar.setRange(0, 1)
    progress_bar.setValue(0)
    progress_bar.setFormat(GUI_TEXT.failed)


def apply_progress_event(progress_bar: QProgressBar, event: ProgressEvent) -> None:
    if event.current is None or event.total is None or event.total <= 0:
        progress_bar.setRange(0, 0)
        progress_bar.setFormat(GUI_TEXT.working)
        return

    progress_bar.setRange(0, event.total)
    progress_bar.setValue(max(0, min(event.current, event.total)))
    progress_bar.setFormat(f'{event.current}/{event.total}')


def open_local_file(path: Path, opener: UrlOpener = QDesktopServices.openUrl) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    return opener(QUrl.fromLocalFile(str(path)))


def open_existing_path(path: Path, opener: UrlOpener = QDesktopServices.openUrl) -> bool:
    if not path.exists():
        return False
    return opener(QUrl.fromLocalFile(str(path)))


def selected_paths(list_widget: QListWidget) -> list[Path]:
    return [Path(list_widget.item(index).text()) for index in range(list_widget.count())]


def optional_path(line_edit: QLineEdit) -> Path | None:
    text = line_edit.text().strip()
    return Path(text) if text else None


def default_output_dir(documents_location: str | None = None) -> Path:
    if documents_location is None:
        documents_location = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation,
        )

    documents_dir = Path(documents_location) if documents_location else Path.home() / 'Documents'
    return documents_dir / 'nte-dice-analysis'


def default_log_dir(documents_location: str | None = None) -> Path:
    return default_output_dir(documents_location) / 'logs'


def apply_cjk_application_font(app: QApplication) -> None:
    font = cjk_application_font(app.font())
    if font is not None:
        app.setFont(font)
        logger.info('Using GUI font family: %s', font.family())


def cjk_application_font(base_font: QFont) -> QFont | None:
    families: list[str] = []
    spec = qt_cjk_font()
    if spec is not None:
        font_id = QFontDatabase.addApplicationFont(str(spec.path))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))

    families.extend(QFontDatabase.families())
    family = select_qt_font_family(unique_strings(families))
    if family is None:
        return None

    font = QFont(base_font)
    font.setFamily(family)
    return font


def unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        unique.append(value)
        seen.add(key)
    return unique


def configure_file_logging(documents_location: str | None = None) -> Path:
    log_dir = default_log_dir(documents_location)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / LOG_FILE_NAME
    resolved_log_path = log_path.resolve()

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == resolved_log_path:
            return log_path

    handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding='utf-8',
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    return log_path


def install_exception_logger() -> None:
    def log_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: object,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.critical(
            'Unhandled exception',
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = log_exception


def run_self_test(
    *,
    importer: Importer = import_module,
    ocr_factory: OcrFactory = create_ocr,
    emit: Emitter = print,
) -> int:
    try:
        os.environ.setdefault('DISABLE_MODEL_SOURCE_CHECK', 'True')
        os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', 'True')

        for module_name in SELF_TEST_IMPORTS:
            importer(module_name)
            emit(f'ok: imported {module_name}')

        known_items = load_known_items()
        if not known_items:
            raise RuntimeError('packaged known_items.txt is missing or empty')
        emit(f'ok: loaded {len(known_items)} known items')

        ocr_factory(self_test_options())
        emit('ok: initialized PaddleOCR pipeline')
    except Exception as error:
        logger.exception('Self-test failed')
        emit(f'failed: {error}')
        return 1

    emit('self-test passed')
    return 0


def self_test_options() -> PipelineOptions:
    return PipelineOptions(
        table_crop=CropBox.parse(DEFAULT_TABLE_CROP),
        pool_crop=CropBox.parse(DEFAULT_POOL_CROP),
        row_boundaries=parse_row_boundaries(DEFAULT_ROW_BOUNDARIES),
        min_score=0.3,
        debug_dir=None,
        det_model_dir=None,
        rec_model_dir=None,
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    log_path = configure_file_logging()
    install_exception_logger()
    logger.info('Starting NTE Dice Analysis; log file: %s', log_path)

    if '--self-test' in args:
        return run_self_test()

    app = QApplication([sys.argv[0], *args])
    apply_cjk_application_font(app)
    window = MainWindow(log_path=log_path)
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
