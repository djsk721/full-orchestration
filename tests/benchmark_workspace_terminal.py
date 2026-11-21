"""Benchmark the real Tk and PTY path with deterministic, offline console processes."""
import argparse
import json
import os
import re
import sys
import tempfile
import time
import tkinter as tk
from collections import Counter
from pathlib import Path
from statistics import median, quantiles
from unittest.mock import patch

import psutil

from smoke_integrated_workspace import (
    WorkspaceDesktop, fixture_repo, inspect_project, put_project, terminal_text, wait,
)


FIXTURE = '''#!{python}
import os
import pathlib
label = pathlib.Path.cwd().name + "-" + pathlib.Path(__file__).name
print("ready:" + label, flush=True)
while True:
    message = input()
    if message.startswith("go:"):
        count = int(message.split(":")[1])
        for offset in range(0, count, 80):
            lines = "".join(f"\\x1b[36mrow-{{n:05}}-한글\\x1b[0m\\n"
                            for n in range(offset, min(offset + 80, count)))
            os.write(1, lines.encode("utf-8"))
        print("complete:" + label, flush=True)
    else:
        print("answer:" + label + ":" + message, flush=True)
'''


def summary(samples):
    if not samples:
        return {}
    p95 = quantiles(samples, n=100, method="inclusive") if len(samples) > 1 else samples * 99
    return {key: round(value, 3) for key, value in (
        ("median", median(samples)), ("p95", p95[94]), ("p99", p95[98]), ("max", max(samples)),
    )}


def timed(sink, operation, *args, **kwargs):
    start = time.perf_counter()
    try:
        return operation(*args, **kwargs)
    finally:
        sink.append((time.perf_counter() - start) * 1000)


class Trace:
    def __init__(self, view, label):
        self.view = view
        self.label = label
        self.marker = f"complete:{label}".encode()
        self.start = 0
        self.parsed = self.rendered = None
        self.read, self.read_sizes, self.put, self.feed, self.draw = [], [], [], [], []
        self.queue_peak = 0
        self.output = bytearray()
        read, put, feed, draw = view.pty.read, view.events.put, view.stream.feed, view.draw

        def traced_read():
            data = timed(self.read, read)
            if data:
                self.read_sizes.append(len(data))
            return data

        def traced_put(*args, **kwargs):
            try:
                return timed(self.put, put, *args, **kwargs)
            finally:
                self.queue_peak = max(self.queue_peak, view.events.qsize())

        def traced_feed(data):
            timed(self.feed, feed, data)
            self.output.extend(data)
            if self.parsed is None and self.marker in self.output[-(len(data) + len(self.marker)):]:
                self.parsed = (time.perf_counter() - self.start) * 1000

        def traced_draw(*args, **kwargs):
            timed(self.draw, draw, *args, **kwargs)
            if self.rendered is None and self.parsed is not None and self.marker.decode() in terminal_text(view):
                self.rendered = (time.perf_counter() - self.start) * 1000

        view.pty.read, view.events.put = traced_read, traced_put
        view.stream.feed, view.draw = traced_feed, traced_draw

    def check(self, lines):
        plain_rows = re.findall(rb"row-(\d+)-([^\r\x1b]+)", self.output)
        ids = [int(value) for value, _ in plain_rows]
        assert all(text == "한글".encode() for _, text in plain_rows), self.label
        assert self.output.count(self.marker) == 1, self.label
        assert self.output.count(b"\x1b[36m") == lines == self.output.count(b"\x1b[0m"), self.label
        counts = Counter(ids)
        missing = len(set(range(lines)) - counts.keys())
        duplicated = sum(count - 1 for count in counts.values())
        assert not missing and not duplicated and ids == list(range(lines)), (self.label, missing, duplicated)
        assert self.rendered is not None, self.label
        assert f"row-{lines - 1:05}-한글" in terminal_text(self.view), self.label
        assert any(str(tag).startswith("colors_cyan_") for tag in self.view.surface.tag_names(
            self.view.surface.search(f"row-{lines - 1:05}", "1.0"))), self.label
        history = self.view.screen.history.top
        assert len(history) == min(1500, max(0, lines + 3 - self.view.screen.lines)), self.label
        retained = ["".join(row[column].data for column in range(self.view.screen.columns)) for row in history]
        retained.extend(self.view.screen.display)
        retained_ids = [int(match[1]) for row in retained if (match := re.fullmatch(r"row-(\d+)-한글", row.rstrip()))]
        assert len(retained_ids) >= len(history) and retained_ids == list(range(lines - len(retained_ids), lines)), self.label
        return {"label": self.label, "parse_ms": round(self.parsed, 3), "display_ms": round(self.rendered, 3),
                "bytes": len(self.output), "reads": len(self.read_sizes), "read_bytes": summary(self.read_sizes),
                "read_block_ms": summary(self.read), "queue_peak": self.queue_peak, "queue_put_ms": summary(self.put),
                "feed_calls": len(self.feed), "feed_total_ms": round(sum(self.feed), 3), "feed_ms": summary(self.feed),
                "draw_calls": len(self.draw), "draw_total_ms": round(sum(self.draw), 3), "draw_ms": summary(self.draw),
                "history_rows": len(history), "missing": missing, "duplicated": duplicated}


def tabs_for(window, app, projects, scenario):
    names = [("horizontal", ("Codex",))] if scenario == "one" else [(scenario, ("Codex", "OpenCode"))]
    if scenario == "four":
        names = [("horizontal", ("Codex", "OpenCode")), ("vertical", ("Codex", "OpenCode"))]
    for project, (orient, tools) in zip(projects, names):
        app.select_workspace_project(project)
        key = app.open_ai_terminal(tools[0])
        if len(tools) == 2:
            app.split_terminal(orient, tools[1])
        views = app.terminal_tabs[key].views
        wait(window, lambda: all("ready:" in terminal_text(view) for view in views), "fixture did not start")
        yield project, key, views, tools


def exercise(window, app, projects, scenario, lines):
    tabs = list(tabs_for(window, app, projects, scenario))
    traced_tabs = [(project, key, [
        Trace(view, f"bench-{projects.index(project)}-{name}") for view, name in zip(views, names)
    ], names) for project, key, views, names in tabs]
    traces = [trace for _, _, group, _ in traced_tabs for trace in group]
    process = psutil.Process()
    pid_set = {trace.view.pty.process.pid for trace in traces}
    assert len(pid_set) == len(traces)
    cpu_before = sum(process.cpu_times()[:2])
    rss_before = rss_peak = process.memory_info().rss
    delays = []
    planned = started = time.perf_counter()
    timer = None
    switch_timer = None
    switches = 0
    switch_error = None

    def pulse():
        nonlocal planned, timer
        now = time.perf_counter()
        delays.append(max(0, (now - planned) * 1000))
        planned = now + .020
        timer = window.after(20, pulse)

    def focus(item, panel):
        project, key, group, names = item
        app.select_workspace_project(project)
        assert app.open_ai_terminal(names[panel]) == key
        assert app.terminal_tabs[key].views[panel] is group[panel].view

    def switch():
        nonlocal switches, switch_timer, switch_error
        try:
            focus(traced_tabs[switches % 2], (switches // 2) % 2)
        except Exception as error:
            switch_error = error
            return
        switches += 1
        switch_timer = window.after(150, switch)

    try:
        pulse()
        if scenario == "four":
            switch_timer = window.after(100, switch)
        for trace in traces:
            trace.start = time.perf_counter()
            trace.view.send(f"go:{lines}\r")
        deadline = started + 40
        while not all(trace.parsed is not None for trace in traces):
            window.update()
            now = time.perf_counter()
            assert now < deadline, "console output stalled"
            if switch_error is not None:
                raise switch_error
            rss_peak = max(rss_peak, process.memory_info().rss)
            time.sleep(.002)
        if switch_timer is not None:
            window.after_cancel(switch_timer)
            switch_timer = None
            assert switches > 1, "did not exercise repeated project and tab selection"
        for item in traced_tabs:
            focus(item, 0)
            wait(window, lambda: all(trace.rendered is not None for trace in item[2]), "terminal did not display its last line")
        cpu = sum(process.cpu_times()[:2]) - cpu_before
        results = [trace.check(lines) for trace in traces]
        assert {view.pty.process.pid for tab in app.terminal_tabs.values() for view in tab.views} == pid_set
        assert all(trace.view.pty.process.poll() is None for trace in traces), "an existing session stopped"
        return {"scenario": scenario, "completion_ms": max(item["display_ms"] for item in results),
                "event_ms": summary(delays[1:]), "event_samples": len(delays) - 1,
                "cpu_ms": round(cpu * 1000, 3), "rss_start": rss_before, "rss_peak": rss_peak,
                "project_tab_switches": switches, "pty_pids_created": len(pid_set), "sessions": results}
    finally:
        if switch_timer is not None:
            window.after_cancel(switch_timer)
        if timer is not None:
            window.after_cancel(timer)
        for _, key, _, _ in tabs:
            app.remove_terminal(key)
        wait(window, lambda: not process.children(), "PTY process leak", timeout=4)


def run(args):
    with tempfile.TemporaryDirectory(prefix="orchestra-terminal-benchmark-") as temp:
        root = Path(temp)
        data = root / "profile"
        repos = [fixture_repo(root / f"bench-{index}") for index in range(2)]
        projects = [put_project(data, inspect_project(repo) | {"name": repo.name}) for repo in repos]
        clis = {}
        for name in ("Codex", "OpenCode"):
            path = root / name
            path.write_text(FIXTURE.replace("{python}", sys.executable).replace("{{", "{").replace("}}", "}"),
                            encoding="utf-8")
            path.chmod(0o700)
            clis[name] = str(path)
        with patch("orchestra.desktop.start_supervisor"), patch("orchestra.workspace_sessions.scan_clis", return_value=clis):
            window = tk.Tk()
            window.geometry("1280x800")
            app = WorkspaceDesktop(window, data)
            try:
                for _ in range(args.rounds):
                    for scenario in args.scenarios:
                        yield exercise(window, app, projects, scenario, args.lines)
            finally:
                app.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--lines", type=int, default=8000)
    parser.add_argument("scenarios", nargs="*", default=["one", "horizontal", "vertical", "four"])
    args = parser.parse_args()
    if os.name != "posix" or args.rounds < 1 or args.lines < 2000 or set(args.scenarios) - {
        "one", "horizontal", "vertical", "four",
    }:
        parser.error("use a POSIX graphical host, positive rounds, at least 2000 lines and known scenarios")
    for result in run(args):
        print(json.dumps(result), flush=True)
