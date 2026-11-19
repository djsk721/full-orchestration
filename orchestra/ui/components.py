"""Reusable styled Tk components aligned with the Orca-inspired design system."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .theme import THEMES, status_tone


class Card(tk.Frame):
    """Subtle bordered surface container with consistent padding and theme support."""

    def __init__(self, parent, palette: dict, *, padding=(14, 12), bg_key="panel"):
        super().__init__(
            parent,
            bg=palette[bg_key],
            highlightthickness=1,
            highlightbackground=palette["border"],
            highlightcolor=palette["border_strong"],
            bd=0,
        )
        self.palette = palette
        self.bg_key = bg_key
        self.body = tk.Frame(self, bg=palette[bg_key], padx=padding[0], pady=padding[1])
        self.body.pack(fill="both", expand=True)

    def apply_palette(self, palette: dict):
        self.palette = palette
        self.configure(
            bg=palette[self.bg_key],
            highlightbackground=palette["border"],
            highlightcolor=palette["border_strong"],
        )
        self.body.configure(bg=palette[self.bg_key])


class StatusBadge(tk.Label):
    """Pill-like semantic status indicator."""

    def __init__(self, parent, palette: dict, text: str = "—", tone: str = "neutral", ui_font: str = "TkDefaultFont"):
        bg, fg, border = palette["badges"].get(tone, palette["badges"]["neutral"])
        super().__init__(
            parent,
            text=text,
            bg=bg,
            fg=fg,
            padx=9,
            pady=2,
            font=(ui_font, 9, "bold"),
            highlightthickness=1,
            highlightbackground=border,
            bd=0,
        )
        self._tone = tone
        self._palette = palette

    def set_status(self, text: str, state: str | None = None, *, tone: str | None = None, palette: dict | None = None):
        if palette is not None:
            self._palette = palette
        resolved_tone = tone or status_tone(state)
        self._tone = resolved_tone
        bg, fg, border = self._palette["badges"].get(resolved_tone, self._palette["badges"]["neutral"])
        self.configure(text=text, bg=bg, fg=fg, highlightbackground=border)


class MetricCard(Card):
    """Interactive KPI card displaying a metric label, value, and optional subtitle."""

    def __init__(self, parent, palette: dict, label: str, ui_font: str, on_click=None):
        super().__init__(parent, palette, padding=(12, 9))
        self.on_click = on_click
        cursor = "hand2" if on_click else ""
        self.title_label = tk.Label(
            self.body, text=label, bg=palette["panel"], fg=palette["muted"],
            font=(ui_font, 9, "bold"), anchor="w", cursor=cursor,
        )
        self.title_label.pack(fill="x")
        self.value_label = tk.Label(
            self.body, text="0", bg=palette["panel"], fg=palette["text"],
            font=(ui_font, 18, "bold"), anchor="w", cursor=cursor,
        )
        self.value_label.pack(fill="x", pady=(3, 0))
        if on_click:
            for widget in (self, self.body, self.title_label, self.value_label):
                widget.bind("<Button-1>", lambda _e: on_click())

    def set_value(self, value: str, accent: str | None = None):
        self.value_label.configure(text=value, fg=accent or self.palette["text"])

    def apply_palette(self, palette: dict):
        super().apply_palette(palette)
        self.title_label.configure(bg=palette["panel"], fg=palette["muted"])
        self.value_label.configure(bg=palette["panel"], fg=palette["text"])


class EmptyState(Card):
    """Helpful empty-state card with guided primary and secondary actions."""

    def __init__(self, parent, palette: dict, title: str, description: str, ui_font: str, actions=()):
        super().__init__(parent, palette, padding=(22, 18))
        self.title_lbl = tk.Label(
            self.body, text=title, bg=palette["panel"], fg=palette["text"],
            font=(ui_font, 13, "bold"), anchor="w", justify="left",
        )
        self.title_lbl.pack(fill="x", pady=(0, 6))
        self.desc_lbl = tk.Label(
            self.body, text=description, bg=palette["panel"], fg=palette["muted"],
            font=(ui_font, 10), anchor="w", justify="left", wraplength=540,
        )
        self.desc_lbl.pack(fill="x", pady=(0, 14))
        self.actions_bar = tk.Frame(self.body, bg=palette["panel"])
        self.actions_bar.pack(fill="x")
        for idx, (label, callback, primary) in enumerate(actions):
            btn = ttk.Button(
                self.actions_bar, text=label, command=callback,
                style="Primary.TButton" if primary else "TButton",
            )
            btn.pack(side="left", padx=(0, 8), pady=2)

    def apply_palette(self, palette: dict):
        super().apply_palette(palette)
        self.title_lbl.configure(bg=palette["panel"], fg=palette["text"])
        self.desc_lbl.configure(bg=palette["panel"], fg=palette["muted"])
        self.actions_bar.configure(bg=palette["panel"])


class CollapsibleSection(ttk.Frame):
    """Progressive-disclosure wrapper hiding advanced settings until requested."""

    def __init__(self, parent, title: str, palette: dict, ui_font: str, *, expanded: bool = False):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.expanded = expanded
        self._title = title
        self._palette = palette
        self.header = tk.Frame(self, bg=palette["elevated"], padx=10, pady=6, highlightthickness=1, highlightbackground=palette["border"])
        self.header.grid(row=0, column=0, sticky="ew")
        self.toggle_btn = tk.Label(
            self.header,
            text=self._label_text(),
            bg=palette["elevated"],
            fg=palette["text_secondary"],
            font=(ui_font, 9, "bold"),
            cursor="hand2",
            anchor="w",
        )
        self.toggle_btn.pack(fill="x")
        self.toggle_btn.bind("<Button-1>", lambda _e: self.toggle())
        self.header.bind("<Button-1>", lambda _e: self.toggle())
        self.content = tk.Frame(self, bg=palette["panel"], padx=12, pady=10, highlightthickness=1, highlightbackground=palette["border"])
        self.content.columnconfigure(1, weight=1)
        if self.expanded:
            self.content.grid(row=1, column=0, sticky="ew")

    def _label_text(self) -> str:
        prefix = "▼" if self.expanded else "▶"
        return f"{prefix}  {self._title}"

    def toggle(self, open_state: bool | None = None):
        self.expanded = (not self.expanded) if open_state is None else bool(open_state)
        self.toggle_btn.configure(text=self._label_text())
        if self.expanded:
            self.content.grid(row=1, column=0, sticky="ew")
        else:
            self.content.grid_forget()

    def apply_palette(self, palette: dict):
        self._palette = palette
        self.header.configure(bg=palette["elevated"], highlightbackground=palette["border"])
        self.toggle_btn.configure(bg=palette["elevated"], fg=palette["text_secondary"])
        self.content.configure(bg=palette["panel"], highlightbackground=palette["border"])


def style_text_widget(widget: tk.Text, palette: dict, mono_font: str | None = None, size: int = 10):
    """Apply consistent colors and subtle border styling to a tk.Text widget."""
    opts = {
        "bg": palette["panel"],
        "fg": palette["text"],
        "insertbackground": palette["text"],
        "selectbackground": palette["active"],
        "selectforeground": palette["text"],
        "highlightbackground": palette["border"],
        "highlightcolor": palette["accent"],
        "highlightthickness": 1,
        "relief": "flat",
    }
    if mono_font:
        opts["font"] = (mono_font, size)
    widget.configure(**opts)


def style_listbox_widget(widget: tk.Listbox, palette: dict, ui_font: str | None = None, size: int = 10):
    """Apply consistent dark/light colors to a tk.Listbox widget."""
    opts = {
        "bg": palette["panel"],
        "fg": palette["text"],
        "selectbackground": palette["active"],
        "selectforeground": palette["text"],
        "highlightbackground": palette["border"],
        "highlightcolor": palette["accent"],
        "highlightthickness": 1,
        "relief": "flat",
    }
    if ui_font:
        opts["font"] = (ui_font, size)
    widget.configure(**opts)
