"""Session management for OT Stem Capture"""

import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Set, Optional

from .midi_handler import MIDIHandler, MIDIEvent
from .audio_handler import AudioHandler


@dataclass
class SessionMetadata:
    """Metadata for a capture session"""
    created: str = ""
    duration_seconds: float = 0
    ot_start_offset: float = 0   # Time between record start and OT transport start
    ot_content_duration: float = 0  # Actual OT playing duration (stop - start)
    sample_rate: int = 48000
    dual_stereo: bool = False  # True if main+cue recorded
    skipped_tracks: List[int] = field(default_factory=list)
    captured_stems: List[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'SessionMetadata':
        return cls(**data)


class Session:
    """
    Manages a single capture session:
    - Initial jam recording (MIDI + audio)
    - Stem capture passes
    - File output

    Supports dual stereo recording:
    - Main outs (1-2): stereo_mix.wav - the full mix
    - Cue outs (3-4): cue_mix.wav - for stem capture source
    """

    def __init__(self, output_folder: Path):
        self.output_folder = output_folder
        self.session_folder: Optional[Path] = None
        self.metadata = SessionMetadata()

        self.midi_handler = MIDIHandler()
        self.audio_handler = AudioHandler()

        self.skipped_tracks: Set[int] = set()
        self.tracks_with_activity: Set[int] = set()

    def create_session_folder(self) -> Path:
        """Create timestamped session folder"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_folder = self.output_folder / f"session_{timestamp}"
        self.session_folder.mkdir(parents=True, exist_ok=True)
        self.metadata.created = timestamp
        return self.session_folder

    def start_jam_recording(self) -> bool:
        """Start recording the initial jam (MIDI + audio)"""
        if not self.session_folder:
            self.create_session_folder()

        # Start both MIDI and audio recording
        self.midi_handler.start_recording()
        if not self.audio_handler.start_recording():
            self.midi_handler.stop_recording()
            return False

        return True

    def stop_jam_recording(self) -> float:
        """
        Stop jam recording and save audio files.
        Returns duration in seconds.
        """
        self.midi_handler.stop_recording()
        self.audio_handler.stop_recording()

        # Get duration
        duration = self.audio_handler.get_duration()
        self.metadata.duration_seconds = duration
        self.metadata.sample_rate = self.audio_handler.sample_rate

        # Detect OT start time - prefer MIDI Transport START, fall back to audio onset
        midi_start = self.midi_handler.ot_start_offset
        midi_stop = self.midi_handler.ot_stop_time

        if midi_start > 0:
            self.metadata.ot_start_offset = midi_start
            print(f"[SESSION] OT start detected from MIDI Transport START: {midi_start:.3f}s")
        else:
            # Fall back to audio onset detection
            audio_onset = self.audio_handler.detect_audio_onset(threshold_db=-40.0)
            self.metadata.ot_start_offset = audio_onset
            print(f"[SESSION] OT start detected from audio onset: {audio_onset:.3f}s")
            if audio_onset == 0:
                print("[SESSION] WARNING: Could not detect OT start! Enable Transport Send on OT for best results.")

        # Calculate actual OT content duration from Transport STOP
        if midi_stop > midi_start:
            self.metadata.ot_content_duration = midi_stop - midi_start
            print(f"[SESSION] OT stop detected at {midi_stop:.3f}s, content duration: {self.metadata.ot_content_duration:.3f}s")
        else:
            # Fall back to stereo duration minus start offset
            self.metadata.ot_content_duration = duration - self.metadata.ot_start_offset
            print(f"[SESSION] No Transport STOP detected, using full duration: {self.metadata.ot_content_duration:.3f}s")

        print(f"[SESSION] Stereo duration: {duration:.2f}s, OT start: {self.metadata.ot_start_offset:.3f}s, OT content: {self.metadata.ot_content_duration:.3f}s")

        # Check if dual stereo mode
        is_dual = self.audio_handler.channels >= 4
        self.metadata.dual_stereo = is_dual

        # Save main mix (channels 1-2)
        stereo_path = self.session_folder / "stereo_mix.wav"
        self.audio_handler.save_main_mix(stereo_path)

        # Save cue mix if dual stereo (channels 3-4)
        if is_dual:
            cue_path = self.session_folder / "cue_mix.wav"
            self.audio_handler.save_cue_mix(cue_path)

        # Analyze track activity
        activity = self.midi_handler.get_track_activity()
        self.tracks_with_activity = {t for t, active in activity.items() if active}

        return duration

    def set_skipped_tracks(self, tracks: Set[int]):
        """Mark tracks that won't be captured as stems"""
        self.skipped_tracks = tracks
        self.metadata.skipped_tracks = list(tracks)

    def get_stems_to_capture(self) -> List[int]:
        """Get list of tracks that need stem capture"""
        # All tracks with activity that aren't skipped
        return sorted(self.tracks_with_activity - self.skipped_tracks)

    def capture_stem(self, track_num: int, on_progress=None) -> bool:
        """
        Capture a single stem by replaying MIDI with track isolation.

        Args:
            track_num: Track number (1-8)
            on_progress: Callback for progress updates
        """
        if not self.midi_handler.midi_out:
            return False

        # Clear audio buffer
        self.audio_handler.clear()

        # Start audio recording
        if not self.audio_handler.start_recording():
            return False

        # Create completion event
        import threading
        playback_done = threading.Event()

        def on_complete():
            playback_done.set()

        # Start MIDI playback with isolation
        self.midi_handler.start_playback(
            isolated_track=track_num,
            on_complete=on_complete
        )

        # Wait for playback to complete
        # Add small buffer for audio tail
        timeout = self.metadata.duration_seconds + 2.0
        playback_done.wait(timeout=timeout)

        # Stop audio recording
        self.audio_handler.stop_recording()

        # Save stem - use main outs (channels 1-2)
        # In stem capture mode, only the isolated track goes to main outs
        stem_path = self.session_folder / f"track_{track_num}.wav"
        success = self.audio_handler.save_main_mix(stem_path)

        if success:
            self.metadata.captured_stems.append(track_num)

        return success

    def save_metadata(self):
        """Save session metadata to JSON"""
        if not self.session_folder:
            return

        meta_path = self.session_folder / "session.json"
        with open(meta_path, 'w') as f:
            json.dump(self.metadata.to_dict(), f, indent=2)

    def cleanup(self):
        """Close all handlers"""
        self.midi_handler.close()
