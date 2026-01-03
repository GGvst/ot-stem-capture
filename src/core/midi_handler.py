"""MIDI recording and playback for Octatrack"""

import time
import threading
from dataclasses import dataclass
from typing import List, Optional, Callable
import rtmidi


@dataclass
class MIDIEvent:
    """A timestamped MIDI event"""
    timestamp: float  # Seconds from session start
    channel: int      # 0-15
    message: List[int]  # Raw MIDI bytes


# Octatrack CC reference
OT_TRACK_MUTE_CC = {
    1: 94,  # Track 1 mute
    2: 95,  # Track 2 mute
    3: 96,  # Track 3 mute
    4: 97,  # Track 4 mute
    5: 98,  # Track 5 mute
    6: 99,  # Track 6 mute
    7: 100, # Track 7 mute
    8: 101, # Track 8 mute
}

OT_AUTO_CHANNEL = 11  # Default auto channel (1-indexed, so send on channel 10 in 0-indexed)

# OT response latency compensation - time between sending Start and OT producing audio
OT_LATENCY_COMPENSATION = 0.2  # ~200ms typical OT response time


class MIDIHandler:
    """Handles MIDI recording from and playback to Octatrack"""

    def __init__(self):
        self.midi_in: Optional[rtmidi.MidiIn] = None
        self.midi_out: Optional[rtmidi.MidiOut] = None
        self.events: List[MIDIEvent] = []
        self.recording = False
        self.playing = False
        self.start_time: float = 0
        self.ot_start_offset: float = 0  # Time between record start and OT transport start
        self.ot_stop_time: float = 0     # Time when OT transport stopped (first stop after start)
        self._playback_thread: Optional[threading.Thread] = None
        self._stop_playback = threading.Event()

    def get_input_ports(self) -> List[str]:
        """List available MIDI input ports"""
        midi_in = rtmidi.MidiIn()
        ports = midi_in.get_ports()
        del midi_in
        return ports

    def get_output_ports(self) -> List[str]:
        """List available MIDI output ports"""
        midi_out = rtmidi.MidiOut()
        ports = midi_out.get_ports()
        del midi_out
        return ports

    def open_input(self, port_index: int) -> bool:
        """Open a MIDI input port"""
        try:
            self.midi_in = rtmidi.MidiIn()
            self.midi_in.open_port(port_index)
            self.midi_in.set_callback(self._midi_callback)
            return True
        except Exception as e:
            print(f"Failed to open MIDI input: {e}")
            return False

    def open_output(self, port_index: int) -> bool:
        """Open a MIDI output port"""
        try:
            self.midi_out = rtmidi.MidiOut()
            ports = self.midi_out.get_ports()
            port_name = ports[port_index] if port_index < len(ports) else "unknown"
            self.midi_out.open_port(port_index)
            self._output_port_name = port_name
            print(f"[MIDI] Opened output port {port_index}: {port_name}")
            return True
        except Exception as e:
            print(f"Failed to open MIDI output: {e}")
            return False

    def close(self):
        """Close MIDI ports"""
        self.stop_recording()
        self.stop_playback()
        if self.midi_in:
            self.midi_in.close_port()
            self.midi_in = None
        if self.midi_out:
            self.midi_out.close_port()
            self.midi_out = None

    def _midi_callback(self, event, data=None):
        """Callback for incoming MIDI messages"""
        if not self.recording:
            return

        message, delta_time = event
        timestamp = time.time() - self.start_time

        # Extract channel from status byte (for channel messages)
        status = message[0]
        if status < 0xF0:  # Channel message
            channel = status & 0x0F
        else:
            channel = 0  # System messages (including transport)

        # Log important messages and track OT start time
        if status == 0xFA:
            print(f"[MIDI IN] Transport START at {timestamp:.2f}s")
            # Capture the first transport start as OT start offset (most reliable)
            if self.ot_start_offset == 0:
                self.ot_start_offset = timestamp
                self._ot_start_source = "Transport START"
                print(f"[MIDI IN] OT start offset captured from Transport START: {timestamp:.2f}s")
        elif status == 0xFC:
            print(f"[MIDI IN] Transport STOP at {timestamp:.2f}s")
            # Capture first stop AFTER start as OT stop time
            if self.ot_start_offset > 0 and self.ot_stop_time == 0:
                self.ot_stop_time = timestamp
                print(f"[MIDI IN] OT stop time captured: {timestamp:.2f}s")
        elif (status & 0xF0) == 0x90:  # Note On (good fallback)
            if self.ot_start_offset == 0:
                self.ot_start_offset = timestamp
                self._ot_start_source = "Note On"
                print(f"[MIDI IN] OT start offset captured from first Note On: {timestamp:.2f}s")

        if (status & 0xF0) == 0xC0:  # Program Change
            channel = (status & 0x0F) + 1
            program = message[1] if len(message) > 1 else 0
            print(f"[MIDI IN] Program Change: ch{channel} prog{program} at {timestamp:.2f}s")

        self.events.append(MIDIEvent(
            timestamp=timestamp,
            channel=channel,
            message=list(message)
        ))

    def start_recording(self):
        """Start recording MIDI events"""
        self.events = []
        self.start_time = time.time()
        self.ot_start_offset = 0  # Reset - will be set when Transport START received
        self.ot_stop_time = 0     # Reset - will be set when Transport STOP received
        self.recording = True

    def stop_recording(self):
        """Stop recording MIDI events"""
        self.recording = False

    def get_track_activity(self) -> dict:
        """Analyze which tracks had MIDI activity"""
        activity = {i: False for i in range(1, 9)}
        for event in self.events:
            # Channels 0-7 map to tracks 1-8
            if event.channel < 8:
                activity[event.channel + 1] = True
        return activity

    def start_playback(self,
                       isolated_track: Optional[int] = None,
                       on_complete: Optional[Callable] = None,
                       duration: float = 0,
                       tail_time: float = 0,
                       on_ready: Optional[Callable] = None,
                       start_pattern: Optional[int] = None,
                       prog_change_channel: int = 16,
                       pre_roll: float = 0,
                       stereo_duration: float = 0):
        """
        Start MIDI playback.

        Args:
            isolated_track: If set, mute all tracks except this one (1-8)
            on_complete: Callback when playback finishes
            duration: Expected duration in seconds (the actual OT content duration)
            tail_time: Extra seconds to wait after playback for effect tails
            on_ready: Callback fired when audio should start (before pre-roll)
            start_pattern: Pattern number (1-16) to send before playback starts
            prog_change_channel: MIDI channel for Program Change (1-16)
            pre_roll: Seconds of silence to wait after audio starts, before OT starts
            stereo_duration: Total stereo recording duration (stems will match this length)
        """
        if not self.midi_out:
            if on_complete:
                on_complete()
            return

        self._stop_playback.clear()
        self._playback_thread = threading.Thread(
            target=self._playback_loop,
            args=(isolated_track, on_complete, duration, tail_time, on_ready, start_pattern, prog_change_channel, pre_roll, stereo_duration),
            daemon=True
        )
        self._playback_thread.start()
        self.playing = True

    def _playback_loop(self,
                       isolated_track: Optional[int],
                       on_complete: Optional[Callable],
                       duration: float,
                       tail_time: float = 0,
                       on_ready: Optional[Callable] = None,
                       start_pattern: Optional[int] = None,
                       prog_change_channel: int = 16,
                       pre_roll: float = 0,
                       stereo_duration: float = 0):
        """Playback thread"""
        auto_ch = prog_change_channel - 1  # 0-indexed for MIDI messages

        # Send isolation mutes BEFORE transport starts
        # The OT needs to receive mutes while stopped so they take effect
        if isolated_track is not None:
            # HARD STOP using OT's Note A1 (33) = Sequencer Stop
            # Need 3 presses: 1st stops sequencer, 2nd+3rd (double-tap) kills delay tails
            # Per OT manual: double-tap stop only works AFTER sequencer is stopped
            self._send_ot_stop(auto_ch)  # Stop 1 - stops sequencer
            time.sleep(0.1)
            self._send_ot_stop(auto_ch)  # Stop 2 - first of double-tap
            time.sleep(0.02)  # Quick double-tap timing
            self._send_ot_stop(auto_ch)  # Stop 3 - kills delay tails
            print("[MIDI] Sent triple-stop (Note A1) to kill delay tails")
            time.sleep(0.5)  # Let delays fully clear

            # Mute ALL tracks
            self._mute_all_tracks()
            time.sleep(0.3)  # Pre-capture silence

            # Now set up isolation (unmute only the solo track)
            self._send_isolation_mutes(isolated_track)
            time.sleep(0.3)  # Give OT time to process mutes before transport

        # Send Bank Select + Program Change to set starting pattern
        # OT uses: CC0 (Bank Select MSB) then Program Change
        # CC0=0 for banks A-H, CC0=1 for banks I-P
        # PC 0-15 = patterns 1-16 in bank A/I, PC 16-31 = bank B/J, etc.
        if start_pattern is not None and prog_change_channel is not None:
            ch = prog_change_channel - 1  # 0-indexed

            # Calculate bank select and program number
            # OT uses 0-indexed: Pattern 1 = PC 0, Pattern 9 = PC 8
            # Bank A (patterns 1-16)
            bank_msb = 0  # Bank A
            prog_num = start_pattern - 1  # 0-indexed (Pattern 9 = PC 8)

            # Send Bank Select (CC 0) - OT uses: 0=Bank A, 1=Bank B, etc.
            self.midi_out.send_message([0xB0 | ch, 0, bank_msb])
            print(f"[MIDI] Sent Bank Select (CC0)={bank_msb} on ch{prog_change_channel}")
            time.sleep(0.02)

            # Send Program Change (1-indexed: 1-16 for patterns 1-16)
            self.midi_out.send_message([0xC0 | ch, prog_num])
            print(f"[MIDI] Sent Program Change {prog_num} on ch{prog_change_channel}")
            time.sleep(0.3)

        # Signal ready - caller can start audio recording NOW
        audio_start_time = None
        if on_ready:
            print("[MIDI] Signaling ready - starting audio capture")
            on_ready()
            audio_start_time = time.time()  # Record when audio actually started
            time.sleep(0.05)  # Brief pause to ensure audio is rolling

        # Pre-roll delay: wait before starting OT to match stereo recording alignment
        # Subtract latency compensation since OT takes time to respond after receiving Start
        effective_pre_roll = max(0, pre_roll - OT_LATENCY_COMPENSATION)
        if effective_pre_roll > 0:
            print(f"[MIDI] Pre-roll: waiting {effective_pre_roll:.2f}s before OT start (original={pre_roll:.2f}s, latency comp={OT_LATENCY_COMPENSATION:.2f}s)")
            time.sleep(effective_pre_roll)

        # Send OT Sequencer Start via Note A#1 (34)
        self._send_ot_start(auto_ch)
        print(f"[MIDI] Sent OT Start (Note A#1) - OT should produce audio in ~{OT_LATENCY_COMPENSATION*1000:.0f}ms")

        # Set playback timer, offset by pre_roll so event timestamps align correctly
        # Event timestamps are relative to jam MIDI recording start (includes pre-roll)
        # By subtracting pre_roll, events sent at correct time relative to OT start
        start_time = time.time() - pre_roll
        event_index = 0

        # Pre-calculate adjusted timestamps for Program Change messages
        # Send PCs early by 20% of pattern duration so OT can queue them
        pc_adjusted_times = self._calculate_pc_lead_times(lead_fraction=0.2)

        # Build a list of PC events to send early, sorted by adjusted time
        # Format: (adjusted_time, event_index, already_sent)
        early_pc_events = [(adj_time, evt_idx, False) for evt_idx, adj_time in pc_adjusted_times.items()]
        early_pc_events.sort(key=lambda x: x[0])  # Sort by adjusted time
        early_pc_sent = set()  # Track which PC events we've already sent

        # Calculate playback duration
        # current_time starts at ~pre_roll when OT starts (due to start_time offset)
        # So we need to add pre_roll to content_duration for the loop exit condition
        content_duration = duration if duration > 0 else (
            self.events[-1].timestamp + 0.5 if self.events else 0
        )
        playback_duration = pre_roll + content_duration  # Loop exits when current_time >= this

        if stereo_duration > 0:
            print(f"[MIDI] Playback: pre_roll={pre_roll:.2f}s + content={content_duration:.2f}s = {playback_duration:.2f}s, target recording={stereo_duration:.2f}s")
        else:
            print(f"[MIDI] Playback duration: {playback_duration:.2f}s (pre_roll={pre_roll:.2f}s + content={content_duration:.2f}s)")

        # Playback loop - replay MIDI events and wait for duration
        while True:
            if self._stop_playback.is_set():
                break

            current_time = time.time() - start_time

            # Check if we've reached the end
            if current_time >= playback_duration:
                break

            # First, check if any early PC events should be sent now
            for adj_time, evt_idx in [(t, i) for t, i, _ in early_pc_events]:
                if evt_idx not in early_pc_sent and current_time >= adj_time:
                    event = self.events[evt_idx]
                    ch = (event.message[0] & 0x0F) + 1
                    prog = event.message[1]
                    print(f"[MIDI] Sending early PC {prog} on ch{ch} (adjusted t={adj_time:.2f}s, now={current_time:.2f}s)")
                    self.midi_out.send_message(event.message)
                    early_pc_sent.add(evt_idx)

            # Send any regular MIDI events that are due
            while event_index < len(self.events):
                event = self.events[event_index]

                # Skip PC events that were already sent early
                if event_index in early_pc_sent:
                    event_index += 1
                    continue

                # For regular events, use original timestamp
                if current_time >= event.timestamp:
                    # Filter mute CCs for non-solo tracks
                    if isolated_track is not None and self._should_filter_event(event, isolated_track):
                        event_index += 1
                        continue  # Skip this event

                    self.midi_out.send_message(event.message)
                    event_index += 1
                else:
                    break

            # Small sleep to avoid busy-waiting
            time.sleep(0.001)

        # Send OT Sequencer Stop via Note A1 (33)
        self._send_ot_stop(auto_ch)
        print("[MIDI] Sent OT Stop (Note A1)")

        # Wait for effect tails to decay (audio keeps recording)
        if tail_time > 0 and not self._stop_playback.is_set():
            print(f"[MIDI] Waiting {tail_time}s for effect tails...")
            time.sleep(tail_time)

        # If stereo_duration was provided, wait until total recording matches stereo length
        # This ensures stems are exactly the same length as the stereo mix
        if stereo_duration > 0 and audio_start_time and not self._stop_playback.is_set():
            # Calculate how much time has elapsed since audio actually started
            elapsed = time.time() - audio_start_time
            remaining = stereo_duration - elapsed
            if remaining > 0:
                print(f"[MIDI] Recording extra {remaining:.2f}s to match stereo length (elapsed={elapsed:.2f}s, target={stereo_duration:.2f}s)")
                time.sleep(remaining)
            else:
                print(f"[MIDI] Audio already at stereo length (elapsed={elapsed:.2f}s, target={stereo_duration:.2f}s)")

        # Signal completion BEFORE unmuting - audio capture ends here
        self.playing = False
        if on_complete and not self._stop_playback.is_set():
            on_complete()

        # Triple-stop before unmuting to kill any remaining delay tails
        if isolated_track is not None:
            # Already sent one stop above, now double-tap to kill delays
            self._send_ot_stop(auto_ch)  # Stop 2
            time.sleep(0.02)
            self._send_ot_stop(auto_ch)  # Stop 3 - kills delay tails
            print("[MIDI] Sent double-tap stop to kill delay tails before unmute")
            time.sleep(0.3)  # Brief settle
            self._unmute_all_tracks()

    def stop_playback(self):
        """Stop MIDI playback"""
        self._stop_playback.set()
        # Send MIDI Stop immediately
        if self.midi_out:
            self.midi_out.send_message([0xFC])
        if self._playback_thread:
            self._playback_thread.join(timeout=1.0)
        self.playing = False

    def _send_isolation_mutes(self, solo_track: int):
        """Mute all tracks except the specified one"""
        port_name = getattr(self, '_output_port_name', 'unknown')
        print(f"[MIDI] Sending isolation mutes for track {solo_track}")
        print(f"[MIDI] Output port: {port_name}")

        for track in range(1, 9):
            # Elektron spec: 0-63 = unmute, 64-127 = mute
            value = 0 if track == solo_track else 127

            # Send CC 49 on each track's channel (this is what worked in manual test)
            track_channel = track - 1  # Track 1 = channel 0, etc.
            msg = [0xB0 | track_channel, 49, value]
            self.midi_out.send_message(msg)

            action = "UNMUTE" if value == 0 else "MUTE"
            print(f"  Track {track}: {action} - CC49={value} on ch{track}")

            # Small delay between messages to let OT process
            time.sleep(0.02)

    def _send_ot_stop(self, auto_ch: int):
        """Send OT Sequencer Stop via Note A1 (33) on auto channel"""
        # Note On then Note Off for clean trigger
        self.midi_out.send_message([0x90 | auto_ch, 33, 100])  # Note On A1
        time.sleep(0.01)
        self.midi_out.send_message([0x80 | auto_ch, 33, 0])    # Note Off A1

    def _send_ot_start(self, auto_ch: int):
        """Send OT Sequencer Start via Note A#1 (34) on auto channel"""
        self.midi_out.send_message([0x90 | auto_ch, 34, 100])  # Note On A#1
        time.sleep(0.01)
        self.midi_out.send_message([0x80 | auto_ch, 34, 0])    # Note Off A#1

    def _mute_all_tracks(self):
        """Mute all tracks (for effect decay before capture)"""
        print(f"[MIDI] Muting all tracks for effect decay")

        for track in range(1, 9):
            # Send CC 49 = 127 (mute) on each track's channel
            track_channel = track - 1
            self.midi_out.send_message([0xB0 | track_channel, 49, 127])
            time.sleep(0.02)

    def _unmute_all_tracks(self):
        """Unmute all tracks"""
        print(f"[MIDI] Unmuting all tracks")

        for track in range(1, 9):
            # Send CC 49 = 0 (unmute) on each track's channel
            track_channel = track - 1
            self.midi_out.send_message([0xB0 | track_channel, 49, 0])
            print(f"  Track {track}: UNMUTE - CC49=0 on ch{track}")
            time.sleep(0.02)

    def _calculate_pc_lead_times(self, lead_fraction: float = 0.2) -> dict:
        """
        Calculate adjusted timestamps for Program Change messages.

        OT queues incoming PC for the next pattern boundary, so we need to send
        them early. We calculate lead time as a fraction of the pattern duration.

        Args:
            lead_fraction: How early to send PC as fraction of pattern duration (0.2 = 20%)

        Returns:
            Dict mapping event index to adjusted timestamp
        """
        adjusted_times = {}

        # Find all PC messages and their indices
        pc_events = []
        for i, event in enumerate(self.events):
            if len(event.message) >= 1 and (event.message[0] & 0xF0) == 0xC0:
                pc_events.append((i, event.timestamp))

        if not pc_events:
            return adjusted_times

        # Calculate pattern durations and adjusted times
        prev_time = 0.0  # Start of recording

        for idx, (event_idx, pc_time) in enumerate(pc_events):
            # Pattern duration is time since last PC (or start)
            pattern_duration = pc_time - prev_time

            # Calculate lead time (fraction of pattern duration)
            lead_time = pattern_duration * lead_fraction

            # Adjusted time = original time - lead time (but not before previous PC)
            adjusted_time = max(prev_time + 0.1, pc_time - lead_time)

            adjusted_times[event_idx] = adjusted_time

            print(f"[MIDI] PC at t={pc_time:.2f}s: pattern lasted {pattern_duration:.2f}s, "
                  f"lead={lead_time:.2f}s, will send at t={adjusted_time:.2f}s")

            prev_time = pc_time

        return adjusted_times

    def _should_filter_event(self, event: MIDIEvent, solo_track: int) -> bool:
        """
        Determine if a MIDI event should be filtered during isolated playback.

        We filter mute CCs (CC 49) for tracks that are NOT the solo track.
        This preserves the solo track's mutes while keeping other tracks muted.
        """
        message = event.message
        if len(message) < 3:
            return False

        status = message[0]
        cc_num = message[1]

        # Check if this is a CC message
        if (status & 0xF0) != 0xB0:
            return False  # Not a CC, don't filter

        channel = (status & 0x0F) + 1  # Convert to 1-indexed

        # CC 49 is track mute
        if cc_num == 49:
            # Filter if this is NOT the solo track
            if channel != solo_track:
                print(f"  [FILTER] Blocking CC49 on ch{channel} (not solo track {solo_track})")
                return True

        return False

    def get_duration(self) -> float:
        """Get duration of recorded MIDI in seconds"""
        if not self.events:
            return 0
        return self.events[-1].timestamp
