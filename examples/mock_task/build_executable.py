"""
Helper script to prepare the mock task for ReBuilder testing.
Since this is a Python script, we just copy it as the executable.
On Unix systems you might use PyInstaller; on Windows we can just run it via Python.

Usage:
    python build_executable.py
    # Then test with: python program.py --help
"""

import shutil
import sys
from pathlib import Path


def main():
    script_dir = Path(__file__).parent
    program_py = script_dir / "program.py"
    
    if not program_py.exists():
        print("program.py not found!")
        sys.exit(1)
    
    # For ReBuilder testing, we'll create a batch wrapper that runs the Python script
    # This simulates an "executable" that ReBuilder can probe
    if sys.platform == "win32":
        batch = script_dir / "program.bat"
        batch.write_text(f'@echo off\npython "{program_py}" %*\n')
        print(f"Created: {batch}")
        # Also copy as "program.exe" dummy for detection
        exe = script_dir / "program.exe"
        shutil.copy(batch, exe)
        print(f"Created: {exe}")
    else:
        # Unix: make it executable
        import stat
        program_py.chmod(program_py.stat().st_mode | stat.S_IEXEC)
        print(f"Made executable: {program_py}")


if __name__ == "__main__":
    main()
