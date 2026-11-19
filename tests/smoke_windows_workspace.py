"""Native Windows interactive-desktop smoke. Run on Windows with Tcl/Tk and pywinpty."""
import argparse
import ctypes
from importlib.metadata import version
import json
import platform
import re
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

import psutil

from benchmark_workspace_terminal import summary
from smoke_integrated_workspace import (
    WorkspaceDesktop, fixture_repo, inspect_project, put_project, screen, terminal_text, wait,
)
from orchestra.platform.desktop import prepare_dpi
from orchestra.platform.terminal_windows import NativePty


CONSOLE_FIXTURE = """import os, subprocess, sys
sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(90)"])
print(f"child-pid={child.pid}")
print("fixture-console · 한글", flush=True)
try:
    while True:
        try:
            text = input()
            if text == "dimensions":
                dims = os.get_terminal_size()
                print(f"size={dims.columns}x{dims.lines}")
            elif text == "burst":
                for number in range(8000):
                    print(f"\\x1b[36mwin-row-{number:04}\\x1b[0m")
                print("burst-complete")
            else:
                print("received:" + text)
        except KeyboardInterrupt:
            print("interrupt-received")
        except EOFError:
            break
finally:
    if child.poll() is None:
        child.terminate()
        child.wait(timeout=5)
"""


def disappeared(process):
    try:
        return not process.is_running() or process.status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


def launch_console(app, repository):
    return app.new_terminal("ConPTY fixture", [sys.executable, "-u", "-c", CONSOLE_FIXTURE], repository)


def exercise(window, app, repository, expected_dpi, output):
    window.update()
    dpi = ctypes.windll.user32.GetDpiForWindow(ctypes.c_void_p(window.winfo_id()))
    assert dpi, "Windows returned no native window DPI"
    if expected_dpi:
        assert dpi == expected_dpi, f"Expected DPI {expected_dpi}, Windows reported {dpi}"
    print(f"{platform.platform()} · Python {platform.python_version()} · "
          f"Tk {window.tk.call('package', 'provide', 'Tk')} · pywinpty {version('pywinpty')}", flush=True)
    print(f"Observed Windows window DPI: {dpi}", flush=True)
    shell = launch_console(app, repository)
    app.split_terminal("horizontal")
    terminal = app.terminal_tabs[shell]
    parents = [psutil.Process(view.pty.pty.pid) for view in terminal.views]
    owned = list(parents)

    try:
        for index, view in enumerate(terminal.views):
            assert isinstance(view.pty, NativePty), "terminal did not use native ConPTY"
            app.focus_terminal(shell, index)
            view.surface.focus_force()
            wait(window, lambda: "fixture-console · 한글" in terminal_text(view), "console did not render Unicode")
            parent = parents[index]
            match = wait(window, lambda: re.search(r"child-pid=(\d+)", terminal_text(view)), "child PID unavailable")
            child = psutil.Process(int(match.group(1)))
            owned.append(child)
            assert child.ppid() == parent.pid

            view.surface.clipboard_clear()
            view.surface.clipboard_append("검증 window")
            view.paste()
            view.send("\r")
            wait(window, lambda: "received:검증 window" in terminal_text(view), "clipboard did not pass through ConPTY")
            marker = view.surface.search("received:검증 window", "1.0")
            view.surface.tag_add("sel", f"{marker}+9c", f"{marker}+18c")
            view.copy_selection()
            assert view.surface.clipboard_get() == "검증 window"

        before = [(view.screen.lines, view.screen.columns) for view in terminal.views]
        app.split_terminal("vertical")
        ready = time.monotonic() + .3
        wait(window, lambda: time.monotonic() >= ready, "split redraw did not settle")
        assert [(view.screen.lines, view.screen.columns) for view in terminal.views] != before, (
            "switching split orientation did not resize the native terminals"
        )
        for index, view in enumerate(terminal.views):
            app.focus_terminal(shell, index)
            view.send("dimensions\r")
            expected = f"size={view.screen.columns}x{view.screen.lines}"
            wait(window, lambda: expected in terminal_text(view), "ConPTY dimensions did not match the terminal")
        terminal.views[1].send("\x03")
        wait(window, lambda: "interrupt-received" in terminal_text(terminal.views[1]), "Ctrl+C did not reach the console")
        screen(window, output, f"windows-conpty-{dpi}dpi.png")
        app.remove_terminal(shell)
        wait(window, lambda: all(disappeared(process) for process in owned), "owned console processes remained after closing",
             timeout=6)
    finally:
        for parent in parents:
            try:
                owned.extend(parent.children(recursive=True))
            except psutil.NoSuchProcess:
                pass
        if shell in app.terminal_tabs:
            app.remove_terminal(shell)
        for process in reversed(owned):
            try:
                if process.is_running():
                    process.kill()
            except psutil.NoSuchProcess:
                pass


def benchmark(window, app, repository, orientation=None):
    key = launch_console(app, repository)
    if orientation:
        app.split_terminal(orientation)
    views = app.terminal_tabs[key].views
    processes = [psutil.Process(view.pty.pty.pid) for view in views]
    children = []
    timer = None
    try:
        for view, process in zip(views, processes):
            match = wait(window, lambda: re.search(r"child-pid=(\d+)", terminal_text(view)), "fixture did not start")
            child = psutil.Process(int(match[1]))
            assert child.ppid() == process.pid
            children.append(child)
        desktop = psutil.Process()
        depths = [0 for _ in views]
        event_delays = []
        start_rss = peak_rss = desktop.memory_info().rss
        cpu = sum(desktop.cpu_times()[:2])
        start = time.perf_counter()
        scheduled = start + .02

        def tick():
            nonlocal scheduled, timer, peak_rss
            now = time.perf_counter()
            event_delays.append(max(0, (now - scheduled) * 1000))
            for index, view in enumerate(views):
                depths[index] = max(depths[index], view.events.qsize())
            peak_rss = max(peak_rss, desktop.memory_info().rss)
            scheduled = now + .02
            timer = window.after(20, tick)

        timer = window.after(20, tick)
        for view in views:
            view.send("burst\r")
        wait(window, lambda: all("burst-complete" in terminal_text(view) for view in views),
             "native ConPTY output stalled", timeout=60)
        elapsed = (time.perf_counter() - start) * 1000
        elapsed_cpu = (sum(desktop.cpu_times()[:2]) - cpu) * 1000
        window.after_cancel(timer)
        timer = None
        for view in views:
            history = view.screen.history.top
            assert len(history) == 1500, "ConPTY did not fill the bounded scrollback"
            retained = ["".join(row[x].data for x in range(view.screen.columns)) for row in history]
            retained.extend(view.screen.display)
            ids = [int(match[1]) for row in retained if (match := re.fullmatch(r"win-row-(\d{4})", row.rstrip()))]
            assert len(ids) >= 1500 and ids == list(range(8000 - len(ids), 8000)), "retained ConPTY rows differ"
            last = view.surface.search("win-row-7999", "1.0")
            assert last and "colors_cyan_default_False" in view.surface.tag_names(last), "ANSI color was lost"
        print("ConPTY benchmark " + json.dumps({
            "scenario": orientation or "one", "sessions": len(views), "rows_per_session": 8000,
            "elapsed_ms": round(elapsed, 1), "event_ms": summary(event_delays), "desktop_cpu_ms": round(elapsed_cpu, 1),
            "rss_start": start_rss, "rss_peak": peak_rss, "sampled_queue_peak": depths,
            "history_rows": [len(view.screen.history.top) for view in views], "pty_pids": [proc.pid for proc in processes],
        }), flush=True)
    finally:
        if timer is not None:
            window.after_cancel(timer)
        app.remove_terminal(key)
        owned = processes + children
        try:
            wait(window, lambda: all(disappeared(process) for process in owned), "benchmark left a child process", timeout=6)
        finally:
            for process in reversed(owned):
                try:
                    if not disappeared(process):
                        process.kill()
                except psutil.NoSuchProcess:
                    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-dpi", type=int, choices=(96, 120, 144))
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    if sys.platform != "win32":
        print("NOT VERIFIED: this smoke requires a native Windows interactive desktop.", file=sys.stderr)
        return 2
    prepare_dpi()
    with tempfile.TemporaryDirectory(prefix="orchestra-native-windows-") as temporary:
        root = Path(temporary)
        repo = fixture_repo(root / "한글 프로젝트")
        data = root / "프로필 데이터"
        put_project(data, inspect_project(repo) | {"name": "Windows Unicode fixture"})
        with patch("orchestra.desktop.start_supervisor"):
            window = tk.Tk()
            app = WorkspaceDesktop(window, data)
            try:
                exercise(window, app, repo, args.expected_dpi, args.screenshots)
                if args.benchmark:
                    for orientation in (None, "horizontal", "vertical"):
                        benchmark(window, app, repo, orientation)
                app.local_project_shell()
                app.save_workspace_layout()
            finally:
                app.close()
            window = tk.Tk()
            app = WorkspaceDesktop(window, data)
            try:
                assert app.terminal_descriptors(), "no session layout was saved"
                assert all(not tab.views for tab in app.terminal_tabs.values()), "restoring the layout launched a process"
            finally:
                app.close()
    print("PASS: native Windows ConPTY fixtures, Unicode path, clipboard, resize, cancellation, cleanup and passive restoration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
