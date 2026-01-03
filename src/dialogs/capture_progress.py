"""Progress dialog for stem capture"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from typing import List


class CaptureProgressDialog(QDialog):
    """Dialog showing stem capture progress"""

    cancelled = pyqtSignal()

    def __init__(self, stems_to_capture: List[int], duration: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Capturing Stems")
        self.setMinimumWidth(450)
        self.setModal(True)

        self.stems = stems_to_capture
        self.duration = duration
        self.current_index = 0
        self.current_progress = 0.0

        self._setup_ui()

        # Timer for progress updates
        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._update_progress)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Title
        self.title_label = QLabel(f"Track 1 of {len(self.stems)}")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.title_label)

        layout.addSpacing(10)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #0a5;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Time display
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.time_label)

        layout.addSpacing(10)

        # Track list
        tracks_frame = QFrame()
        tracks_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border-radius: 4px;
                padding: 10px;
            }
        """)
        self.tracks_layout = QVBoxLayout(tracks_frame)

        self.track_labels = {}
        for i, track in enumerate(self.stems):
            label = QLabel(f"○ Track {track}")
            label.setStyleSheet("color: #888;")
            self.track_labels[track] = label
            self.tracks_layout.addWidget(label)

        layout.addWidget(tracks_frame)

        layout.addSpacing(20)

        # Cancel button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self._on_cancel)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def start_capture(self, track_index: int):
        """Start capturing a specific track"""
        self.current_index = track_index
        self.current_progress = 0.0

        track = self.stems[track_index]

        self.title_label.setText(f"Track {track_index + 1} of {len(self.stems)}")

        # Update track list styling
        for t, label in self.track_labels.items():
            if t == track:
                label.setText(f"● Track {t} capturing...")
                label.setStyleSheet("color: #0f0;")
            elif self.stems.index(t) < track_index:
                label.setText(f"✓ Track {t}")
                label.setStyleSheet("color: #0a5;")
            else:
                label.setText(f"○ Track {t}")
                label.setStyleSheet("color: #888;")

        # Start progress timer
        self._progress_timer.start(100)  # Update every 100ms

    def _update_progress(self):
        """Update progress bar based on elapsed time"""
        self.current_progress += 0.1  # 100ms

        progress = min(self.current_progress / self.duration, 1.0)
        self.progress_bar.setValue(int(progress * 1000))

        # Update time display
        current_min = int(self.current_progress // 60)
        current_sec = int(self.current_progress % 60)
        total_min = int(self.duration // 60)
        total_sec = int(self.duration % 60)
        self.time_label.setText(
            f"{current_min}:{current_sec:02d} / {total_min}:{total_sec:02d}"
        )

    def finish_capture(self, track_index: int):
        """Mark a track capture as complete"""
        self._progress_timer.stop()

        track = self.stems[track_index]
        label = self.track_labels[track]
        label.setText(f"✓ Track {track}")
        label.setStyleSheet("color: #0a5;")

    def _on_cancel(self):
        """Handle cancel button"""
        self._progress_timer.stop()
        self.cancelled.emit()
        self.reject()

    def all_complete(self):
        """Called when all stems are captured"""
        self._progress_timer.stop()
        self.title_label.setText("Capture Complete!")
        self.progress_bar.setValue(1000)
        self.accept()
