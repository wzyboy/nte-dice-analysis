import sys
from pathlib import Path
from dataclasses import dataclass
from collections.abc import Callable

from PySide6.QtGui import QColor
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
from PySide6.QtWidgets import QSpinBox
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
from PySide6.QtWidgets import QDoubleSpinBox
from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtWidgets import QListWidgetItem

from .models import Record
from .constants import A_CLASS
from .constants import B_CLASS
from .constants import S_CLASS
from .constants import POOL_TYPES
from .constants import OUTPUT_FIELDS
from .constants import DEFAULT_POOL_CROP
from .constants import DEFAULT_TABLE_CROP
from .gui_workflow import CropConfig
from .gui_workflow import CropResult
from .gui_workflow import ExportConfig
from .gui_workflow import ExportResult
from .gui_workflow import SimpleConfig
from .gui_workflow import SimpleResult
from .gui_workflow import RecognizeConfig
from .gui_workflow import RecognizeResult
from .gui_workflow import run_crop
from .gui_workflow import run_export
from .gui_workflow import run_simple
from .gui_workflow import run_recognize

type WorkerTask = Callable[[Callable[[str], None]], object]


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
            return OUTPUT_FIELDS[section]
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
    progress = Signal(str)
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
            self.error.emit(system_exit_message(error))
        except Exception as error:
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
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle('NTE Dice Analysis')
        self.resize(1180, 820)

        self._thread: QThread | None = None
        self._worker: WorkflowWorker | None = None
        self._default_output_dir = default_output_dir()

        self.records_model = RecordsTableModel(self)
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.build_crop_tab(), 'Crop')
        self.tab_widget.addTab(self.build_recognize_tab(), 'Recognize')
        self.tab_widget.addTab(self.build_export_tab(), 'Export')
        self.mode_tabs = QTabWidget()
        self.mode_tabs.addTab(self.build_simple_tab(), 'Simple')
        self.mode_tabs.addTab(self.tab_widget, 'Advanced')

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
            'Open Selected',
        )
        self.open_output_button.clicked.connect(self.open_selected_output)

        lower_splitter = QSplitter(Qt.Orientation.Horizontal)
        lower_splitter.addWidget(self.grouped('Records', self.records_table))
        lower_splitter.addWidget(self.grouped('Log', self.log_edit))
        lower_splitter.addWidget(self.build_outputs_panel())
        lower_splitter.setSizes([640, 360, 260])

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.mode_tabs)
        splitter.addWidget(lower_splitter)
        splitter.setSizes([430, 330])

        self.setCentralWidget(splitter)
        self.statusBar().showMessage('Ready')

    def grouped(self, title: str, widget: QWidget) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.addWidget(widget)
        return group

    def build_outputs_panel(self) -> QGroupBox:
        group = QGroupBox('Outputs')
        layout = QVBoxLayout(group)
        layout.addWidget(self.output_list)
        layout.addWidget(self.open_output_button)
        return group

    def build_simple_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.simple_inputs = QListWidget()
        layout.addWidget(self.grouped('Screenshots', self.simple_inputs))
        layout.addLayout(
            self.path_buttons(
                self.simple_inputs,
                file_caption='Select screenshots',
                file_filter='Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*)',
            ),
        )

        self.simple_out_dir = QLineEdit(str(self._default_output_dir))
        layout.addLayout(self.directory_row('Output folder', self.simple_out_dir))

        self.simple_run_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            'Run Analysis',
        )
        self.simple_run_button.clicked.connect(self.run_simple_task)
        layout.addWidget(self.simple_run_button)
        layout.addStretch(1)
        return tab

    def build_crop_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.crop_inputs = QListWidget()
        layout.addWidget(self.grouped('Screenshots', self.crop_inputs))
        layout.addLayout(
            self.path_buttons(
                self.crop_inputs,
                file_caption='Select screenshots',
                file_filter='Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*)',
            ),
        )

        self.crop_out_dir = QLineEdit(str(self._default_output_dir))
        layout.addLayout(self.directory_row('Output directory', self.crop_out_dir))

        self.crop_overwrite = QCheckBox('Overwrite existing table images')
        layout.addWidget(self.crop_overwrite)

        advanced = self.advanced_group('Advanced crop settings')
        form = QFormLayout(advanced.body)
        self.crop_table_crop = QLineEdit(DEFAULT_TABLE_CROP)
        self.crop_pool_crop = QLineEdit(DEFAULT_POOL_CROP)
        self.crop_device = device_combo()
        self.crop_det_model_dir = QLineEdit()
        self.crop_rec_model_dir = QLineEdit()
        form.addRow('Table crop', self.crop_table_crop)
        form.addRow('Pool crop', self.crop_pool_crop)
        form.addRow('Device', self.crop_device)
        form.addRow('Detection model', self.directory_picker(self.crop_det_model_dir))
        form.addRow('Recognition model', self.directory_picker(self.crop_rec_model_dir))
        layout.addWidget(advanced.group)

        self.crop_run_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            'Run Crop',
        )
        self.crop_run_button.clicked.connect(self.run_crop_task)
        layout.addWidget(self.crop_run_button)
        layout.addStretch(1)
        return tab

    def build_recognize_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.recognize_inputs = QListWidget()
        layout.addWidget(self.grouped('Table Images', self.recognize_inputs))
        layout.addLayout(
            self.path_buttons(
                self.recognize_inputs,
                file_caption='Select table images',
                file_filter='Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*)',
            ),
        )

        self.recognize_out_dir = QLineEdit(str(self._default_output_dir))
        self.recognize_debug_dir = QLineEdit()
        self.recognize_known_items = QLineEdit()
        layout.addLayout(self.directory_row('Output directory', self.recognize_out_dir))
        layout.addLayout(self.directory_row('Debug directory', self.recognize_debug_dir))
        layout.addLayout(self.file_row('Known items', self.recognize_known_items, 'Text files (*.txt);;All files (*)'))

        self.recognize_pool_type = QComboBox()
        self.recognize_pool_type.setEditable(True)
        self.recognize_pool_type.addItem('')
        self.recognize_pool_type.addItems(POOL_TYPES)
        pool_row = QHBoxLayout()
        pool_row.addWidget(QLabel('Pool type override'))
        pool_row.addWidget(self.recognize_pool_type)
        layout.addLayout(pool_row)

        self.recognize_overwrite = QCheckBox('Overwrite existing JSON files')
        layout.addWidget(self.recognize_overwrite)

        advanced = self.advanced_group('Advanced OCR settings')
        form = QFormLayout(advanced.body)
        self.recognize_row_count = QSpinBox()
        self.recognize_row_count.setRange(1, 50)
        self.recognize_row_count.setValue(5)
        self.recognize_row_top = double_spin(0.17, 0.0, 1.0, 0.01, 4)
        self.recognize_row_bottom = double_spin(0.95, 0.0, 1.0, 0.01, 4)
        self.recognize_min_score = double_spin(0.3, 0.0, 1.0, 0.05, 3)
        self.recognize_device = device_combo()
        self.recognize_det_model_dir = QLineEdit()
        self.recognize_rec_model_dir = QLineEdit()
        form.addRow('Row count', self.recognize_row_count)
        form.addRow('Row top', self.recognize_row_top)
        form.addRow('Row bottom', self.recognize_row_bottom)
        form.addRow('Min score', self.recognize_min_score)
        form.addRow('Device', self.recognize_device)
        form.addRow('Detection model', self.directory_picker(self.recognize_det_model_dir))
        form.addRow('Recognition model', self.directory_picker(self.recognize_rec_model_dir))
        layout.addWidget(advanced.group)

        self.recognize_run_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            'Run OCR',
        )
        self.recognize_run_button.clicked.connect(self.run_recognize_task)
        layout.addWidget(self.recognize_run_button)
        layout.addStretch(1)
        return tab

    def build_export_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.export_inputs = QListWidget()
        layout.addWidget(self.grouped('JSON Files', self.export_inputs))
        layout.addLayout(
            self.path_buttons(
                self.export_inputs,
                file_caption='Select JSON files',
                file_filter='JSON files (*.json);;All files (*)',
            ),
        )

        self.export_write_xlsx = QCheckBox('Write XLSX')
        self.export_write_xlsx.setChecked(True)
        self.export_xlsx_out = QLineEdit(str(self._default_output_dir / 'records.xlsx'))
        layout.addLayout(self.output_file_row(self.export_write_xlsx, self.export_xlsx_out, 'XLSX (*.xlsx)'))

        self.export_write_png = QCheckBox('Write PNG')
        self.export_write_png.setChecked(True)
        self.export_png_out = QLineEdit(str(self._default_output_dir / 'records.png'))
        layout.addLayout(self.output_file_row(self.export_write_png, self.export_png_out, 'PNG (*.png)'))

        self.export_run_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
            'Run Export',
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
        add_files = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon), 'Add Files')
        add_folder = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon), 'Add Folder')
        clear = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon), 'Clear')
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
        browse = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), 'Browse')
        browse.clicked.connect(lambda: self.choose_directory(line_edit))
        layout.addWidget(browse)
        return layout

    def file_row(self, label: str, line_edit: QLineEdit, file_filter: str) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addWidget(QLabel(label))
        layout.addWidget(line_edit)
        browse = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), 'Browse')
        browse.clicked.connect(lambda: self.choose_file(line_edit, file_filter))
        layout.addWidget(browse)
        return layout

    def output_file_row(self, checkbox: QCheckBox, line_edit: QLineEdit, file_filter: str) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addWidget(checkbox)
        layout.addWidget(line_edit)
        browse = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), 'Browse')
        browse.clicked.connect(lambda: self.choose_output_file(line_edit, file_filter))
        layout.addWidget(browse)
        return layout

    def directory_picker(self, line_edit: QLineEdit) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        browse = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), 'Browse')
        browse.clicked.connect(lambda: self.choose_directory(line_edit))
        layout.addWidget(browse)
        return widget

    def add_files(self, list_widget: QListWidget, caption: str, file_filter: str) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, caption, '', file_filter)
        self.add_paths(list_widget, [Path(file) for file in files])

    def add_folder(self, list_widget: QListWidget) -> None:
        directory = QFileDialog.getExistingDirectory(self, 'Select folder')
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
        directory = QFileDialog.getExistingDirectory(self, 'Select folder', line_edit.text())
        if directory:
            line_edit.setText(directory)

    def choose_file(self, line_edit: QLineEdit, file_filter: str) -> None:
        file, _ = QFileDialog.getOpenFileName(self, 'Select file', line_edit.text(), file_filter)
        if file:
            line_edit.setText(file)

    def choose_output_file(self, line_edit: QLineEdit, file_filter: str) -> None:
        file, _ = QFileDialog.getSaveFileName(self, 'Select output file', line_edit.text(), file_filter)
        if file:
            line_edit.setText(file)

    def run_simple_task(self) -> None:
        paths = selected_paths(self.simple_inputs)
        if not paths:
            self.show_warning('Select at least one screenshot or folder.')
            return

        out_dir = optional_path(self.simple_out_dir)
        if out_dir is None:
            self.show_warning('Select an output folder.')
            return

        config = SimpleConfig(paths=paths, out_dir=out_dir)
        self.start_task(
            lambda progress: run_simple(config, progress=progress),
            self.simple_run_button,
            self.handle_simple_result,
        )

    def run_crop_task(self) -> None:
        paths = selected_paths(self.crop_inputs)
        if not paths:
            self.show_warning('Select at least one screenshot or folder.')
            return

        config = CropConfig(
            paths=paths,
            out_dir=optional_path(self.crop_out_dir),
            overwrite=self.crop_overwrite.isChecked(),
            device=self.crop_device.currentText().strip() or 'auto',
            table_crop=self.crop_table_crop.text().strip(),
            pool_crop=self.crop_pool_crop.text().strip(),
            det_model_dir=optional_path(self.crop_det_model_dir),
            rec_model_dir=optional_path(self.crop_rec_model_dir),
        )
        self.start_task(
            lambda progress: run_crop(config, progress=progress),
            self.crop_run_button,
            self.handle_crop_result,
        )

    def run_recognize_task(self) -> None:
        paths = selected_paths(self.recognize_inputs)
        if not paths:
            self.show_warning('Select at least one table image or folder.')
            return

        pool_type = self.recognize_pool_type.currentText().strip() or None
        config = RecognizeConfig(
            paths=paths,
            out_dir=optional_path(self.recognize_out_dir),
            overwrite=self.recognize_overwrite.isChecked(),
            pool_type=pool_type,
            debug_dir=optional_path(self.recognize_debug_dir),
            device=self.recognize_device.currentText().strip() or 'auto',
            row_count=self.recognize_row_count.value(),
            row_top=self.recognize_row_top.value(),
            row_bottom=self.recognize_row_bottom.value(),
            min_score=self.recognize_min_score.value(),
            known_items_path=optional_path(self.recognize_known_items),
            det_model_dir=optional_path(self.recognize_det_model_dir),
            rec_model_dir=optional_path(self.recognize_rec_model_dir),
        )
        self.start_task(
            lambda progress: run_recognize(config, progress=progress),
            self.recognize_run_button,
            self.handle_recognize_result,
        )

    def run_export_task(self) -> None:
        paths = selected_paths(self.export_inputs)
        if not paths:
            self.show_warning('Select at least one JSON file or folder.')
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
        )

    def start_task(
        self,
        task: WorkerTask,
        button: QPushButton,
        on_result: Callable[[object], None],
    ) -> None:
        if self._thread is not None:
            self.show_warning('A task is already running.')
            return

        self.clear_log()
        self.set_outputs([])
        button.setEnabled(False)
        self.statusBar().showMessage('Running...')

        thread = QThread(self)
        worker = WorkflowWorker(task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.append_log)
        worker.result.connect(on_result)
        worker.error.connect(self.handle_worker_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self.finish_task(button))

        self._thread = thread
        self._worker = worker
        thread.start()

    def finish_task(self, button: QPushButton) -> None:
        button.setEnabled(True)
        self._thread = None
        self._worker = None
        self.statusBar().showMessage('Ready', 3000)

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

    def handle_worker_error(self, message: str) -> None:
        self.append_log(message)
        QMessageBox.critical(self, 'Task failed', message)

    def show_warning(self, message: str) -> None:
        QMessageBox.warning(self, 'NTE Dice Analysis', message)

    def clear_log(self) -> None:
        self.log_edit.clear()

    def append_log(self, message: str) -> None:
        self.log_edit.appendPlainText(message)

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
            self.show_warning('Select an output first.')
            return

        path = Path(item.data(Qt.ItemDataRole.UserRole))
        if not path.exists():
            self.show_warning(f'Output does not exist: {path}')
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def device_combo() -> QComboBox:
    combo = QComboBox()
    combo.setEditable(True)
    combo.addItems(['auto', 'cpu', 'gpu:0'])
    return combo


def double_spin(value: float, minimum: float, maximum: float, step: float, decimals: int) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setSingleStep(step)
    spin.setDecimals(decimals)
    spin.setValue(value)
    return spin


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


def main(argv: list[str] | None = None) -> int:
    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
