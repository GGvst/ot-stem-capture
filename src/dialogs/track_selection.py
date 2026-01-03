"""Track selection dialog for selecting stems to capture"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QPushButton, QFrame, QButtonGroup
)
from PyQt6.QtCore import Qt
from typing import Set


class TrackSelectionDialog(QDialog):
    """Dialog for selecting which tracks to capture as stems"""

    def __init__(self, duration: float, tracks_with_activity: Set[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Stems to Capture")
        self.setMinimumWidth(500)

        self.tracks_with_activity = tracks_with_activity
        self.stem_checkboxes = {}

        self._setup_ui(duration)

    def _setup_ui(self, duration: float):
        layout = QVBoxLayout(self)

        # Duration info
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        duration_label = QLabel(f"Session Captured: {minutes}:{seconds:02d}")
        duration_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(duration_label)

        layout.addSpacing(10)

        # Instructions
        instructions = QLabel(
            "Select which tracks to capture as isolated stems.\n"
            "Unchecked tracks will only appear in the stereo mix."
        )
        instructions.setStyleSheet("color: #aaa;")
        layout.addWidget(instructions)

        layout.addSpacing(10)

        # Track selection
        tracks_frame = QFrame()
        tracks_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border-radius: 4px;
                padding: 15px;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        tracks_layout = QVBoxLayout(tracks_frame)

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("Track"))
        header.addStretch()
        activity_header = QLabel("MIDI Activity")
        activity_header.setStyleSheet("color: #888;")
        header.addWidget(activity_header)
        tracks_layout.addLayout(header)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #444;")
        tracks_layout.addWidget(sep)

        # Track rows
        for track in range(1, 9):
            row = QHBoxLayout()

            # Stem capture checkbox - ALL enabled
            checkbox = QCheckBox(f"Track {track}")
            checkbox.setChecked(True)  # Default to capturing all
            checkbox.setStyleSheet("color: white; font-size: 14px;")
            self.stem_checkboxes[track] = checkbox
            row.addWidget(checkbox)

            row.addStretch()

            # Activity indicator (informational only)
            if track in self.tracks_with_activity:
                activity = QLabel("● active")
                activity.setStyleSheet("color: #0f0; font-size: 12px;")
            else:
                activity = QLabel("○ none")
                activity.setStyleSheet("color: #555; font-size: 12px;")
            row.addWidget(activity)

            tracks_layout.addLayout(row)

        layout.addWidget(tracks_frame)

        # Quick selection buttons
        quick_layout = QHBoxLayout()

        select_all = QPushButton("Select All")
        select_all.clicked.connect(lambda: self._set_all(True))
        quick_layout.addWidget(select_all)

        select_none = QPushButton("Select None")
        select_none.clicked.connect(lambda: self._set_all(False))
        quick_layout.addWidget(select_none)

        select_active = QPushButton("Select Active Only")
        select_active.clicked.connect(self._select_active_only)
        quick_layout.addWidget(select_active)

        quick_layout.addStretch()
        layout.addLayout(quick_layout)

        layout.addSpacing(10)

        # Summary
        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        layout.addSpacing(20)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self.capture_btn = QPushButton("Start Stem Capture")
        self.capture_btn.setStyleSheet("""
            QPushButton {
                background-color: #0a5;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b6;
            }
            QPushButton:disabled {
                background-color: #333;
                color: #666;
            }
        """)
        self.capture_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.capture_btn)

        layout.addLayout(button_layout)

        # Connect checkboxes and update summary (after button exists)
        for cb in self.stem_checkboxes.values():
            cb.stateChanged.connect(self._update_summary)
        self._update_summary()

    def _set_all(self, checked: bool):
        """Set all checkboxes"""
        for cb in self.stem_checkboxes.values():
            cb.setChecked(checked)

    def _select_active_only(self):
        """Select only tracks with MIDI activity"""
        for track, cb in self.stem_checkboxes.items():
            cb.setChecked(track in self.tracks_with_activity)

    def _update_summary(self):
        """Update the summary text"""
        stems = sum(1 for cb in self.stem_checkboxes.values() if cb.isChecked())
        self.summary_label.setText(f"Stems to capture: {stems}")
        self.capture_btn.setEnabled(stems > 0)

    def get_stems_to_capture(self) -> Set[int]:
        """Get the tracks selected for stem capture"""
        return {
            track for track, cb in self.stem_checkboxes.items()
            if cb.isChecked()
        }

    def get_skipped_tracks(self) -> Set[int]:
        """Get tracks NOT selected for stem capture"""
        return {
            track for track, cb in self.stem_checkboxes.items()
            if not cb.isChecked()
        }
