"""Bridge the pyte VT parser to primary and alternate terminal buffers."""
from __future__ import annotations

from functools import lru_cache


ALTERNATE_MODES = frozenset({47, 1047, 1049})


@lru_cache(maxsize=1)
def _history_screen_type(pyte):
    class HistoryScreen(pyte.HistoryScreen):
        # pyte 0.8.2 constructs an event wrapper on every matching lookup
        # and intercepts ordinary attribute reads in its per-character loop.
        # Each screen has stable handlers, so bind pyte's own wrappers once.
        __getattribute__ = object.__getattribute__

        def __init__(self, columns, lines, *, history):
            for event in pyte.Stream.events | {"prev_page", "next_page"}:
                setattr(self, event, pyte.HistoryScreen.__getattribute__(self, event))
            super().__init__(columns, lines, history=history)

    return HistoryScreen


class TerminalScreen:
    def __init__(self, pyte, columns, lines, reply):
        self._pyte = pyte
        self._reply = reply
        self._main = self._buffer(columns, lines, history=1500)
        self._alternate = None

    def _buffer(self, columns, lines, *, history):
        screen = _history_screen_type(self._pyte)(columns, lines, history=history)
        screen.write_process_input = self._reply
        return screen

    @property
    def active(self):
        return self._alternate if self._alternate is not None else self._main

    def __getattr__(self, name):
        if name in self._pyte.Stream.events:
            # pyte keeps parser handlers for the lifetime of the stream.
            # Resolve the receiver for each event when a client switches buffers.
            def dispatch(*args, **kwargs):
                return getattr(self.active, name)(*args, **kwargs)

            setattr(self, name, dispatch)
            return dispatch
        return getattr(self.active, name)

    def set_mode(self, *modes, private=False):
        if private and self._alternate is None and ALTERNATE_MODES.intersection(modes):
            main = self._main
            self._alternate = self._buffer(main.columns, main.lines, history=0)
            self._alternate.mode.update(main.mode.intersection({1 << 5, 2004 << 5}))
        self.active.set_mode(*modes, private=private)

    def reset_mode(self, *modes, private=False):
        if private and ALTERNATE_MODES.intersection(modes):
            self._alternate = None
            self._main.dirty.update(range(self._main.lines))
        self.active.reset_mode(*modes, private=private)

    def reset(self):
        self._alternate = None
        self._main.reset()

    def resize(self, lines, columns):
        self._resize_buffer(self._main, lines, columns)
        if self._alternate is not None:
            self._resize_buffer(self._alternate, lines, columns)

    @staticmethod
    def _resize_buffer(screen, lines, columns):
        if lines < screen.lines:
            while screen.history.position < screen.history.size:
                screen.next_page()
            # Trim from the bottom unless the cursor would disappear. Preserve
            # any rows that move above the cursor's new viewport in scrollback.
            offset = max(0, screen.cursor.y - lines + 1)
            screen.history.top.extend(screen.buffer[index] for index in range(offset))
            visible = {index - offset: row for index, row in screen.buffer.items()
                       if offset <= index < offset + lines}
            screen.buffer.clear()
            screen.buffer.update(visible)
            screen.cursor.y -= offset
            screen.lines = lines
            screen.dirty.update(range(lines))
        screen.resize(lines, columns)

    def report_device_status(self, mode, private=False):
        if private and mode == 6:
            cursor = self.active.cursor
            self._reply(f"\x1b[?{cursor.y + 1};{min(cursor.x + 1, self.active.columns)}R")
        elif not private:
            self.active.report_device_status(mode)
