import os
import sys
import math
import signal
import logging
from html import escape
from types import FrameType
from types import TracebackType
from shutil import SameFileError
from shutil import copy2
from pathlib import Path
from datetime import datetime
from importlib import import_module
from dataclasses import dataclass
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from importlib.resources import files

from PySide6.QtGui import QPen
from PySide6.QtGui import QFont
from PySide6.QtGui import QIcon
from PySide6.QtGui import QBrush
from PySide6.QtGui import QColor
from PySide6.QtGui import QImage
from PySide6.QtGui import QPixmap
from PySide6.QtGui import QPainter
from PySide6.QtGui import QShowEvent
from PySide6.QtGui import QPaintEvent
from PySide6.QtGui import QFontMetrics
from PySide6.QtGui import QResizeEvent
from PySide6.QtGui import QFontDatabase
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import Qt
from PySide6.QtCore import QUrl
from PySide6.QtCore import Slot
from PySide6.QtCore import QRect
from PySide6.QtCore import QRectF
from PySide6.QtCore import QTimer
from PySide6.QtCore import Signal
from PySide6.QtCore import QObject
from PySide6.QtCore import QPointF
from PySide6.QtCore import QThread
from PySide6.QtCore import QModelIndex
from PySide6.QtCore import QStandardPaths
from PySide6.QtCore import QAbstractTableModel
from PySide6.QtCore import QPersistentModelIndex
from PySide6.QtWidgets import QFrame
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QStyle
from PySide6.QtWidgets import QDialog
from PySide6.QtWidgets import QLayout
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
from PySide6.QtWidgets import QGridLayout
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QHeaderView
from PySide6.QtWidgets import QListWidget
from PySide6.QtWidgets import QMainWindow
from PySide6.QtWidgets import QMessageBox
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QScrollArea
from PySide6.QtWidgets import QSizePolicy
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
from .layouts import is_arc_pool_type
from .summary import BLUE_COLOR
from .summary import GREEN_COLOR
from .summary import MUTED_COLOR
from .summary import LEADER_COLOR
from .summary import RarityStat
from .summary import PoolSummary
from .summary import history_color
from .summary import format_average
from .summary import summarize_records
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
from .gui_workflow import ExistingAnalysisResult
from .gui_workflow import run_crop
from .gui_workflow import run_export
from .gui_workflow import run_simple
from .gui_workflow import run_recognize
from .gui_workflow import load_existing_analysis

type WorkerTask = Callable[[Callable[[ProgressEvent], None]], object]
type Importer = Callable[[str], object]
type Emitter = Callable[[str], None]
type OcrFactory = Callable[[PipelineOptions], object]
type UrlOpener = Callable[[QUrl], bool]

LOG_FILE_NAME = 'nte-dice-analysis.log'
LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'
APP_ICON_RESOURCE = 'assets/app_icon.png'
MAIN_WINDOW_INITIAL_WIDTH = 1440
MAIN_WINDOW_INITIAL_HEIGHT = 1040
DASHBOARD_CARD_TARGET_WIDTH = 420
DASHBOARD_CARD_MAX_WIDTH = 560
DASHBOARD_CARD_SPACING = 20
PIE_LABEL_EDGE_PADDING = 8
PIE_LABEL_FONT_POINT_SIZE = 10
PIE_LABEL_GAP = 16
PIE_LABEL_LINE_SPACING = 2
PIE_LABEL_VERTICAL_OFFSET = 28
PIE_LABEL_MIN_HORIZONTAL_MARGIN = 60
DASHBOARD_STYLESHEET = """
    #DashboardContainer {
        background-color: #f1f5f9;
    }
    #ActionBar {
        background-color: white;
        border-radius: 12px;
    }
    QLabel#SelectedInputLabel {
        background-color: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        color: #475569;
        padding: 9px 12px;
    }
    QPushButton#PrimaryButton,
    QPushButton#SecondaryButton {
        padding: 10px 24px;
        border-radius: 8px;
        font-weight: bold;
    }
    QPushButton#PrimaryButton {
        background-color: #4f46e5;
        color: white;
        border: none;
    }
    QPushButton#PrimaryButton:hover {
        background-color: #4338ca;
    }
    QPushButton#SecondaryButton {
        background-color: white;
        color: #4f46e5;
        border: 1px solid #e2e8f0;
    }
    QPushButton#SecondaryButton:hover {
        background-color: #f8fafc;
    }
"""
SELF_TEST_IMPORTS = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PIL.Image',
    'openpyxl',
    'paddleocr',
]

logger = logging.getLogger(__name__)


@dataclass
class PieChartLabelRow:
    stat: RarityStat
    lines: tuple[str, str]
    edge_x: float
    edge_y: float
    label_y: float
    side: str


def rgb_to_qcolor(rgb: tuple[int, int, int]) -> QColor:
    return QColor(*rgb)


class PieChartWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rarity_stats: list[RarityStat] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(300, 280)

    def set_stats(self, stats: list[RarityStat]) -> None:
        self.rarity_stats = stats
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        total = sum(stat.count for stat in self.rarity_stats)
        rect = self.rect()
        label_font = self.label_font()
        label_metrics = QFontMetrics(label_font)
        pie_rect = self.pie_rect_for(rect, total, label_metrics)

        if total == 0:
            painter.setPen(QPen(rgb_to_qcolor(LEADER_COLOR), 2))
            painter.drawEllipse(pie_rect)
            painter.setPen(rgb_to_qcolor(MUTED_COLOR))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, GUI_TEXT.no_data)
            return

        start_angle = 90 * 16  # Qt uses 1/16th of a degree, 0 is at 3 o'clock. 90 is 12 o'clock.
        # png.py uses -90 as start (12 o'clock), and positive is clockwise.
        # QPainter.drawPie: positive is counter-clockwise.
        # To match png.py: start at 90 (12 o'clock) and use negative spans.

        for stat in self.rarity_stats:
            if stat.count == 0:
                continue
            span_angle = -int(360 * 16 * stat.count / total)
            painter.setBrush(QBrush(rgb_to_qcolor(stat.color)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPie(pie_rect, start_angle, span_angle)

            start_angle += span_angle

        # Draw white border between slices
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawEllipse(pie_rect)

        # Draw labels in side lanes so edge labels never clamp back over the pie.
        self.draw_labels(painter, pie_rect, total, label_font)

    def label_font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSize(PIE_LABEL_FONT_POINT_SIZE)
        return font

    def pie_rect_for(self, rect: QRect, total: int, label_metrics: QFontMetrics) -> QRectF:
        margin_h = PIE_LABEL_MIN_HORIZONTAL_MARGIN
        margin_v = min(40, max(28, rect.height() // 9))
        if total > 0:
            label_width = max(
                (
                    self.label_width(self.label_lines(stat), label_metrics)
                    for stat in self.rarity_stats
                    if stat.count > 0
                ),
                default=0,
            )
            margin_h = max(margin_h, label_width + PIE_LABEL_GAP + PIE_LABEL_EDGE_PADDING)

        available_width = max(0, rect.width() - (margin_h * 2))
        available_height = max(0, rect.height() - (margin_v * 2))
        size = min(available_width, available_height)
        return QRectF((rect.width() - size) / 2, (rect.height() - size) / 2, size, size)

    @staticmethod
    def label_lines(stat: RarityStat) -> tuple[str, str]:
        return stat.label, f'{stat.percent:.2f}%'

    @staticmethod
    def label_width(lines: tuple[str, str], metrics: QFontMetrics) -> int:
        return max(metrics.horizontalAdvance(line) for line in lines)

    def label_rows(self, pie_rect: QRectF, total: int) -> list[PieChartLabelRow]:
        center = pie_rect.center()
        radius = pie_rect.width() / 2
        current_angle = 90.0
        rows: list[PieChartLabelRow] = []

        for stat in self.rarity_stats:
            if stat.count == 0:
                continue

            angle_span = 360.0 * stat.count / total
            middle_angle = current_angle - angle_span / 2
            middle_rad = math.radians(middle_angle)

            edge_x = center.x() + math.cos(middle_rad) * radius
            edge_y = center.y() - math.sin(middle_rad) * radius

            label_y = center.y() - math.sin(middle_rad) * (radius + PIE_LABEL_VERTICAL_OFFSET)
            rows.append(
                PieChartLabelRow(
                    stat=stat,
                    lines=self.label_lines(stat),
                    edge_x=edge_x,
                    edge_y=edge_y,
                    label_y=label_y,
                    side='right' if math.cos(middle_rad) >= 0 else 'left',
                ),
            )

            current_angle -= angle_span

        return rows

    @staticmethod
    def adjusted_label_rows(
        rows: list[PieChartLabelRow],
        min_y: float,
        max_y: float,
        min_gap: int,
    ) -> list[PieChartLabelRow]:
        adjusted: list[PieChartLabelRow] = []
        for side in ('left', 'right'):
            side_rows = [
                PieChartLabelRow(
                    stat=row.stat,
                    lines=row.lines,
                    edge_x=row.edge_x,
                    edge_y=row.edge_y,
                    label_y=row.label_y,
                    side=row.side,
                )
                for row in rows
                if row.side == side
            ]
            side_rows.sort(key=lambda row: row.label_y)
            previous_y: float | None = None
            for row in side_rows:
                label_y = max(min_y, row.label_y)
                if previous_y is not None and label_y - previous_y < min_gap:
                    label_y = previous_y + min_gap
                row.label_y = label_y
                previous_y = label_y

            if side_rows and side_rows[-1].label_y > max_y:
                offset = side_rows[-1].label_y - max_y
                for row in side_rows:
                    row.label_y = max(min_y, row.label_y - offset)
            adjusted.extend(side_rows)
        return adjusted

    @staticmethod
    def label_text_x(row: PieChartLabelRow, pie_rect: QRectF, text_width: int) -> float:
        if row.side == 'right':
            return pie_rect.right() + PIE_LABEL_GAP
        return pie_rect.left() - PIE_LABEL_GAP - text_width

    def draw_labels(self, painter: QPainter, pie_rect: QRectF, total: int, font: QFont) -> None:
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text_height = (metrics.height() * 2) + PIE_LABEL_LINE_SPACING
        min_y = max(
            PIE_LABEL_EDGE_PADDING + text_height / 2,
            pie_rect.top() - PIE_LABEL_VERTICAL_OFFSET,
        )
        max_y = min(
            self.rect().height() - PIE_LABEL_EDGE_PADDING - text_height / 2,
            pie_rect.bottom() + PIE_LABEL_VERTICAL_OFFSET,
        )
        rows = self.adjusted_label_rows(
            self.label_rows(pie_rect, total),
            min_y,
            max_y,
            text_height + 3,
        )

        for row in rows:
            text_width = self.label_width(row.lines, metrics)
            label_x = self.label_text_x(row, pie_rect, text_width)
            anchor_x = label_x if row.side == 'right' else label_x + text_width

            painter.setPen(QPen(rgb_to_qcolor(LEADER_COLOR), 1.2))
            painter.drawLine(QPointF(row.edge_x, row.edge_y), QPointF(anchor_x, row.label_y))

            painter.setPen(rgb_to_qcolor(row.stat.color))
            first_line_y = row.label_y - text_height / 2 + metrics.ascent()
            for line_index, line in enumerate(row.lines):
                line_width = metrics.horizontalAdvance(line)
                line_x = label_x if row.side == 'right' else label_x + text_width - line_width
                line_y = first_line_y + line_index * (metrics.height() + PIE_LABEL_LINE_SPACING)
                painter.drawText(QPointF(line_x, line_y), line)


class AnalysisCardWidget(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName('AnalysisCard')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMaximumWidth(DASHBOARD_CARD_MAX_WIDTH)
        self.setStyleSheet("""
            #AnalysisCard {
                background-color: white;
                border-radius: 15px;
            }
            QLabel {
                color: #334155;
                font-size: 13px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = self.font()
        title_font.setPointSize(14)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        layout.addWidget(self.title_label)

        # Legend
        self.legend_layout = QHBoxLayout()
        self.legend_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(self.legend_layout)

        self.pie_chart = PieChartWidget()
        layout.addWidget(self.pie_chart, 1)  # Give chart stretch priority

        self.date_label = QLabel()
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_label.setStyleSheet('color: #64748b; font-size: 11px;')
        self.date_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.date_label)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary_label)

        self.history_label = QLabel()
        self.history_label.setWordWrap(True)
        self.history_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.history_label)

        self.average_label = QLabel()
        self.average_label.setWordWrap(True)
        self.average_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.average_label)

        layout.addStretch(0)

    def set_summary(self, summary: PoolSummary) -> None:
        self.title_label.setText(summary.pool_type)
        self.pie_chart.set_stats(summary.rarity_stats)

        # Update Legend
        clear_layout_widgets(self.legend_layout)

        for stat in summary.rarity_stats:
            dot = QFrame()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(f'background-color: {rgb_to_qcolor(stat.color).name()}; border-radius: 6px;')
            label = QLabel(stat.label)
            self.legend_layout.addWidget(dot)
            self.legend_layout.addWidget(label)
            self.legend_layout.addSpacing(15)

        self.date_label.setText(dashboard_date_text(summary))

        self.summary_label.setText(dashboard_summary_html(summary))
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)

        self.history_label.setText(dashboard_history_html(summary))
        self.history_label.setTextFormat(Qt.TextFormat.RichText)

        self.average_label.setText(dashboard_average_html(summary))
        self.average_label.setTextFormat(Qt.TextFormat.RichText)


def dashboard_grid_column_count(card_count: int, available_width: int) -> int:
    if card_count <= 0:
        return 0

    column_width = DASHBOARD_CARD_TARGET_WIDTH + DASHBOARD_CARD_SPACING
    max_columns = max(1, (available_width + DASHBOARD_CARD_SPACING) // column_width)
    return min(card_count, max_columns)


class DashboardResultsGridWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('ResultsGrid')
        self.setStyleSheet('background-color: transparent;')
        self._cards: list[AnalysisCardWidget] = []
        self._slots: list[QWidget] = []
        self._column_count = 0
        self._virtual_column_count = 0

        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(DASHBOARD_CARD_SPACING)
        self.grid_layout.setContentsMargins(0, 10, 0, 10)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

    @property
    def card_count(self) -> int:
        return len(self._cards)

    @property
    def column_count(self) -> int:
        return self._column_count

    def set_summaries(self, summaries: list[PoolSummary]) -> None:
        self.clear_cards()
        for summary in summaries:
            slot = QWidget(self)
            slot.setStyleSheet('background-color: transparent;')
            slot_layout = QHBoxLayout(slot)
            slot_layout.setContentsMargins(0, 0, 0, 0)
            slot_layout.setSpacing(0)
            slot_layout.addStretch(1)

            card = AnalysisCardWidget(slot)
            card.set_summary(summary)
            slot_layout.addWidget(card, 100)
            slot_layout.addStretch(1)

            self._cards.append(card)
            self._slots.append(slot)
        self._relayout_cards(force=True)

    def clear_cards(self) -> None:
        self._take_grid_items()
        for slot in self._slots:
            slot.hide()
            slot.setParent(None)
            slot.deleteLater()
        self._cards = []
        self._slots = []
        self._column_count = 0

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._relayout_cards()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self._relayout_cards(force=True))

    def _relayout_cards(self, *, force: bool = False) -> None:
        column_count = dashboard_grid_column_count(len(self._cards), self.width())
        if not force and column_count == self._column_count:
            return

        self._take_grid_items()
        self._column_count = column_count
        if column_count == 0:
            return

        virtual_column_count = column_count * 2
        for column in range(max(self._virtual_column_count, virtual_column_count)):
            stretch = 1 if column < virtual_column_count else 0
            self.grid_layout.setColumnStretch(column, stretch)
        self._virtual_column_count = virtual_column_count

        for row_index, row_start in enumerate(range(0, len(self._slots), column_count)):
            row_slots = self._slots[row_start : row_start + column_count]
            column_offset = column_count - len(row_slots)
            for slot_index, slot in enumerate(row_slots):
                column = column_offset + (slot_index * 2)
                self.grid_layout.addWidget(slot, row_index, column, 1, 2)

    def _take_grid_items(self) -> None:
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)


def color_qss(rgb: tuple[int, int, int]) -> str:
    return rgb_to_qcolor(rgb).name()


def dashboard_date_text(summary: PoolSummary) -> str:
    if summary.date_start is None or summary.date_end is None:
        return GUI_TEXT.no_records
    return f'{summary.date_start} - {summary.date_end}'


def dashboard_summary_html(summary: PoolSummary) -> str:
    target_name = GUI_TEXT.dashboard_character_target
    if is_arc_pool_type(summary.pool_type):
        target_name = GUI_TEXT.dashboard_arc_target
    return GUI_TEXT.dashboard_summary.format(
        total_color=color_qss(BLUE_COLOR),
        total_pulls=summary.total_pulls,
        pity_color=color_qss(GREEN_COLOR),
        current_pity=summary.current_pity,
        target_name=target_name,
    )


def dashboard_history_html(summary: PoolSummary) -> str:
    history_text = ' '.join(
        [
            (f'<span style="color: {history_color_qss(item.name)};">{escape(item.name)}[{item.pulls}]</span>')
            for item in summary.s_history
        ]
    )
    return GUI_TEXT.dashboard_history.format(history=history_text or GUI_TEXT.none)


def dashboard_average_html(summary: PoolSummary) -> str:
    color = color_qss(GREEN_COLOR if summary.average_s_pulls is not None else MUTED_COLOR)
    target_name = GUI_TEXT.dashboard_character_target
    if is_arc_pool_type(summary.pool_type):
        target_name = GUI_TEXT.dashboard_arc_target
    return GUI_TEXT.dashboard_average.format(
        target_name=target_name,
        color=color,
        average=format_average(summary.average_s_pulls),
    )


def history_color_qss(name: str) -> str:
    rgb = history_color(name)
    return rgb_to_qcolor(rgb).name()


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
            self.btn_analyze,
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
        self.update_analysis_cards(export_result.records)
        if export_result.png_path is not None:
            self._latest_png_path = export_result.png_path
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


def apply_cjk_application_font(app: QApplication) -> None:
    font = cjk_application_font(app.font())
    if font is not None:
        app.setFont(font)
        logger.info('Using GUI font family: %s', font.family())


def app_icon_bytes() -> bytes:
    return files('nte_dice_analysis').joinpath(APP_ICON_RESOURCE).read_bytes()


def app_icon() -> QIcon:
    pixmap = QPixmap()
    if not pixmap.loadFromData(app_icon_bytes()):
        logger.warning('Failed to load GUI icon resource: %s', APP_ICON_RESOURCE)
    return QIcon(pixmap)


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
        exc_traceback: TracebackType | None,
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


def install_ctrl_c_handler(app: QApplication) -> QTimer:
    previous_handler = signal.getsignal(signal.SIGINT)

    def quit_app(_signum: int, _frame: FrameType | None) -> None:
        app.quit()

    def restore_previous_handler() -> None:
        signal.signal(signal.SIGINT, previous_handler)

    signal.signal(signal.SIGINT, quit_app)
    app.aboutToQuit.connect(restore_previous_handler)

    timer = QTimer(app)
    timer.setInterval(200)
    timer.timeout.connect(lambda: None)
    timer.start()
    return timer


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
    ctrl_c_timer = install_ctrl_c_handler(app)
    app.setWindowIcon(app_icon())
    apply_cjk_application_font(app)
    window = MainWindow(log_path=log_path)
    window.show()
    exit_code = app.exec()
    ctrl_c_timer.stop()
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
