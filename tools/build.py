from pathlib import Path
import subprocess
import sys

def main():
    ROOT = Path.cwd()

    subprocess.run(
        [sys.executable, "tools/generate_version_info.py"],
        check=True
    )

    subprocess.run(
        ["pyinstaller", "pytomator.spec"],
        check=True
    )
