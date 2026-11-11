# -*- mode: python ; coding: utf-8 -*-
# pyqt6_learning_studio/packaging/pyqt6_learning_studio.spec
# PyInstaller recept: python3 -m PyInstaller packaging/pyqt6_learning_studio.spec
# (ili packaging/build_pyinstaller.sh, koji paket i proverava).
#
# Paket je „one-dir“ (folder sa izvršnim fajlom). Korisnikov kod pokreće Python
# sa sistema, a ako ga nema — Python ugrađen u paket (vidi core/python_locator.py).
# Za taj slučaj u paket su dodati i moduli standardne biblioteke koje kurs koristi.
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH zadaje PyInstaller

datas = [
    (str(ROOT / "data"), "data"),
    (str(ROOT / "resources"), "resources"),
    (str(ROOT / "database" / "schema.sql"), "database"),
]

# Moduli koje korisnikov kod u lekcijama može da koristi kada radi „ugrađeni“ Python.
course_stdlib = [
    "random", "math", "statistics", "decimal", "fractions", "json", "csv", "sqlite3",
    "datetime", "time", "calendar", "string", "textwrap", "re", "collections",
    "itertools", "functools", "pathlib", "os", "shutil", "tempfile", "unittest",
    "dataclasses", "enum", "typing", "copy", "pprint",
]

a = Analysis(  # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=["PyQt6.Qsci", "PyQt6.QtSvg", *course_stdlib],
    excludes=["tkinter", "pytest", "_pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pyqt6-learning-studio",
    console=True,  # potrebno da bi „ugrađeni“ Python imao stdout/stderr (i na Windows-u)
    disable_windowed_traceback=False,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    name="pyqt6-learning-studio",
)
