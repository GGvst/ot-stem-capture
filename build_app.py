#!/usr/bin/env python3
"""Build script for creating macOS app bundle"""

import subprocess
import sys
import os

def main():
    # Ensure we're in the project directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Check if PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=OT Stem Capture",
        "--windowed",  # No console window
        "--onedir",    # Create a directory with all files (faster startup than onefile)
        "--noconfirm", # Overwrite without asking
        "--clean",     # Clean cache before building

        # Hidden imports that PyInstaller might miss
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtWidgets",
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=rtmidi",
        "--hidden-import=sounddevice",
        "--hidden-import=soundfile",
        "--hidden-import=numpy",

        # Collect all data from these packages
        "--collect-all=sounddevice",
        "--collect-all=soundfile",

        # Entry point
        "run.py"
    ]

    print("Building OT Stem Capture.app...")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("\n" + "="*50)
        print("Build successful!")
        print("App location: dist/OT Stem Capture.app")
        print("\nTo install, drag the app to your Applications folder.")
        print("="*50)
    else:
        print("\nBuild failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
