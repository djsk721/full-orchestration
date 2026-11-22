"""Reusable styled Tk components aligned with the unified Orca-inspired design system."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .theme import THEMES, TYPE_SCALE, status_tone


def retheme_widget_tree(widget: tk.Misc, palette: dict, bg_key: str = "panel") -> None:
    """Recursively update classic tk Frame/Label widgets inside a container to match palette."""
    for child in widget.winfo_children():
        if isinstance(child, Card):
            child.apply_palette(palette)
            continue
        if isinstance(child, StatusBadge):
            child.set_status(child.cget("text"), tone=child._tone, palette=palette)
            continue
        if isinstance(child, NavRow):
            child.apply_palette(palette)
            continue
        if isinstance(child, CollapsibleSection):
            child.apply_palette(palette)
            continue
        role_bg = getattr(child, "_theme_bg", bg_key)
        role_fg = getattr(child, "_theme_fg", None)
        if isinstance(child, tk.Frame):
            child.configure(bg=palette.get(role_bg, palette[bg_key]))
            retheme_widget_tree(child, palette, role_bg)
        elif isinstance(child, tk.Label):
            fg = palette.get(role_fg, palette["text"]) if role_fg else palette["text"]
            child.configure(bg=palette.get(role_bg, palette[bg_key]), fg=fg)


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
        retheme_widget_tree(self.body, palette, self.bg_key)


class StatusBadge(tk.Label):
    """Pill-like semantic status indicator."""

    def __init__(self, parent, palette: dict, text: str = "—", tone: str = "neutral", ui_font: str = "TkDefaultFont"):
        bg, fg, border = palette["badges"].get(tone, palette["badges"]["neutral"])
        super().__init__(
            parent,
            text=text,
            bg=bg,
            fg=fg,
            padx=8,
            pady=2,
            font=(ui_font, TYPE_SCALE["small"], "bold"),
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
    """Interactive KPI card displaying a metric label and value."""

    def __init__(self, parent, palette: dict, label: str, ui_font: str, on_click=None):
        super().__init__(parent, palette, padding=(12, 9))
        self.on_click = on_click
        cursor = "hand2" if on_click else ""
        self.title_label = tk.Label(
            self.body, text=label, bg=palette["panel"], fg=palette["muted"],
            font=(ui_font, TYPE_SCALE["small"], "bold"), anchor="w", cursor=cursor,
        )
        self.title_label._theme_fg = "muted"
        self.title_label.pack(fill="x")
        self.value_label = tk.Label(
            self.body, text="0", bg=palette["panel"], fg=palette["text"],
            font=(ui_font, 17, "bold"), anchor="w", cursor=cursor,
        )
        self.value_label._theme_fg = "text"
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
        super().__init__(parent, palette, padding=(20, 16))
        self.title_lbl = tk.Label(
            self.body, text=title, bg=palette["panel"], fg=palette["text"],
            font=(ui_font, 12, "bold"), anchor="w", justify="left",
        )
        self.title_lbl._theme_fg = "text"
        self.title_lbl.pack(fill="x", pady=(0, 6))
        self.desc_lbl = tk.Label(
            self.body, text=description, bg=palette["panel"], fg=palette["muted"],
            font=(ui_font, TYPE_SCALE["body"]), anchor="w", justify="left", wraplength=540,
        )
        self.desc_lbl._theme_fg = "muted"
        self.desc_lbl.pack(fill="x", pady=(0, 12))
        self.actions_bar = tk.Frame(self.body, bg=palette["panel"])
        self.actions_bar.pack(fill="x")
        for label, callback, primary in actions:
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
            font=(ui_font, TYPE_SCALE["small"], "bold"),
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


class NavRow(tk.Frame):
    """Compact Orca-style sidebar navigation row with accent indicator, hover, and badge."""

    def __init__(
        self,
        parent,
        palette: dict,
        text: str,
        *,
        icon: str = "",
        ui_font: str = "TkDefaultFont",
        command=None,
    ):
        super().__init__(parent, bg=palette["sidebar"], cursor="hand2")
        self.palette = palette
        self._command = command
        self._active = False
        self._hover = False
        self._ui_font = ui_font

        self.indicator = tk.Frame(self, bg=palette["sidebar"], width=3)
        self.indicator.pack(side="left", fill="y")

        self.icon_lbl = tk.Label(
            self,
            text=icon,
            bg=palette["sidebar"],
            fg=palette["nav_muted"],
            font=(ui_font, TYPE_SCALE["small"]),
            padx=6 if icon else 2,
            pady=5,
            cursor="hand2",
        )
        self.icon_lbl.pack(side="left")

        self.label = tk.Label(
            self,
            text=text,
            anchor="w",
            bg=palette["sidebar"],
            fg=palette["nav_fg"],
            font=(ui_font, TYPE_SCALE["small"]),
            padx=2,
            pady=5,
            cursor="hand2",
        )
        self.label.pack(side="left", fill="x", expand=True)

        self.badge_lbl = tk.Label(
            self,
            text="",
            bg=palette["sidebar"],
            fg=palette["nav_muted"],
            font=(ui_font, TYPE_SCALE["micro"], "bold"),
            padx=6,
            pady=1,
            cursor="hand2",
        )

        for widget in (self, self.indicator, self.icon_lbl, self.label, self.badge_lbl):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<Button-1>", self._on_click)

    def _on_enter(self, _=None):
        self._hover = True
        self._refresh_colors()

    def _on_leave(self, _=None):
        self._hover = False
        self._refresh_colors()

    def _on_click(self, _=None):
        if self._command:
            self._command()

    def invoke(self):
        if self._command:
            self._command()

    def set_active(self, active: bool):
        self._active = bool(active)
        self._refresh_colors()

    def set_text(self, text: str):
        self.label.configure(text=text)

    def set_badge(self, text: str | None):
        if text:
            self.badge_lbl.configure(text=text)
            if not self.badge_lbl.winfo_manager():
                self.badge_lbl.pack(side="right", padx=(2, 6))
        else:
            self.badge_lbl.pack_forget()
        self._refresh_colors()

    def apply_palette(self, palette: dict):
        self.palette = palette
        self._refresh_colors()

    def _refresh_colors(self):
        p = self.palette
        if self._active:
            bg = p["active"]
            fg = p["nav_active_fg"]
            icon_fg = p["accent"]
            ind = p["accent"]
            weight = "bold"
        elif self._hover:
            bg = p["hover"]
            fg = p["nav_active_fg"]
            icon_fg = p["nav_fg"]
            ind = bg
            weight = "normal"
        else:
            bg = p["sidebar"]
            fg = p["nav_fg"]
            icon_fg = p["nav_muted"]
            ind = bg
            weight = "normal"
        self.configure(bg=bg)
        self.indicator.configure(bg=ind)
        self.icon_lbl.configure(bg=bg, fg=icon_fg)
        self.label.configure(bg=bg, fg=fg, font=(self._ui_font, TYPE_SCALE["small"], weight))
        self.badge_lbl.configure(bg=p["elevated"] if self._active else bg, fg=p["accent"] if self._active else p["nav_muted"])


class SettingsSection(Card):
    """Titled configuration section card with consistent inner spacing and theme updates."""

    def __init__(self, parent, palette: dict, title: str, subtitle: str = "", ui_font: str = "TkDefaultFont"):
        super().__init__(parent, palette, padding=(14, 12))
        self.title_lbl = tk.Label(
            self.body, text=title, bg=palette["panel"], fg=palette["text"],
            font=(ui_font, TYPE_SCALE["section"], "bold"), anchor="w",
        )
        self.title_lbl._theme_fg = "text"
        self.title_lbl.pack(fill="x")
        self.subtitle_lbl = None
        if subtitle:
            self.subtitle_lbl = tk.Label(
                self.body, text=subtitle, bg=palette["panel"], fg=palette["muted"],
                font=(ui_font, TYPE_SCALE["small"]), anchor="w", justify="left",
            )
            self.subtitle_lbl._theme_fg = "muted"
            self.subtitle_lbl.pack(fill="x", pady=(2, 8))
        self.content = tk.Frame(self.body, bg=palette["panel"])
        self.content.pack(fill="x", pady=(4 if not subtitle else 0, 0))

    def apply_palette(self, palette: dict):
        super().apply_palette(palette)


class SearchBox(ttk.Frame):
    """Compact search input with optional trailing action button."""

    def __init__(self, parent, textvariable: tk.StringVar, *, button_text: str | None = None, command=None, width: int = 16):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.entry = ttk.Entry(self, textvariable=textvariable, width=width)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.button = None
        if button_text and command:
            self.button = ttk.Button(self, text=button_text, style="Compact.TButton", command=command)
            self.button.grid(row=0, column=1, padx=(4, 0))


class Tooltip:
    """Hover tooltip that adapts to the widget and dismisses cleanly."""

    def __init__(self, widget: tk.Misc, message, delay_ms: int = 550):
        self.widget = widget
        self.message = message
        self.delay_ms = delay_ms
        self._pending = None
        self._tip = None
        widget.bind("<Enter>", self._hover, add="+")
        for event in ("<Leave>", "<ButtonPress>", "<Destroy>"):
            widget.bind(event, self._dismiss, add="+")

    def _show(self):
        self._pending = None
        if not self.widget.winfo_exists():
            return
        text = self.message() if callable(self.message) else str(self.message)
        if not text:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        ttk.Label(tip, text=text, padding=6, wraplength=320, style="Elevated.TLabel").pack()
        tip.update_idletasks()
        x = min(self.widget.winfo_rootx(), self.widget.winfo_screenwidth() - tip.winfo_reqwidth())
        tip.geometry(f"+{max(0, x)}+{self.widget.winfo_rooty() + self.widget.winfo_height() + 3}")
        self._tip = tip

    def _hover(self, _=None):
        if self._pending is None and self._tip is None:
            self._pending = self.widget.after(self.delay_ms, self._show)

    def _dismiss(self, _=None):
        if self._pending is not None:
            try:
                self.widget.after_cancel(self._pending)
            except tk.TclError:
                pass
            self._pending = None
        if self._tip is not None:
            if self._tip.winfo_exists():
                self._tip.destroy()
            self._tip = None


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
