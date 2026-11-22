"""Unified Orca workspace integration, regression, and multi-resolution screenshot QA suite."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from orchestra.core import defaults
from orchestra.platform.command_line import format_commands
from orchestra.store import Store
from orchestra.ui import Card
from orchestra.workspace import STRATEGIES, inspect_project, put_host, put_project, save_registry
from orchestra.workspace_desktop import WorkspaceDesktop
from orchestra.workspace_shell import read_layout
from smoke_integrated_workspace import (
    descendants,
    dialog,
    fixture_repo,
    press,
    select_context,
    terminal_fixture,
    terminal_text,
    wait,
)
from test_orchestra import config, git, http_fixture

VIEWPORTS = ((1280, 770), (1664, 900), (1920, 1080))


def _grab_bbox(dest: Path, x: int, y: int, w: int, h: int) -> None:
    import shutil
    import struct
    from PIL import Image, ImageGrab

    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("xwd"):
        raw = subprocess.check_output(["xwd", "-root", "-silent"])
        vals = struct.unpack(">25I", raw[:100])
        header_size, pw, ph, bpl, ncolors = vals[0], vals[4], vals[5], vals[12], vals[19]
        offset = header_size + ncolors * 12
        img = Image.frombytes("RGB", (pw, ph), raw[offset:], "raw", "BGRX", bpl, 1)
        img.crop((x, y, x + w, y + h)).save(dest)
        return
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(dest)


def capture_sizes(window, output: Path | None, slug: str, *, also_940: bool = False):
    if output is None:
        return
    sizes = ((940, 650), *VIEWPORTS) if also_940 else VIEWPORTS
    for w, h in sizes:
        window.geometry(f"{w}x{h}+0+0")
        window.update_idletasks()
        window.update()
        time.sleep(0.05)
        window.update()
        x, y = max(0, window.winfo_rootx()), max(0, window.winfo_rooty())
        ww, wh = window.winfo_width(), window.winfo_height()
        assert x + ww <= window.winfo_screenwidth() and y + wh <= window.winfo_screenheight(), (
            f"Screen {window.winfo_screenwidth()}x{window.winfo_screenheight()} too small for {w}x{h}"
        )
        _grab_bbox(output / f"{w}x{h}" / f"{slug}.png", x, y, ww, wh)


def assert_single_shell(app, expected_ids):
    assert not hasattr(app, "nav_scroll_canvas"), "legacy nav_scroll_canvas still present"
    assert not hasattr(app, "nav_inner"), "legacy nav_inner still present"
    assert not hasattr(app, "sidebar_footer"), "legacy sidebar_footer still present"
    for attr in ("nav_frame", "header_bar", "workspace_book", "workspace_context", "status_bar"):
        assert getattr(app, attr) is expected_ids[attr], f"{attr} was recreated during navigation"
    assert set(app.nav_rows) == {"workspace", "jobs", "agents", "projects", "settings"}
    tabs = app.workspace_book.tabs()
    assert len(tabs) == len(set(tabs)), "duplicate tabs found in workspace_book"


def assert_header_fits(app, window, width):
    window.geometry(f"{width}x770+0+0")
    window.update_idletasks()
    window.update()
    end = window.winfo_rootx() + window.winfo_width()
    for btn in (app.header_new_task, app.workspace_terminal_button, app.workspace_layout_button,
                app.workspace_focus_button, app.theme_btn):
        assert btn.winfo_ismapped(), f"{btn} not mapped at width {width}"
        assert btn.winfo_rootx() + btn.winfo_width() <= end, f"{btn} clipped at width {width}"
    assert app.workspace_runtime_status.winfo_y() >= app.workspace_status.winfo_height()


def assert_theme_colors(app):
    p = app.palette
    assert app.nav_frame.cget("bg") == p["sidebar"]
    assert app.header_bar.cget("bg") == p["header"]
    assert app.status_bar.cget("bg") == p["status_bar"]
    for card in app._themed_cards:
        if card.winfo_exists() and isinstance(card, Card):
            assert card.cget("bg") == p[card.bg_key], (card, card.cget("bg"), p[card.bg_key])


def run_suite(screenshots: Path | None):
    with tempfile.TemporaryDirectory(prefix="orchestra-unified-ui-") as temporary, http_fixture() as (server, url):
        root = Path(temporary)
        data = root / "workspace-data"
        repo1 = fixture_repo(root / "alpha-service")
        repo2 = fixture_repo(root / "beta-worker")
        cli_map = {} if os.name == "nt" else {
            tool: terminal_fixture(tool, root / exe) for tool, exe in (("OpenCode", "opencode"), ("Codex", "codex"))
        }
        registry = config(url)
        registry["models"]["secondary"] = dict(registry["models"]["model"])
        if cli_map:
            registry["harnesses"]["terminal-opencode"] = {
                "kind": "opencode", "executable": cli_map["OpenCode"], "trusted": True,
            }
            registry["models"]["terminal-fixture"] = {
                "provider": "subscription", "model": "fixture/selected-model", "harnesses": ["terminal-opencode"],
            }
        errors = []
        with patch("orchestra.workspace_sessions.scan_clis", return_value=cli_map), \
                patch("orchestra.workspace_onboarding.scan_clis", return_value=cli_map), \
                patch("tkinter.messagebox.askyesno", return_value=True), \
                patch("tkinter.messagebox.showinfo"), \
                patch("tkinter.messagebox.showerror", side_effect=lambda title, msg, **_: errors.append((title, msg))):
            # Case 10: Empty project list & first-run onboarding
            window = tk.Tk()
            app = WorkspaceDesktop(window, data, startup_locale="ko")
            shell_ids = {
                attr: getattr(app, attr)
                for attr in ("nav_frame", "header_bar", "workspace_book", "workspace_context", "status_bar")
            }
            try:
                window.update()
                assert app.theme_name == "light"
                assert app.view == "workspace"
                assert not app.project_rows()
                assert app.workspace_setup_button.winfo_ismapped()
                assert_single_shell(app, shell_ids)
                assert_header_fits(app, window, 940)
                capture_sizes(window, screenshots, "01-empty-workspace")

                save_registry(data, registry)
                first_id = put_project(data, inspect_project(repo1) | {"name": "Alpha Service", "model": "model"})
                second_id = put_project(data, inspect_project(repo2) | {"name": "Beta Worker"})
                put_host(data, {
                    "name": "Lab Linux Worker", "host": "127.0.0.1", "port": 2222,
                    "user": "operator", "auth": "agent", "os": "linux", "worker_dir": "/opt/worker",
                })
                app.refresh_sidebar()
                app.select_workspace_project(first_id)
                window.update()
                capture_sizes(window, screenshots, "02-registered-project")

                # Case 1: Workspace -> Settings -> Workspace
                app.show("settings")
                window.update()
                assert app.view == "settings"
                assert app.nav_frame.winfo_ismapped()
                assert app.nav_rows["settings"]._active
                assert_single_shell(app, shell_ids)
                app.show("workspace")
                window.update()
                assert app.view == "workspace"
                assert app.nav_rows["workspace"]._active
                assert_single_shell(app, shell_ids)

                # Case 2 & Case 6: OpenCode & Codex terminals + navigation preserving live PTY PIDs
                pids = []
                opencode_tab = None
                codex_tab = None
                if cli_map:
                    opencode_tab = app.workspace_open_ai("OpenCode", "terminal-fixture")
                    oc_view = app.terminals[opencode_tab][1][0]
                    wait(window, lambda: "Model: fixture/selected-model" in terminal_text(oc_view), "OpenCode did not start")
                    capture_sizes(window, screenshots, "03-opencode-terminal")

                    codex_tab = app.open_ai_terminal("Codex")
                    cx_view = app.terminals[codex_tab][1][0]
                    wait(window, lambda: "Codex" in terminal_text(cx_view), "Codex did not start")

                    # Workspace -> Provider -> Terminal
                    app.show("providers")
                    window.update()
                    assert app.nav_rows["settings"]._active
                    assert_single_shell(app, shell_ids)
                    capture_sizes(window, screenshots, "07-provider-settings")

                    app.focus_terminal(opencode_tab)
                    window.update()
                    assert app.terminals[opencode_tab][1][0] is oc_view and not oc_view.closed.is_set()

                    # Split OpenCode + Codex
                    app.split_terminal("horizontal", "Codex")
                    panels = app.terminals[opencode_tab][1]
                    assert len(panels) == 2 and panels[1] is cx_view
                    pids = [v.pty.process.pid for v in panels if getattr(v.pty, "process", None)]
                    capture_sizes(window, screenshots, "04-split-terminals")

                # Case 3: Workspace -> SSH -> Project
                app.show("ssh")
                window.update()
                assert app.nav_rows["settings"]._active
                assert_single_shell(app, shell_ids)
                capture_sizes(window, screenshots, "08-ssh-management")

                app.show("projects")
                window.update()
                app.open_project(first_id)
                window.update()
                assert app.nav_rows["projects"]._active
                assert app.project_id == first_id
                assert_single_shell(app, shell_ids)

                # Case 4: Workspace -> MCP -> Agent
                app.show("mcp")
                window.update()
                assert app.nav_rows["settings"]._active
                capture_sizes(window, screenshots, "09-mcp-management")

                app.show("agents")
                window.update()
                assert app.nav_rows["agents"]._active
                assert_single_shell(app, shell_ids)

                # Close route tabs (must not kill terminals)
                for route in ("providers", "ssh", "mcp", "projects", "settings"):
                    frame = app.pages[route]
                    if str(frame) in app.workspace_book.tabs():
                        app.close_workspace_tab(str(frame))
                if cli_map:
                    assert all(not v.closed.is_set() for v in app.terminals[opencode_tab][1])
                    for v, pid in zip(app.terminals[opencode_tab][1], pids):
                        assert v.pty.process.pid == pid

                # Project File Explorer screenshot
                app.select_workspace_project(first_id)
                (repo1 / "src" / "workflow.py").write_text("print('unified workspace')\n", encoding="utf-8")
                select_context(app.workspace_context, app.context_file_tree)
                app.refresh_workspace_context()
                wait(window, lambda: app.context_file_tree.exists("src"), "explorer missing src")
                app.context_file_tree.focus("src")
                app.context_file_tree.item("src", open=True)
                app.context_file_tree.event_generate("<<TreeviewOpen>>")
                wait(window, lambda: app.context_file_tree.exists("src/workflow.py"), "explorer did not expand src")
                app.context_file_tree.selection_set("src/workflow.py")
                app.preview_workspace_file()
                wait(window, lambda: "unified workspace" in app.context_file_preview.get("1.0", "end"), "preview empty")
                capture_sizes(window, screenshots, "05-project-file-explorer")
                (repo1 / "src" / "workflow.py").write_text("print('original workflow')\n", encoding="utf-8")

                # Case 5: Task -> QA -> Git Approval
                app.workspace_new_task()
                guide = dialog(window, "작업 계획 만들기")
                guide.set("intent", "ui workflow: unified ui verification task")
                guide.set("strategy", STRATEGIES[1])
                guide.set("model", "model")
                guide.set("harness", "managed")
                guide.set("paths", "ui-result.txt")
                check = [sys.executable, "-c", "from pathlib import Path; assert Path('ui-result.txt').is_file()"]
                guide.set("qa", format_commands([check]))
                press(guide.footer, "검토할 계획 생성")
                plan = dialog(window, "실행 계획 검토")
                press(plan.footer, "검증 후 실행")
                wait(window, server.stalled.is_set, "Supervisor did not reach model fixture")
                store = Store(data)
                job_id = store.list_jobs()[0]["id"]
                server.released.set()
                ready = wait(
                    window,
                    lambda: (row if (row := store.job(job_id))["state"] == "AWAITING_APPROVAL" else None),
                    "job did not reach AWAITING_APPROVAL",
                    timeout=30,
                )

                # Agent Dashboard screenshot
                app.agent_job = job_id
                app.show("agents")
                app.refresh_agents()
                wait(window, lambda: bool(app.agent_list.get_children()), "agent rows missing")
                capture_sizes(window, screenshots, "06-agent-dashboard")

                # Task & DAG screenshot
                app.open_job(job_id)
                app.detail_book.select(1)  # DAG tab
                window.update()
                assert app.detail_dag_canvas.find_all()
                capture_sizes(window, screenshots, "10-task-and-dag")

                # Git & QA approval screenshot + actual approval
                app.detail_book.select(5)  # Approval tab
                window.update()
                assert app.inline_approval_badge.cget("text") == "승인 준비 완료"

                problems = []

                def drive_approval():
                    modal = dialog(window, "Git 병합 승인")
                    try:
                        text = next(w for w in descendants(modal) if isinstance(w, tk.Text)).get("1.0", "end")
                        assert ready["result"]["candidate"] in text
                        assert ready["result"]["approval_revision"] in text
                        if screenshots is not None:
                            for w, h in VIEWPORTS:
                                window.geometry(f"{w}x{h}+0+0")
                                window.update_idletasks()
                                modal.update_idletasks()
                                mx = max(40, (w - modal.winfo_reqwidth()) // 2)
                                my = max(40, (h - modal.winfo_reqheight()) // 2)
                                modal.geometry(f"+{window.winfo_rootx() + mx}+{window.winfo_rooty() + my}")
                                window.update()
                                _grab_bbox(
                                    screenshots / f"{w}x{h}" / "11-qa-and-git-approval.png",
                                    window.winfo_rootx(),
                                    window.winfo_rooty(),
                                    window.winfo_width(),
                                    window.winfo_height(),
                                )
                        press(modal, "이 후보 승인")
                    except Exception as exc:
                        problems.append(exc)
                        modal.destroy()

                window.after(80, drive_approval)
                press(app.pages["jobs"], "병합 승인")
                if problems:
                    raise problems[0]
                wait(window, lambda: store.job(job_id)["state"] == "MERGED", "job did not merge")
                assert git(repo1, "rev-parse", "HEAD") == ready["result"]["candidate"]

                # Case 7: Theme switching across all screens
                app.toggle_theme()
                assert app.theme_name == "dark"
                for route in ("workspace", "jobs", "agents", "projects", "providers", "ssh", "mcp", "settings", "history"):
                    app.show(route)
                    window.update()
                    assert_theme_colors(app)
                    assert_single_shell(app, shell_ids)
                if cli_map:
                    app.focus_terminal(opencode_tab)
                else:
                    app.show("workspace")
                window.update()
                capture_sizes(window, screenshots, "12-dark-theme")
                app.toggle_theme()
                assert app.theme_name == "light"
                assert_theme_colors(app)

                # Case 9: Application restart and workspace restoration
                app.show("settings")
                window.update()
                saved_tabs = [app.workspace_book.tab(t_id, "text") for t_id in app.workspace_book.tabs()]
                saved_active = app.workspace_book.tab(app.workspace_book.select(), "text")
                app.save_workspace_layout()
                saved_layout = read_layout(app.workspace_layout_path)
                app.close()
                if cli_map:
                    assert all(v.closed.is_set() for v in (oc_view, cx_view))

                window = tk.Tk()
                app = WorkspaceDesktop(window, data, startup_locale="ko")
                window.update()
                assert app.project_id == first_id
                assert [app.workspace_book.tab(t_id, "text") for t_id in app.workspace_book.tabs()] == saved_tabs
                assert app.workspace_book.tab(app.workspace_book.select(), "text") == saved_active
                assert all(not views for _, views in app.terminals.values()), "restored terminals auto-launched CLI processes"
                assert app.terminal_descriptors() == saved_layout["terminals"]

                # Case 8: Korean / English switching across all screens
                app.workspace_set_language("en")
                app.close()
                with patch.dict(os.environ, {"ORCHESTRA_LANG": "en"}):
                    window = tk.Tk()
                    app = WorkspaceDesktop(window, data, startup_locale="en")
                    window.update()
                    assert app.locale == "en"
                    assert app.nav_rows["workspace"].label.cget("text") == "Workspace"
                    assert app.nav_rows["settings"].label.cget("text") == "Settings"
                    assert_header_fits(app, window, 940)
                    for route in ("workspace", "jobs", "agents", "projects", "providers", "ssh", "mcp", "settings"):
                        app.show(route)
                        window.update()
                    app.workspace_set_language("ko")
                    assert not errors, errors
            finally:
                server.released.set()
                try:
                    app.close()
                except tk.TclError:
                    pass
                status = data / "supervisor.json"
                if status.exists():
                    (data / "supervisor.stop").touch()
                    deadline = time.monotonic() + 12
                    while status.exists() and time.monotonic() < deadline:
                        time.sleep(0.05)
    print("Unified Orca workspace regression suite (10 cases + 12 screens) PASSED.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path, help="Directory for 1280x770, 1664x900, 1920x1080 captures.")
    run_suite(parser.parse_args().screenshots)


if __name__ == "__main__":
    main()
