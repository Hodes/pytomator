from pathlib import Path
import tomllib

def main():
    ROOT = Path.cwd()

    pyproject = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    version = pyproject["tool"]["poetry"]["version"]
    major, minor, patch = version.split(".")

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

    print(f"Version info generated ({version})")
