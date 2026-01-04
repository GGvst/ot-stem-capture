# OT Stem Capture

A macOS application for capturing isolated stem recordings from the Elektron Octatrack. Record a jam session, then automatically capture each track as a separate stem file - perfect for mixing in your DAW.

## How It Works

1. **Record your jam** - Play your Octatrack while the app records MIDI and audio
2. **Select tracks** - Choose which tracks to capture as stems
3. **Automatic capture** - The app replays your MIDI, muting all tracks except the one being captured, recording each stem in isolation

The stems are automatically aligned with your original stereo mix, so you can drop them into your DAW at the same position.

## Features

- Records MIDI and audio simultaneously during jam session
- Detects active tracks from MIDI data
- Isolates tracks using CC49 (track mute) messages
- Handles pattern changes during capture
- Kills delay/reverb tails between captures (triple-stop method)
- Configurable effect tail time for long reverbs/delays
- Dual stereo support (main + cue outputs)
- Dark UI designed to match Elektron aesthetic

## Requirements

### Hardware
- Elektron Octatrack (tested with MKI, should work with MKII)
- Audio interface with at least 2 inputs
- MIDI interface (USB or DIN)

### Octatrack Setup
1. **MIDI Output** - Connect OT MIDI OUT to your computer
2. **MIDI Input** - Connect computer MIDI OUT to OT MIDI IN
3. **Audio** - Connect OT main outputs to your audio interface inputs
4. **Transport Send** - Enable in OT settings (PROJECT > MIDI > SYNC > TRANSPORT SEND)
   - This allows the app to detect when OT starts/stops for accurate alignment
5. **Auto Channel** - Note which channel is set (default: 11) - used for transport control
6. **Audio CC In + Out** - Enable both
7. **Prog Ch** - Send and Receive on. Use same channel as for transport send.

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/GGvst/ot-stem-capture.git
cd ot-stem-capture

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run
python run.py
```

### macOS App

Download the latest `.app` from the Releases page.

## Usage

1. **Configure devices** - Expand the Device Configuration panel and select your MIDI and audio devices
2. **Set channel inputs** - Choose which audio interface inputs receive OT's main outputs
3. **Set start pattern** - The pattern number to begin stem capture from
4. **Set PC channel** - The MIDI channel for Program Change messages (usually your Auto Channel)
5. **Set tail time** - Extra recording time after playback for reverb/delay tails (0-5 seconds)

### Recording a Jam

1. Click the record button
2. Press play on your Octatrack and perform your jam
3. Press stop on the Octatrack when done
4. Click the record button again to stop recording
5. Select which tracks to capture as stems
6. Reload Part on the Octatrack (resets knob positions)
7. Click "Capture Stems" - the app handles the rest

### Output Files

Sessions are saved to `~/Music/OT Sessions/` by default:

```
session_20240115_143022/
  stereo_mix.wav      # Full stereo recording of your jam
  track_1.wav         # Isolated stem for track 1
  track_2.wav         # Isolated stem for track 2
  ...
  session.json        # Metadata (timing, sample rate, etc.)
```

## Tips

- **Reload Part before capture** - This resets all knob positions to their saved state, ensuring stems match the original recording
- **Use Transport Send** - Enables accurate timing alignment between stereo mix and stems
- **Set appropriate tail time** - If you have long delays/reverbs, increase the tail time
- **Monitor levels** - Use the level meters to ensure you're not clipping

## Known Limitations

- ~100ms timing offset between stereo and stems is normal (can be nudged in DAW if needed)
- Neighbor machines and pickup machines may not isolate perfectly
- Scene/crossfader automation during the jam is not captured

## Troubleshooting

### No MIDI devices showing
- Check that your MIDI interface is connected
- Try refreshing the device list

### Stems don't match stereo timing
- Ensure Transport Send is enabled on the Octatrack
- The app uses Transport START/STOP messages for alignment

### Delay tails bleeding between stems
- The app sends triple-stop (Note A1) to kill delays
- If still hearing bleed, increase the silence time between captures in the code

## Technical Details

- Built with PyQt6 for the UI
- Uses python-rtmidi for MIDI I/O
- Uses sounddevice + soundfile for audio recording
- Track isolation via CC49 (Elektron track mute standard)
- Transport control via Note A1 (stop) and Note A#1 (start)

## License

MIT License - See LICENSE file

## Contributing

Contributions welcome! Please open an issue first to discuss what you'd like to change.

## Acknowledgments

- Built for the Elektronauts community
- Inspired by the need to get stems out of the Octatrack for mixing
