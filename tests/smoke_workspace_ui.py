import argparse
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch


from orchestra.core import defaults
from orchestra.runtime import RuntimePool
from orchestra.store import Store
from orchestra.supervisor import JobRunner
from orchestra.workspace import STRATEGIES, draft_plan, inspect_project, put_project
from orchestra.workspace_desktop import WorkspaceDesktop

parser = argparse.ArgumentParser(description="Exercise the actual Tk workspace and operator PTY.")
parser.add_argument("--screenshot", type=Path, help="Optional workspace image output (requires Pillow)")
args = parser.parse_args()

with tempfile.TemporaryDirectory(prefix="orchestra-workspace-ui-") as directory:
    root = Path(directory)
    repo = root / "sample-workspace"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "--allow-empty", "-qm", "Fixture"], check=True)
    data = root / "data"
    store = Store(data)
    meta = inspect_project(repo)
    key = put_project(data, meta | {"name": "샘플 워크스페이스"})
    plan = draft_plan(meta, "로컬 환경 검증", STRATEGIES[2], qa=[["git", "--version"]])
    job_id = store.submit(plan, defaults(), None)
    assert store.claim(job_id, "ui-fixture")
    JobRunner(store, RuntimePool(), store.job(job_id), threading.Event(), lambda _: True, threading.Lock()).work()
    assert store.job(job_id)["state"] == "SUCCEEDED"

    with patch("orchestra.desktop.start_supervisor"):
        window = tk.Tk()
        app = WorkspaceDesktop(window, data)
        for size in ("940x650", "1330x850"):
            window.geometry(size + "+10+10")
            for page in app.pages:
                app.show(page)
                window.update()
                assert app.pages[page].winfo_ismapped(), page
        app.show("projects")
        app.open_project(key)
        assert app.project_book.select()
        app.guided_dialog()
        window.update()
        form = next(child for child in window.winfo_children() if hasattr(child, "fields") and "intent" in child.fields)
        form.set("intent", "QA 워크플로 구성")
        form.set("strategy", STRATEGIES[2])
        form.set("qa", "git --version")
        approve = next(child for child in form.footer.winfo_children() if child.cget("text") == "검토할 계획 생성")
        approve.invoke()
        window.update()
        review = next(child for child in window.winfo_children() if hasattr(child, "fields") and child.title() == "실행 계획 검토")
        assert review.get("title") == "QA 워크플로 구성"
        review.destroy()
        app.show("agents")
        app.agent_job = job_id
        app.refresh_agents()
        assert "qa.result" in app.agent_detail.get("1.0", "end")
        app.show("dag")
        assert len(app.graph.find_all()) >= 3
        app.new_terminal("PTY QA", [sys.executable, "-c",
                         "print('\\x1b[32mready\\x1b[0m', flush=True); value=input(); print('received:'+value,flush=True)"], cwd=repo)
        panel = app.terminals[app.terminal_book.select()][1][0]
        deadline = time.monotonic() + 6
        while "ready" not in panel.surface.get("1.0", "end") and time.monotonic() < deadline:
            window.update()
            time.sleep(.04)
        assert "ready" in panel.surface.get("1.0", "end")
        assert any(name.startswith("colors_green") for name in panel.surface.tag_names())
        panel.send("desktop smoke\r")
        while "received:desktop smoke" not in panel.surface.get("1.0", "end") and time.monotonic() < deadline:
            window.update()
            time.sleep(.04)
        assert "received:desktop smoke" in panel.surface.get("1.0", "end")
        app.remove_terminal()
        app.show("home")
        window.update()
        app.refresh_home()
        x, y = window.winfo_rootx(), window.winfo_rooty()
        w, h = window.winfo_width(), window.winfo_height()
        if args.screenshot:
            from PIL import ImageGrab
            ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(args.screenshot)
        app.close()
print("Native UI, two sizes, guided QA form, Agent events, DAG and interactive ANSI PTY passed.")
