"""Styled modal dialogs (the stock tkinter message boxes look out of place)."""

from __future__ import annotations

import tkinter as tk
from typing import Optional, Sequence, Tuple

import customtkinter as ctk

BG = "#12151c"
CARD = "#1a1f2b"
CARD_HI = "#212734"
STROKE = "#2b3342"
TEXT = "#e7ebf3"
MUTED = "#8b94a7"

KIND_COLORS = {
    "info": "#3b82f6",
    "warning": "#f59e0b",
    "error": "#e11d48",
    "success": "#22c55e",
    "question": "#3b82f6",
}
KIND_GLYPHS = {
    "info": "i",
    "warning": "!",
    "error": "\u00d7",
    "success": "\u2713",
    "question": "?",
}


class Dialog(ctk.CTkToplevel):
    """A small dark modal with a coloured status dot and 1-2 buttons."""

    def __init__(
        self,
        parent,
        title: str,
        message: str,
        kind: str = "info",
        buttons: Sequence[Tuple[str, str]] = (("OK", "ok"),),
        width: int = 440,
    ) -> None:
        super().__init__(fg_color=CARD)
        self.withdraw()
        self.result: Optional[str] = None
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.configure(fg_color=CARD)
        self._buttons = buttons

        color = KIND_COLORS.get(kind, KIND_COLORS["info"])
        glyph = KIND_GLYPHS.get(kind, "i")

        wrap = width - 110
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=22, pady=20)
        outer.grid_columnconfigure(1, weight=1)

        badge = ctk.CTkFrame(outer, fg_color=color, width=34, height=34, corner_radius=17)
        badge.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 14))
        badge.grid_propagate(False)
        ctk.CTkLabel(badge, text=glyph, font=ctk.CTkFont(size=17, weight="bold"),
                     text_color="#ffffff").place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(outer, text=title, font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT, anchor="w").grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(outer, text=message, font=ctk.CTkFont(size=12), text_color=MUTED,
                     anchor="w", justify="left", wraplength=wrap).grid(
            row=1, column=1, sticky="ew", pady=(6, 0))

        row = ctk.CTkFrame(outer, fg_color="transparent")
        row.grid(row=2, column=0, columnspan=2, sticky="e", pady=(18, 0))
        for idx, (label, value) in enumerate(reversed(buttons)):
            primary = idx == 0 and len(buttons) == 1
            btn = ctk.CTkButton(
                row, text=label, width=104, height=32, corner_radius=9,
                font=ctk.CTkFont(size=12, weight="bold" if primary else "normal"),
                fg_color=color if primary else CARD_HI,
                hover_color=color if primary else STROKE,
                text_color="#ffffff" if primary else TEXT,
                command=lambda v=value: self._close(v))
            btn.pack(side="right", padx=(8, 0))
        if buttons:
            self.bind("<Return>", lambda _e: self._close(buttons[0][1]))
        self.bind("<Escape>", lambda _e: self._close(buttons[-1][1]))

        self.update_idletasks()
        self._center(parent, width)
        self.deiconify()
        self.attributes("-topmost", True)
        self.after(120, lambda: self.attributes("-topmost", False))
        try:
            self.grab_set()
        except Exception:
            pass

    def _center(self, parent, width: int) -> None:
        self.update_idletasks()
        w = max(width, self.winfo_reqwidth())
        h = self.winfo_reqheight()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 3
        except Exception:
            x = y = 200
        self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

    def _close(self, value: str) -> None:
        self.result = value
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def show(parent, title: str, message: str, kind: str = "info",
         buttons: Sequence[Tuple[str, str]] = (("OK", "ok"),)) -> str:
    """Show a modal dialog and return the chosen button value."""
    try:
        existing = [w for w in parent.winfo_children() if isinstance(w, Dialog)]
        for win in existing:
            win.destroy()
        dlg = Dialog(parent, title, message, kind, buttons)
        parent.wait_window(dlg)
        return dlg.result or buttons[-1][1]
    except Exception:
        # last-resort fallback so a dialog problem never kills the app
        try:
            from tkinter import messagebox

            messagebox.showinfo(title, message)
        except Exception:
            pass
        return buttons[-1][1]


def info(parent, title: str, message: str) -> str:
    return show(parent, title, message, "info")


def success(parent, title: str, message: str) -> str:
    return show(parent, title, message, "success")


def warn(parent, title: str, message: str) -> str:
    return show(parent, title, message, "warning")


def error(parent, title: str, message: str) -> str:
    return show(parent, title, message, "error")


def ask(parent, title: str, message: str, yes: str = "Yes", no: str = "Cancel") -> bool:
    return show(parent, title, message, "question",
                ((yes, "yes"), (no, "no"))) == "yes"


# ``Dialog.warn(...)``-style shortcuts used by the main window
Dialog.info = staticmethod(info)
Dialog.success = staticmethod(success)
Dialog.warn = staticmethod(warn)
Dialog.error = staticmethod(error)
Dialog.ask = staticmethod(ask)
