import math
from html import escape
from dataclasses import dataclass

from PySide6.QtGui import QPen
from PySide6.QtGui import QFont
from PySide6.QtGui import QBrush
from PySide6.QtGui import QColor
from PySide6.QtGui import QPainter
from PySide6.QtGui import QShowEvent
from PySide6.QtGui import QPaintEvent
from PySide6.QtGui import QFontMetrics
from PySide6.QtGui import QResizeEvent
from PySide6.QtCore import Qt
from PySide6.QtCore import QRect
from PySide6.QtCore import QRectF
from PySide6.QtCore import QTimer
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QFrame
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QWidget
from PySide6.QtWidgets import QGridLayout
from PySide6.QtWidgets import QHBoxLayout
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QVBoxLayout

from .widgets import clear_layout_widgets
from ..layouts import is_arc_pool_type
from ..summary import BLUE_COLOR
from ..summary import GREEN_COLOR
from ..summary import MUTED_COLOR
from ..summary import LEADER_COLOR
from ..summary import RarityStat
from ..summary import PoolSummary
from ..summary import history_color
from ..summary import format_average
from ..gui_strings import GUI_TEXT

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
