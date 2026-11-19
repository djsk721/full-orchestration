"""PTY-backed user terminal sessions with VT rendering and bounded scrollback."""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk

from .core import Invalid
from .platform.terminal import create_pty as Pty, operator_shell as operator_shell


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


class TerminalView(ttk.Frame):
    def __init__(self, parent, argv, cwd=None, env=None, *, font="Consolas", palette=None):
        super().__init__(parent)
        try:
            import pyte
        except ImportError as exc:
            self.destroy()
            raise Invalid("통합 터미널에 pyte가 필요합니다. requirements-desktop.txt를 설치하세요.") from exc
        self.screen = pyte.HistoryScreen(80, 25, history=1500)
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
        self.status = ttk.Label(self, text="연결됨 · Ctrl+Shift+V 붙여넣기 · Shift+PgUp/PgDn 스크롤", style="Muted.TLabel")
        self.status.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.surface = tk.Text(self, bg=self.term_bg, fg=self.term_fg, insertbackground="white", relief="flat",
                               highlightthickness=1, highlightbackground=self.term_border,
                               font=(font, 11), wrap="none", padx=10, pady=8, width=32, height=9,
                               state="disabled", takefocus=True)
        self.surface.grid(row=1, column=0, sticky="nsew")
        self.surface.bind("<KeyPress>", self.key)
        self.surface.bind("<Button-1>", lambda _: self.surface.focus_set(), add="+")
        self.surface.bind("<Configure>", self.resize)
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
        for _ in range(12):
            try:
                data = self.events.get_nowait()
            except queue.Empty:
                break
            if data is None:
                self.status.configure(text="세션 종료됨")
                self.close()
                alive = False
                break
            self.stream.feed(data)
            changed = True
        if changed:
            self.draw()
        if alive:
            self.timer = self.after(35, self.poll)

    def key(self, event):
        if self.closed.is_set():
            return "break"
        if event.state & 0x01 and event.keysym in ("Prior", "Next"):
            return self.page(event.keysym == "Prior")
        if event.state & 0x05 == 0x05 and event.keysym.lower() == "v":
            return self.paste(event)
        if event.state & 0x05 == 0x05 and event.keysym.lower() == "c":
            return None
        value = KEYS.get(event.keysym, event.char)
        if value:
            self.send(value)
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
                self.status.configure(text="세션이 입력을 받을 수 없습니다.")

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
                        def color(value, fallback):
                            import re
                            return PALETTE.get(value) or ("#" + value if re.fullmatch(r"[a-fA-F0-9]{6}", value) else fallback)
                        self.surface.tag_configure(tag, foreground=color(fg, self.term_fg), background=color(bg, self.term_bg),
                                                   underline=underline)
                        self.tags.add(tag)
                self.surface.insert("end", "".join(parts), tag)
            if position + 1 < self.screen.lines:
                self.surface.insert("end", "\n")
        if not self.screen.cursor.hidden:
            row, col = self.screen.cursor.y + 1, min(self.screen.cursor.x, self.screen.columns - 1)
            self.surface.tag_configure("terminal_cursor", background="#526583")
            self.surface.tag_raise("terminal_cursor")
            self.surface.tag_add("terminal_cursor", f"{row}.{col}", f"{row}.{col + 1}")
        self.surface.configure(state="disabled")
        self.rendered = True

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
        self.status.configure(text="세션 종료됨")
