# PyInstaller (Windows y macOS):  pyinstaller packaging/pyinstaller/simplepostit.spec
# Crea dist/SimplePost-It/ (Windows) o dist/SimplePost-It.app (macOS). Requiere Pillow para el ícono.
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
with open(os.path.join(ROOT, "simplepostit.py"), encoding="utf-8") as f:
    VERSION = re.search(r'^VERSION = "(.+)"', f.read(), re.M).group(1)
ICON = os.path.join(ROOT, "data", "simplepostit.png")

a = Analysis(
    [os.path.join(ROOT, "simplepostit.py")],
    datas=[(os.path.join(ROOT, "i18n"), "i18n")],
    hiddenimports=["AppKit", "objc"] if sys.platform == "darwin" else [],
    excludes=["tkinter", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtQml",
              "PyQt6.QtQuick", "PyQt6.QtMultimedia", "PyQt6.QtPdf", "PyQt6.Qt3DCore"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SimplePost-It", console=False, icon=ICON)
coll = COLLECT(exe, a.binaries, a.datas, name="SimplePost-It")
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="SimplePost-It.app",
        icon=ICON,
        bundle_identifier="com.frankmncrf.simplepostit",
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSUIElement": True,             # vive en la barra de menús, sin ícono en el Dock
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "© 2026 FrankMncrf — GPL-3.0-or-later",
        },
    )
