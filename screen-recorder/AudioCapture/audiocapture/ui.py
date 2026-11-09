"""Audio Capture Studio - CustomTkinter user interface."""

from __future__ import annotations

import os
import platform
import sys
import threading
import time
import tempfile
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk

from .audio import (
    DEFAULT_RATE,
    AudioEngine,
    BackendError,
    Device,
    describe_channels,
    format_rate,
    rate_choices,
)
from .recorder import (
    AudioFile,
    Player,
    Recorder,
    RecordingInfo,
)
from .settings import (
    APP_TITLE,
    Settings,
    build_filename,
    human_size,
    human_time,
    list_recordings,
    music_dir,
    open_in_file_manager,
    open_with_default_app,
    unique_path,
)
from .dialogs import Dialog
from .waveform import Waveform
from .editing import AudioEditSession
from .url_source import validate_web_url, url_recording_stem, autoplay_url

# ---------------------------------------------------------------- palette ---
BG = "#12151c"
CARD = "#1a1f2b"
CARD_HI = "#212734"
STROKE = "#2b3342"
TEXT = "#e7ebf3"
MUTED = "#8b94a7"
ACCENT = "#e11d48"        # record red
ACCENT_HOVER = "#f43f5e"
BLUE = "#3b82f6"
BLUE_HOVER = "#60a5fa"
GREEN = "#22c55e"
CYAN = "#22d3ee"
WARN = "#f59e0b"

FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
MONO = "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono"

__version__ = "1.0.0"


def _f(size: int, weight: str = "normal", family: str = FONT):
    return ctk.CTkFont(family=family, size=size, weight=weight)


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=BG)
        self.title(f"{APP_TITLE}  v{__version__}")
        self.geometry("1180x780")
        self.minsize(1040, 700)
        try:
            self.iconbitmap(default="")  # harmless if missing
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.settings = Settings()
        ctk.set_appearance_mode(self.settings["appearance"])

        self.engine = AudioEngine()
        self.devices: list[Device] = []
        self.recorder: Optional[Recorder] = None
        self.info: Optional[RecordingInfo] = None
        self.live_file: Optional[AudioFile] = None
        self.player = Player(on_finish=self._on_play_finish, on_error=self._on_play_error)
        self.file_audio: Optional[AudioFile] = None
        self._ui_queue: list = []
        self._closing = False
        self._rec_started_monotonic = 0.0
        self._last_wave_paint = 0.0
        self._scrub_active = False
        # URL lists are deliberately session-only: they may contain signed URLs
        # or query tokens and should not be written to settings/logs.
        self._web_url_items: list[tuple[str, str]] = []
        self._web_selected_index = -1
        self._web_opened_index = -1
        self._pending_web_next: Optional[int] = None
        self._web_listbox = None
        self._web_waiting_audio = False
        self._web_audio_hits = 0
        self._web_url_manager = None

        self._build_ui()
        self._bind_shortcuts()
        self.after(80, self._initial_load)
        self.after(33, self._ui_tick)

    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-r>", lambda _e: self.toggle_record() or "break")
        self.bind_all("<Control-R>", lambda _e: self.toggle_record() or "break")
        self.bind_all("<Control-space>", lambda _e: self.toggle_play() or "break")
        self.bind_all("<Control-o>", lambda _e: self.open_file_dialog() or "break")
        self.bind_all("<Control-s>", lambda _e: self.choose_dir() or "break")
        self.bind_all("<Left>", self._seek_key)
        self.bind_all("<Right>", self._seek_key)
        self.bind_all("<Home>", lambda _e: self.player.loaded and self.player.seek(0))
        self.bind_all("<space>", self._space_key)

    def _typing(self, event) -> bool:
        try:
            return isinstance(event.widget, (ctk.CTkEntry, tk.Entry))
        except Exception:
            return False

    def _space_key(self, event):
        if self._typing(event):
            return None
        if self.focus_get() is not None and "entry" in str(self.focus_get()).lower():
            return None
        self.toggle_play()
        return "break"

    def _seek_key(self, event):
        if self._typing(event) or not self.player.loaded:
            return None
        delta = -5.0 if str(event.keysym) == "Left" else 5.0
        if event.state & 0x1:  # Shift = 1 second steps
            delta /= 5.0
        self.player.seek_relative(delta)
        self._sync_progress(self.player.position)
        return "break"

    # =====================================================================
    #  Layout
    # =====================================================================
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ---------- header ----------
        header = ctk.CTkFrame(self, fg_color="transparent", height=64)
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 4))
        header.grid_columnconfigure(1, weight=1)

        logo = ctk.CTkFrame(header, fg_color=ACCENT, width=38, height=38, corner_radius=11)
        logo.grid(row=0, column=0, padx=(0, 12), pady=6)
        logo.grid_propagate(False)
        ctk.CTkLabel(logo, text="\u25CF", font=_f(17, "bold"), text_color="#ffffff").place(
            relx=0.5, rely=0.5, anchor="center"
        )

        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(titles, text="Audio Capture Studio", font=_f(21, "bold"),
                     text_color=TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            titles,
            text="Records your speaker output in full quality \u2014 or the microphone if you prefer",
            font=_f(12), text_color=MUTED, anchor="w").pack(anchor="w")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e")
        self.quality_chip = ctk.CTkLabel(
            right, text="", font=_f(12, "bold"), text_color=CYAN,
            fg_color=CARD, corner_radius=9, padx=12, height=30)
        self.quality_chip.pack(side="left", padx=(0, 8))

        self.refresh_btn = ctk.CTkButton(
            right, text="\u21BB  Refresh devices", width=132, height=32, corner_radius=9,
            fg_color=CARD, hover_color=CARD_HI, text_color=TEXT, font=_f(12),
            border_width=1, border_color=STROKE, command=self.refresh_devices)
        self.refresh_btn.pack(side="left")

        # ---------- body ----------
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=22, pady=(8, 16))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_left(body)
        self._build_right(body)

    # ------------------------------------------------------------ left card
    def _build_left(self, parent) -> None:
        card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=16, width=340,
                            border_width=1, border_color=STROKE)
        card.grid(row=0, column=0, sticky="nsw", padx=(0, 16))
        card.grid_propagate(False)
        card.grid_columnconfigure(0, weight=1)

        pad = {"padx": 20}
        ctk.CTkLabel(card, text="What to record", font=_f(13, "bold"), text_color=TEXT,
                     anchor="w").grid(row=0, column=0, sticky="ew", pady=(18, 6), **pad)

        self.mode_switch = ctk.CTkSegmentedButton(
            card, values=["System audio", "Microphone", "Web URL"],
            font=_f(12, "bold"), height=32, corner_radius=8,
            selected_color=BLUE, selected_hover_color=BLUE_HOVER,
            unselected_color=CARD_HI, unselected_hover_color=STROKE,
            text_color=TEXT, command=self._on_mode_change)
        self.mode_switch.grid(row=1, column=0, sticky="ew", pady=(0, 8), **pad)
        self.mode_switch.set("System audio")

        ctk.CTkLabel(card, text="OUTPUT DEVICE", font=_f(10, "bold"), text_color=MUTED,
                     anchor="w").grid(row=2, column=0, sticky="ew", pady=(10, 4), **pad)
        self.device_menu = ctk.CTkOptionMenu(
            card, values=["Detecting devices\u2026"], font=_f(12), height=34,
            corner_radius=8, fg_color=CARD_HI, button_color=STROKE,
            button_hover_color="#39435a", dropdown_fg_color=CARD_HI,
            dropdown_hover_color=STROKE, dropdown_font=_f(12), text_color=TEXT,
            anchor="w", command=self._on_device_change)
        self.device_menu.grid(row=3, column=0, sticky="ew", **pad)

        self.device_sub = ctk.CTkLabel(card, text="", font=_f(11), text_color=MUTED,
                                       anchor="w", justify="left", wraplength=290)
        self.device_sub.grid(row=4, column=0, sticky="ew", pady=(4, 10), **pad)

        ctk.CTkFrame(card, height=1, fg_color=STROKE).grid(row=5, column=0, sticky="ew",
                                                          pady=(2, 12), **pad)

        ctk.CTkLabel(card, text="RECORDING QUALITY", font=_f(10, "bold"), text_color=MUTED,
                     anchor="w").grid(row=6, column=0, sticky="ew", pady=(0, 4), **pad)
        self.rate_menu = ctk.CTkOptionMenu(
            card, values=["48,000 Hz"], font=_f(12), height=34, corner_radius=8,
            fg_color=CARD_HI, button_color=STROKE, button_hover_color="#39435a",
            dropdown_fg_color=CARD_HI, dropdown_hover_color=STROKE, dropdown_font=_f(12),
            text_color=TEXT, anchor="w", command=self._on_quality_change)
        self.rate_menu.grid(row=7, column=0, sticky="ew", pady=(0, 10), **pad)

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.grid(row=8, column=0, sticky="ew", **pad)
        row.grid_columnconfigure((0, 1), weight=1)
        self.channel_menu = ctk.CTkOptionMenu(
            row, values=["Stereo", "Mono"], font=_f(12), height=34, corner_radius=8,
            fg_color=CARD_HI, button_color=STROKE, button_hover_color="#39435a",
            dropdown_fg_color=CARD_HI, dropdown_hover_color=STROKE, dropdown_font=_f(12),
            text_color=TEXT, anchor="w", command=self._on_quality_change)
        self.channel_menu.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.format_menu = ctk.CTkOptionMenu(
            row, values=["WAV", "FLAC"], font=_f(12), height=34, corner_radius=8,
            fg_color=CARD_HI, button_color=STROKE, button_hover_color="#39435a",
            dropdown_fg_color=CARD_HI, dropdown_hover_color=STROKE, dropdown_font=_f(12),
            text_color=TEXT, anchor="w", command=self._on_quality_change)
        self.format_menu.grid(row=0, column=1, sticky="ew")

        self.quality_hint = ctk.CTkLabel(
            card, text="", font=_f(11), text_color=MUTED, anchor="w", justify="left",
            wraplength=290)
        self.quality_hint.grid(row=9, column=0, sticky="ew", pady=(8, 10), **pad)

        ctk.CTkFrame(card, height=1, fg_color=STROKE).grid(row=10, column=0, sticky="ew",
                                                          pady=(2, 12), **pad)

        ctk.CTkLabel(card, text="SAVE TO", font=_f(10, "bold"), text_color=MUTED,
                     anchor="w").grid(row=11, column=0, sticky="ew", pady=(0, 4), **pad)
        pathrow = ctk.CTkFrame(card, fg_color="transparent")
        pathrow.grid(row=12, column=0, sticky="ew", **pad)
        pathrow.grid_columnconfigure(0, weight=1)
        self.dir_label = ctk.CTkLabel(pathrow, text="", font=_f(11), text_color=TEXT,
                                      anchor="w", justify="left", wraplength=230)
        self.dir_label.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(pathrow, text="Change", width=66, height=28, corner_radius=8,
                      fg_color=CARD_HI, hover_color=STROKE, text_color=TEXT,
                      font=_f(11), command=self.choose_dir).grid(row=0, column=1, padx=(8, 0))

        ctk.CTkLabel(card, text="FILE NAME", font=_f(10, "bold"), text_color=MUTED,
                     anchor="w").grid(row=13, column=0, sticky="ew", pady=(14, 4), **pad)
        self.name_entry = ctk.CTkEntry(
            card, font=_f(12), height=32, corner_radius=8, fg_color=CARD_HI,
            border_color=STROKE, text_color=TEXT)
        self.name_entry.grid(row=14, column=0, sticky="ew", **pad)
        self.name_entry.bind("<KeyRelease>", lambda _e: self._update_name_preview())
        self.name_preview = ctk.CTkLabel(card, text="", font=_f(11), text_color=MUTED,
                                        anchor="w", justify="left", wraplength=290)
        self.name_preview.grid(row=15, column=0, sticky="ew", pady=(4, 10), **pad)
        ctk.CTkLabel(card, text="Tokens: {date} {time} {datetime}", font=_f(10),
                     text_color="#5b6478", anchor="w").grid(row=16, column=0, sticky="ew",
                                                            pady=(0, 14), **pad)
        card.grid_rowconfigure(17, weight=1)

        self.source_note = ctk.CTkLabel(
            card, text="", font=_f(11), text_color=MUTED, anchor="w", justify="left",
            wraplength=290)
        self.source_note.grid(row=18, column=0, sticky="ew", pady=(0, 16), **pad)

    # ----------------------------------------------------------- right side
    def _build_right(self, parent) -> None:
        right = ctk.CTkFrame(parent, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        # ---------------- recorder card ----------------
        rec = ctk.CTkFrame(right, fg_color=CARD, corner_radius=16, border_width=1,
                           border_color=STROKE)
        rec.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        rec.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(rec, fg_color="transparent")
        left.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(20, 10), pady=16)

        self.rec_button = ctk.CTkButton(
            left, text="\u25CF   Record", width=170, height=52, corner_radius=14,
            font=_f(17, "bold"), fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="#ffffff", command=self.toggle_record)
        self.rec_button.pack(anchor="w")
        self.pause_btn = ctk.CTkButton(
            left, text="Pause", width=170, height=30, corner_radius=9,
            font=_f(12, "bold"), fg_color=CARD_HI, hover_color=STROKE,
            text_color=TEXT, state="disabled", command=self.toggle_pause)
        self.pause_btn.pack(anchor="w", pady=(7, 0))
        self.status_label = ctk.CTkLabel(left, text="Ready", font=_f(11, "bold"),
                                        text_color=MUTED, anchor="w")
        self.status_label.pack(anchor="w", pady=(8, 0))

        mid = ctk.CTkFrame(rec, fg_color="transparent")
        mid.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=6, pady=16)
        mid.grid_columnconfigure(0, weight=1)
        self.time_label = ctk.CTkLabel(mid, text="00:00", font=_f(40, "bold", MONO),
                                      text_color=TEXT, anchor="w")
        self.time_label.grid(row=0, column=0, sticky="w")
        self.meter_canvas = tk.Canvas(mid, height=16, bg=CARD, highlightthickness=0)
        self.meter_canvas.grid(row=1, column=0, sticky="ew", pady=(6, 4))
        self.meter_canvas.bind("<Configure>", lambda _e: self._draw_meter(0.0, 0.0))
        self.meter_text = ctk.CTkLabel(mid, text="Level meter", font=_f(11),
                                      text_color=MUTED, anchor="w")
        self.meter_text.grid(row=2, column=0, sticky="w")

        stats = ctk.CTkFrame(rec, fg_color="transparent")
        stats.grid(row=0, column=2, rowspan=2, sticky="e", padx=(10, 20), pady=16)
        self.size_label = ctk.CTkLabel(stats, text="0.0 MB", font=_f(15, "bold"),
                                      text_color=TEXT, anchor="e")
        self.size_label.pack(anchor="e")
        self.stream_label = ctk.CTkLabel(stats, text="", font=_f(11),
                                        text_color=MUTED, anchor="e")
        self.stream_label.pack(anchor="e", pady=(2, 0))
        self.stream_label_2 = ctk.CTkLabel(stats, text="", font=_f(11),
                                          text_color=MUTED, anchor="e")
        self.stream_label_2.pack(anchor="e", pady=(2, 0))

        # ---------------- waveform card ----------------
        wave_card = ctk.CTkFrame(right, fg_color=CARD, corner_radius=16, border_width=1,
                                 border_color=STROKE)
        wave_card.grid(row=1, column=0, sticky="nsew")
        wave_card.grid_columnconfigure(0, weight=1)
        wave_card.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(wave_card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 4))
        head.grid_columnconfigure(1, weight=1)
        self.wave_title = ctk.CTkLabel(head, text="Live input", font=_f(13, "bold"),
                                      text_color=TEXT)
        self.wave_title.grid(row=0, column=0, sticky="w")
        self.wave_sub = ctk.CTkLabel(head, text="", font=_f(11), text_color=MUTED)
        self.wave_sub.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.chip_top = ctk.CTkLabel(head, text="", font=_f(11, "bold"), text_color=CYAN,
                                     fg_color=CARD_HI, corner_radius=8, padx=10, height=24)
        self.chip_top.grid(row=0, column=2, sticky="e")

        self.wave_canvas = tk.Canvas(wave_card, bg="#151a23", highlightthickness=0)
        self.wave_canvas.grid(row=1, column=0, sticky="nsew", padx=16, pady=(2, 8))
        self.wave = Waveform(self.wave_canvas, bg="#151a23", color="#e11d48",
                             midline="#2b3342",
                             empty_text="Press Record \u2014 the live waveform shows here")
        self.wave.live_color = "#38bdf8"
        # the canvas is not laid out yet; bake in the intended width so the live
        # view covers the full card from the very first frame
        self.wave.set_width_hint(1180 - 340 - 16 - 44 - 32 - 60)

        # ---------------- player card ----------------
        play = ctk.CTkFrame(right, fg_color=CARD, corner_radius=16, border_width=1,
                            border_color=STROKE)
        play.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        play.grid_columnconfigure(0, weight=1)

        prow = ctk.CTkFrame(play, fg_color="transparent")
        prow.grid(row=0, column=0, sticky="ew", padx=18, pady=(12, 0))
        prow.grid_columnconfigure(1, weight=1)

        btns = ctk.CTkFrame(prow, fg_color="transparent")
        btns.grid(row=0, column=0, rowspan=2, padx=(0, 14))
        self.play_btn = ctk.CTkButton(
            btns, text="\u25B6", width=52, height=44, corner_radius=12, font=_f(16, "bold"),
            fg_color=BLUE, hover_color=BLUE_HOVER, text_color="#ffffff",
            command=self.toggle_play, state="disabled")
        self.play_btn.grid(row=0, column=0, padx=(0, 6))
        self.stop_btn = ctk.CTkButton(
            btns, text="\u25A0", width=40, height=44, corner_radius=12, font=_f(14, "bold"),
            fg_color=CARD_HI, hover_color=STROKE, text_color=TEXT,
            command=self.stop_play, state="disabled")
        self.stop_btn.grid(row=0, column=1)

        center = ctk.CTkFrame(prow, fg_color="transparent")
        center.grid(row=0, column=1, rowspan=2, sticky="ew")
        center.grid_columnconfigure(0, weight=1)
        self.slider = ctk.CTkSlider(
            center, from_=0, to=1, height=18, corner_radius=9, fg_color="#2b3342",
            progress_color=BLUE, button_color=BLUE, button_hover_color=BLUE_HOVER,
            command=self._on_scrub)
        self.slider.grid(row=0, column=0, sticky="ew", pady=(2, 2))
        self.slider.set(0)
        self.slider.bind("<ButtonPress-1>", self._scrub_start)
        self.slider.bind("<ButtonRelease-1>", self._scrub_end)
        times = ctk.CTkFrame(center, fg_color="transparent")
        times.grid(row=1, column=0, sticky="ew")
        times.grid_columnconfigure(1, weight=1)
        self.cur_time = ctk.CTkLabel(times, text="0:00", font=_f(11, family=MONO), text_color=MUTED)
        self.cur_time.grid(row=0, column=0, sticky="w")
        self.file_label = ctk.CTkLabel(times, text="Nothing loaded", font=_f(11),
                                      text_color=MUTED)
        self.file_label.grid(row=0, column=1, sticky="", padx=6)
        self.tot_time = ctk.CTkLabel(times, text="0:00", font=_f(11, family=MONO), text_color=MUTED)
        self.tot_time.grid(row=0, column=2, sticky="e")

        volume = ctk.CTkFrame(prow, fg_color="transparent")
        volume.grid(row=0, column=2, rowspan=2, sticky="e", padx=(16, 0))
        ctk.CTkLabel(volume, text="Vol", font=_f(11, "bold"), text_color=MUTED).pack(side="left")
        self.vol_slider = ctk.CTkSlider(
            volume, from_=0, to=1, width=96, height=18, corner_radius=9,
            fg_color="#2b3342", progress_color=CYAN, button_color=CYAN,
            button_hover_color="#67e8f9", command=self._on_volume)
        self.vol_slider.pack(side="left", padx=6)
        self.vol_slider.set(float(self.settings["volume"] or 0.85))

        tools = ctk.CTkFrame(play, fg_color="transparent")
        tools.grid(row=1, column=0, sticky="ew", padx=18, pady=(4, 12))
        tools.grid_columnconfigure(1, weight=1)
        self.after_btn = ctk.CTkButton(
            tools, text="Open last recording again", height=30, corner_radius=9,
            font=_f(12), fg_color=CARD_HI, hover_color=STROKE, text_color=TEXT,
            width=180, command=self.load_last_recording)
        self.after_btn.grid(row=0, column=0, sticky="w")
        self.open_btn = ctk.CTkButton(
            tools, text="Open file\u2026", height=30, corner_radius=9, font=_f(12),
            fg_color=CARD_HI, hover_color=STROKE, text_color=TEXT, width=100,
            command=self.open_file_dialog)
        self.open_btn.grid(row=0, column=1, sticky="w", padx=8)
        self.reveal_btn = ctk.CTkButton(
            tools, text="Show in folder", height=30, corner_radius=9, font=_f(12),
            fg_color=CARD_HI, hover_color=STROKE, text_color=TEXT, width=110,
            command=self.reveal_current)
        self.reveal_btn.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self.ext_btn = ctk.CTkButton(
            tools, text="Play in default app", height=30, corner_radius=9, font=_f(12),
            fg_color=CARD_HI, hover_color=STROKE, text_color=TEXT, width=140,
            command=self.open_external)
        self.ext_btn.grid(row=0, column=3, sticky="e", padx=(8, 0))
        self.edit_btn = ctk.CTkButton(
            tools, text="Edit recording…", height=30, corner_radius=9, font=_f(12),
            fg_color=BLUE, hover_color=BLUE_HOVER, text_color="#ffffff", width=120,
            command=self.open_editor)
        self.edit_btn.grid(row=0, column=4, sticky="e", padx=(8, 0))

        # ---------------- recordings list ----------------
        lib = ctk.CTkFrame(right, fg_color=CARD, corner_radius=16, border_width=1,
                           border_color=STROKE, height=120)
        lib.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        lib.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(lib, text="Recent recordings", font=_f(12, "bold"), text_color=TEXT,
                     anchor="w").grid(row=0, column=0, sticky="w", padx=18, pady=(10, 0))
        ctk.CTkButton(lib, text="Refresh", width=70, height=24, font=_f(11),
                      corner_radius=7, fg_color=CARD_HI, hover_color=STROKE,
                      text_color=TEXT, command=self.refresh_library).grid(
            row=0, column=1, sticky="e", padx=18, pady=(10, 0))
        self.lib_frame = ctk.CTkScrollableFrame(lib, fg_color="transparent", height=84,
                                                orientation="horizontal")
        self.lib_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(6, 10))

    # =====================================================================
    #  Startup / device handling
    # =====================================================================
    def _initial_load(self) -> None:
        self._apply_settings_to_widgets()
        self.refresh_devices(select_saved=True)
        self.refresh_library()
        self._update_name_preview()
        if not self.engine.available:
            self._set_status("No audio system found - see the panel on the left", WARN)

    def _apply_settings_to_widgets(self) -> None:
        self.dir_label.configure(text=self._elide(self.settings["output_dir"], 44))
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, self.settings["filename_pattern"])
        self.channel_menu.set("Stereo" if int(self.settings["channels"]) >= 2 else "Mono")
        self.format_menu.set(str(self.settings["container"]).upper())

    @staticmethod
    def _elide(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        keep = limit - 1
        head = keep * 2 // 5
        return text[:head] + "\u2026" + text[-(keep - head):]

    @property
    def mode(self) -> str:
        # A web page is played by the user's normal browser and captured from
        # the system output loopback. This preserves normal OAuth/MFA flows.
        return "input" if self.mode_switch.get() == "Microphone" else "loopback"

    def refresh_devices(self, select_saved: bool = False) -> None:
        self._set_status("Refreshing devices\u2026", MUTED)
        self.devices = []
        try:
            if self.mode == "loopback":
                self.devices = self.engine.list_loopbacks()
            else:
                self.devices = self.engine.list_inputs()
        except BackendError as exc:
            self._set_status("No audio devices found", WARN)
            self.device_menu.configure(values=["No devices"])
            self.device_menu.set("No devices")
            self.device_sub.configure(text=str(exc))
            self._update_quality_widgets()
            return
        except Exception as exc:  # pragma: no cover
            self._set_status("Device error", WARN)
            self.device_menu.configure(values=["No devices"])
            self.device_menu.set("No devices")
            self.device_sub.configure(text=str(exc))
            return

        if not self.devices:
            self.device_menu.configure(values=["No devices"])
            self.device_menu.set("No devices")
            self.device_sub.configure(text="Connect an output device and press Refresh.")
            self._set_status("No devices", WARN)
            self._update_quality_widgets()
            return

        # pick default (or previously saved) device
        chosen = self.engine.default_loopback(self.devices)
        if select_saved and self.settings["device_id"]:
            saved_kind = self.settings["device_kind"]
            if saved_kind == self.mode:
                for dev in self.devices:
                    if str(dev.id) == str(self.settings["device_id"]):
                        chosen = dev
                        break
        values = [d.label for d in self.devices]
        self.device_menu.configure(values=values)
        if chosen is not None:
            self.device_menu.set(chosen.label)
            self._current_device = chosen
            self.settings["device_id"] = str(chosen.id)
            self.settings["device_kind"] = chosen.kind
            self._describe_device(chosen)
        self._update_quality_widgets()
        self._set_status("Ready", MUTED)

    def _on_mode_change(self, _value: str) -> None:
        if self.recorder:
            return
        # keep an eye on which setting we persist per mode
        self.settings["device_id"] = None
        self.settings["device_kind"] = self.mode
        self.refresh_devices()
        if _value == "Web URL":
            self.after(120, self._prompt_web_url)

    def _prompt_web_url(self) -> None:
        """Open a session-only playlist manager for sequential web capture."""
        if self.mode_switch.get() != "Web URL" or self.recorder:
            return
        if self._web_url_manager is not None:
            try:
                if self._web_url_manager.winfo_exists():
                    self._web_url_manager.deiconify()
                    self._web_url_manager.lift()
                    return
            except Exception:
                pass
        from urllib.parse import unquote, urlsplit

        dialog = ctk.CTkToplevel(self)
        self._web_url_manager = dialog
        dialog.title("Web URL playlist")
        dialog.geometry("620x650")
        dialog.minsize(580, 620)
        dialog.transient(self)
        dialog.configure(fg_color=BG)
        dialog.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - 620) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - 650) // 2)
        dialog.geometry(f"620x650+{x}+{y}")
        dialog.protocol("WM_DELETE_WINDOW", dialog.withdraw)

        ctk.CTkLabel(dialog, text="Web URL playlist", font=_f(18, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=22, pady=(18, 4))
        ctk.CTkLabel(
            dialog,
            text="Paste one http(s) URL per line. Open each in order; sign in and play it in your browser.",
            font=_f(11), text_color=MUTED, anchor="w", wraplength=570
        ).pack(anchor="w", padx=22, pady=(0, 8))
        self.web_url_text = ctk.CTkTextbox(dialog, height=112, corner_radius=8,
                                           fg_color=CARD_HI, text_color=TEXT,
                                           font=_f(11, family=MONO))
        self.web_url_text.pack(fill="x", padx=22)
        self.web_url_text.insert("1.0", "")

        row = ctk.CTkFrame(dialog, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(8, 8))
        ctk.CTkButton(row, text="Load / replace list", width=150, height=30,
                      fg_color=CARD_HI, hover_color=STROKE,
                      command=lambda: self._load_web_url_list(listbox)).pack(side="left")
        self.web_url_count = ctk.CTkLabel(row, text="No URLs loaded", font=_f(11), text_color=MUTED)
        self.web_url_count.pack(side="left", padx=12)

        listbox = tk.Listbox(dialog, height=7, bg=CARD_HI, fg=TEXT,
                             selectbackground=BLUE, selectforeground="#ffffff",
                             highlightthickness=1, highlightbackground=STROKE,
                             relief="flat", font=(FONT, 11), activestyle="none")
        listbox.pack(fill="both", expand=True, padx=22, pady=(0, 8))
        self._web_listbox = listbox
        listbox.bind("<<ListboxSelect>>", lambda _e: self._select_web_url(listbox))

        saved_row = ctk.CTkFrame(dialog, fg_color="transparent")
        saved_row.pack(fill="x", padx=22, pady=(0, 8))
        self.web_playlist_name = ctk.CTkEntry(
            saved_row, width=160, height=30, placeholder_text="Playlist name",
            fg_color=CARD_HI, text_color=TEXT, border_color=STROKE)
        self.web_playlist_name.pack(side="left", padx=(0, 6))
        ctk.CTkButton(saved_row, text="Save safe copy", width=112, height=30,
                      fg_color=CARD_HI, hover_color=STROKE,
                      command=lambda: self._save_web_playlist()).pack(side="left", padx=(0, 12))
        from .web_playlists import load_saved_playlists
        saved_names = sorted(load_saved_playlists())
        self.web_saved_menu = ctk.CTkOptionMenu(
            saved_row, values=saved_names or ["(no saved lists)"], width=165, height=30,
            fg_color=CARD_HI, button_color=STROKE, button_hover_color="#39435a",
            dropdown_fg_color=CARD_HI, dropdown_hover_color=STROKE,
            dropdown_font=_f(11), font=_f(11), text_color=TEXT, anchor="w")
        self.web_saved_menu.pack(side="left", padx=(0, 6))
        ctk.CTkButton(saved_row, text="Load", width=68, height=30,
                      fg_color=CARD_HI, hover_color=STROKE,
                      command=lambda: self._load_saved_web_playlist(listbox)).pack(side="left")

        mode = ctk.StringVar(value=str(self.settings["url_file_mode"] or "separate"))
        self._web_url_file_mode = mode
        modeframe = ctk.CTkFrame(dialog, fg_color="transparent")
        modeframe.pack(fill="x", padx=18)
        ctk.CTkLabel(modeframe, text="Save mode", font=_f(11, "bold"), text_color=TEXT).pack(side="left", padx=4)
        ctk.CTkRadioButton(modeframe, text="Separate files (default)", variable=mode,
                           value="separate", font=_f(11), text_color=TEXT,
                           command=lambda: self._set_url_file_mode(mode.get())).pack(side="left", padx=8)
        ctk.CTkRadioButton(modeframe, text="One combined file", variable=mode,
                           value="combined", font=_f(11), text_color=TEXT,
                           command=lambda: self._set_url_file_mode(mode.get())).pack(side="left", padx=8)
        self.web_autoplay_var = ctk.BooleanVar(value=bool(self.settings["url_autoplay"]))
        ctk.CTkCheckBox(
            dialog, text="Try autoplay for supported sites (best effort)",
            variable=self.web_autoplay_var, font=_f(11), text_color=TEXT,
            command=lambda: self.settings.__setitem__("url_autoplay", bool(self.web_autoplay_var.get()))
        ).pack(anchor="w", padx=22, pady=(6, 0))
        ctk.CTkLabel(
            dialog,
            text=("Separate: Start playlist opens and records the selected URL. Next URL saves it and starts the next file.\n"
                  "Combined: start once; Next URL opens remaining pages into that file. Pause/Resume is available.\n"
                  "Autoplay is best-effort. If blocked, sign in/click Play; meter status confirms audio activity. Retry URL reopens it.\n"
                  "Saved playlists strip auth tokens. Capture is system loopback and includes other computer sounds."),
            font=_f(10), text_color=MUTED, justify="left", anchor="w", wraplength=570
        ).pack(anchor="w", padx=22, pady=(8, 4))

        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.pack(fill="x", padx=22, pady=(4, 16))
        ctk.CTkButton(buttons, text="Start playlist", width=135, height=34,
                      fg_color=BLUE, hover_color=BLUE_HOVER,
                      command=lambda: self._start_selected_web_url(listbox)).pack(side="left")
        ctk.CTkButton(buttons, text="Next URL", width=90, height=34,
                      fg_color=CARD_HI, hover_color=STROKE,
                      command=lambda: self._advance_web_playlist(listbox)).pack(side="left", padx=8)
        ctk.CTkButton(buttons, text="Retry URL", width=90, height=34,
                      fg_color=CARD_HI, hover_color=STROKE,
                      command=lambda: self._retry_web_url(listbox)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(buttons, text="Done", width=74, height=34,
                      fg_color=CARD_HI, hover_color=STROKE,
                      command=dialog.withdraw).pack(side="right")
        if self._web_url_items:
            for _url, title in self._web_url_items:
                listbox.insert("end", title)
            if self._web_selected_index >= 0:
                listbox.selection_set(self._web_selected_index)
                listbox.activate(self._web_selected_index)
            self.web_url_count.configure(text=f"{len(self._web_url_items)} URLs loaded")

    def _set_url_file_mode(self, value: str) -> None:
        value = "combined" if value == "combined" else "separate"
        self.settings["url_file_mode"] = value

    def _load_web_url_list(self, listbox) -> None:
        if self.recorder is not None:
            Dialog.warn(self._web_url_manager, "Recording in progress",
                        "Stop or finish the current recording before replacing the URL list.")
            return
        from .url_source import validate_web_url
        from urllib.parse import unquote, urlsplit
        urls = [line.strip() for line in self.web_url_text.get("1.0", "end").splitlines() if line.strip()]
        if not urls:
            Dialog.warn(self._web_url_manager, "No URLs", "Paste one http(s) URL per line first.")
            return
        items = []
        for n, url in enumerate(urls, 1):
            ok, reason = validate_web_url(url)
            if not ok:
                Dialog.warn(self._web_url_manager, f"URL {n} is invalid", reason)
                return
            parts = urlsplit(url)
            leaf = unquote(parts.path.rstrip("/").split("/")[-1]) or parts.hostname or f"URL {n}"
            if "." in leaf:
                leaf = leaf.rsplit(".", 1)[0]
            title = f"{parts.hostname} - {leaf}" if leaf != parts.hostname else leaf
            items.append((url, title[:70]))
        self._web_url_items = items
        self._web_selected_index = 0
        self._web_opened_index = -1
        listbox.delete(0, "end")
        for i, (_url, title) in enumerate(items, 1):
            listbox.insert("end", f"{i:02d}. {title}")
        listbox.selection_set(0)
        listbox.activate(0)
        self.web_url_count.configure(text=f"{len(items)} URLs loaded (session only)")
        self._select_web_url(listbox)

    def _save_web_playlist(self) -> None:
        from .web_playlists import save_playlist
        name = self.web_playlist_name.get().strip()
        urls = [url for url, _title in self._web_url_items]
        if not urls:
            urls = [line.strip() for line in self.web_url_text.get("1.0", "end").splitlines()
                    if line.strip()]
        if not name:
            Dialog.warn(self._web_url_manager, "Name the playlist", "Enter a name before saving.")
            return
        try:
            stored_name, removed = save_playlist(name, urls)
        except Exception as exc:
            Dialog.error(self._web_url_manager, "Could not save playlist", str(exc))
            return
        from .web_playlists import load_saved_playlists
        names = sorted(load_saved_playlists())
        self.web_saved_menu.configure(values=names)
        self.web_saved_menu.set(stored_name)
        note = (f"Removed {removed} auth-related URL parameter(s). Sign-in will use the browser session."
                if removed else "No auth parameters needed removal.")
        Dialog.info(self._web_url_manager, "Playlist saved safely", note)

    def _load_saved_web_playlist(self, listbox) -> None:
        if self.recorder is not None:
            Dialog.warn(self._web_url_manager, "Recording in progress",
                        "Finish the current recording before loading another playlist.")
            return
        from .web_playlists import load_saved_playlists
        name = self.web_saved_menu.get()
        saved = load_saved_playlists()
        urls = saved.get(name)
        if not urls:
            Dialog.warn(self._web_url_manager, "No saved playlist", "Choose a saved playlist first.")
            return
        self.web_url_text.delete("1.0", "end")
        self.web_url_text.insert("1.0", "\n".join(urls))
        self._load_web_url_list(listbox)
        self.web_url_count.configure(text=f"{len(urls)} URLs loaded from safe saved list")

    def _retry_web_url(self, listbox) -> None:
        if not self._web_url_items:
            Dialog.warn(self._web_url_manager, "No URL loaded", "Load a URL list first.")
            return
        index = self._web_opened_index if self.recorder is not None else self._web_selected_index
        if index < 0 or index >= len(self._web_url_items):
            self._select_web_url(listbox)
            index = self._web_selected_index
        if index >= 0:
            self._open_web_url(listbox, index=index)

    def _select_web_url(self, listbox) -> None:
        selection = listbox.curselection()
        if selection and selection[0] < len(self._web_url_items):
            self._web_selected_index = int(selection[0])

    def _start_selected_web_url(self, listbox) -> None:
        """Default automation: open the selected URL and begin capture immediately."""
        if self.recorder is not None:
            Dialog.warn(self, "Already recording", "Stop the current recording before starting another.")
            return
        if not self._web_url_items:
            self._load_web_url_list(listbox)
            if not self._web_url_items:
                return
        self._select_web_url(listbox)
        if self._open_web_url(listbox):
            self.start_recording()

    def _advance_web_playlist(self, listbox) -> None:
        if not self._web_url_items:
            self._load_web_url_list(listbox)
            if not self._web_url_items:
                return
            self._select_web_url(listbox)
            if self._open_web_url(listbox, index=0) and self.recorder is None:
                self.start_recording()
            return
        self._select_web_url(listbox)
        current = self._web_opened_index if self.recorder is not None else self._web_selected_index
        target = current + 1
        if target >= len(self._web_url_items):
            Dialog.info(self._web_url_manager, "Playlist complete",
                        "There are no more URLs in this list.")
            return
        if self.settings["url_file_mode"] == "separate" and self.recorder is not None:
            # Stop/save this URL, then the completion callback opens and records
            # the next item automatically. Pause remains available at any time.
            self._pending_web_next = target
            self.stop_recording()
            return
        if self._open_web_url(listbox, index=target) and self.recorder is None:
            # For combined mode, first Next can start capture if the user had
            # stopped it; when already recording we leave the single file open.
            self.start_recording()

    def _start_web_url_index(self, index: int) -> None:
        listbox = self._web_listbox
        if listbox is None or not self._web_url_items:
            return
        listbox.selection_clear(0, "end")
        listbox.selection_set(index)
        listbox.activate(index)
        self._select_web_url(listbox)
        if self._open_web_url(listbox, index=index):
            self.start_recording()

    def _open_web_url(self, listbox, index: Optional[int] = None) -> bool:
        import webbrowser
        from .url_source import validate_web_url
        if not self._web_url_items:
            self._load_web_url_list(listbox)
            if not self._web_url_items:
                return False
        self._select_web_url(listbox)
        idx = self._web_selected_index if index is None else int(index)
        if idx < 0 or idx >= len(self._web_url_items):
            return False
        listbox.selection_clear(0, "end")
        listbox.selection_set(idx)
        listbox.activate(idx)
        url, title = self._web_url_items[idx]
        ok, reason = validate_web_url(url)
        if not ok:
            Dialog.warn(self._web_url_manager, "Check the URL", reason)
            return False
        autoplay_provider = None
        if bool(self.settings["url_autoplay"]):
            url, autoplay_provider = autoplay_url(url)
        try:
            if not webbrowser.open(url, new=2):
                raise RuntimeError("No browser accepted the URL")
        except Exception as exc:
            Dialog.error(self._web_url_manager, "Could not open browser", str(exc))
            return False
        self._web_selected_index = idx
        self._web_opened_index = idx
        self._active_web_title = title
        if self.recorder is not None:
            self._web_waiting_audio = True
            self._web_audio_hits = 0
        if not bool(self.settings["url_autoplay"]):
            hint = "Autoplay requests are disabled; click Play in the browser if needed."
        elif autoplay_provider:
            hint = f"Requested {autoplay_provider} autoplay; browser policies may still require a click."
        else:
            hint = "No autoplay adapter for this site; click Play in the browser if needed."
        self.source_note.configure(
            text=f"Web URL {idx + 1}/{len(self._web_url_items)}: {title}. {hint}")
        return True

    def _on_device_change(self, label: str) -> None:
        for dev in self.devices:
            if dev.label == label:
                self._current_device = dev
                self.settings["device_id"] = str(dev.id)
                self.settings["device_kind"] = dev.kind
                self._describe_device(dev)
                self._update_quality_widgets()
                break

    @property
    def current_device(self) -> Optional[Device]:
        return getattr(self, "_current_device", None)

    def _describe_device(self, dev: Device) -> None:
        bits = [dev.info or ("System output" if dev.is_loopback else "Microphone")]
        bits.append(describe_channels(dev.channels))
        if dev.sample_rate:
            bits.append(f"device runs at {format_rate(dev.sample_rate)}")
        self.device_sub.configure(text=" \u00b7 ".join(bits))
        default = "default output" if dev.is_loopback else "default input"
        self.source_note.configure(
            text=(f"Recording the {default}: \u201c{dev.name}\u201d. Everything the "
                  f"computer plays is captured digitally \u2014 system beeps, browser "
                  f"audio, games and media players.") if dev.is_loopback else
            f"Recording microphone: \u201c{dev.name}\u201d.")
        if self.mode_switch.get() == "Web URL":
            self.source_note.configure(
                text="Web URL mode: play the page in your browser, then press Record. "
                     "System-output capture includes other computer sounds too.")
        self.stream_label.configure(text=dev.name)
        self.stream_label_2.configure(
            text=f"{describe_channels(dev.channels)}"
                 + (f" \u00b7 {dev.sample_rate:,} Hz device" if dev.sample_rate else ""))

    def _update_quality_widgets(self) -> None:
        dev = self.current_device
        choices = rate_choices(dev)
        saved_raw = self.settings["samplerate"]
        if saved_raw in (None, "", "auto", 0):
            saved = (dev.sample_rate if dev and dev.sample_rate else DEFAULT_RATE)
        else:
            try:
                saved = int(saved_raw)
            except (TypeError, ValueError):
                saved = DEFAULT_RATE
        labels = [label for _rate, label in choices]
        self.rate_menu.configure(values=labels)
        match = next((label for rate, label in choices if rate == saved), labels[0])
        self.rate_menu.set(match)
        self._rate_by_label = {label: rate for rate, label in choices}
        self._update_quality_hint()

    def _selected_rate(self) -> int:
        label = self.rate_menu.get()
        return int(getattr(self, "_rate_by_label", {}).get(label, DEFAULT_RATE))

    def _selected_channels(self) -> int:
        dev = self.current_device
        wanted = 2 if self.channel_menu.get() == "Stereo" else 1
        if dev is not None and dev.channels < wanted:
            return 1
        return wanted

    def _update_quality_hint(self) -> None:
        rate = self._selected_rate()
        # what we will actually write: never upmix a mono device to stereo
        ch = 2 if self.channel_menu.get() == "Stereo" else 1
        container = self.format_menu.get()
        depth = "32-bit float" if container == "WAV" else "24-bit"
        format_note = ("uncompressed, preserves float32 samples" if container == "WAV"
                       else "FLAC lossless codec, 24-bit PCM")
        self.quality_hint.configure(
            text=f"{depth} {'stereo' if ch == 2 else 'mono'} \u00b7 "
                 f"{rate / 1000:g} kHz \u00b7 {format_note}")
        approx = rate * ch * (4 if container == "WAV" else 3) * 60 / 1_000_000
        if container == "FLAC":
            approx *= 0.45  # typical compressed audio; actual size depends on content
        self.chip_top.configure(text=f"{describe_channels(ch)} \u00b7 {rate / 1000:g} kHz")
        self.quality_chip.configure(
            text=f"\u25C6 {container} {depth} \u00b7 {rate / 1000:g} kHz \u00b7 "
                 f"{'stereo' if ch == 2 else 'mono'}   (~{approx:.1f} MB/min)")

    def _on_quality_change(self, _value: str) -> None:
        dev = self.current_device
        rate = self._selected_rate()
        if dev and dev.sample_rate and rate == dev.sample_rate:
            self.settings["samplerate"] = None  # "auto" - follow the device
        else:
            self.settings["samplerate"] = rate
        self.settings["channels"] = self._selected_channels()
        self.settings["container"] = self.format_menu.get()
        self._update_quality_hint()

    # =====================================================================
    #  Recording
    # =====================================================================
    def toggle_record(self) -> None:
        if self.recorder is not None:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self) -> None:
        dev = self.current_device
        if dev is None:
            Dialog.warn(self, "No device selected",
                        "Pick an output device first, or press \u201cRefresh devices\u201d.")
            return
        if self.player.playing:
            self.player.pause()
            self._sync_play_button(False)
        rate = self._selected_rate()
        channels = self._selected_channels()
        container = self.format_menu.get()
        ext = ".wav" if container == "WAV" else ".flac"
        stem = build_filename(self.settings["filename_pattern"])
        if self.mode_switch.get() == "Web URL":
            if (self._web_selected_index < 0 or
                    self._web_selected_index >= len(self._web_url_items) or
                    self._web_opened_index != self._web_selected_index):
                Dialog.warn(self, "Choose a URL first", "Open the URL you want to capture from the playlist first.")
                return
            if self.settings["url_file_mode"] == "separate":
                title = self._web_url_items[self._web_selected_index][1]
                stem = url_recording_stem(self._web_selected_index, title, stem)
        try:
            path = unique_path(Path(self.settings["output_dir"] or music_dir()), stem, ext)
        except Exception as exc:
            Dialog.error(self, "Cannot save there",
                         f"Could not create the recordings folder:\n{exc}\n\n"
                         "Choose a different folder under \u201cSAVE TO\u201d.")
            return
        try:
            source = self.engine.capture_source(dev)
        except BackendError as exc:
            Dialog.error(self, "Audio device error", str(exc))
            return
        try:
            self.recorder = Recorder(source, str(path), rate, channels, container,
                                     device_name=dev.name)
            self.recorder.start()
        except Exception as exc:
            self.recorder = None
            Dialog.error(self, "Could not start recording",
                         f"{exc}\n\nTry another device, or a lower sample rate.")
            return

        self._rec_started_monotonic = time.monotonic()
        self.rec_button.configure(text="\u25A0   Stop", fg_color="#9f1239",
                                  hover_color=ACCENT)
        self.pause_btn.configure(text="Pause", state="normal")
        self._lock_controls(True)
        self._web_waiting_audio = self.mode_switch.get() == "Web URL"
        self._web_audio_hits = 0
        if self._web_waiting_audio:
            self._set_status("Waiting for browser audio", WARN)
        else:
            self._set_status("\u25CF Recording", ACCENT)
        self.wave_title.configure(text="Live input")
        self.wave_sub.configure(text=dev.name)
        self.wave.reset_live()
        self.size_label.configure(text="0.0 MB")
        self.time_label.configure(text="00:00")
        self.meter_text.configure(
            text=("Waiting for playback - sign in/click Play in browser"
                  if self._web_waiting_audio else "Input level  \u2212\u221e dBFS"))
        self._draw_meter(0.0, 0.0)
        self.play_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")

    def toggle_pause(self) -> None:
        rec = self.recorder
        if rec is None:
            return
        if rec.paused:
            rec.resume()
            self.pause_btn.configure(text="Pause")
            self._set_status("Recording", ACCENT)
            self.meter_text.configure(text="Input level  \u2212\u221e dBFS")
        else:
            rec.pause()
            self.pause_btn.configure(text="Resume")
            self._set_status("Paused", WARN)
            self.meter_text.configure(text="Paused \u00b7 audio is not being captured")
            self._draw_meter(0.0, 0.0)

    def stop_recording(self) -> None:
        rec = self.recorder
        if rec is None:
            return
        self.rec_button.configure(text="Saving\u2026", state="disabled")
        self.pause_btn.configure(state="disabled")
        self._set_status("Saving\u2026", WARN)

        def worker():
            info = None
            error = None
            try:
                info = rec.stop()
            except Exception as exc:
                error = exc
            self._post(lambda: self._recording_finished(info, error))

        threading.Thread(target=worker, daemon=True).start()

    def _recording_finished(self, info: Optional[RecordingInfo], error) -> None:
        self.recorder = None
        self.rec_button.configure(text="\u25CF   Record", state="normal",
                                  fg_color=ACCENT, hover_color=ACCENT_HOVER)
        self.pause_btn.configure(text="Pause", state="disabled")
        self._lock_controls(False)
        if error is not None:
            self._pending_web_next = None
            self._set_status("Recording failed", WARN)
            Dialog.error(self, "Recording stopped unexpectedly", str(error))
            self.wave.clear()
            return
        self.info = info
        self.time_label.configure(text=human_time(info.duration))
        self.size_label.configure(text=human_size(info.size_bytes))
        self.meter_text.configure(text="Saved \u00b7 ready to play")
        self._draw_meter(0.0, 0.0)
        self._set_status("Saved", GREEN)
        note = ""
        if info.fallback_reason:
            note = " " + info.fallback_reason
        if getattr(info, "is_silent", False):
            Dialog.warn(
                self, "Saved \u2014 but the recording is silent",
                "The file was saved, but it contains silence only.\n\n"
                "Check that something is playing through the selected output. "
                "If the app that plays audio runs as administrator, Windows may "
                "not route it to the shared mixer this app listens to.\n\n"
                f"Saved to: {os.path.basename(info.path)}")
        self._load_for_playback(info.path, autoplay=False)
        self.refresh_library()
        if note:
            self._set_status("Saved (converted to WAV)", GREEN)
        next_index = self._pending_web_next
        self._pending_web_next = None
        if next_index is not None:
            self.after(400, lambda idx=next_index: self._start_web_url_index(idx))

    def _lock_controls(self, locked: bool) -> None:
        state = "disabled" if locked else "normal"
        for widget in (self.device_menu, self.rate_menu, self.channel_menu,
                       self.format_menu, self.mode_switch, self.refresh_btn,
                       self.name_entry):
            try:
                widget.configure(state=state)
            except Exception:
                pass

    # =====================================================================
    #  Playback
    # =====================================================================
    def _load_for_playback(self, path: str, autoplay: bool = False) -> None:
        try:
            audio = AudioFile(path)
        except Exception as exc:
            Dialog.error(self, "Cannot open file", str(exc))
            return
        if audio.data is None and not audio.streaming:
            Dialog.error(self, "Cannot open file",
                         audio.error or "The file is unsupported or corrupt.")
            return
        self.file_audio = audio
        self.player.load(audio)
        self.player.volume = float(self.vol_slider.get())
        name = os.path.basename(path)
        self.file_label.configure(text=self._elide(name, 46))
        self.tot_time.configure(text=human_time(audio.duration))
        self.cur_time.configure(text="0:00")
        self.slider.configure(to=max(0.001, audio.duration))
        self.slider.set(0)
        self.play_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        self.wave.set_duration(audio.duration)
        if audio.streaming:
            peaks = audio.overview_peaks(int(self.wave_canvas.winfo_width() or 800))
            self.wave.show_file(None, audio.samplerate, peaks=peaks)
        else:
            self.wave.show_file(audio.data, audio.samplerate)
        self.wave.set_duration(audio.duration)
        self.wave_title.configure(text="Recording")
        self.wave_sub.configure(
            text=f"{audio.samplerate:,} Hz \u00b7 {describe_channels(audio.channels)} \u00b7 "
                 f"{human_time(audio.duration)}"
                 + ("  \u00b7  streamed from disk" if audio.streaming else ""))
        self.wave.set_progress(0)
        if autoplay:
            self.start_play()

    def start_play(self) -> None:
        if not self.player.loaded:
            return
        if self.player.position >= self.file_audio.duration - 0.01:
            self.player.seek(0)
        self.player.volume = float(self.vol_slider.get())
        self.player.play()
        self._sync_play_button(True)

    def toggle_play(self) -> None:
        if not self.player.loaded:
            return
        playing = self.player.toggle()
        self._sync_play_button(playing)

    def stop_play(self) -> None:
        self.player.stop()
        self.player.seek(0)
        self._sync_play_button(False)
        self._sync_progress(0.0)

    def _sync_play_button(self, playing: bool) -> None:
        # ASCII-only glyphs render on every Windows/GTK font set; "||" reads
        # clearly as pause, ">" as play.
        self.play_btn.configure(text="||" if playing else "\u25B6")

    def _on_play_finish(self, ok: bool) -> None:
        self._post(lambda: self._finish_ui(ok))

    def _finish_ui(self, ok: bool) -> None:
        self._sync_play_button(False)
        if ok and self.file_audio:
            self.player.seek(self.file_audio.duration)
            self._sync_progress(self.file_audio.duration)

    def _on_play_error(self, message: str) -> None:
        self._post(lambda: self._play_error_ui(message))

    def _play_error_ui(self, message: str) -> None:
        self._sync_play_button(False)
        self._set_status("Playback error", WARN)
        Dialog.error(self, "Playback error",
                     f"Could not play audio:\n{message}\n\n"
                     "Check that an output device is available (and not in exclusive use).")

    def _on_volume(self, value) -> None:
        self.player.volume = float(value)
        self.settings["volume"] = float(value)

    def _scrub_start(self, _event) -> None:
        self._scrub_active = True

    def _scrub_end(self, _event) -> None:
        self._scrub_active = False
        if self.player.loaded:
            self.player.seek(float(self.slider.get()))

    def _on_scrub(self, value) -> None:
        if self._scrub_active and self.file_audio:
            self.wave.set_progress(float(value))

    def _sync_progress(self, seconds: float) -> None:
        if not self.file_audio:
            return
        self.cur_time.configure(text=human_time(seconds))
        if not self._scrub_active:
            self.slider.set(seconds)
            self.wave.set_progress(seconds)

    def open_file_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open audio file",
            initialdir=self.settings["output_dir"],
            filetypes=[("Audio files", "*.wav *.flac *.ogg *.mp3 *.m4a *.aiff *.aif"),
                       ("All files", "*.*")])
        if path:
            self._load_for_playback(path)

    def load_last_recording(self) -> None:
        if self.info and os.path.exists(self.info.path):
            self._load_for_playback(self.info.path)
        else:
            self.refresh_library()
            self._set_status("No recording yet", MUTED)

    def reveal_current(self) -> None:
        path = self.info.path if self.info else None
        if path and os.path.exists(path):
            open_in_file_manager(path)
        else:
            open_in_file_manager(self.settings["output_dir"])

    def open_external(self) -> None:
        if self.info and os.path.exists(self.info.path):
            open_with_default_app(self.info.path)

    # =====================================================================
    #  Library
    # =====================================================================
    def refresh_library(self) -> None:
        for child in list(self.lib_frame.winfo_children()):
            child.destroy()
        files = list_recordings(self.settings["output_dir"])
        if not files:
            ctk.CTkLabel(self.lib_frame, text="No recordings in this folder yet.",
                         font=_f(11), text_color=MUTED).pack(side="left", padx=6)
            return
        for path in files[:12]:
            self._library_chip(path)

    def _library_chip(self, path: str) -> None:
        name = os.path.basename(path)
        try:
            size = human_size(os.path.getsize(path))
        except OSError:
            size = ""
        chip = ctk.CTkButton(
            self.lib_frame, text=f"{self._elide(name, 28)}\n{size}", width=190, height=54,
            font=_f(11), fg_color=CARD_HI, hover_color=STROKE, text_color=TEXT,
            corner_radius=10, anchor="w", command=lambda p=path: self._load_for_playback(p))
        chip.pack(side="left", padx=(6, 0), pady=2)

    # =====================================================================
    #  Basic non-destructive editor
    # =====================================================================
    def open_editor(self) -> None:
        audio = getattr(self, "file_audio", None)
        if audio is None or not audio.path:
            Dialog.error(self, "No recording loaded", "Open a recording before editing it.")
            return
        try:
            session = AudioEditSession(audio)
        except Exception as exc:
            Dialog.error(self, "Cannot edit recording", str(exc))
            return
        self.player.pause()
        self._sync_play_button(False)
        win = ctk.CTkToplevel(self)
        win.title("Audio editor — original remains unchanged")
        win.geometry("760x570")
        win.minsize(620, 470)
        win.configure(fg_color=BG)
        win.transient(self)
        win.grab_set()
        win.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(win, text="Select a range, then trim to it or remove it",
                     font=_f(20, "bold"), text_color=TEXT).grid(row=0, column=0, padx=20, pady=(18, 4), sticky="w")
        ctk.CTkLabel(win, text="Drag on the waveform, or enter start/end times. The source file is never changed.",
                     font=_f(12), text_color=MUTED).grid(row=1, column=0, padx=20, pady=(0, 10), sticky="w")
        canvas = tk.Canvas(win, height=190, bg="#0f131a", highlightthickness=1, highlightbackground=STROKE)
        canvas.grid(row=2, column=0, padx=20, pady=6, sticky="ew")
        times = ctk.CTkFrame(win, fg_color="transparent")
        times.grid(row=3, column=0, padx=20, pady=5, sticky="w")
        ctk.CTkLabel(times, text="Start (seconds)", text_color=MUTED).pack(side="left")
        startv, endv = tk.StringVar(value="0.00"), tk.StringVar(value=f"{session.duration:.2f}")
        start_entry = ctk.CTkEntry(times, width=100, textvariable=startv)
        start_entry.pack(side="left", padx=(8, 18))
        ctk.CTkLabel(times, text="End (seconds)", text_color=MUTED).pack(side="left")
        end_entry = ctk.CTkEntry(times, width=100, textvariable=endv)
        end_entry.pack(side="left", padx=8)
        info = ctk.CTkLabel(win, text=f"Current edit: {session.duration:.2f} sec  ·  {audio.samplerate:,} Hz  ·  {audio.channels} channel(s)",
                            text_color=MUTED, font=_f(12))
        info.grid(row=4, column=0, padx=20, pady=4, sticky="w")
        status = ctk.CTkLabel(win, text="Original preserved. Save creates a separate file.", text_color=GREEN, font=_f(12))
        status.grid(row=5, column=0, padx=20, pady=4, sticky="w")
        controls = ctk.CTkFrame(win, fg_color="transparent")
        controls.grid(row=6, column=0, padx=20, pady=(10, 18), sticky="ew")
        preview_player = Player()
        temp_paths = []
        busy = {"value": False}
        dragging = {"x": None}
        peaks_cache = {"value": None}

        def draw():
            w, h = max(canvas.winfo_width(), 100), max(canvas.winfo_height(), 80)
            canvas.delete("all")
            mid = h / 2
            canvas.create_line(0, mid, w, mid, fill="#344052")
            peaks = peaks_cache["value"]
            if peaks is not None:
                step = w / max(1, len(peaks))
                for i, (lo, hi) in enumerate(peaks):
                    canvas.create_line(i * step + step / 2, mid - float(hi) * (h/2-8),
                                       i * step + step / 2, mid - float(lo) * (h/2-8), fill="#60a5fa")
            try:
                a, b = float(startv.get()), float(endv.get())
                dur = max(session.duration, 0.001)
                x1, x2 = max(0, min(w, a/dur*w)), max(0, min(w, b/dur*w))
                canvas.create_rectangle(x1, 1, x2, h-1, fill="#2563eb", stipple="gray25", outline="#93c5fd", width=2)
                canvas.tag_lower("selection")
            except ValueError:
                pass
            canvas.create_text(8, 8, anchor="nw", text=f"0.00 s", fill="#94a3b8")
            canvas.create_text(w-8, 8, anchor="ne", text=f"{session.duration:.2f} s", fill="#94a3b8")

        def update_wave():
            peaks_cache["value"] = np.stack(session.overview_peaks(900), axis=1)
            info.configure(text=f"Current edit: {session.duration:.2f} sec  ·  {audio.samplerate:,} Hz  ·  {audio.channels} channel(s)")
            draw()
            undo_btn.configure(state="normal" if session._undo else "disabled")
            redo_btn.configure(state="normal" if session._redo else "disabled")

        import numpy as np
        def canvas_time(x):
            return max(0.0, min(session.duration, x / max(1, canvas.winfo_width()) * session.duration))
        def begin_drag(e):
            dragging["x"] = e.x
            startv.set(f"{canvas_time(e.x):.3f}")
        def drag(e):
            if dragging["x"] is not None:
                endv.set(f"{canvas_time(e.x):.3f}")
                draw()
        def end_drag(e):
            dragging["x"] = None
            endv.set(f"{canvas_time(e.x):.3f}")
            draw()
        canvas.bind("<ButtonPress-1>", begin_drag)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", end_drag)
        startv.trace_add("write", lambda *_: draw())
        endv.trace_add("write", lambda *_: draw())
        canvas.bind("<Configure>", lambda _e: draw())

        def get_range():
            a, b = float(startv.get()), float(endv.get())
            if b < a:
                a, b = b, a
            if a < 0 or b > session.duration or b <= a:
                raise ValueError("Choose a valid range within the current waveform.")
            return a, b
        def set_busy(flag, message=None):
            busy["value"] = flag
            if message:
                status.configure(text=message, text_color=BLUE if flag else GREEN)
            for button in action_buttons:
                button.configure(state="disabled" if flag else "normal")
            if not flag:
                undo_btn.configure(state="normal" if session._undo else "disabled")
                redo_btn.configure(state="normal" if session._redo else "disabled")
        def preview():
            if busy["value"]: return
            try: a, b = get_range()
            except Exception as exc:
                status.configure(text=str(exc), text_color=ACCENT); return
            suffix = Path(audio.path).suffix.lower()
            if suffix not in (".wav", ".flac"): suffix = ".wav"
            fd, path = tempfile.mkstemp(suffix=suffix, prefix="audiocapture-preview-")
            os.close(fd); temp_paths.append(path)
            set_busy(True, "Preparing preview…")
            def work():
                try:
                    session.export_selection(path, a, b)
                    self._post(lambda: preview_ready(path))
                except Exception as exc:
                    self._post(lambda exc=exc: (set_busy(False), status.configure(text=f"Preview failed: {exc}", text_color=ACCENT)))
            threading.Thread(target=work, daemon=True).start()
        def preview_ready(path):
            try:
                preview_player.stop()
                preview_player.load(AudioFile(path))
                preview_player.play()
                status.configure(text="Playing selected range…", text_color=GREEN)
            except Exception as exc:
                status.configure(text=f"Preview failed: {exc}", text_color=ACCENT)
            set_busy(False)
        def edit(kind):
            try:
                a, b = get_range()
                getattr(session, kind)(a, b)
                startv.set("0.000"); endv.set(f"{session.duration:.3f}")
                status.configure(text="Edit applied. Use Undo/Redo or save a new copy.", text_color=GREEN)
                update_wave()
            except Exception as exc:
                status.configure(text=str(exc), text_color=ACCENT)
        def undo():
            if session.undo():
                startv.set("0.000"); endv.set(f"{session.duration:.3f}")
                update_wave(); status.configure(text="Undo applied.", text_color=GREEN)
        def redo():
            if session.redo():
                startv.set("0.000"); endv.set(f"{session.duration:.3f}")
                update_wave(); status.configure(text="Redo applied.", text_color=GREEN)
        def save_copy():
            if busy["value"]: return
            source = Path(audio.path)
            suffix = source.suffix.lower() if source.suffix.lower() in (".wav", ".flac") else ".wav"
            suggested = unique_path(str(source.with_name(source.stem + " (edited)" + suffix)))
            path = filedialog.asksaveasfilename(parent=win, title="Save edited copy", initialdir=str(Path(suggested).parent),
                                               initialfile=Path(suggested).name, defaultextension=suffix,
                                               filetypes=[("WAV audio", "*.wav"), ("FLAC audio", "*.flac")])
            if not path: return
            set_busy(True, "Saving edited copy…")
            def work():
                try:
                    result = session.export(path)
                    self._post(lambda: saved(result))
                except Exception as exc:
                    self._post(lambda exc=exc: (set_busy(False), status.configure(text=f"Save failed: {exc}", text_color=ACCENT)))
            threading.Thread(target=work, daemon=True).start()
        def saved(path):
            set_busy(False)
            self.refresh_library()
            self._load_for_playback(path)
            status.configure(text=f"Saved new copy: {os.path.basename(path)}", text_color=GREEN)
        preview_btn = ctk.CTkButton(controls, text="Preview selection", command=preview, width=130)
        preview_btn.pack(side="left", padx=4)
        trim_btn = ctk.CTkButton(controls, text="Trim to selection", command=lambda: edit("trim"), width=125, fg_color=BLUE, hover_color=BLUE_HOVER)
        trim_btn.pack(side="left", padx=4)
        remove_btn = ctk.CTkButton(controls, text="Remove selection", command=lambda: edit("remove"), width=125)
        remove_btn.pack(side="left", padx=4)
        undo_btn = ctk.CTkButton(controls, text="Undo", command=undo, width=65, state="disabled")
        undo_btn.pack(side="left", padx=4)
        redo_btn = ctk.CTkButton(controls, text="Redo", command=redo, width=65, state="disabled")
        redo_btn.pack(side="left", padx=4)
        save_btn = ctk.CTkButton(controls, text="Save edited copy…", command=save_copy, width=145, fg_color=GREEN, hover_color="#16a34a")
        save_btn.pack(side="right", padx=4)
        action_buttons = [preview_btn, trim_btn, remove_btn, undo_btn, redo_btn, save_btn]
        win.protocol("WM_DELETE_WINDOW", lambda: (preview_player.stop(), [os.path.exists(p) and os.remove(p) for p in temp_paths], win.destroy()))
        update_wave()

    # =====================================================================
    #  Settings helpers
    # =====================================================================
    def choose_dir(self) -> None:
        path = filedialog.askdirectory(title="Choose where recordings are saved",
                                       initialdir=self.settings["output_dir"])
        if path:
            self.settings["output_dir"] = path
            self.dir_label.configure(text=self._elide(path, 44))
            self.refresh_library()

    def _update_name_preview(self) -> None:
        pattern = self.name_entry.get()
        self.settings["filename_pattern"] = pattern
        ext = ".wav" if self.format_menu.get() == "WAV" else ".flac"
        self.name_preview.configure(text="e.g. " + build_filename(pattern) + ext)

    # =====================================================================
    #  UI plumbing
    # =====================================================================
    def _post(self, callback) -> None:
        """Queue a callable for the Tk main thread."""
        self._ui_queue.append(callback)

    def _set_status(self, text: str, color: str = MUTED) -> None:
        self.status_label.configure(text=text, text_color=color)

    def _draw_meter(self, rms: float, peak: float) -> None:
        c = self.meter_canvas
        c.delete("all")
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())
        c.create_rectangle(0, 3, w, h - 3, fill="#0f131a", outline="")
        bars = 40
        seg_w = w / bars
        # -60..0 dBFS scale
        import math
        def db(x):
            return 20 * math.log10(max(x, 1e-6))
        lit_rms = int(max(0.0, min(1.0, (db(rms) + 60) / 60)) * bars)
        lit_peak = int(max(0.0, min(1.0, (db(peak) + 60) / 60)) * bars)
        for i in range(bars):
            x0 = i * seg_w + 1
            x1 = (i + 1) * seg_w - 1
            if i < lit_rms:
                color = GREEN if i < bars * 0.75 else WARN
            elif i < lit_peak:
                color = "#365314"
            else:
                color = "#20262f"
            c.create_rectangle(x0, 4, x1, h - 4, fill=color, outline="")
        if peak > 0.999:
            c.create_text(w - 40, h / 2, text="CLIP", fill="#ffffff",
                          font=("Segoe UI", 10, "bold"))

    def _ui_tick(self) -> None:
        if self._closing:
            return
        # run queued callbacks from worker threads
        while self._ui_queue:
            cb = self._ui_queue.pop(0)
            try:
                cb()
            except Exception as exc:  # pragma: no cover
                print("UI callback error:", exc)
        try:
            self._tick_body()
        except tk.TclError:
            return  # window is being destroyed
        try:
            self.after(50, self._ui_tick)
        except tk.TclError:
            pass

    def _tick_body(self) -> None:
        rec = self.recorder
        if rec is not None:
            self.time_label.configure(text=human_time(rec.duration))
            size = rec.frames * rec.channels * (4 if rec.container == "WAV" else 3)
            self.size_label.configure(text=human_size(int(size)))
            if rec.paused:
                self._draw_meter(0.0, 0.0)
                return
            rms, peak = rec.level()
            self._draw_meter(rms, peak)
            import math
            dbs = 20 * math.log10(max(rms, 1e-6))
            if self._web_waiting_audio:
                if rms >= 0.002:
                    self._web_audio_hits += 1
                else:
                    self._web_audio_hits = 0
                if self._web_audio_hits >= 3:
                    self._web_waiting_audio = False
                    self._set_status("Browser audio detected", GREEN)
                    self.source_note.configure(
                        text="System audio detected. This meter sees the full system mix, including other sounds.")
            if self._web_waiting_audio:
                self.meter_text.configure(
                    text=f"Waiting for browser audio · {dbs:+.1f} dBFS · sign in/click Play if idle")
            else:
                self.meter_text.configure(
                    text=f"Input level {dbs:+.1f} dBFS · "
                         f"{'digital system audio' if self.mode == 'loopback' else 'microphone'}")
            try:
                block = rec.drain_preview()
                if block is not None:
                    self.wave.add_block(block, rec.samplerate)
                    self.wave.live_follow = True
                else:
                    # nothing arrived from the device: keep the trace scrolling
                    # on the wall clock so silences stay visible
                    self.wave.add_tick(max(1, int(rec.samplerate * 0.05)),
                                       rec.samplerate)
                now = time.monotonic()
                if now - self._last_wave_paint >= 0.12:
                    self._last_wave_paint = now
                    self.wave.tick()
            except Exception:
                pass
        elif self.player.loaded:
            self._sync_progress(self.player.position)
            if self.player.playing != getattr(self, "_last_playing_state", None):
                self._last_playing_state = self.player.playing
                self._sync_play_button(self.player.playing)

    def on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._ui_queue.clear()
        try:
            if self.recorder is not None:
                self.recorder.stop()
        except Exception:
            pass
        try:
            self.player.stop()
        except Exception:
            pass
        try:
            self.settings.save()
        except Exception:
            pass
        self.destroy()


def main() -> None:
    ctk.set_appearance_mode("dark")
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
