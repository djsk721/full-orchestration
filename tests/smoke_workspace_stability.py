"""Measure native workspace resources while cycling sessions, views and layout."""
import argparse
import os
import sys
from statistics import median, quantiles
import tempfile
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

import psutil

from smoke_integrated_workspace import (
    WorkspaceDesktop, fixture_repo, inspect_project, put_project, terminal_fixture, terminal_text, wait,
)
from orchestra.core import Invalid
from orchestra.project_files import browse_project, project_file_diff


def exercise(window, app, projects, cycles, idle_seconds, rounds):
    process = psutil.Process()
    if idle_seconds:
        app.select_workspace_project(projects[0])
        tab = app.open_ai_terminal("Codex")
        app.split_terminal("horizontal", "OpenCode")
        views = app.terminal_tabs[tab].views
        wait(window, lambda: "OpenCode" in terminal_text(views[1]), "idle PTY failed to start")
        before_idle = sum(process.cpu_times()[:2])
        stop_idle = time.monotonic() + idle_seconds
        while time.monotonic() < stop_idle:
            window.update()
            time.sleep(.04)
        assert all(view.pty.process.poll() is None for view in views)
        print(f"resident PTY idle: wall_s={idle_seconds} cpu_s={sum(process.cpu_times()[:2]) - before_idle:.2f} "
              f"rss_end={process.memory_info().rss}", flush=True)
        app.remove_terminal(tab)

    delays = []
    scheduled = time.monotonic()
    pulse_id = None

    def sample():
        nonlocal pulse_id, scheduled
        now = time.monotonic()
        delays.append(max(0, (now - scheduled) * 1000))
        scheduled = now + .020
        pulse_id = window.after(20, sample)

    def run_round(index):
        nonlocal scheduled
        scheduled = time.monotonic()
        delays.clear()
        sample()
        baseline = process.memory_info().rss
        baseline_cpu = sum(process.cpu_times()[:2])
        started = time.monotonic()
        peak = baseline
        child_peak = 0
        seen = set()
        for attempt in range(cycles):
            app.select_workspace_project(projects[attempt % 2])
            tab = app.open_ai_terminal("Codex")
            first = app.terminal_tabs[tab].views[0]
            app.split_terminal("horizontal", "OpenCode")
            second = app.terminal_tabs[tab].views[1]
            wait(window, lambda: "OpenCode" in terminal_text(second), "second session did not render")
            assert app.open_ai_terminal("Codex") == tab
            app.split_terminal("vertical")
            window.geometry(f"{1040 + 30 * (attempt % 4)}x{700 + 20 * (attempt % 3)}")
            app.workspace_toggle_focus()
            window.update()
            app.workspace_toggle_focus()
            window.update()
            children = [item.pty.process for item in (first, second)]
            child_peak = max(child_peak, len(process.children(recursive=True)))
            seen.update(child.pid for child in children)
            app.remove_terminal(tab)
            assert all(child.poll() is not None for child in children)
            assert not app.terminals
            peak = max(peak, process.memory_info().rss)
        burst_start = time.monotonic()
        tab = app.new_terminal("Output fixture", [
            sys.executable, "-u", "-c", "for i in range(8000): print(f'output-line-{i:05}')\ninput()",
        ])
        view = app.terminal_tabs[tab].views[0]
        wait(window, lambda: "output-line-07999" in terminal_text(view), "terminal lost long output")
        burst_ms = (time.monotonic() - burst_start) * 1000
        assert len(view.screen.history.top) <= 1500
        app.remove_terminal(tab)
        wait(window, lambda: not process.children(), "fixture sessions left live child processes", timeout=4)
        settle_until = time.monotonic() + .8
        while time.monotonic() < settle_until:
            window.update()
            time.sleep(.01)
        finish = process.memory_info().rss
        p95 = quantiles(delays, n=20, method="inclusive")[18]
        print(f"workspace round={index} cycles={cycles} unique_pty_pids={len(seen)} child_peak={child_peak} "
              f"wall_s={time.monotonic()-started:.2f} cpu_s={sum(process.cpu_times()[:2])-baseline_cpu:.2f} "
              f"rss_start={baseline} rss_peak={max(peak, finish)} rss_end={finish} threads_end={process.num_threads()} "
              f"event_samples={len(delays)} event_median_ms={median(delays):.2f} event_p95_ms={p95:.2f} "
              f"event_max_ms={max(delays):.2f} terminal_burst_ms={burst_ms:.2f}", flush=True)

    for index in range(1, rounds + 1):
        try:
            run_round(index)
        finally:
            if pulse_id is not None:
                window.after_cancel(pulse_id)
                pulse_id = None


def main(cycles, idle_seconds, rounds):
    if os.name != "posix":
        raise SystemExit("This resource measurement uses POSIX PTY process IDs.")
    with tempfile.TemporaryDirectory(prefix="orchestra-stability-") as directory:
        root = Path(directory)
        repos = [fixture_repo(root / name) for name in ("workspace-one", "workspace-two")]
        for index in range(500):
            (repos[0] / f"file-{index:04}.txt").touch()
        files, truncated = browse_project(repos[0])
        assert truncated and len(files) == 400
        (repos[1] / "large.txt").write_bytes(b"x" * 200_001)
        try:
            project_file_diff(repos[1], "large.txt", "??")
        except Invalid:
            pass
        else:
            raise AssertionError("large diff exceeded the bounded preview")
        data = root / "data"
        ids = [put_project(data, inspect_project(repo) | {"name": repo.name}) for repo in repos]
        saved = data / "ui-workspace.json"
        outdated = b'{"version":999,"terminals":[{"command":"must not launch"}]}'
        saved.write_bytes(outdated)
        cli = {name: terminal_fixture(name, root / name.lower()) for name in ("Codex", "OpenCode")}
        with patch("orchestra.desktop.start_supervisor"), patch("orchestra.workspace_sessions.scan_clis", return_value=cli):
            window = tk.Tk()
            app = WorkspaceDesktop(window, data)
            window.update()
            assert not app.terminals and not app.workspace_layout_writable
            exercise(window, app, ids, cycles, idle_seconds, rounds)
            app.close()
            assert saved.read_bytes() == outdated
            malformed = b'{"version": 1'
            saved.write_bytes(malformed)
            window = tk.Tk()
            app = WorkspaceDesktop(window, data)
            window.update()
            assert not app.terminals and not app.workspace_layout_writable
            app.workspace_reset_layout()
            window.update()
            app.close()
            assert b'"version": 1' in saved.read_bytes()
        print("Layout restart, malformed/outdated fallback, capped tree and large diff rejection passed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=30)
    parser.add_argument("--idle-seconds", type=int, default=0)
    parser.add_argument("--rounds", type=int, default=1)
    args = parser.parse_args()
    if args.cycles < 1 or args.rounds < 1 or args.idle_seconds < 0:
        parser.error("cycles and rounds must be positive and idle-seconds cannot be negative")
    main(args.cycles, args.idle_seconds, args.rounds)
