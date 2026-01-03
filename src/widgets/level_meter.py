"""Multi-channel level meter widget"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QLinearGradient
from typing import List


class ChannelMeter(QWidget):
    """Single channel level meter"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(20)
        self.setMinimumWidth(150)

        self._level = -60.0
        self._peak = -60.0

    def set_level(self, db: float):
        """Set level in dB"""
        self._level = max(-60.0, min(0.0, db))
        if self._level > self._peak:
            self._peak = self._level
        self.update()

    def decay_peak(self, amount: float = 0.5):
        """Decay peak indicator"""
        self._peak = max(self._level, self._peak - amount)

    def _db_to_x(self, db: float, width: float) -> float:
        """Convert dB to x position"""
        normalized = (db + 60.0) / 60.0
        return normalized * width

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background
        painter.fillRect(0, 0, w, h, QColor(25, 25, 25))

        # Gradient
        gradient = QLinearGradient(0, 0, w, 0)
        gradient.setColorAt(0.0, QColor(0, 150, 0))
        gradient.setColorAt(0.6, QColor(0, 200, 0))
        gradient.setColorAt(0.8, QColor(200, 200, 0))
        gradient.setColorAt(1.0, QColor(220, 50, 0))

        # Level bar
        level_width = self._db_to_x(self._level, w)
        painter.fillRect(0, 2, int(level_width), h - 4, gradient)

        # Peak indicator
        painter.setPen(QColor(255, 255, 255))
        peak_x = int(self._db_to_x(self._peak, w))
        painter.drawLine(peak_x, 0, peak_x, h)


class LevelMeter(QWidget):
    """Multi-channel level meter with labels"""

    def __init__(self, channels: int = 2, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(60 if channels <= 2 else 120)

        self._channels = channels
        self._meters: List[ChannelMeter] = []
        self._labels = ["Main L", "Main R", "Cue L", "Cue R"]

        self._setup_ui()

        # Peak decay timer
        self._decay_timer = QTimer(self)
        self._decay_timer.timeout.connect(self._decay_peaks)
        self._decay_timer.start(50)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        for i in range(self._channels):
            row = QHBoxLayout()
            row.setSpacing(8)

            # Label
            label = QLabel(self._labels[i] if i < len(self._labels) else f"Ch {i+1}")
            label.setFixedWidth(50)
            label.setStyleSheet("color: #888; font-size: 11px;")
            row.addWidget(label)

            # Meter
            meter = ChannelMeter()
            self._meters.append(meter)
            row.addWidget(meter, 1)

            layout.addLayout(row)

    def set_channels(self, channels: int):
        """Change number of displayed channels"""
        if channels == self._channels:
            return

        # Clear existing
        while self.layout().count():
            item = self.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._meters = []
        self._channels = channels
        self._setup_ui()

        self.setMinimumHeight(30 * channels)

    def set_levels(self, levels: List[float]):
        """Set levels for all channels"""
        for i, level in enumerate(levels):
            if i < len(self._meters):
                self._meters[i].set_level(level)

    def _decay_peaks(self):
        """Decay peak indicators"""
        for meter in self._meters:
            meter.decay_peak()
            meter.update()


class CompactLevelMeter(QWidget):
    """Compact stereo meter (no labels)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(30)
        self.setMinimumWidth(200)

        self._left_level = -60.0
        self._right_level = -60.0
        self._peak_left = -60.0
        self._peak_right = -60.0

        self._decay_timer = QTimer(self)
        self._decay_timer.timeout.connect(self._decay_peaks)
        self._decay_timer.start(50)

    def set_levels(self, left_db: float, right_db: float):
        """Set current levels in dB"""
        self._left_level = max(-60.0, min(0.0, left_db))
        self._right_level = max(-60.0, min(0.0, right_db))

        if self._left_level > self._peak_left:
            self._peak_left = self._left_level
        if self._right_level > self._peak_right:
            self._peak_right = self._right_level

        self.update()

    def _decay_peaks(self):
        """Decay peak indicators"""
        self._peak_left = max(self._left_level, self._peak_left - 0.5)
        self._peak_right = max(self._right_level, self._peak_right - 0.5)
        self.update()

    def _db_to_x(self, db: float, width: float) -> float:
        normalized = (db + 60.0) / 60.0
        return normalized * width

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        bar_height = (h - 4) // 2

        painter.fillRect(0, 0, w, h, QColor(25, 25, 25))

        gradient = QLinearGradient(0, 0, w, 0)
        gradient.setColorAt(0.0, QColor(0, 150, 0))
        gradient.setColorAt(0.7, QColor(180, 180, 0))
        gradient.setColorAt(1.0, QColor(220, 0, 0))

        # Left channel
        left_width = self._db_to_x(self._left_level, w)
        painter.fillRect(0, 0, int(left_width), bar_height, gradient)

        # Right channel
        right_width = self._db_to_x(self._right_level, w)
        painter.fillRect(0, bar_height + 4, int(right_width), bar_height, gradient)

        # Peak indicators
        painter.setPen(QColor(255, 255, 255))
        peak_left_x = int(self._db_to_x(self._peak_left, w))
        peak_right_x = int(self._db_to_x(self._peak_right, w))
        painter.drawLine(peak_left_x, 0, peak_left_x, bar_height)
        painter.drawLine(peak_right_x, bar_height + 4, peak_right_x, h)
