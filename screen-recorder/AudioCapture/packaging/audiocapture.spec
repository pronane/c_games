# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir build for Windows; run from build_windows.bat."""
import os
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(SPEC)), ".."))

datas, binaries, hiddenimports = [], [], [
    "audiocapture", "audiocapture.audio", "audiocapture.recorder",
    "audiocapture.ui", "audiocapture.waveform", "audiocapture.dialogs",
    "audiocapture.settings", "audiocapture.url_source",
    "audiocapture.web_playlists", "audiocapture.editing",
    "audiocapture.ffmpeg_support", "soundcard", "imageio_ffmpeg",
]
# Pull package data and optional/native imports needed by the packaged runtime.
for package in ("customtkinter", "soundfile", "soundcard", "imageio_ffmpeg"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(ROOT, "audiocapture_app.py")], pathex=[ROOT],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["matplotlib", "scipy", "pandas", "PIL.ImageQt", "PyQt5", "PySide2"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="AudioCaptureStudio", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
    icon=os.path.join(ROOT, "packaging", "app.ico")
    if os.path.exists(os.path.join(ROOT, "packaging", "app.ico")) else None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
               strip=False, upx=False, name="AudioCaptureStudio")
