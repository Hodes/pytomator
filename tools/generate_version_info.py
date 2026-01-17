from pathlib import Path
import tomllib

ROOT = Path.cwd()

# ROOT = Path(__file__).resolve().parent
PYPROJECT = ROOT / "pyproject.toml"
INIT_FILE = ROOT / "src" / "pytomator" / "__init__.py"

def main():
    with PYPROJECT.open("rb") as f:
      data = tomllib.load(f)
    version = data["tool"]["poetry"]["version"]
    major, minor, patch = version.split(".")
    
    update_version_info(version, major, minor, patch)
    update_app_version(version)
  
def update_version_info(version, major, minor, patch):
    content = f"""
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major},{minor},{patch},0),
    prodvers=({major},{minor},{patch},0),
    mask=0x3f,
    flags=0x0,
    OS=0x4,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', 'Henrique Otavio'),
            StringStruct('FileDescription', 'Python script automation tool'),
            StringStruct('FileVersion', '{version}'),
            StringStruct('InternalName', 'Pytomator'),
            StringStruct('ProductName', 'Pytomator'),
            StringStruct('ProductVersion', '{version}'),
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""".strip()

    out = ROOT / "tools" / "version_info.txt"
    out.write_text(content, encoding="utf-8")
    
    print(f"✅ Version info generated ({version})")
    
def update_app_version(version):
  content = f'''# Auto-generated
# Do not edit manually

__version__ = "{version}"
'''
  INIT_FILE.parent.mkdir(parents=True, exist_ok=True)
  INIT_FILE.write_text(content, encoding="utf-8")
  print(f"✅ Updated __init__.py with version {version}")