"""Drive the native UI through a real Supervisor and Git with scripted inference."""
import time
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestra.platform.command_line import format_commands
from orchestra.store import Store
from orchestra.workspace import STRATEGIES
from orchestra.workspace_desktop import WorkspaceDesktop
from test_orchestra import git, http_fixture


def wait(window, condition, description, timeout=24):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        window.update()
        if result := condition():
            return result
        time.sleep(.03)
    raise AssertionError(description)


def children(parent):
    for widget in parent.winfo_children():
        yield widget
        yield from children(widget)


def press(parent, label):
    matches = [widget for widget in children(parent) if isinstance(widget, ttk.Button) and widget.cget("text") == label]
    assert len(matches) == 1, label
    matches[0].invoke()


def dialog(window, title):
    return wait(window, lambda: next((child for child in window.winfo_children()
                if isinstance(child, tk.Toplevel) and child.title() == title), None), title)


def exercise(window, app, repo, data, server, url):
    confirmations = []
    errors = []
    declines = {"Git 병합 승인"}

    def confirm(title, message, **_):
        confirmations.append((title, message))
        if title in declines:
            declines.remove(title)
            return False
        return True

    with patch("tkinter.filedialog.askdirectory", return_value=str(repo)), \
            patch("tkinter.messagebox.askyesno", side_effect=confirm), \
            patch("tkinter.messagebox.showerror", side_effect=lambda title, message, **_: errors.append(message)):
        app.show("projects")
        press(app.pages["projects"], "로컬 저장소 추가")
        project = dialog(window, "프로젝트 등록")
        project.set("name", "UI test project")
        press(project.footer, "프로젝트 저장")
        assert app.project_rows()[app.project_id]["path"] == str(repo.resolve())

        app.show("hosts")
        app.hosts_list.selection_set("local")
        press(app.pages["hosts"], "연결 테스트")
        resources = wait(window, lambda: app.host_evidence.get("local", {}).get("resources"), "local environment")
        assert resources["os"] and resources["gpu"] is None

        app.show("settings")
        press(app.pages["settings"], "Provider 설정 마법사")
        wizard = dialog(window, "Provider 설정 마법사")
        wizard.set("kind", "llama.cpp")
        wizard.fields["kind"][1].event_generate("<<ComboboxSelected>>")
        window.update()
        wizard.set("endpoint", url)
        wizard.set("id", "ui-model")
        press(wizard.footer, "연결 확인")
        wait(window, lambda: wizard.get("found") == "test-model", "runtime model catalog")
        assert wizard.get("model") == "test-model"
        press(wizard.footer, "프로필 저장")
        assert app.settings_list.exists("ui-model")

        app.guided_dialog()
        guide = dialog(window, "작업 계획 만들기")
        guide.set("intent", "ui workflow: create and review the approved change")
        guide.set("strategy", STRATEGIES[1])
        guide.set("provider", "local")
        guide.fields["provider"][1].event_generate("<<ComboboxSelected>>")
        guide.set("model", "ui-model")
        guide.fields["model"][1].event_generate("<<ComboboxSelected>>")
        assert tuple(guide.fields["harness"][1].cget("values")) == ("", "managed")
        guide.set("harness", "managed")
        guide.set("paths", "ui-result.txt")
        check = [sys.executable, "-c", "from pathlib import Path; assert Path('ui-result.txt').read_text() == 'approved change\\n'"]
        guide.set("qa", format_commands([check]))
        press(guide.footer, "검토할 계획 생성")
        review = dialog(window, "실행 계획 검토")
        listing = next(item for item in children(review) if isinstance(item, tk.Listbox))
        develop, reviewer = listing.get(0, "end")
        assert "develop" in develop and "managed" in develop and "선행 develop" in reviewer
        press(review.footer, "검증 후 실행")
        assert confirmations[0][0] == "계획 제출 승인"
        job = app.selected_job
        assert job
        store = Store(data)
        wait(window, server.stalled.is_set, "managed agent did not enter real execution")
        assert store.job(job)["state"] == "RUNNING"
        app.agent_job = job
        app.show("agents")
        assert "route.selected" in app.agent_detail.get("1.0", "end")
        assert app.agent_record["develop"]["state"] == "RUNNING"
        server.released.set()
        result = wait(window, lambda: (row := store.job(job))["state"] == "AWAITING_APPROVAL" and row["result"],
                      "integration QA and approval candidate")

        app.show("dag")
        assert app.graph.find_all()
        app.show("agents")
        app.refresh_agents()
        assert "ui-result.txt" in app.agent_detail.get("1.0", "end")
        app.open_job(job)
        evidence = app.detail.get("1.0", "end")
        assert "qa.result" in evidence and '"exit_code": 0' in evidence
        assert not (repo / "ui-result.txt").exists()
        press(app.pages["jobs"], "병합 승인")
        assert store.job(job)["state"] == "AWAITING_APPROVAL"
        press(app.pages["jobs"], "병합 승인")
        wait(window, lambda: store.job(job)["state"] == "MERGED", "approved Git integration")
        assert confirmations[-1][0] == "Git 병합 승인" and result["candidate"] in confirmations[-1][1]
        assert git(repo, "rev-parse", "HEAD") == result["candidate"]
        assert (repo / "ui-result.txt").read_text(encoding="utf-8") == "approved change\n"
        app.new_terminal("Verify merged file", [sys.executable, "-c",
                         "from pathlib import Path; print(Path('ui-result.txt').read_text().strip(), flush=True)"], cwd=repo)
        panel = app.terminals[app.terminal_book.select()][1][0]
        wait(window, lambda: "approved change" in panel.surface.get("1.0", "end"), "terminal output")
        assert not errors, errors


with tempfile.TemporaryDirectory(prefix="orchestra-workspace-flow-") as directory, http_fixture() as (server, url):
    root = Path(directory)
    repo, data = root / "repo", root / "data"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "commit", "--allow-empty", "-m", "UI fixture base")
    window = tk.Tk()
    app = WorkspaceDesktop(window, data)
    try:
        exercise(window, app, repo, data, server, url)
    finally:
        server.released.set()
        app.close()
        status = data / "supervisor.json"
        if status.exists():
            (data / "supervisor.stop").touch()
            deadline = time.monotonic() + 10
            while status.exists() and time.monotonic() < deadline:
                time.sleep(.05)
            assert not status.exists(), "fixture Supervisor did not stop"

print("Native UI submission, live Agents, Managed HTTP fixture, task logs, QA, Git approval and native terminal passed.")
