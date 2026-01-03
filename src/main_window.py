"""Main application window - Redesigned UI"""

import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QLineEdit,
    QFileDialog, QFrame, QMessageBox, QCheckBox,
    QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QFont, QPainter, QColor, QLinearGradient, QPalette

from .dialogs.track_selection import TrackSelectionDialog
from .dialogs.capture_progress import CaptureProgressDialog
from .core.session import Session
from .core.midi_handler import MIDIHandler
from .core.audio_handler import AudioHandler


# ============================================================================
# Custom Widgets
# ============================================================================

class StatusDot(QWidget):
    """Small status indicator dot"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self._connected = False
        self._color = QColor("#4ade80")  # Green

    def set_connected(self, connected: bool):
        self._connected = connected
        self._color = QColor("#4ade80") if connected else QColor("#ef4444")
        self.update()

    def set_warning(self):
        self._color = QColor("#f59e0b")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 8, 8)


class MeterWithDB(QWidget):
    """Level meter with dB readout"""

    def __init__(self, label: str = "L", parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self._label = label
        self._level = -60.0
        self._peak = -60.0

        # Peak decay timer
        self._decay_timer = QTimer(self)
        self._decay_timer.timeout.connect(self._decay_peak)
        self._decay_timer.start(50)

    def set_level(self, db: float):
        self._level = max(-60.0, min(0.0, db))
        if self._level > self._peak:
            self._peak = self._level
        self.update()

    def _decay_peak(self):
        self._peak = max(self._level, self._peak - 0.5)
        self.update()

    def _db_to_width(self, db: float, max_width: float) -> float:
        normalized = (db + 60.0) / 60.0
        return normalized * max_width

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Layout: [Label 20px] [Meter flex] [dB 50px]
        label_width = 20
        db_width = 50
        meter_x = label_width + 8
        meter_width = w - label_width - db_width - 16
        meter_height = 10
        meter_y = (h - meter_height) // 2

        # Label
        painter.setPen(QColor("#505050"))
        painter.setFont(QFont("IBM Plex Mono", 10))
        painter.drawText(0, 0, label_width, h, Qt.AlignmentFlag.AlignVCenter, self._label)

        # Meter background
        painter.fillRect(meter_x, meter_y, meter_width, meter_height, QColor("#0d0d0d"))

        # Meter gradient fill
        level_width = int(self._db_to_width(self._level, meter_width))
        if level_width > 0:
            gradient = QLinearGradient(meter_x, 0, meter_x + meter_width, 0)
            gradient.setColorAt(0.0, QColor("#22543d"))
            gradient.setColorAt(0.7, QColor("#4ade80"))
            gradient.setColorAt(0.9, QColor("#f59e0b"))
            gradient.setColorAt(1.0, QColor("#ef4444"))
            painter.fillRect(meter_x, meter_y, level_width, meter_height, gradient)

        # Peak indicator
        peak_x = meter_x + int(self._db_to_width(self._peak, meter_width))
        painter.setPen(QColor("#ffffff"))
        painter.drawLine(peak_x, meter_y, peak_x, meter_y + meter_height)

        # dB value
        db_text = f"{self._level:.0f} dB" if self._level > -60 else "-∞ dB"
        painter.setPen(QColor("#505050"))
        painter.drawText(w - db_width, 0, db_width, h,
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, db_text)


class RecordButton(QPushButton):
    """Circular record button with pulse animation"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(72, 72)
        self._recording = False
        self._pulse_opacity = 0.0

        # Pulse animation
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._update_pulse)
        self._pulse_phase = 0.0

        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
            }
        """)

    def set_recording(self, recording: bool):
        self._recording = recording
        if recording:
            self._pulse_timer.start(30)
        else:
            self._pulse_timer.stop()
            self._pulse_opacity = 0.0
        self.update()

    def _update_pulse(self):
        import math
        self._pulse_phase += 0.1
        self._pulse_opacity = (math.sin(self._pulse_phase) + 1) / 2 * 0.4
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx, cy = w // 2, h // 2

        # Pulse glow when recording
        if self._recording and self._pulse_opacity > 0:
            glow_color = QColor(239, 68, 68, int(self._pulse_opacity * 255))
            painter.setBrush(glow_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(cx - 40, cy - 40, 80, 80)

        # Outer ring
        painter.setPen(QColor("#ef4444"))
        painter.setBrush(QColor("#0d0d0d") if not self._recording else QColor("#ef4444"))
        from PyQt6.QtGui import QPen
        pen = QPen(QColor("#ef4444"), 3)
        painter.setPen(pen)
        painter.drawEllipse(cx - 33, cy - 33, 66, 66)

        # Inner icon
        if self._recording:
            # Stop square
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(cx - 10, cy - 10, 20, 20, 3, 3)
        else:
            # Record circle
            painter.setBrush(QColor("#ef4444"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(cx - 12, cy - 12, 24, 24)


class CollapsiblePanel(QFrame):
    """Collapsible configuration panel"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._expanded = False
        self._title = title

        self.setStyleSheet("""
            CollapsiblePanel {
                background: #1a1a1a;
                border: 1px solid #333;
                border-radius: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header (always visible)
        self._header = QPushButton()
        self._header.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                padding: 12px 16px;
                text-align: left;
                color: #808080;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #252525;
            }
        """)
        self._header.clicked.connect(self.toggle)
        self._update_header()
        layout.addWidget(self._header)

        # Content area
        self._content = QWidget()
        self._content.setVisible(False)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 0, 16, 16)
        layout.addWidget(self._content)

    def _update_header(self):
        arrow = "▼" if self._expanded else "▶"
        self._header.setText(f"  ⚙  {self._title}  {arrow}")

    def toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._update_header()

    def content_layout(self):
        return self._content_layout


# ============================================================================
# Main Window
# ============================================================================

class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OT Stem Capture")
        self.setFixedSize(520, 580)

        # Session state
        self.session: Session = None
        self.session_folder = Path.home() / "Music" / "OT Sessions"
        self.recording = False
        self.record_start_time = 0

        # Handlers for device discovery and monitoring
        self._midi_handler = MIDIHandler()
        self._audio_handler = AudioHandler()
        self._monitoring = False

        self._setup_ui()
        self._setup_timers()
        self._refresh_devices()
        self._update_status("Ready to record")

    def _setup_ui(self):
        """Build the UI"""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # ===== Header with status =====
        header = QHBoxLayout()

        title = QLabel("OT STEM CAPTURE")
        title.setFont(QFont("IBM Plex Mono", 12, QFont.Weight.Bold))
        title.setStyleSheet("letter-spacing: 2px;")
        header.addWidget(title)

        header.addStretch()

        # Status indicators
        self.midi_status_dot = StatusDot()
        self.midi_status_label = QLabel("MIDI")
        self.midi_status_label.setStyleSheet("color: #808080; font-size: 11px;")
        header.addWidget(self.midi_status_dot)
        header.addWidget(self.midi_status_label)

        header.addSpacing(12)

        self.audio_status_dot = StatusDot()
        self.audio_status_label = QLabel("Audio")
        self.audio_status_label.setStyleSheet("color: #808080; font-size: 11px;")
        header.addWidget(self.audio_status_dot)
        header.addWidget(self.audio_status_label)

        layout.addLayout(header)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #333;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # ===== Collapsible Config Panel =====
        self.config_panel = CollapsiblePanel("Device Configuration")
        config_layout = self.config_panel.content_layout()

        config_grid = QGridLayout()
        config_grid.setSpacing(12)

        # MIDI In
        config_grid.addWidget(QLabel("MIDI In"), 0, 0)
        self.midi_in_combo = QComboBox()
        self.midi_in_combo.setMinimumWidth(180)
        config_grid.addWidget(self.midi_in_combo, 0, 1)

        # MIDI Out
        config_grid.addWidget(QLabel("MIDI Out"), 0, 2)
        self.midi_out_combo = QComboBox()
        self.midi_out_combo.setMinimumWidth(180)
        config_grid.addWidget(self.midi_out_combo, 0, 3)

        # Audio Device
        config_grid.addWidget(QLabel("Audio"), 1, 0)
        self.audio_combo = QComboBox()
        self.audio_combo.currentIndexChanged.connect(self._on_audio_device_changed)
        config_grid.addWidget(self.audio_combo, 1, 1)

        # Sample Rate (display only)
        self.sample_rate_label = QLabel("44100 Hz")
        self.sample_rate_label.setStyleSheet("color: #808080;")
        config_grid.addWidget(self.sample_rate_label, 1, 2)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_devices)
        config_grid.addWidget(refresh_btn, 1, 3)

        # Input channels
        config_grid.addWidget(QLabel("Main Inputs"), 2, 0)
        self.main_input_combo = QComboBox()
        self.main_input_combo.currentIndexChanged.connect(self._on_channel_config_changed)
        config_grid.addWidget(self.main_input_combo, 2, 1)

        config_grid.addWidget(QLabel("Cue Inputs"), 2, 2)
        self.cue_input_combo = QComboBox()
        self.cue_input_combo.setEnabled(False)
        self.cue_input_combo.currentIndexChanged.connect(self._on_channel_config_changed)
        config_grid.addWidget(self.cue_input_combo, 2, 3)

        config_layout.addLayout(config_grid)
        layout.addWidget(self.config_panel)

        # ===== Main Recording Panel =====
        record_panel = QFrame()
        record_panel.setStyleSheet("""
            QFrame {
                background: #1a1a1a;
                border: 1px solid #333;
                border-radius: 8px;
            }
        """)
        record_layout = QVBoxLayout(record_panel)
        record_layout.setContentsMargins(0, 0, 0, 0)
        record_layout.setSpacing(0)

        # Session path bar
        session_bar = QFrame()
        session_bar.setStyleSheet("""
            QFrame {
                background: #252525;
                border: none;
                border-bottom: 1px solid #333;
                border-radius: 0;
            }
        """)
        session_layout = QHBoxLayout(session_bar)
        session_layout.setContentsMargins(16, 10, 16, 10)

        self.session_path_label = QLabel(str(self.session_folder))
        self.session_path_label.setStyleSheet("color: #808080; font-size: 11px;")
        session_layout.addWidget(self.session_path_label, 1)

        browse_btn = QPushButton("Browse")
        browse_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #444;
                padding: 4px 12px;
                color: #808080;
                font-size: 11px;
            }
            QPushButton:hover {
                border-color: #666;
                color: #fff;
            }
        """)
        browse_btn.clicked.connect(self._browse_folder)
        session_layout.addWidget(browse_btn)

        record_layout.addWidget(session_bar)

        # Input meters
        meters_frame = QFrame()
        meters_frame.setStyleSheet("border: none; background: transparent;")
        meters_layout = QVBoxLayout(meters_frame)
        meters_layout.setContentsMargins(16, 16, 16, 8)
        meters_layout.setSpacing(4)

        self.meter_l = MeterWithDB("L")
        self.meter_r = MeterWithDB("R")
        meters_layout.addWidget(self.meter_l)
        meters_layout.addWidget(self.meter_r)

        # Cue meters (hidden by default)
        self.meter_cue_l = MeterWithDB("CL")
        self.meter_cue_r = MeterWithDB("CR")
        self.meter_cue_l.setVisible(False)
        self.meter_cue_r.setVisible(False)
        meters_layout.addWidget(self.meter_cue_l)
        meters_layout.addWidget(self.meter_cue_r)

        # Monitor toggle (next to meters)
        monitor_row = QHBoxLayout()
        monitor_row.addStretch()
        self.monitor_btn = QPushButton("Monitor")
        self.monitor_btn.setCheckable(True)
        self.monitor_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #444;
                padding: 4px 12px;
                color: #606060;
                font-size: 11px;
            }
            QPushButton:checked {
                border-color: #4ade80;
                color: #4ade80;
            }
            QPushButton:hover {
                border-color: #666;
            }
        """)
        self.monitor_btn.clicked.connect(self._toggle_monitoring)
        monitor_row.addWidget(self.monitor_btn)
        meters_layout.addLayout(monitor_row)

        record_layout.addWidget(meters_frame)

        # Quick settings row
        settings_frame = QFrame()
        settings_frame.setStyleSheet("""
            QFrame {
                border: none;
                border-top: 1px solid #333;
                border-bottom: 1px solid #333;
                background: transparent;
            }
        """)
        settings_layout = QHBoxLayout(settings_frame)
        settings_layout.setContentsMargins(16, 10, 16, 10)
        settings_layout.setSpacing(16)

        # Start pattern
        settings_layout.addWidget(QLabel("Start Pattern"))
        self.start_pattern_combo = QComboBox()
        self.start_pattern_combo.setFixedWidth(50)
        for i in range(1, 17):
            self.start_pattern_combo.addItem(str(i), i)
        settings_layout.addWidget(self.start_pattern_combo)

        settings_layout.addSpacing(8)

        # PC Channel
        settings_layout.addWidget(QLabel("PC Ch"))
        self.prog_ch_combo = QComboBox()
        self.prog_ch_combo.setFixedWidth(50)
        for i in range(1, 17):
            self.prog_ch_combo.addItem(str(i), i)
        self.prog_ch_combo.setCurrentIndex(10)  # Default to 11 (AUTO)
        settings_layout.addWidget(self.prog_ch_combo)

        settings_layout.addSpacing(8)

        # Tail time
        settings_layout.addWidget(QLabel("Tail"))
        self.tail_time_combo = QComboBox()
        self.tail_time_combo.setFixedWidth(50)
        self.tail_time_combo.addItem("0s", 0)
        self.tail_time_combo.addItem("1s", 1)
        self.tail_time_combo.addItem("2s", 2)
        self.tail_time_combo.addItem("3s", 3)
        self.tail_time_combo.addItem("5s", 5)
        self.tail_time_combo.setCurrentIndex(2)  # Default 2s
        settings_layout.addWidget(self.tail_time_combo)

        settings_layout.addStretch()

        # Cue toggle
        self.dual_stereo_check = QCheckBox("Cue")
        self.dual_stereo_check.setStyleSheet("color: #606060;")
        self.dual_stereo_check.stateChanged.connect(self._on_dual_stereo_changed)
        settings_layout.addWidget(self.dual_stereo_check)

        record_layout.addWidget(settings_frame)

        # Transport section
        transport_frame = QFrame()
        transport_frame.setStyleSheet("border: none; background: transparent;")
        transport_layout = QHBoxLayout(transport_frame)
        transport_layout.setContentsMargins(20, 20, 20, 20)
        transport_layout.setSpacing(20)

        # Record button
        self.record_btn = RecordButton()
        self.record_btn.clicked.connect(self._toggle_recording)
        transport_layout.addWidget(self.record_btn)

        # Time display
        self.time_label = QLabel("00:00:00")
        self.time_label.setFont(QFont("IBM Plex Mono", 28))
        self.time_label.setStyleSheet("color: #505050;")
        transport_layout.addWidget(self.time_label)

        transport_layout.addStretch()

        # Pattern display
        pattern_widget = QWidget()
        pattern_layout = QVBoxLayout(pattern_widget)
        pattern_layout.setContentsMargins(0, 0, 0, 0)
        pattern_layout.setSpacing(2)

        pattern_label = QLabel("PATTERN")
        pattern_label.setStyleSheet("color: #505050; font-size: 10px;")
        pattern_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        pattern_layout.addWidget(pattern_label)

        self.pattern_display = QLabel("--")
        self.pattern_display.setFont(QFont("IBM Plex Mono", 18))
        self.pattern_display.setStyleSheet("color: #808080;")
        self.pattern_display.setAlignment(Qt.AlignmentFlag.AlignRight)
        pattern_layout.addWidget(self.pattern_display)

        transport_layout.addWidget(pattern_widget)

        record_layout.addWidget(transport_frame)

        # Status footer
        self.status_footer = QFrame()
        self.status_footer.setStyleSheet("""
            QFrame {
                background: #252525;
                border: none;
                border-top: 1px solid #333;
            }
        """)
        footer_layout = QHBoxLayout(self.status_footer)
        footer_layout.setContentsMargins(16, 10, 16, 10)

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #4ade80; font-size: 10px;")
        footer_layout.addWidget(self.status_dot)

        self.status_label = QLabel("Ready to record")
        self.status_label.setStyleSheet("color: #505050; font-size: 11px;")
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch()

        record_layout.addWidget(self.status_footer)

        layout.addWidget(record_panel)
        layout.addStretch()

        # Apply base styles
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0d0d0d;
                color: #e0e0e0;
                font-family: 'IBM Plex Sans', -apple-system, sans-serif;
            }
            QLabel {
                color: #808080;
                font-size: 11px;
            }
            QComboBox {
                background: #252525;
                border: 1px solid #333;
                padding: 6px 10px;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 12px;
            }
            QComboBox:hover {
                border-color: #444;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 8px;
            }
            QComboBox QAbstractItemView {
                background-color: #252525;
                color: #e0e0e0;
                selection-background-color: #444;
                selection-color: #ffffff;
                border: 1px solid #333;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                background-color: #252525;
                color: #e0e0e0;
                padding: 4px 8px;
                min-height: 20px;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #444;
                color: #ffffff;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #333;
                color: #ffffff;
            }
            QPushButton {
                background: #333;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background: #444;
            }
            QCheckBox {
                spacing: 8px;
            }
        """)

    def _setup_timers(self):
        """Setup update timers"""
        self._record_timer = QTimer(self)
        self._record_timer.timeout.connect(self._update_record_time)

        self._level_timer = QTimer(self)
        self._level_timer.timeout.connect(self._update_levels)

    def _style_combo_dark(self, combo: QComboBox):
        """Apply dark palette to combo box popup"""
        palette = combo.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#252525"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#e0e0e0"))
        palette.setColor(QPalette.ColorRole.Window, QColor("#252525"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#e0e0e0"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#252525"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e0e0e0"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#444444"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        combo.setPalette(palette)
        combo.view().setPalette(palette)

    def _update_status(self, message: str, state: str = "ready"):
        """Update status footer"""
        self.status_label.setText(message)
        if state == "ready":
            self.status_dot.setStyleSheet("color: #4ade80; font-size: 10px;")
        elif state == "recording":
            self.status_dot.setStyleSheet("color: #ef4444; font-size: 10px;")
        elif state == "warning":
            self.status_dot.setStyleSheet("color: #f59e0b; font-size: 10px;")
        else:
            self.status_dot.setStyleSheet("color: #505050; font-size: 10px;")

    def _browse_folder(self):
        """Open folder selection dialog"""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Session Folder", str(self.session_folder)
        )
        if folder:
            self.session_folder = Path(folder)
            self.session_path_label.setText(str(self.session_folder))

    def _refresh_devices(self):
        """Refresh available MIDI and audio devices"""
        if self._monitoring:
            self._stop_monitoring()

        # MIDI inputs
        self.midi_in_combo.clear()
        midi_inputs = self._midi_handler.get_input_ports()
        if midi_inputs:
            self.midi_in_combo.addItems(midi_inputs)
            self.midi_status_dot.set_connected(True)
        else:
            self.midi_in_combo.addItem("No MIDI inputs")
            self.midi_status_dot.set_connected(False)

        # MIDI outputs
        self.midi_out_combo.clear()
        midi_outputs = self._midi_handler.get_output_ports()
        if midi_outputs:
            self.midi_out_combo.addItems(midi_outputs)
        else:
            self.midi_out_combo.addItem("No MIDI outputs")

        # Audio inputs
        self.audio_combo.clear()
        audio_devices = self._audio_handler.get_input_devices()
        if audio_devices:
            for dev in audio_devices:
                label = f"{dev.name} ({dev.max_channels}ch)"
                self.audio_combo.addItem(label, dev.index)
            self.audio_status_dot.set_connected(True)
            self._on_audio_device_changed()
        else:
            self.audio_combo.addItem("No audio inputs")
            self.audio_status_dot.set_connected(False)

        # Apply dark styling to all combo boxes
        for combo in [self.midi_in_combo, self.midi_out_combo, self.audio_combo,
                      self.main_input_combo, self.cue_input_combo,
                      self.start_pattern_combo, self.prog_ch_combo, self.tail_time_combo]:
            self._style_combo_dark(combo)

    def _on_audio_device_changed(self):
        """Handle audio device selection change"""
        idx = self.audio_combo.currentData()
        if idx is None:
            return

        info = self._audio_handler.get_device_info(idx)
        if info:
            self.sample_rate_label.setText(f"{int(info.sample_rate)} Hz")

            # Populate channel pair options
            self.main_input_combo.clear()
            self.cue_input_combo.clear()

            num_pairs = info.max_channels // 2
            for i in range(num_pairs):
                ch1 = i * 2 + 1
                ch2 = i * 2 + 2
                label = f"{ch1}-{ch2}"
                self.main_input_combo.addItem(label, i * 2)
                self.cue_input_combo.addItem(label, i * 2)

            if num_pairs >= 2:
                self.cue_input_combo.setCurrentIndex(1)

            # Enable dual stereo if enough channels
            can_dual = info.max_channels >= 4
            self.dual_stereo_check.setEnabled(can_dual)
            if not can_dual:
                self.dual_stereo_check.setChecked(False)

    def _on_dual_stereo_changed(self):
        """Handle dual stereo checkbox change"""
        is_dual = self.dual_stereo_check.isChecked()
        self.cue_input_combo.setEnabled(is_dual)
        self.meter_cue_l.setVisible(is_dual)
        self.meter_cue_r.setVisible(is_dual)
        self._update_audio_config()

    def _on_channel_config_changed(self):
        """Handle channel selection change"""
        self._update_audio_config()
        if self._monitoring:
            self._stop_monitoring()
            self._start_monitoring()

    def _update_audio_config(self):
        """Update audio handler with current channel configuration"""
        idx = self.audio_combo.currentData()
        if idx is None:
            return

        main_offset = self.main_input_combo.currentData() or 0
        cue_offset = self.cue_input_combo.currentData() or 2
        is_dual = self.dual_stereo_check.isChecked()

        self._audio_handler.set_input_device(idx)
        self._audio_handler.set_channel_config(main_offset, cue_offset if is_dual else None)

    def _toggle_monitoring(self):
        """Toggle input monitoring"""
        if self._monitoring:
            self._stop_monitoring()
            self.monitor_btn.setChecked(False)
        else:
            self._start_monitoring()
            self.monitor_btn.setChecked(True)

    def _start_monitoring(self):
        """Start input level monitoring"""
        idx = self.audio_combo.currentData()
        if idx is None:
            return

        self._update_audio_config()
        self._audio_handler.set_level_callback(self._on_levels)

        if self._audio_handler.start_monitoring():
            self._monitoring = True
            self._level_timer.start(50)

    def _stop_monitoring(self):
        """Stop input monitoring"""
        self._audio_handler.stop_monitoring()
        self._monitoring = False
        self._level_timer.stop()

    def _on_levels(self, levels):
        """Callback for level updates"""
        if len(levels) >= 2:
            self.meter_l.set_level(levels[0])
            self.meter_r.set_level(levels[1])
        if len(levels) >= 4:
            self.meter_cue_l.set_level(levels[2])
            self.meter_cue_r.set_level(levels[3])

    def _toggle_recording(self):
        """Start or stop recording"""
        if not self.recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        """Start jam recording"""
        if self._monitoring:
            self._stop_monitoring()
            self.monitor_btn.setChecked(False)

        # Create session
        self.session = Session(self.session_folder)

        # Open MIDI ports
        midi_in_idx = self.midi_in_combo.currentIndex()
        midi_out_idx = self.midi_out_combo.currentIndex()
        audio_idx = self.audio_combo.currentData()

        if not self.session.midi_handler.open_input(midi_in_idx):
            self._show_error("Failed to open MIDI input")
            return

        if not self.session.midi_handler.open_output(midi_out_idx):
            self._show_error("Failed to open MIDI output")
            return

        # Configure audio
        main_offset = self.main_input_combo.currentData() or 0
        cue_offset = self.cue_input_combo.currentData() or 2
        is_dual = self.dual_stereo_check.isChecked()

        if audio_idx is not None:
            self.session.audio_handler.set_input_device(audio_idx)
            self.session.audio_handler.set_channel_config(
                main_offset,
                cue_offset if is_dual else None
            )

        self.session.audio_handler.set_level_callback(self._on_levels)

        if not self.session.start_jam_recording():
            self._show_error("Failed to start recording")
            return

        self.recording = True
        self.record_start_time = 0

        # Update UI
        self.record_btn.set_recording(True)
        self.time_label.setStyleSheet("color: #4ade80;")
        self._update_status("Recording...", "recording")
        self._record_timer.start(1000)
        self._level_timer.start(50)

    def _stop_recording(self):
        """Stop jam recording and show track selection"""
        self._record_timer.stop()
        self._level_timer.stop()

        duration = self.session.stop_jam_recording()

        self.recording = False
        self.record_btn.set_recording(False)
        self.time_label.setStyleSheet("color: #505050;")
        self._update_status("Processing...", "ready")

        # Show track selection dialog
        dialog = TrackSelectionDialog(
            duration,
            self.session.tracks_with_activity,
            self
        )

        if dialog.exec():
            stems = dialog.get_stems_to_capture()
            skipped = dialog.get_skipped_tracks()
            self.session.set_skipped_tracks(skipped)
            self._start_stem_capture(stems)
        else:
            self._update_status(f"Saved to {self.session.session_folder.name}")
            self.session.save_metadata()

    def _start_stem_capture(self, stems_to_capture):
        """Start the stem capture process"""
        from PyQt6.QtWidgets import QApplication

        stems = sorted(stems_to_capture)

        if not stems:
            self._update_status("No stems to capture")
            self.session.save_metadata()
            return

        # Prompt user to reload part (knob states) - pattern will be set automatically
        reply = QMessageBox.information(
            self,
            "Prepare OT",
            f"Before capturing stems:\n\n"
            f"Reload Part on the Octatrack\n"
            f"(This resets knobs to saved state)\n\n"
            f"Pattern will be set automatically via MIDI.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        if reply == QMessageBox.StandardButton.Cancel:
            self._update_status("Stem capture cancelled")
            self.session.save_metadata()
            return

        # Show progress dialog
        progress = CaptureProgressDialog(
            stems,
            self.session.metadata.duration_seconds,
            self
        )

        cancelled = False

        def on_cancel():
            nonlocal cancelled
            cancelled = True
            self.session.midi_handler.stop_playback()

        progress.cancelled.connect(on_cancel)
        progress.show()
        QApplication.processEvents()

        # Capture each stem
        for i, track in enumerate(stems):
            if cancelled:
                break

            progress.start_capture(i)
            QApplication.processEvents()

            success = self._capture_stem_with_events(track, progress, lambda: cancelled)

            if success and not cancelled:
                progress.finish_capture(i)
            elif not cancelled:
                self._show_error(f"Failed to capture track {track}")
                break

            QApplication.processEvents()

        if not cancelled:
            progress.all_complete()

        self.session.save_metadata()
        self.session.cleanup()

        folder = self.session.session_folder
        self._update_status(f"Complete! Saved to {folder.name}")

        reply = QMessageBox.question(
            self,
            "Capture Complete",
            f"Stem capture complete.\n\nOpen folder?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            os.system(f'open "{folder}"')

    def _capture_stem_with_events(self, track_num: int, progress, is_cancelled) -> bool:
        """Capture a stem while keeping UI responsive"""
        from PyQt6.QtWidgets import QApplication
        import threading
        import time

        if not self.session.midi_handler.midi_out:
            return False

        tail_time = self.tail_time_combo.currentData() or 0

        self.session.audio_handler.clear()

        playback_done = threading.Event()
        audio_started = threading.Event()

        def on_complete():
            playback_done.set()

        def on_ready():
            if self.session.audio_handler.start_recording():
                audio_started.set()

        # Get pattern settings
        start_pattern = self.start_pattern_combo.currentData() or 1
        prog_change_channel = self.prog_ch_combo.currentData() or 11

        # Calculate timing to match stereo recording alignment:
        # - pre_roll: silence before OT starts (matches stereo pre-roll)
        # - content_duration: actual OT playing time (from Transport START to STOP)
        # - stereo_duration: total stereo recording length (stems will match this)
        ot_start_offset = self.session.metadata.ot_start_offset
        content_duration = self.session.metadata.ot_content_duration
        stereo_duration = self.session.metadata.duration_seconds

        print(f"[STEM] OT offset={ot_start_offset:.2f}s, Content={content_duration:.2f}s, Stereo={stereo_duration:.2f}s")

        self.session.midi_handler.start_playback(
            isolated_track=track_num,
            on_complete=on_complete,
            duration=content_duration,
            tail_time=tail_time,
            on_ready=on_ready,
            start_pattern=start_pattern,
            prog_change_channel=prog_change_channel,
            pre_roll=ot_start_offset,
            stereo_duration=stereo_duration
        )

        # Wait for audio to start - may take longer with pre-roll
        audio_started.wait(timeout=3.0 + ot_start_offset)
        if not audio_started.is_set():
            print("[ERROR] Audio failed to start")
            return False

        # Total timeout = stereo_duration + tail + buffer (stems match stereo length)
        timeout = stereo_duration + tail_time + 2.0
        start_time = time.time()

        while not playback_done.is_set():
            if is_cancelled():
                self.session.midi_handler.stop_playback()
                self.session.audio_handler.stop_recording()
                return False

            if time.time() - start_time > timeout:
                break

            QApplication.processEvents()
            time.sleep(0.05)

        self.session.audio_handler.stop_recording()

        stem_path = self.session.session_folder / f"track_{track_num}.wav"
        success = self.session.audio_handler.save_main_mix(stem_path)

        if success:
            self.session.metadata.captured_stems.append(track_num)

        return success

    def _update_record_time(self):
        """Update recording time display"""
        self.record_start_time += 1
        hours = self.record_start_time // 3600
        minutes = (self.record_start_time % 3600) // 60
        seconds = self.record_start_time % 60
        self.time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    def _update_levels(self):
        """Update level meter"""
        if self.session and self.session.audio_handler.recording:
            levels = self.session.audio_handler.get_levels()
            self._on_levels(levels)

    def _show_error(self, message: str):
        """Show error message"""
        QMessageBox.critical(self, "Error", message)
        self._update_status(f"Error: {message}", "warning")

    def closeEvent(self, event):
        """Handle window close"""
        if self._monitoring:
            self._stop_monitoring()

        if self.recording:
            reply = QMessageBox.question(
                self,
                "Recording in Progress",
                "Recording is in progress. Stop and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

            self.session.stop_jam_recording()
            self.session.cleanup()

        event.accept()
