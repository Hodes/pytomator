import subprocess
import sys
import os

def main():
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    rccbin = "pyside6-rcc"
    if sys.platform == "win32":
        rccbin += ".exe"

    rcc = os.path.join(
        os.path.dirname(sys.executable),
        rccbin
    )

    qrc = os.path.join(
        ROOT, "src", "pytomator", "resources", "resources.qrc"
    )

    out = os.path.join(
        ROOT, "src", "pytomator", "resources", "resources_rc.py"
    )

    result = subprocess.run(
        [rcc, qrc, "-o", out],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    print("Running command:", ' '.join([rcc, qrc, "-o", out]))
    if result.stdout:
        print("STDOUT:\n", result.stdout)
    if result.stderr:
        print("STDERR:\n", result.stderr)

    result.check_returncode()
