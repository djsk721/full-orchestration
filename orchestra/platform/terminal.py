"""Terminal port and operating-system dispatch."""
from __future__ import annotations

import os
from typing import Protocol

from ..processes import executable


class TerminalSession(Protocol):
    def read(self) -> bytes: ...
    def write(self, data: str) -> None: ...
    def resize(self, lines: int, columns: int) -> None: ...
    def close(self) -> None: ...


def backend():
    if os.name == "nt":
        from . import terminal_windows
        return terminal_windows
    from . import terminal_posix
    return terminal_posix


def create_pty(argv, cwd, env, lines=25, columns=80) -> TerminalSession:
    return backend().NativePty([executable(argv[0], env), *argv[1:]], cwd, env, lines, columns)


def operator_shell(cwd=None):
    return backend().operator_shell()
