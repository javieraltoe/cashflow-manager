# PyInstaller · CashFlow Manager (carpeta ejecutable, sin consola).
# Uso: .\scripts\build\build-desktop.ps1   (o: pyinstaller desktop\packaging\cashflow.spec)
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

PACKAGING = Path(SPECPATH)
ROOT = PACKAGING.parents[1]
ICON = str(PACKAGING / "cashflow.ico")

a = Analysis(
    [str(ROOT / "desktop" / "run_desktop.py")],
    pathex=[str(ROOT)],
    binaries=[],
    # tzdata: Windows no trae base de zonas horarias (fechas de Buenos Aires).
    datas=[(ICON, "assets")] + collect_data_files("tzdata"),
    hiddenimports=["tzdata", "truststore"],
    excludes=["tkinter", "pytest", "fastapi", "sqlalchemy"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CashFlowManager",
    console=False,
    icon=ICON,
    version=str(PACKAGING / "version_info.txt"),
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="CashFlowManager",
)
