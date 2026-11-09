"""Tiny JSON-backed settings store + file naming helpers."""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

APP_NAME = "AudioCapture"
APP_TITLE = "Audio Capture Studio"


def music_dir() -> Path:
    """Best-effort user Music folder."""
    home = Path.home()
    for name in ("Music", "Musique", "Musik", "Muzyka", "Música", "Muziek"):
        candidate = home / name
        if candidate.is_dir():
            return candidate
    return home


def default_recordings_dir() -> Path:
    return music_dir() / "Audio Capture"


def settings_path() -> Path:
    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home() / ".config")
    return Path(base) / APP_NAME / "settings.json"


DEFAULTS: Dict[str, Any] = {
    "output_dir": str(default_recordings_dir()),
    "filename_pattern": "Recording {date} {time}",
    "samplerate": None,  # None = follow the device's native rate
    "channels": 2,
    "container": "WAV",  # exact float32 capture; choose FLAC explicitly to compress
    "url_file_mode": "separate",  # one file per URL unless user chooses combined
    "url_autoplay": True,  # best-effort site-specific autoplay request
    "device_id": None,
    "device_kind": "loopback",
    "volume": 0.85,
    "appearance": "dark",
}


class Settings:
    def __init__(self) -> None:
        self._path = settings_path()
        self.data = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                self.data.update({k: v for k, v in stored.items() if k in DEFAULTS})
        except Exception:
            pass

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2)
            os.replace(tmp, self._path)
        except Exception:
            pass

    def __getitem__(self, key: str) -> Any:
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key: str, value: Any) -> None:
        if self.data.get(key) != value:
            self.data[key] = value
            self.save()


# --------------------------------------------------------------------------- #
#  File naming
# --------------------------------------------------------------------------- #
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(name: str, fallback: str = "Recording") -> str:
    name = _ILLEGAL.sub("", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    return name[:120] or fallback


def build_filename(pattern: str, when: datetime | None = None) -> str:
    when = when or datetime.now()
    out = pattern
    mapping = {
        "{date}": when.strftime("%Y-%m-%d"),
        "{time}": when.strftime("%H.%M.%S"),
        "{datetime}": when.strftime("%Y-%m-%d %H.%M.%S"),
        "{day}": when.strftime("%d"),
        "{month}": when.strftime("%m"),
        "{year}": when.strftime("%Y"),
        "{YYYY}": when.strftime("%Y"),
        "{MM}": when.strftime("%m"),
        "{DD}": when.strftime("%d"),
        "{hh}": when.strftime("%H"),
        "{mm}": when.strftime("%M"),
        "{ss}": when.strftime("%S"),
    }
    for token, value in mapping.items():
        out = out.replace(token, value)
    return sanitize(out)


def unique_path(directory: Path, stem: str, ext: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stem}{ext}"
    if not candidate.exists():
        return candidate
    for i in range(2, 10000):
        candidate = directory / f"{stem} ({i}){ext}"
        if not candidate.exists():
            return candidate
    return directory / f"{stem}-{int(time.time())}{ext}"


# --------------------------------------------------------------------------- #
#  OS integration
# --------------------------------------------------------------------------- #
def open_in_file_manager(path: str) -> None:
    """Reveal a file in Explorer / the desktop file manager."""
    path = os.path.abspath(path)
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", path])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            if os.path.isfile(path):
                path = os.path.dirname(path)
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def open_with_default_app(path: str) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def list_recordings(directory: str) -> list[str]:
    """All audio files in ``directory``, newest first."""
    out = []
    for pattern in ("*.wav", "*.flac", "*.ogg", "*.mp3", "*.m4a", "*.aiff"):
        out.extend(glob.glob(os.path.join(directory, pattern)))
    out.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
    return out


def human_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.0f} {unit}" if unit in ("B", "KB") else f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"


def human_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
