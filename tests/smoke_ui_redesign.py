"""Comprehensive UI/UX redesign smoke test & real screenshot capture for WorkspaceDesktop."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tkinter import messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestra.core import config_check, defaults, plan_check
from orchestra.store import Store
from orchestra.supervisor import read_config
from orchestra.workspace import (
    RUNTIME_KINDS,
    STRATEGIES,
    add_setup_profile,
    inspect_project,
    put_project,
    registry_revision,
    save_registry,
)
from orchestra.workspace_desktop import WorkspaceDesktop


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def pump(window: tk.Tk, seconds: float = 0.08) -> None:
    deadline = time.monotonic() + seconds
    while True:
        window.update_idletasks()
        window.update()
        if time.monotonic() >= deadline:
            break
        time.sleep(0.015)


def wait(window: tk.Tk, predicate, description: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pump(window, 0.05)
        if predicate():
            return
    raise AssertionError(f"Timed out waiting for: {description}")


def find_buttons(root: tk.Misc, label: str) -> list[ttk.Button]:
    found = []
    for child in root.winfo_children():
        if isinstance(child, ttk.Button) and str(child.cget("text")) == label:
            found.append(child)
        found.extend(find_buttons(child, label))
    return found


def find_radios(root: tk.Misc, label: str) -> list[ttk.Radiobutton]:
    found = []
    for child in root.winfo_children():
        if isinstance(child, ttk.Radiobutton) and str(child.cget("text")) == label:
            found.append(child)
        found.extend(find_radios(child, label))
    return found


def capture_window(window: tk.Tk, dest: Path) -> None:
    import shutil
    import struct
    from PIL import Image, ImageGrab

    pump(window, 0.2)
    x = max(0, window.winfo_rootx())
    y = max(0, window.winfo_rooty())
    w = window.winfo_width()
    h = window.winfo_height()
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


@contextmanager
def http_model_fixture():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def _send(self, code: int, payload: dict):
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == "/v1/models":
                self._send(200, {
                    "object": "list",
                    "data": [{
                        "id": "fixture-qwen",
                        "context_length": 32768,
                        "max_output_tokens": 4096,
                    }],
                })
                return
            if self.path == "/props":
                self._send(200, {
                    "model_alias": "fixture-qwen",
                    "total_slots": 2,
                    "chat_template": "default",
                    "default_generation_settings": {
                        "n_ctx": 32768,
                        "params": {"n_predict": 4096},
                    },
                })
                return
            if self.path == "/health":
                self._send(200, {"status": "ok"})
                return
            self._send(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            model = body.get("model", "fixture-qwen")
            tools = body.get("tools") or []
            messages = body.get("messages") or []

            # Tool calling handshake probe
            if any((t.get("function") or {}).get("name") == "orchestra_probe" for t in tools):
                self._send(200, {
                    "model": model,
                    "choices": [{
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": "probe_1",
                                "type": "function",
                                "function": {"name": "orchestra_probe", "arguments": "{}"},
                            }],
                        },
                    }],
                    "usage": {"prompt_tokens": 18, "completion_tokens": 8, "total_tokens": 26},
                })
                return

            user_prompt = "\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "user")
            has_tool_result = any(m.get("role") == "tool" for m in messages)

            if "Role: developer" in user_prompt and not has_tool_result:
                self._send(200, {
                    "model": model,
                    "choices": [{
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": "write_auth_1",
                                "type": "function",
                                "function": {
                                    "name": "write_file",
                                    "arguments": json.dumps({
                                        "path": "src/auth.py",
                                        "content": (
                                            "def verify_token(token: str) -> bool:\n"
                                            '    """Validate bearer token length and prefix."""\n'
                                            "    return isinstance(token, str) and len(token) >= 8 and token.startswith('tok_')\n"
                                        ),
                                    }),
                                },
                            }],
                        },
                    }],
                    "usage": {"prompt_tokens": 64, "completion_tokens": 42, "total_tokens": 106},
                })
                return

            if "Role: reviewer" in user_prompt:
                reply = "Verified token prefix check cleanly without side effects.\nREVIEW: PASS"
            else:
                reply = "Implemented verify_token guard in src/auth.py and completed checks."

            self._send(200, {
                "model": model,
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": reply},
                }],
                "usage": {"prompt_tokens": 80, "completion_tokens": 36, "total_tokens": 116},
            })

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()


def seed_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "src").mkdir(exist_ok=True)
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "README.md").write_text("# Demo Auth Workspace\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text("[project]\nname = 'demo-auth'\nversion = '0.1.0'\n", encoding="utf-8")
    (repo / "src" / "auth.py").write_text(
        "def verify_token(token: str) -> bool:\n    return bool(token)\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_auth.py").write_text(
        "from src.auth import verify_token\nassert verify_token('tok_12345')\n",
        encoding="utf-8",
    )
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "UI QA Bot")
    git(repo, "config", "user.email", "ui-qa@example.invalid")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Initial demo auth service")


def exercise(screenshots_dir: Path | None = None) -> None:
    with tempfile.TemporaryDirectory(prefix="orchestra-ui-redesign-") as directory, http_model_fixture() as url:
        root = Path(directory)
        repo = root / "demo-auth-workspace"
        data = root / "data"
        seed_repo(repo)

        window = tk.Tk()
        errors = []
        window.report_callback_exception = lambda exc, val, tb: errors.append((exc, val))
        app = WorkspaceDesktop(window, data)

        orig_askyesno = messagebox.askyesno
        asked_prompts = []

        def auto_yes(title, message, **kwargs):
            asked_prompts.append((title, message))
            return True

        messagebox.askyesno = auto_yes
        try:
            # 1. Empty state + Responsive resizing + Dark/Light toggle
            app.show("home")
            pump(window, 0.15)
            assert app.home_empty_card.winfo_ismapped(), "home_empty_card should be visible when workspace is empty"

            for width, height in ((940, 650), (1280, 800), (1440, 900)):
                window.geometry(f"{width}x{height}+0+0")
                pump(window, 0.12)
                assert app.nav_frame.winfo_width() > 150, f"sidebar collapsed at {width}x{height}"
                assert app.header_bar.winfo_height() >= 48, f"header collapsed at {width}x{height}"
                assert app.main_shell.winfo_width() > 600, f"main shell collapsed at {width}x{height}"

            # Light/dark toggle and ui_prefs.json persistence (without breaking registry.json)
            assert app.theme_name == "dark"
            app.toggle_theme()
            pump(window, 0.1)
            assert app.theme_name == "light"
            assert app.palette["name"] == "light"
            assert (data / "ui_prefs.json").exists()
            assert config_check(read_config(data)) is not None
            app.toggle_theme()
            pump(window, 0.1)
            assert app.theme_name == "dark"

            # 2. Register Project + Provider Profile
            runtime_kind = "llama.cpp" if "llama.cpp" in RUNTIME_KINDS else RUNTIME_KINDS[0]
            cfg = read_config(data)
            updated_cfg = add_setup_profile(cfg, {
                "kind": runtime_kind,
                "id": "fixture-qwen",
                "endpoint": url,
                "auth_env": "",
                "executable": "",
                "model": "fixture-qwen",
                "context": "32768",
                "trusted": False,
                "default": True,
            })
            # Ensure all roles allowed for multi-step DAG
            updated_cfg["models"]["fixture-qwen"]["roles"] = [
                "planner", "developer", "explorer", "reviewer", "qa", "diagnostic"
            ]
            save_registry(data, updated_cfg, registry_revision(data))
            app.restart_supervisor()
            wait(window, lambda: (data / "supervisor.json").exists(), "supervisor running after config save")

            proj_info = inspect_project(str(repo))
            proj_id = put_project(data, proj_info | {
                "name": "Demo Auth Service · Long Workspace Name Verification",
                "branch": "main",
                "model": "fixture-qwen",
                "harness": "managed",
                "paths": ["src/auth.py", "tests/test_auth.py"],
                "read_paths": ["src/auth.py", "tests/test_auth.py", "README.md", "pyproject.toml"],
                "qa": [[sys.executable, "-c", "raise SystemExit(0)"]],
            })
            app.project_id = proj_id
            app.refresh_sidebar()
            app.refresh_projects()

            # 3. Verify Provider Settings Wizard Simple/Advanced toggle (non-modal Form)
            app.provider_wizard()
            pump(window, 0.12)
            forms = [w for w in window.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Provider 설정 마법사"]
            assert forms, "Provider settings wizard did not open"
            form = forms[0]
            assert len(form.fields) == 10, f"expected 10 fields, got {set(form.fields)}"
            assert not form.field_rows["endpoint"][0].winfo_ismapped(), "endpoint should be hidden in simple mode"
            adv_radios = find_radios(form, "고급 모드")
            assert adv_radios, "missing 고급 모드 radio"
            adv_radios[0].invoke()
            pump(window, 0.12)
            assert form.field_rows["endpoint"][0].winfo_ismapped(), "endpoint should be visible in advanced mode"
            form.destroy()
            pump(window, 0.05)

            # 4. Exercise 6-step in-place Task Wizard -> Submit real DAG job reaching AWAITING_APPROVAL
            app.show("submit")
            pump(window, 0.1)
            assert app.wizard_step == 0
            app._wizard_go(1)
            app.wiz_intent.delete("1.0", "end")
            app.wiz_intent.insert("1.0", "Add strict token prefix verification and regression test coverage in src/auth.py.")
            app.wiz_strategy_var.set(STRATEGIES[1])
            app._wizard_go(2)
            app.wiz_paths_var.set("src/auth.py, tests/test_auth.py")
            app.write(app.wiz_qa_text, f"{sys.executable} -c \"raise SystemExit(0)\"")
            app._wizard_go(3)
            pump(window, 0.1)
            assert app.wizard_draft and len(app.wizard_draft["tasks"]) >= 2
            app._wizard_go(4)
            app._wizard_go(5)
            pump(window, 0.1)
            assert "예상 실행 경로" in app.wiz_review_box.get("1.0", "end")

            app._wizard_submit()
            store = Store(data)
            wait(window, lambda: len(store.list_jobs()) >= 1, "first wizard job created")
            ready_job_id = store.list_jobs()[0]["id"]
            wait(window, lambda: store.job(ready_job_id)["state"] == "AWAITING_APPROVAL", "ready job reaches AWAITING_APPROVAL", timeout=30.0)

            # Submit a second real QA failure job for blocked approval / filter coverage
            qa_fail_plan = plan_check({
                "title": "Regression QA failure verification",
                "repo": str(repo),
                "target": "main",
                "background": False,
                "tasks": [{"id": "qa", "role": "qa", "prompt": "Run fail QA", "acceptance": "Exit 0",
                           "qa": [[sys.executable, "-c", "raise SystemExit(0)"]]}],
                "qa": [[sys.executable, "-c", "raise SystemExit(7)"]],
            }, read_config(data))
            app.accept_local_plan(qa_fail_plan)
            wait(window, lambda: len(store.list_jobs()) >= 2, "second QA failure job created")
            fail_job_id = next(j["id"] for j in store.list_jobs() if j["id"] != ready_job_id)
            wait(window, lambda: store.job(fail_job_id)["state"] == "FAILED", "QA failure job fails", timeout=25.0)

            # 5. Exercise all 11 primary sidebar pages & hidden pages
            for page_key in ("home", "projects", "jobs", "agents", "terminals", "hosts", "ssh", "mcp", "providers", "history", "settings", "dag", "registry", "remote_runs"):
                app.show(page_key)
                pump(window, 0.08)

            # Check history search and status filters
            app.show("history")
            pump(window, 0.1)
            app.history_state.set("실패")
            app.refresh_history()
            assert len(app.history_table.get_children()) == 1
            app.history_state.set("전체")
            app.history_query.set("token prefix")
            app.refresh_history()
            assert len(app.history_table.get_children()) == 1
            app.history_query.set("")
            app.refresh_history()
            assert len(app.history_table.get_children()) == 2

            # Check failed job inline approval shows blocked/disabled
            app.open_job(fail_job_id)
            pump(window, 0.1)
            assert app.inline_approval_badge.cget("text") == "QA 실패"
            assert app.inline_approve_btn.instate(["disabled"])

            # Check ready job 7-tab Task Detail
            app.open_job(ready_job_id)
            pump(window, 0.15)
            assert app.inline_approval_badge.cget("text") == "승인 준비 완료"
            assert not app.inline_approve_btn.instate(["disabled"])
            for tab_idx in range(7):
                app.detail_book.select(tab_idx)
                pump(window, 0.06)
            assert app.detail_dag_canvas.find_all(), "Task detail DAG canvas must draw nodes"
            assert app.detail_agents_table.get_children(), "Agent tab must populate rows"
            assert app.detail_qa_table.get_children(), "QA tab must populate rows"

            # 6. Capture all 7 real Tk screenshots at 1360x860 if requested
            if screenshots_dir is not None:
                window.geometry("1360x860+0+0")
                pump(window, 0.2)

                # 01 Home Dashboard
                app.show("home")
                capture_window(window, screenshots_dir / "01-tk-home-dashboard.png")

                # 02 Projects Workspace
                app.show("projects")
                app.open_project(proj_id)
                capture_window(window, screenshots_dir / "02-tk-projects.png")

                # 03 6-step Task Creation Wizard (Step 4 Plan view populated)
                app.show("submit")
                app.wiz_intent.delete("1.0", "end")
                app.wiz_intent.insert("1.0", "Add strict token prefix verification and regression test coverage in src/auth.py.")
                app.wiz_strategy_var.set(STRATEGIES[1])
                app.wiz_paths_var.set("src/auth.py, tests/test_auth.py")
                app.write(app.wiz_qa_text, f"{sys.executable} -c \"raise SystemExit(0)\"")
                app._wizard_generate_plan()
                app._wizard_go(3)
                capture_window(window, screenshots_dir / "03-tk-task-creation.png")

                # 04 Task Detail Workspace (on 개요 tab of AWAITING_APPROVAL job)
                app.open_job(ready_job_id)
                app.detail_book.select(0)
                capture_window(window, screenshots_dir / "04-tk-task-detail.png")

                # 05 Agent Monitor
                app.agent_job = ready_job_id
                app.show("agents")
                app.refresh_agents()
                first_agent = next(iter(app.agent_list.get_children()), None)
                if first_agent:
                    app.agent_list.selection_set(first_agent)
                    app.select_agent(None)
                capture_window(window, screenshots_dir / "05-tk-agent-monitor.png")

                # 07 Provider & Model Configuration
                app.show("providers")
                app.refresh_providers()
                capture_window(window, screenshots_dir / "07-tk-provider-settings.png")

            # 7. Exercise Git Merge Approval Modal ("변경 사항 보기" + optional 06 screenshot + approve merge)
            app.open_job(ready_job_id)
            app.detail_book.select(5)  # 승인 tab
            pump(window, 0.15)
            modal_checks = {"diff_checked": False, "screenshot": False, "approved": False}

            def drive_merge_modal():
                modals = [w for w in window.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Git 병합 승인"]
                if not modals:
                    window.after(60, drive_merge_modal)
                    return
                modal = modals[0]
                modal.update_idletasks()
                mx = max(40, (window.winfo_width() - modal.winfo_reqwidth()) // 2)
                my = max(40, (window.winfo_height() - modal.winfo_reqheight()) // 2)
                modal.geometry(f"+{window.winfo_rootx() + mx}+{window.winfo_rooty() + my}")
                pump(window, 0.12)

                def inspect_diff():
                    diffs = [w for w in modal.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "변경 사항 보기"]
                    if not diffs:
                        window.after(60, inspect_diff)
                        return
                    diff_win = diffs[0]
                    pump(window, 0.15)
                    modal_checks["diff_checked"] = True
                    diff_win.destroy()
                    pump(window, 0.12)
                    if screenshots_dir is not None:
                        capture_window(window, screenshots_dir / "06-tk-git-approval.png")
                        modal_checks["screenshot"] = True
                    approve_btns = find_buttons(modal, "이 후보 승인")
                    assert approve_btns, "이 후보 승인 button missing"
                    approve_btns[0].invoke()
                    modal_checks["approved"] = True

                diff_btns = find_buttons(modal, "변경 사항 보기")
                assert diff_btns, "변경 사항 보기 button missing"
                window.after(80, inspect_diff)
                diff_btns[0].invoke()

            window.after(100, drive_merge_modal)
            app.job_action("merge")
            assert modal_checks["diff_checked"], "diff dialog did not open"
            assert modal_checks["approved"], "merge approval button did not trigger"
            wait(window, lambda: store.job(ready_job_id)["state"] == "MERGED", "ready job merges on main", timeout=20.0)

            assert not errors, f"Uncaught Tk callback errors: {errors}"
        finally:
            messagebox.askyesno = orig_askyesno
            app.close()
            status = data / "supervisor.json"
            if status.exists():
                (data / "supervisor.stop").touch()
                deadline = time.monotonic() + 10
                while status.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)


def main():
    parser = argparse.ArgumentParser(description="Smoke test the redesigned Orca-inspired UI/UX.")
    parser.add_argument("--screenshots-dir", type=Path, default=None, help="Directory to save 01..07 Tk screenshots.")
    args = parser.parse_args()
    exercise(args.screenshots_dir)
    print("UI/UX redesign smoke verification (11 nav views, 3 responsive sizes, dark/light toggle, 6-step wizard, 7-tab detail, diff & Git merge) passed.")


if __name__ == "__main__":
    main()
