"""Launch the frozen Tk workspace and verify it owns and recovers its Supervisor."""
import argparse
from contextlib import closing
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

import psutil


def wait_for(probe, description, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result := probe():
            return result
        time.sleep(.1)
    raise AssertionError(description)


def native_windows():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    visitor = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [visitor, wintypes.LPARAM]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, wintypes.WPARAM]
    user32.keybd_event.restype = None

    def visible_windows(pid):
        matches = []

        @visitor
        def collect(hwnd, _):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid and user32.IsWindowVisible(hwnd):
                title = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title, len(title))
                matches.append((hwnd, title.value))
            return True

        user32.EnumWindows(collect, 0)
        return matches

    def find(pid, *, excluding=None):
        return next((hwnd for hwnd, title in visible_windows(pid)
                     if hwnd != excluding and title == "Model Orchestration"), None)

    def close(hwnd):
        if not user32.PostMessageW(hwnd, 0x0010, 0, 0):  # WM_CLOSE
            raise ctypes.WinError(ctypes.get_last_error())

    def open_terminal(hwnd):
        user32.SetForegroundWindow(hwnd)
        wait_for(lambda: user32.GetForegroundWindow() == hwnd, "the packaged workspace did not receive focus", timeout=5)
        tab, control, letter_t, key_up = 0x09, 0x11, 0x54, 0x02
        # Establish focus inside Tk after the first-run dialog has closed.
        user32.keybd_event(tab, 0, 0, 0)
        user32.keybd_event(tab, 0, key_up, 0)
        user32.keybd_event(control, 0, 0, 0)
        try:
            user32.keybd_event(letter_t, 0, 0, 0)
            user32.keybd_event(letter_t, 0, key_up, 0)
        finally:
            user32.keybd_event(control, 0, key_up, 0)

    return find, close, open_terminal, visible_windows


def supervisor_for(profile, owner, *, previous=None):
    try:
        status = json.loads((profile / "supervisor.json").read_text(encoding="utf-8"))
        if status["pid"] == previous or time.time() - status["at"] >= 5:
            return None
        process = psutil.Process(status["pid"])
        assert process.ppid() == owner.pid, "heartbeat did not originate from the packaged workspace child"
        assert Path(process.exe()).samefile(owner.exe()), "the Supervisor was not launched from the frozen executable"
        return process
    except (FileNotFoundError, json.JSONDecodeError, psutil.NoSuchProcess):
        return None


def local_shell(owner):
    for process in owner.children(recursive=True):
        try:
            if process.name().casefold() == "powershell.exe" and "-NoLogo" in process.cmdline():
                return process
        except psutil.NoSuchProcess:
            continue
    return None


def start_local_shell(owner, window, open_terminal, visible_windows):
    next_shortcut = 0.0

    def probe():
        nonlocal next_shortcut
        if shell := local_shell(owner):
            return shell
        if time.monotonic() >= next_shortcut:
            # Reopening the same local session focuses its existing terminal.
            open_terminal(window)
            next_shortcut = time.monotonic() + 5
        return None

    try:
        return wait_for(probe, "the packaged Tk workspace did not start its local shell")
    except AssertionError:
        print(f"Tk windows after shortcut: {[title for _, title in visible_windows(owner.pid)]}", flush=True)
        print(f"Tk child processes after shortcut: {[child.name() for child in owner.children()]}", flush=True)
        raise


def exercise(binary, profile, *, open_terminal):
    find_window, close_window, open_local_terminal, visible_windows = native_windows()
    env = os.environ | {"ORCHESTRA_DATA": str(profile)}
    env.pop("ORCHESTRA_LANG", None)
    app = subprocess.Popen([str(binary)], env=env)
    owner = psutil.Process(app.pid)
    owned = []
    try:
        picker = wait_for(lambda: find_window(app.pid), "frozen application did not show the first-run picker")
        assert not (profile / "ui_prefs.json").exists(), "first run used a pre-existing preference"
        close_window(picker)  # The picker applies its default language when closed.
        window = wait_for(lambda: find_window(app.pid, excluding=picker), "frozen Tk main window did not open")
        assert json.loads((profile / "ui_prefs.json").read_text(encoding="utf-8"))["locale"] == "ko"

        first = wait_for(lambda: supervisor_for(profile, owner), "packaged Supervisor did not start")
        owned.append(first)
        status = profile / "supervisor.json"
        print(f"Tk first-run and packaged Supervisor startup PASS (PID {first.pid})", flush=True)
        if open_terminal:
            terminal = start_local_shell(owner, window, open_local_terminal, visible_windows)
            owned.append(terminal)
            print(f"Packaged local terminal startup PASS (PowerShell PID {terminal.pid})", flush=True)

        # Kill only the child located through the isolated profile and verified above.
        first.kill()
        first.wait(timeout=10)
        second = wait_for(lambda: supervisor_for(profile, owner, previous=first.pid),
                          "frozen workspace did not replace the terminated Supervisor")
        owned.append(second)
        print(f"Packaged Supervisor recovery PASS (replacement PID {second.pid})", flush=True)

        close_window(window)
        assert app.wait(timeout=12) == 0, "frozen workspace did not exit cleanly"
        if open_terminal:
            terminal.wait(timeout=8)
        (profile / "supervisor.stop").touch()
        second.wait(timeout=12)
        assert not status.exists(), "Supervisor status remained after graceful shutdown"
        layout = json.loads((profile / "ui-workspace.json").read_text(encoding="utf-8"))
        assert layout["version"] == 1
        if open_terminal:
            assert layout["terminals"], "the packaged workspace did not persist the local terminal layout"
        with closing(sqlite3.connect((profile / "state.db").as_uri() + "?mode=ro", uri=True)) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        if app.poll() is None:
            try:
                owned.extend(owner.children(recursive=True))
            except psutil.NoSuchProcess:
                pass
            app.kill()
            app.wait(timeout=10)
        for process in owned:
            try:
                process.kill()
                process.wait(timeout=10)
            except psutil.NoSuchProcess:
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--open-terminal", action="store_true")
    args = parser.parse_args()
    if sys.platform != "win32":
        print("NOT VERIFIED: packaged Tk startup requires native Windows.", file=sys.stderr)
        return 2
    binary = args.binary.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="orchestra-frozen-windows-") as directory:
        exercise(binary, Path(directory) / "한글 프로필", open_terminal=args.open_terminal)
    print("PASS: frozen Tk first-run language, Supervisor restart, shutdown, layout and SQLite integrity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
