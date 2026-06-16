# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for WorkerBee v2 (onedir Windows build).

Run from this directory:
    pyinstaller WorkerBee_v2.spec

Output lands in `dist/WorkerBee_v2/`. Launch via
`dist/WorkerBee_v2/WorkerBee_v2.exe`. The runtime hook `rthook_v2.py`
patches sys.path at startup so the bundled `src/` package layout
matches the source tree (where v2_launcher.py prepends both the repo
root and `src/` to sys.path).

Asset / data shipping:
- ImageAssets/   -> _MEIPASS/ImageAssets/   (PTH templates, app icon)
- audio/         -> _MEIPASS/audio/
- version       \\
- version.json  /  paths.py reads either (we ship both so legacy
                   _MEIPASS layouts and the new one both work)
- bridge.dll    -> _MEIPASS/bridge/         (alongside bridge.py)
- Help.txt      -> _MEIPASS/Help.txt
"""

import os
import shutil

# Make sure a `version` (no-extension) file exists alongside
# `version.json` so paths.py finds it under _MEIPASS even on builds
# that ship only one of the two.
_root = os.path.dirname(os.path.abspath(SPEC))
_version_json = os.path.join(_root, "version.json")
_version_plain = os.path.join(_root, "version")
if os.path.isfile(_version_json) and not os.path.isfile(_version_plain):
    shutil.copyfile(_version_json, _version_plain)


datas = [
    ("ImageAssets", "ImageAssets"),
    ("audio",        "audio"),
    ("version.json", "."),
    ("version",      "."),
    ("Help.txt",     "."),
    ("app_icon.ico", "."),
    # The bridge package's Python module is auto-collected by Analysis;
    # the DLL is a runtime data file that must sit next to bridge.py.
    ("src/bridge/bridge.dll", "bridge"),
    # Movement model (trained Bezier-control parameters for the bot's
    # mouse trajectories). `wbcore/utils/movement/builder.py` looks for
    # it next to itself via `os.path.dirname(__file__)`, so it MUST
    # land at `_MEIPASS/wbcore/utils/movement/model.npz` after the
    # Phase A `automation` -> `wbcore` rename.
    ("src/wbcore/utils/movement/model.npz",
     "wbcore/utils/movement"),
]

binaries = []

hiddenimports = [
    # PySide6 sub-modules that pyinstaller's static scan misses on
    # some platforms.
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtMultimedia",
    # The audio backend uses pygame.
    "pygame",
    "pygame.mixer",
    # Discord bot integration.
    "discord",
    "discord.ext",
    "discord.ext.commands",
    "aiohttp",
    # opencv + mss for the capture path.
    "cv2",
    "mss",
    "mss.tools",
    "numpy",
    # Bridge for input.
    "bridge",
    "bridge.bridge",
    # Our own packages.
    "wbcore",
    "gui_v2",
    "audio_manager",
    "discord_integration",
    "secret_store",
]


a = Analysis(
    ["v2_launcher.py"],
    pathex=[".", "src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["rthook_v2.py"],
    excludes=[
        # We ship our own logging config; drop unrelated test/dev deps.
        "pytest", "tkinter", "customtkinter", "PyQt5",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WorkerBee_v2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # UPX produces false-positive AV hits
    console=False,
    disable_windowed_traceback=False,
    icon="app_icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="WorkerBee_v2",
)
