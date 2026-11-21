"""PTY-backed user terminal sessions with VT rendering and bounded scrollback."""
from __future__ import annotations

import os
import queue
import re
import threading
import time
import tkinter as tk
from functools import partial
from tkinter import ttk

from .core import Invalid
from .platform.terminal import create_pty as Pty, operator_shell as operator_shell
from .terminal_screen import TerminalScreen
from .ui.workspace_strings import workspace_text


__all__ = ["Pty", "TerminalView", "operator_shell"]


KEYS = {"Return": "\r", "BackSpace": "\x7f", "Escape": "\x1b", "Tab": "\t",
        "Up": "\x1b[A", "Down": "\x1b[B", "Right": "\x1b[C", "Left": "\x1b[D",
        "Home": "\x1b[H", "End": "\x1b[F", "Delete": "\x1b[3~",
        "Insert": "\x1b[2~", "Prior": "\x1b[5~", "Next": "\x1b[6~"}
PALETTE = {"black": "#1a2535", "red": "#f07883", "green": "#8cd4aa", "brown": "#f4c880",
           "blue": "#8bb8ff", "magenta": "#d2a6ed", "cyan": "#7dd5dc", "white": "#e5edf7",
           "brightblack": "#8192a7", "brightred": "#ffa2aa", "brightgreen": "#b7f4bd",
           "brightbrown": "#ffe09a", "brightblue": "#9bcfff", "brightmagenta": "#eec0ff",
           "brightcyan": "#98ebeb", "brightwhite": "#ffffff"}
HEX_COLOR = re.compile(r"[a-fA-F0-9]{6}")


def terminal_color(value, fallback):
    return PALETTE.get(value) or ("#" + value if HEX_COLOR.fullmatch(value) else fallback)


class TerminalView(ttk.Frame):
    def __init__(self, parent, argv, cwd=None, env=None, *, font="Consolas", palette=None, locale="ko"):
        super().__init__(parent)
        self.w = partial(workspace_text, locale)
        self.session_title = ""
        self.session_state = self.w("대화형 터미널")
        try:
            import pyte
        except ImportError as exc:
            self.destroy()
            raise Invalid(self.w("통합 터미널에 pyte가 필요합니다. requirements-desktop.txt를 설치하세요.")) from exc
        self.screen = TerminalScreen(pyte, 80, 25, self.send)
        self.stream = pyte.ByteStream(self.screen)
        self.events = queue.Queue(maxsize=48)
        self.closed = threading.Event()
        self.rendered = False
        self.tags = set()
        self.term_bg = (palette or {}).get("terminal_bg", "#0f1724")
        self.term_fg = (palette or {}).get("terminal_fg", "#e5edf7")
        self.term_border = (palette or {}).get("border", "#2a364b")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.status = ttk.Label(self, text=self.session_state, style="Muted.TLabel")
        self.status.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.surface = tk.Text(self, bg=self.term_bg, fg=self.term_fg, insertbackground="white", relief="flat",
                               highlightthickness=2, highlightbackground=self.term_border,
                               highlightcolor=(palette or {}).get("accent", "#3b82f6"),
                               font=(font, 11), wrap="none", padx=10, pady=8, width=32, height=9,
                               state="disabled", takefocus=True)
        self.surface.grid(row=1, column=0, sticky="nsew")
        self.surface.bind("<KeyPress>", self.key)
        self.surface.bind("<Button-1>", lambda _: self.surface.focus_set(), add="+")
        self.surface.bind("<Configure>", self.resize)
        self.surface.bind("<Map>", self.redraw_when_visible)
        self.surface.bind("<MouseWheel>", lambda event: self.page(event.delta > 0))
        self.surface.bind("<Button-4>", lambda _: self.page(True))
        self.surface.bind("<Button-5>", lambda _: self.page(False))
        self.surface.bind("<<Paste>>", self.paste)
        launch_env = dict(os.environ if env is None else env)
        launch_env.setdefault("TERM", "xterm-256color")
        try:
            self.pty = Pty(argv, cwd, launch_env)
        except BaseException:
            self.destroy()
            raise
        threading.Thread(target=self.reader, name="terminal-read", daemon=True).start()
        self.timer = self.after(35, self.poll)

    def reader(self):
        try:
            while not self.closed.is_set():
                data = self.pty.read()
                if not data:
                    break
                while not self.closed.is_set():
                    try:
                        self.events.put(data, timeout=.15)
                        break
                    except queue.Full:
                        continue
        except (EOFError, OSError, TypeError, ValueError):
            pass
        finally:
            while not self.closed.is_set():
                try:
                    self.events.put(None, timeout=.15)
                    break
                except queue.Full:
                    continue

    def poll(self):
        changed = not self.rendered
        alive = True
        # Each pane yields after a short slice so active panes and input
        # handlers can share the Tk thread even while the PTY queue is full.
        deadline = time.monotonic() + .008
        for _ in range(12):
            try:
                data = self.events.get_nowait()
            except queue.Empty:
                break
            if data is None:
                self.close()
                alive = False
                break
            self.stream.feed(data)
            changed = True
            if time.monotonic() >= deadline:
                break
        if changed and self.surface.winfo_ismapped():
            self.draw()
        if alive:
            self.timer = self.after(4 if not self.events.empty() else 35, self.poll)

    def redraw_when_visible(self, _=None):
        self.draw()

    def key(self, event):
        if event.state & 0x01 and event.keysym in ("Prior", "Next"):
            return self.page(event.keysym == "Prior")
        if event.state & 0x05 == 0x05 and event.keysym.lower() == "c":
            return self.copy_selection()
        if self.closed.is_set():
            return "break"
        if event.state & 0x05 == 0x05 and event.keysym.lower() == "v":
            return self.paste(event)
        value = KEYS.get(event.keysym, event.char)
        if event.keysym in ("Up", "Down", "Left", "Right") and 1 << 5 in self.screen.mode:
            value = "\x1bO" + value[-1]
        if value:
            self.send(value)
        return "break"

    def copy_selection(self, _=None):
        try:
            value = self.surface.get("sel.first", "sel.last")
            self.clipboard_clear()
            self.clipboard_append(value)
        except tk.TclError:
            pass
        return "break"

    def paste(self, _=None):
        try:
            value = self.clipboard_get()
        except tk.TclError:
            return "break"
        if value and len(value) <= 12000:
            if 2004 << 5 in self.screen.mode:
                value = "\x1b[200~" + value + "\x1b[201~"
            self.send(value)
        return "break"

    def send(self, data):
        if not self.closed.is_set():
            try:
                self.pty.write(data)
            except (OSError, EOFError, ValueError):
                self.set_session_label(state=self.w("세션이 입력을 받을 수 없습니다."))

    def page(self, up):
        (self.screen.prev_page if up else self.screen.next_page)()
        self.draw()
        return "break"

    def resize(self, event):
        import tkinter.font as tkfont
        font = tkfont.Font(font=self.surface.cget("font"))
        columns = max(20, min(260, (event.width - 20) // max(1, font.measure("M"))))
        lines = max(4, min(100, (event.height - 14) // max(1, font.metrics("linespace"))))
        if self.closed.is_set() or (lines, columns) == (self.screen.lines, self.screen.columns):
            return
        self.screen.resize(lines, columns)
        try:
            self.pty.resize(lines, columns)
        except (OSError, EOFError):
            pass
        self.draw()

    def draw(self):
        self.surface.configure(state="normal")
        self.surface.delete("1.0", "end")
        chunks = []
        for position in range(self.screen.lines):
            line = self.screen.buffer[position]
            spans = []
            for x in range(self.screen.columns):
                char = line[x]
                fg, bg = (char.bg, char.fg) if char.reverse else (char.fg, char.bg)
                style = (fg, bg, char.underscore)
                if spans and spans[-1][0] == style:
                    spans[-1][1].append(char.data)
                else:
                    spans.append((style, [char.data]))
            for style, parts in spans:
                fg, bg, underline = style
                tag = f"colors_{fg}_{bg}_{underline}"
                if tag not in self.tags:
                    if len(self.tags) >= 256:
                        tag = ""
                    else:
                        self.surface.tag_configure(tag, foreground=terminal_color(fg, self.term_fg),
                                                   background=terminal_color(bg, self.term_bg),
                                                   underline=underline)
                        self.tags.add(tag)
                chunks.extend(("".join(parts), tag))
            if position + 1 < self.screen.lines:
                chunks.extend(("\n", ""))
        self.surface.insert("end", *chunks)
        if not self.screen.cursor.hidden:
            position = self.screen.cursor.y
            line = self.screen.buffer[position]
            column = min(self.screen.cursor.x, self.screen.columns - 1)
            while column and not line[column].data:
                column -= 1
            preceding = "".join(line[x].data for x in range(column))
            offset = self.surface.tk.call("string", "length", preceding)
            width = self.surface.tk.call("string", "length", line[column].data)
            self.surface.tag_configure("terminal_cursor", background="#526583")
            self.surface.tag_raise("terminal_cursor")
            self.surface.tag_add("terminal_cursor", f"{position + 1}.{offset}", f"{position + 1}.{offset + width}")
        self.surface.configure(state="disabled")
        self.rendered = True

    def apply_palette(self, palette):
        self.term_bg = palette["terminal_bg"]
        self.term_fg = palette["terminal_fg"]
        self.term_border = palette["border"]
        self.surface.configure(bg=self.term_bg, fg=self.term_fg, highlightbackground=self.term_border,
                               highlightcolor=palette["accent"])
        self.tags.clear()
        self.draw()

    def close(self):
        if self.closed.is_set():
            return
        self.closed.set()
        if hasattr(self, "timer"):
            self.after_cancel(self.timer)
        try:
            self.pty.close()
        except (OSError, EOFError, ValueError):
            pass
        self.set_session_label(state=self.w("세션 종료됨"))

    def set_session_label(self, *, title=None, state=None):
        if title is not None:
            self.session_title = title
        if state is not None:
            self.session_state = state
        self.status.configure(text=" · ".join(filter(None, (self.session_title, self.session_state))))
