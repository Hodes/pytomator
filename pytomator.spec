# -*- mode: python ; coding: utf-8 -*-
import tomllib
from pathlib import Path
import platform

ROOT = Path.cwd()

pyproject = tomllib.loads(
    (ROOT / "pyproject.toml").read_text(encoding="utf-8")
)

os_name = "windows"
arch = "x64"

so = platform.system()
if so == "Windows":
    os_name = "windows"
elif so == "Darwin":
    os_name = "macos"
elif so == "Linux":
    os_name = "linux"
else:
    os_name = "unknown"

version = pyproject["tool"]["poetry"]["version"]
exe_name = f"Pytomator-{version}-{os_name}-{arch}"


a = Analysis(
    ['src\\pytomator\\app.py'],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=exe_name,
    icon='assets/app.ico',
    version='assets/version_info.txt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
