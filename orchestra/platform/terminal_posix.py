"""Controlled POSIX terminal sessions, usable on headless Worker hosts."""
from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import pty
import signal
import struct
import subprocess
import sys
import termios
from pathlib import Path


class NativePty:
    def __init__(self, argv, cwd, env, lines, columns):
        self.master, slave = pty.openpty()
        try:
            self.resize(lines, columns)
            slave_entry = str(Path(__file__).resolve())
            self.process = subprocess.Popen([sys.executable, slave_entry, "--slave", *argv],
                                            stdin=slave, stdout=slave, stderr=slave, env=env, cwd=cwd,
                                            start_new_session=True)
        except BaseException:
            os.close(self.master)
            self.master = None
            raise
        finally:
            os.close(slave)

    def read(self):
        master = self.master
        if master is None:
            return b""
        try:
            return os.read(master, 8192)
        except OSError as exc:
            if exc.errno in (errno.EIO, errno.EBADF):
                return b""
            raise

    def write(self, data):
        needed = memoryview(data.encode())
        while needed:
            master = self.master
            if master is None:
                break
            needed = needed[os.write(master, needed):]

    def resize(self, lines, columns):
        master = self.master
        if master is not None:
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", lines, columns, 0, 0))

    def close(self):
        master, self.master = self.master, None
        if master is None:
            return
        os.close(master)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(self.process.pid, signal.SIGHUP)
        try:
            self.process.wait(timeout=.35)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=3)


def operator_shell():
    return [os.environ.get("SHELL") or "/bin/sh", "-i"]


if __name__ == "__main__" and sys.argv[1:2] == ["--slave"]:
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    os.tcsetpgrp(0, os.getpgrp())
    # Some CLI clients use PWD to choose a project even after the PTY child has changed directories.
    os.execvpe(sys.argv[2], sys.argv[2:], os.environ | {"PWD": os.getcwd()})
