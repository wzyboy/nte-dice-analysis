import logging
from shutil import SameFileError
from shutil import copy2
from pathlib import Path
from datetime import datetime
from collections.abc import Callable

from PySide6.QtGui import QColor
from PySide6.QtGui import QImage
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import Qt
from PySide6.QtCore import QUrl
from PySide6.QtCore import Slot
from PySide6.QtCore import Signal
from PySide6.QtCore import QObject
from PySide6.QtCore import QModelIndex
from PySide6.QtCore import QStandardPaths
from PySide6.QtCore import QAbstractTableModel
from PySide6.QtCore import QPersistentModelIndex
from PySide6.QtWidgets import QLayout
from PySide6.QtWidgets import QLineEdit
from PySide6.QtWidgets import QListWidget
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QProgressBar
from PySide6.QtWidgets import QDoubleSpinBox

from ..models import Record
from ..constants import A_CLASS
from ..constants import B_CLASS
from ..constants import S_CLASS
from ..constants import OUTPUT_FIELDS
from ..gui_strings import GUI_TEXT
from ..gui_strings import OUTPUT_FIELD_LABELS
from ..gui_workflow import ProgressEvent

type WorkerTask = Callable[[Callable[[ProgressEvent], None]], object]
type UrlOpener = Callable[[QUrl], bool]

logger = logging.getLogger(__name__)


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

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(OUTPUT_FIELDS)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
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

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
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


def double_spin(value: float, minimum: float, maximum: float, step: float, decimals: int) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setSingleStep(step)
    spin.setDecimals(decimals)
    spin.setValue(value)
    return spin


def clear_layout_widgets(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue

        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def progress_bar(*, text_visible: bool, styled: bool) -> QProgressBar:
    bar = QProgressBar()
    bar.setFixedHeight(20 if text_visible else 6)
    bar.setTextVisible(text_visible)
    bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    if styled:
        bar.setStyleSheet("""
            QProgressBar {
                background-color: #e2e8f0;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #4f46e5;
                border-radius: 3px;
            }
        """)
    reset_progress_bar(bar)
    return bar


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


def copy_image_to_clipboard(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False

    image = QImage(str(path))
    if image.isNull():
        return False

    QApplication.clipboard().setImage(image)
    return True


def copy_existing_file(source: Path, destination: Path) -> bool:
    if not source.exists() or not source.is_file():
        return False

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        copy2(source, destination)
    except SameFileError:
        return True
    except OSError:
        logger.exception('Failed to copy %s to %s', source, destination)
        return False

    return True


def default_export_dialog_path(filename: str, now: datetime | None = None) -> Path:
    timestamp = now or datetime.now()
    suffix = Path(filename).suffix
    output_filename = f'NTE_Dice_Analysis_{timestamp:%Y-%m-%d_%H-%M-%S}{suffix}'
    return Path.home() / 'Desktop' / output_filename


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
