import subprocess
import sys
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

rcc = os.path.join(
    os.path.dirname(sys.executable),
    "pyside6-rcc.exe"
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

print("STDOUT:\n", result.stdout)
print("STDERR:\n", result.stderr)

result.check_returncode()
