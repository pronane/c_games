"""Entry point: ``python -m audiocapture`` / ``python audiocapture_app.py``."""

from __future__ import annotations

import sys


def run() -> int:
    try:
        from .ui import main
    except ImportError:  # running the file directly from the package folder
        import os

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from audiocapture.ui import main  # type: ignore
    try:
        main()
        return 0
    except Exception as exc:  # pragma: no cover - last-resort crash handler
        import traceback

        traceback.print_exc()
        try:
            import tkinter.messagebox as mb
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            mb.showerror(
                "Audio Capture Studio",
                f"The application could not start:\n\n{exc}\n\n"
                "See the console output for details.",
            )
            root.destroy()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
