"""Audio recording for stem capture - supports configurable input channels"""

import numpy as np
import sounddevice as sd
import soundfile as sf
from typing import List, Optional, Callable, Tuple
from pathlib import Path
from dataclasses import dataclass


@dataclass
class AudioDeviceInfo:
    """Information about an audio device"""
    index: int
    name: str
    max_channels: int
    sample_rate: float


class AudioHandler:
    """
    Handles audio recording from interface inputs.

    Supports configurable channel pairs:
    - Main: user-selected stereo pair (e.g., inputs 1-2 or 3-4)
    - Cue: optional second stereo pair for dual recording
    """

    DEFAULT_SAMPLE_RATE = 48000
    DTYPE = 'float32'
    BLOCKSIZE = 1024

    def __init__(self):
        self.recording = False
        self.audio_data: List[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._level_callback: Optional[Callable[[List[float]], None]] = None
        self._current_levels: List[float] = [-60.0, -60.0, -60.0, -60.0]
        self._device_index: Optional[int] = None
        self._device_max_channels: int = 2
        self._sample_rate: int = self.DEFAULT_SAMPLE_RATE

        # Channel configuration (0-indexed)
        self._main_offset: int = 0  # Main stereo pair starts at this channel
        self._cue_offset: Optional[int] = None  # Cue pair offset, None if not used
        self._recording_channels: int = 2  # Total channels to record

    def get_input_devices(self) -> List[AudioDeviceInfo]:
        """List available audio input devices with channel info"""
        devices = []
        for i, dev in enumerate(sd.query_devices()):
            if dev['max_input_channels'] >= 2:
                devices.append(AudioDeviceInfo(
                    index=i,
                    name=dev['name'],
                    max_channels=dev['max_input_channels'],
                    sample_rate=dev['default_samplerate']
                ))
        return devices

    def get_device_info(self, device_index: int) -> Optional[AudioDeviceInfo]:
        """Get info for a specific device"""
        try:
            dev = sd.query_devices(device_index)
            return AudioDeviceInfo(
                index=device_index,
                name=dev['name'],
                max_channels=dev['max_input_channels'],
                sample_rate=dev['default_samplerate']
            )
        except Exception:
            return None

    def set_input_device(self, device_index: int) -> bool:
        """Set the input device to use."""
        try:
            dev = sd.query_devices(device_index)
            self._device_index = device_index
            self._device_max_channels = dev['max_input_channels']
            self._sample_rate = int(dev['default_samplerate'])
            print(f"[AUDIO] Device set: {dev['name']}, {self._sample_rate}Hz, {self._device_max_channels}ch")
            return True
        except Exception as e:
            print(f"Failed to set audio input device: {e}")
            return False

    @property
    def sample_rate(self) -> int:
        """Current sample rate"""
        return self._sample_rate

    def set_channel_config(self, main_offset: int, cue_offset: Optional[int] = None):
        """
        Configure which input channels to record.

        Args:
            main_offset: 0-indexed offset for main stereo pair (0 = ch 1-2, 2 = ch 3-4)
            cue_offset: 0-indexed offset for cue stereo pair, or None for stereo-only
        """
        self._main_offset = main_offset
        self._cue_offset = cue_offset

        # Calculate how many channels we need from the device
        if cue_offset is not None:
            # Need to capture up to the highest channel used
            max_needed = max(main_offset + 2, cue_offset + 2)
        else:
            max_needed = main_offset + 2

        self._recording_channels = min(max_needed, self._device_max_channels)

    @property
    def channels(self) -> int:
        """Number of output channels (2 for stereo, 4 for main+cue)"""
        return 4 if self._cue_offset is not None else 2

    def set_level_callback(self, callback: Callable[[List[float]], None]):
        """Set callback for level metering (list of dB values per channel)"""
        self._level_callback = callback

    def _calc_db(self, data: np.ndarray) -> float:
        """Calculate dB level from audio data"""
        rms = np.sqrt(np.mean(data**2))
        return 20 * np.log10(max(rms, 1e-10))

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback for audio input"""
        if status:
            print(f"Audio status: {status}")

        # Store raw audio data
        self.audio_data.append(indata.copy())

        # Calculate levels for configured channels
        self._update_levels(indata)

    def _update_levels(self, indata: np.ndarray):
        """Update level meters for configured channels"""
        levels = []

        # Main L/R
        main_l = self._main_offset
        main_r = self._main_offset + 1
        if main_l < indata.shape[1]:
            levels.append(self._calc_db(indata[:, main_l]))
        else:
            levels.append(-60.0)
        if main_r < indata.shape[1]:
            levels.append(self._calc_db(indata[:, main_r]))
        else:
            levels.append(-60.0)

        # Cue L/R (if configured)
        if self._cue_offset is not None:
            cue_l = self._cue_offset
            cue_r = self._cue_offset + 1
            if cue_l < indata.shape[1]:
                levels.append(self._calc_db(indata[:, cue_l]))
            else:
                levels.append(-60.0)
            if cue_r < indata.shape[1]:
                levels.append(self._calc_db(indata[:, cue_r]))
            else:
                levels.append(-60.0)
        else:
            levels.extend([-60.0, -60.0])

        self._current_levels = levels

        if self._level_callback:
            self._level_callback(levels)

    def start_recording(self) -> bool:
        """Start recording audio"""
        try:
            self.audio_data = []

            print(f"[AUDIO] Starting recording:")
            print(f"  Device index: {self._device_index}")
            print(f"  Recording channels: {self._recording_channels}")
            print(f"  Main offset: {self._main_offset} (inputs {self._main_offset+1}-{self._main_offset+2})")
            if self._cue_offset is not None:
                print(f"  Cue offset: {self._cue_offset} (inputs {self._cue_offset+1}-{self._cue_offset+2})")

            self._stream = sd.InputStream(
                device=self._device_index,
                samplerate=self._sample_rate,
                channels=self._recording_channels,
                dtype=self.DTYPE,
                blocksize=self.BLOCKSIZE,
                callback=self._audio_callback
            )
            print(f"  Sample rate: {self._sample_rate}Hz")
            self._stream.start()
            self.recording = True
            return True
        except Exception as e:
            print(f"Failed to start recording: {e}")
            return False

    def stop_recording(self):
        """Stop recording audio"""
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.recording = False

    def _extract_stereo(self, audio: np.ndarray, offset: int) -> np.ndarray:
        """Extract a stereo pair from multi-channel audio"""
        ch1 = offset
        ch2 = offset + 1

        if ch2 < audio.shape[1]:
            return audio[:, [ch1, ch2]]
        elif ch1 < audio.shape[1]:
            # Only one channel available, duplicate to stereo
            return np.column_stack([audio[:, ch1], audio[:, ch1]])
        else:
            # No channels available, return silence
            return np.zeros((audio.shape[0], 2), dtype=audio.dtype)

    def save_main_mix(self, filepath: Path) -> bool:
        """Save main stereo pair to file"""
        if not self.audio_data:
            print(f"[AUDIO] No audio data to save!")
            return False

        try:
            audio = np.concatenate(self.audio_data, axis=0)
            print(f"[AUDIO] Saving main mix:")
            print(f"  Total audio shape: {audio.shape}")
            print(f"  Extracting from offset {self._main_offset} (channels {self._main_offset+1}-{self._main_offset+2})")

            stereo = self._extract_stereo(audio, self._main_offset)
            print(f"  Stereo shape: {stereo.shape}")
            print(f"  Max level: {np.max(np.abs(stereo)):.4f}")

            sf.write(str(filepath), stereo, self._sample_rate, subtype='PCM_24')
            print(f"  Saved to: {filepath}")
            return True
        except Exception as e:
            print(f"Failed to save main mix: {e}")
            return False

    def save_cue_mix(self, filepath: Path) -> bool:
        """Save cue stereo pair to file"""
        if not self.audio_data or self._cue_offset is None:
            return False

        try:
            audio = np.concatenate(self.audio_data, axis=0)
            stereo = self._extract_stereo(audio, self._cue_offset)

            sf.write(str(filepath), stereo, self._sample_rate, subtype='PCM_24')
            return True
        except Exception as e:
            print(f"Failed to save cue mix: {e}")
            return False

    def save_to_file(self, filepath: Path, channels: Tuple[int, int] = (0, 1)) -> bool:
        """Save specified channels to file (legacy method)"""
        if not self.audio_data:
            return False

        try:
            audio = np.concatenate(self.audio_data, axis=0)
            ch1, ch2 = channels
            if ch2 < audio.shape[1]:
                stereo = audio[:, [ch1, ch2]]
            else:
                stereo = audio[:, :2]

            sf.write(str(filepath), stereo, self._sample_rate, subtype='PCM_24')
            return True
        except Exception as e:
            print(f"Failed to save audio: {e}")
            return False

    def get_duration(self) -> float:
        """Get duration of recorded audio in seconds"""
        if not self.audio_data:
            return 0
        total_samples = sum(chunk.shape[0] for chunk in self.audio_data)
        return total_samples / self._sample_rate

    def detect_audio_onset(self, threshold_db: float = -40.0) -> float:
        """
        Detect when audio actually started (first sound above threshold).
        Returns time in seconds from start of recording.

        This is used to align stems with stereo - detects when OT started
        playing by finding when audio amplitude exceeds noise floor.
        """
        if not self.audio_data:
            return 0.0

        # Convert threshold from dB to linear
        threshold_linear = 10 ** (threshold_db / 20)

        # Analyze in chunks for efficiency
        samples_checked = 0
        chunk_size = 1024  # Analyze in ~23ms chunks at 44.1kHz

        for chunk in self.audio_data:
            # Check each sub-chunk
            for i in range(0, len(chunk), chunk_size):
                sub_chunk = chunk[i:i + chunk_size]
                # Get max amplitude across all channels
                max_amp = np.max(np.abs(sub_chunk))

                if max_amp > threshold_linear:
                    # Found audio! Return timestamp
                    onset_sample = samples_checked + i
                    onset_time = onset_sample / self._sample_rate
                    print(f"[AUDIO] Detected audio onset at {onset_time:.3f}s (amplitude: {20 * np.log10(max_amp):.1f} dB)")
                    return onset_time

            samples_checked += len(chunk)

        # No audio detected above threshold
        print(f"[AUDIO] No audio detected above {threshold_db} dB threshold")
        return 0.0

    def get_levels(self) -> List[float]:
        """Get current audio levels (dB) for configured channels"""
        return self._current_levels

    def clear(self):
        """Clear recorded audio data"""
        self.audio_data = []

    def start_monitoring(self) -> bool:
        """Start monitoring input levels without recording"""
        try:
            if self._stream is not None:
                return True

            self._stream = sd.InputStream(
                device=self._device_index,
                samplerate=self._sample_rate,
                channels=self._recording_channels,
                dtype=self.DTYPE,
                blocksize=self.BLOCKSIZE,
                callback=self._monitor_callback
            )
            self._stream.start()
            return True
        except Exception as e:
            print(f"Failed to start monitoring: {e}")
            return False

    def _monitor_callback(self, indata, frames, time_info, status):
        """Callback for monitoring (levels only, no storage)"""
        self._update_levels(indata)

    def stop_monitoring(self):
        """Stop monitoring"""
        if self._stream and not self.recording:
            self._stream.stop()
            self._stream.close()
            self._stream = None
