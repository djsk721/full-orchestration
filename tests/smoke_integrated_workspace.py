"""Native Tk workspace smoke using disposable repositories and real PTYs."""
import argparse
import getpass
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from contextlib import contextmanager
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestra.platform.command_line import format_commands
from orchestra.remote import register_project
from orchestra.ssh import fingerprint, scan_keys, trust_key
from orchestra.store import Store
from orchestra.workspace import STRATEGIES, inspect_project, put_host, put_project, save_registry
from orchestra.workspace_desktop import WorkspaceDesktop
from orchestra.workspace_shell import read_layout
from test_orchestra import config, git, http_fixture


def wait(window, condition, description, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        window.update()
        if value := condition():
            return value
        time.sleep(.03)
    raise AssertionError(description)


def descendants(parent):
    for child in parent.winfo_children():
        yield child
        yield from descendants(child)


def press(parent, text):
    buttons = [item for item in descendants(parent) if isinstance(item, ttk.Button) and item.cget("text") == text]
    assert len(buttons) == 1, (text, len(buttons))
    buttons[0].invoke()


def dialog(window, title):
    return wait(window, lambda: next((child for child in window.winfo_children()
                if isinstance(child, tk.Toplevel) and child.title() == title), None), title)


def fixture_repo(path):
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "Workspace fixture")
    git(path, "config", "user.email", "workspace@example.invalid")
    (path / "src").mkdir()
    (path / "src" / "workflow.py").write_text("print('original workflow')\n", encoding="utf-8")
    (path / "README.md").write_text("# Example project\n\nAn isolated workspace fixture.\n", encoding="utf-8")
    git(path, "add", ".")
    git(path, "commit", "-m", "Fixture base")
    return path


def terminal_fixture(name, path):
    # The app launches these fixture executables through its real PTY adapter.
    path.write_text(f"""#!{sys.executable}
import os
import pathlib
import sys
if sys.argv[1:] == ["--version"]:
    print("opencode v2.2.7")
    raise SystemExit(0)
print("\\033[2J\\033[H\\033[36m{name} · test fixture\\033[0m", flush=True)
print("Project: " + pathlib.Path.cwd().name, flush=True)
if "--model" in sys.argv:
    print("Model: " + sys.argv[sys.argv.index("--model") + 1], flush=True)
print("Interactive terminal ready. Type a line to echo it.", flush=True)
while True:
    try:
        value = input("fixture> ")
    except KeyboardInterrupt:
        print("\\ninterrupted", flush=True)
        continue
    except EOFError:
        break
    if value == "dimensions":
        columns, rows = os.get_terminal_size()
        print(f"terminal-size [{{columns}} x {{rows}}]", flush=True)
    elif value == "history":
        for number in range(120):
            print(f"scrollback-fixture:{{number}}", flush=True)
    else:
        print("received: " + value, flush=True)
""", encoding="utf-8")
    path.chmod(0o700)
    return str(path)


def screen(window, output, name, geometry=None):
    if geometry:
        width, height = geometry
        window.geometry(f"{width}x{height}+0+0")
    window.update()
    if output is None:
        return
    from PIL import ImageGrab

    x, y = window.winfo_rootx(), window.winfo_rooty()
    width, height = window.winfo_width(), window.winfo_height()
    assert x + width <= window.winfo_screenwidth() and y + height <= window.winfo_screenheight(), (
        "Use a display at least 1920 × 1080 for screenshot capture."
    )
    output.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(bbox=(x, y, x + width, y + height)).save(output / name)


def terminal_text(terminal):
    return terminal.surface.get("1.0", "end")


def verify_split_input_during_output(window, app, repository):
    fixture = """
import time
import sys
sys.stdout.reconfigure(line_buffering=True)
print("split-ready")
while True:
    value = input()
    if value == "produce":
        for batch in range(100):
            print("\\n".join(f"continuous-{batch:02}-{index:02}" for index in range(40)))
            time.sleep(.025)
        print("producer-done")
    else:
        print("answer:" + value)
"""
    key = app.new_terminal("Concurrent PTY regression", [sys.executable, "-u", "-c", fixture], repository)
    try:
        app.split_terminal("horizontal")
        producer, interactive = app.terminal_tabs[key].views
        wait(window, lambda: all("split-ready" in terminal_text(view) for view in (producer, interactive)),
             "split console fixtures did not start")
        app.focus_terminal(key, 1)
        interactive.surface.focus_force()
        producer.send("produce\r")
        wait(window, lambda: "continuous-" in terminal_text(producer), "background output did not start")
        started = time.monotonic()
        interactive.send("split-input")
        interactive.surface.event_generate("<KeyPress-Return>")
        wait(window, lambda: "answer:split-input" in terminal_text(interactive), "interactive pane stalled")
        assert "producer-done" not in terminal_text(producer), "interactive input waited until the producer finished"
        assert "split-input" not in terminal_text(producer), "peer pane received the interactive input"
        print(f"Split pane responded during sustained PTY output in {(time.monotonic() - started) * 1000:.0f} ms.",
              flush=True)
        wait(window, lambda: "producer-done" in terminal_text(producer), "background output did not finish")
    finally:
        app.remove_terminal(key)


def select_context(book, widget):
    while widget.master != book:
        widget = widget.master
    book.select(widget)


def tree_items(tree, parent=""):
    for item in tree.get_children(parent):
        yield item
        yield from tree_items(tree, item)


@contextmanager
def ssh_profile(root, data, project):
    root.mkdir()
    worker = root / "worker"
    register_project(worker, project)
    source = Path(__file__).resolve().parents[1]
    rpc = f"cd -- {shlex.quote(str(source))} && exec {shlex.quote(sys.executable)} -m orchestra.remote"
    for name in ("host", "operator"):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(root / name)], check=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    fixture_shell = root / "fixture-shell"
    fixture_home = root / "empty-home"
    fixture_home.mkdir()
    fixture_shell.write_text(f"""#!/bin/sh
if [ "${{SSH_ORIGINAL_COMMAND:-}}" = 'uname -s' ]; then
  exec uname -s
fi
if [ "${{SSH_ORIGINAL_COMMAND:-}}" = {shlex.quote(rpc)} ]; then
  cd {shlex.quote(str(source))}
  ORCHESTRA_REMOTE_DATA={shlex.quote(str(worker))} exec {shlex.quote(sys.executable)} -m orchestra.remote
fi
cd {shlex.quote(str(project))}
export HOME={shlex.quote(str(fixture_home))}
export PS1='ssh-fixture$ '
export HISTFILE=/dev/null
printf '\\033[2J\\033[HOpenSSH test fixture connected\\n'
exec /bin/sh -i
""", encoding="utf-8")
    fixture_shell.chmod(0o700)
    user = getpass.getuser()
    configuration = root / "sshd_config"
    configuration.write_text(f"""Port {port}
ListenAddress 127.0.0.1
HostKey {root / 'host'}
AuthorizedKeysFile {root / 'operator.pub'}
PidFile {root / 'sshd.pid'}
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM no
StrictModes no
ForceCommand {fixture_shell}
AllowUsers {user}
""", encoding="utf-8")
    executable = shutil.which("sshd") or "/usr/sbin/sshd"
    with (root / "sshd.log").open("wb") as trace:
        daemon = subprocess.Popen([executable, "-D", "-e", "-f", str(configuration)], stderr=trace)
        try:
            for _ in range(80):
                if daemon.poll() is not None:
                    raise AssertionError((root / "sshd.log").read_text())
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.15):
                        break
                except OSError:
                    time.sleep(.04)
            else:
                raise AssertionError("OpenSSH fixture did not start")
            profile = {"name": "Loopback · test fixture", "host": "127.0.0.1", "port": port,
                       "user": user, "identity": str(root / "operator"), "auth": "key",
                       "directory": str(project), "os": "linux", "worker_dir": str(source), "python": sys.executable}
            host = put_host(data, profile)
            algorithm, public_key, *_ = (root / "host.pub").read_text().split()
            expected = fingerprint(public_key)
            observed = scan_keys(profile)
            assert observed[expected] == (algorithm, public_key)
            trust_key(data, host, profile, expected, observed)
            yield host
        finally:
            if daemon.poll() is None:
                daemon.terminate()
                daemon.wait(timeout=5)


def workflow(window, app, store, repository, server, output, *, preferred="alternative", model="model", background=True):
    w = app.w
    app.workspace_new_task()
    guide = dialog(window, w("작업 계획 만들기"))
    assert guide.get("model") == preferred, "the workspace model selection did not reach the workflow"
    guide.set("intent", "ui workflow: verify the integrated workspace")
    guide.set("strategy", w(STRATEGIES[1]))
    guide.set("model", model)
    guide.set("harness", "managed")
    guide.set("background", background)
    guide.set("paths", "ui-result.txt")
    check = [sys.executable, "-c", "from pathlib import Path; assert Path('ui-result.txt').is_file()"]
    guide.set("qa", format_commands([check]))
    press(guide.footer, w("검토할 계획 생성"))
    plan = dialog(window, w("실행 계획 검토"))
    listing = next(widget for widget in descendants(plan) if isinstance(widget, tk.Listbox))
    assert any("develop" in row for row in listing.get(0, "end"))
    assert any("review" in row and "develop" in row for row in listing.get(0, "end"))
    press(plan.footer, w("검증 후 실행"))
    wait(window, server.stalled.is_set, "Supervisor did not enter the fixture Agent call")
    jobs = [job for job in store.list_jobs() if job["plan"]["title"] == "ui workflow: verify the integrated workspace"]
    assert len(jobs) == 1
    job = jobs[0]["id"]
    assert store.job(job)["state"] == "RUNNING"
    app.open_workspace_job(job)
    app.close_workspace_tab()
    assert job not in app.workspace_tabs
    assert store.job(job)["state"] == "RUNNING", "closing an execution tab stopped a detached job"
    app.open_workspace_job(job)
    fields = app.workspace_tabs[job]
    fields["detail"].select(fields["dag"].master)
    screen(window, output, "task-execution-1440x900.png", (1440, 900))
    select_context(app.workspace_context, app.workspace_agents)
    agent_rows = wait(window, app.workspace_agents.get_children, "integrated Agent panel is empty", timeout=7)
    app.workspace_agents.selection_set(agent_rows[0])
    app.workspace_agents.event_generate("<<TreeviewSelect>>")
    wait(window, lambda: "Harness managed" in app.workspace_agent_detail.get("1.0", "end"),
         "Agent selection did not show execution details")
    screen(window, output, "agent-context-1440x900.png")
    # The model HTTP fixture waits for this event; the Supervisor and Git are real.
    server.released.set()
    ready = wait(window, lambda: (snapshot if (snapshot := store.job(job))["state"] == "AWAITING_APPROVAL" else None),
                 "Supervisor did not publish the integration QA result")
    assert ready["result"]["changed"] == ["ui-result.txt"]
    assert ready["result"]["qa"][0]["exit_code"] == 0
    assert ready["result"]["approval_revision"]
    assert not (repository / "ui-result.txt").exists(), "Unapproved candidate affected the target"
    fields = app.workspace_tabs[job]
    app.open_workspace_job(job)
    assert fields["dag"].find_all()
    assert "test-model" in fields["overview"].get("1.0", "end")
    assert str(repository) in fields["overview"].get("1.0", "end")
    assert "ui-result.txt" in fields["qa"].get("1.0", "end")
    assert w("검증 {0} · 종료 코드 {1}", 1, 0).rsplit("· ", 1)[-1] in fields["qa"].get("1.0", "end")
    assert "ui-result.txt" in fields["changes"].get("1.0", "end")
    frame = fields["frame"]
    approval = wait(window, lambda: next((button for button in descendants(frame)
                    if isinstance(button, ttk.Button) and button.cget("text") == w("병합 검토")
                    and not button.instate(["disabled"])), None), "workspace merge action is unavailable")
    problems = []

    def inspect_approval():
        review = dialog(window, w("Git 병합 승인"))
        try:
            text = next(widget for widget in descendants(review) if isinstance(widget, tk.Text)).get("1.0", "end")
            for value in ("ui-result.txt", ready["result"]["approval_revision"], ready["result"]["candidate"],
                          w("{0}. 통과 (종료 코드 {1})", 1, 0)):
                assert value in text, value
            screen(review, output, "git-qa-approval.png")
            press(review, w("이 후보 승인"))
        except Exception as error:
            problems.append(error)
            review.destroy()

    window.after(80, inspect_approval)
    approval.invoke()
    if problems:
        raise problems[0]
    wait(window, lambda: store.job(job)["state"] == "MERGED", "candidate was not integrated")
    assert git(repository, "rev-parse", "HEAD") == ready["result"]["candidate"]
    assert (repository / "ui-result.txt").read_text(encoding="utf-8") == "approved change\n"


def run_test(args):
    with tempfile.TemporaryDirectory(prefix="orchestra-integrated-workspace-") as temporary, http_fixture() as (server, url):
        root = Path(temporary)
        data = root / "workspace-data"
        repository = fixture_repo(root / "workspace-fixture")
        other = fixture_repo(root / "second-project")
        first_id = put_project(data, inspect_project(repository) | {"name": "Workspace fixture", "model": "model"})
        second_id = put_project(data, inspect_project(other) | {"name": "Second project"})
        registry = config(url)
        registry["models"]["alternative"] = dict(registry["models"]["model"])
        errors = []
        fixture_cli = {}
        if os.name != "nt":
            fixture_cli = {tool: terminal_fixture(tool, root / executable) for tool, executable in
                           (("OpenCode", "opencode"), ("Codex", "codex"))}
            registry["harnesses"]["terminal-opencode"] = {
                "kind": "opencode", "executable": fixture_cli["OpenCode"], "trusted": True,
            }
            registry["models"]["terminal-fixture"] = {
                "provider": "subscription", "model": "fixture/selected-model", "harnesses": ["terminal-opencode"],
            }
        save_registry(data, registry)
        store = Store(data)
        with patch("orchestra.workspace_sessions.scan_clis", return_value=fixture_cli), \
                patch("tkinter.messagebox.askyesno", return_value=True), \
                patch("tkinter.messagebox.showerror", side_effect=lambda title, msg, **_: errors.append((title, msg))):
            window = tk.Tk()
            app = WorkspaceDesktop(window, data)
            try:
                exercise(args, window, app, store, root, repository, first_id, second_id, server)
                previous_registry = (data / "registry.json").read_bytes()
                descriptors = app.terminal_descriptors()
                active_views = [view for _, views in app.terminals.values() for view in views]
                app.workspace_move_tab(-1)
                tab_order = [app.workspace_book.tab(tab, "text") for tab in app.workspace_book.tabs()]
                active_tab = app.workspace_book.tab(app.workspace_book.select(), "text")
                app.workspace_toggle_context()
                app.workspace_toggle_sidebar()
                window.update()
                app.save_workspace_layout()
                saved_layout = read_layout(app.workspace_layout_path)
                app.close()
                assert all(view.closed.is_set() for view in active_views)
                window = tk.Tk()
                app = WorkspaceDesktop(window, data)
                window.update()
                assert app.project_id == first_id
                assert all(not views for _, views in app.terminals.values())
                assert len(app.terminal_descriptors()) == len(descriptors)
                assert app.terminal_descriptors() == saved_layout["terminals"], "split direction or sash ratio changed"
                assert [app.workspace_book.tab(tab, "text") for tab in app.workspace_book.tabs()] == tab_order
                assert app.workspace_book.tab(app.workspace_book.select(), "text") == active_tab
                assert app.workspace_prefs["sidebar_hidden"] and app.workspace_prefs["context_hidden"]
                assert (data / "registry.json").read_bytes() == previous_registry
                assert not errors, errors
            finally:
                server.released.set()
                app.close()
                status = data / "supervisor.json"
                if status.exists():
                    (data / "supervisor.stop").touch()
                    deadline = time.monotonic() + 12
                    while status.exists() and time.monotonic() < deadline:
                        time.sleep(.05)
                    assert not status.exists(), "fixture Supervisor did not stop"
    print("Integrated Tk workspace verified with real PTYs, disposable Git and scripted inference.")


def exercise(args, window, app, store, root, repository, first_id, second_id, server):
    assert app.view == "workspace"
    verify_split_input_during_output(window, app, repository)
    app.select_workspace_project(first_id)
    assert app.project_id == first_id
    screen(window, args.screenshots, "integrated-workspace-1440x900.png", (1440, 900))
    app.toggle_theme()
    assert app.theme_name == "light"
    screen(window, args.screenshots, "integrated-workspace-light-1920x1080.png", (1920, 1080))
    app.toggle_theme()
    screen(window, None, "", (1440, 900))
    app.workspace_search.set("second project")
    items = [app.workspace_tree.item(key, "text").casefold() for key in tree_items(app.workspace_tree)]
    assert any("second project" in value for value in items)
    assert not any("workspace fixture" in value for value in items)
    row = next(key for key, action in app.workspace_sidebar_actions.items() if action == ("project", second_id))
    app.workspace_tree.selection_set(row)
    app.workspace_sidebar_open()
    assert app.project_id == second_id
    app.workspace_search.set("")
    app.select_workspace_project(first_id)
    model = next(label for label, key in app.workspace_model_keys.items() if key == "alternative")
    app.workspace_model_picker.set(model)
    app.workspace_model_picker.event_generate("<<ComboboxSelected>>")
    assert app.workspace_models.get() == model
    if args.screenshots and window.tk.call("tk", "windowingsystem") == "x11":
        window.tk.call("ttk::combobox::Post", str(app.workspace_model_picker))
    screen(window, args.screenshots, "model-selector-1440x900.png")
    if args.screenshots and window.tk.call("tk", "windowingsystem") == "x11":
        window.tk.call("ttk::combobox::Unpost", str(app.workspace_model_picker))
    automatic = next(label for label, key in app.workspace_model_keys.items() if not key)
    app.workspace_model_picker.set(automatic)
    app.workspace_choose_model()
    app.workspace_new_task()
    guide = dialog(window, "작업 계획 만들기")
    assert not guide.get("model"), "automatic selection reused the project's configured model"
    guide.destroy()
    app.workspace_model_picker.set(model)
    app.workspace_choose_model()
    if os.name != "nt":
        app.workspace_open_ai("OpenCode", "terminal-fixture")
        opencode = app.terminal_book.select()
        codex = app.open_ai_terminal("Codex")
        assert opencode != codex
        first = app.terminals[opencode][1][0]
        second = app.terminals[codex][1][0]
        wait(window, lambda: "Codex" in terminal_text(second), "Codex fixture did not start")
        assert app.open_ai_terminal("Codex") == codex
        assert app.terminals[codex][1][0] is second
        screen(window, args.screenshots, "multiple-ai-tabs-1440x900.png", (1440, 900))
        app.select_workspace_project(second_id)
        assert app.project_id == second_id
        app.select_workspace_project(first_id)
        app.focus_terminal(opencode)
        wait(window, lambda: "Model: fixture/selected-model" in terminal_text(first),
             "OpenCode did not render its configured startup model")
        assert app.terminal_tabs[opencode].args[0][0][1:] == ["mini", "--standalone", "--model", "fixture/selected-model"]
        assert "fixture/selected-model" in app.workspace_runtime_status.cget("text")
        app.workspace_open_ai("OpenCode", "terminal-fixture")
        assert app.terminal_book.select() == opencode and app.terminal_tabs[opencode].views[0] is first
        assert any(name.startswith("colors_cyan") for name in first.surface.tag_names())
        first.send("한국어 확인")
        wait(window, lambda: "한국어 확인" in terminal_text(first), "Korean PTY input was not rendered")
        typed = first.surface.search("한국어 확인", "1.0")
        cursor = first.surface.tag_ranges("terminal_cursor")[0]
        assert str(cursor) == first.surface.index(f"{typed} + 6 chars"), "cursor drifted after Korean wide characters"
        first.send("\r")
        wait(window, lambda: "received: 한국어 확인" in terminal_text(first), "Unicode PTY echo unavailable")
        selection = first.surface.search("한국어 확인", "1.0")
        first.surface.tag_add("sel", selection, f"{selection} + 6 chars")
        first.copy_selection()
        assert first.surface.clipboard_get() == "한국어 확인"
        first.surface.clipboard_clear()
        first.surface.clipboard_append("paste fixture")
        first.paste()
        first.send("\r")
        wait(window, lambda: "received: paste fixture" in terminal_text(first), "terminal clipboard input failed")
        first.send("\x03")
        wait(window, lambda: "interrupted" in terminal_text(first), "Ctrl+C did not reach the foreground PTY")
        previous = (first.screen.lines, first.screen.columns)
        app.split_terminal(orient="horizontal", kind="Codex")
        panels = app.terminals[opencode][1]
        assert len(panels) == 2
        wait(window, lambda: "Codex" in terminal_text(panels[1]), "Split Codex fixture did not start")
        assert panels[1] is second, "splitting relaunched the existing Codex terminal"
        app.focus_terminal(opencode, 0)
        assert app.workspace_runtime_status.cget("text").startswith("OpenCode ")
        app.focus_terminal(opencode, 1)
        assert app.workspace_runtime_status.cget("text").startswith("Codex ")
        screen(window, args.screenshots, "split-terminals-1920x1080.png", (1920, 1080))
        app.workspace_toggle_focus()
        window.update()
        assert len(app.workspace_panes.panes()) == 1 and not app.nav_frame.winfo_ismapped()
        assert panels[1] is second and not second.closed.is_set()
        app.save_workspace_layout()
        focused_layout = read_layout(app.workspace_layout_path)
        assert not focused_layout["sidebar_hidden"] and not focused_layout["context_hidden"]
        app.workspace_toggle_focus()
        window.update()
        assert len(app.workspace_panes.panes()) == 2 and app.nav_frame.winfo_ismapped()
        assert (first.screen.lines, first.screen.columns) != previous
        first.send("dimensions\r")
        wait(window, lambda: f"[{first.screen.columns} x {first.screen.lines}]" in terminal_text(first), "PTY resize not applied")
        terminal_row = next(row for row, action in app.workspace_sidebar_actions.items()
                            if action[:3] == ("terminal", opencode, 1))
        app.focus_terminal(opencode, 0)
        app.workspace_tree.see(terminal_row)
        window.update()
        x, y, width, height = app.workspace_tree.bbox(terminal_row)
        app.workspace_tree.selection_set(terminal_row)
        app.workspace_tree.event_generate("<ButtonRelease-1>", x=x + width // 2, y=y + height // 2)
        assert app.terminal_tabs[opencode].active_panel == 1, "sidebar did not focus the selected split panel"
        app.hide_terminal(opencode)
        window.update()
        assert app.terminal_book.tab(opencode, "state") == "hidden", "sidebar selection reopened a hidden terminal"
        assert not first.closed.is_set()
        app.focus_terminal(opencode, 0)
        assert app.terminal_book.select() == opencode
        assert "한국어 확인" in terminal_text(first)
        app.split_terminal(orient="vertical")
        assert len(app.terminals[opencode][1]) == 2
        assert app.terminal_tabs[opencode].orient == "vertical"
        first.send("history\r")
        wait(window, lambda: "scrollback-fixture:119" in terminal_text(first), "terminal history fixture did not finish")
        first.page(True)
        assert "scrollback-fixture:" in terminal_text(first) and "scrollback-fixture:119" not in terminal_text(first)
    (repository / "src" / "workflow.py").write_text("print('changed workflow')\n", encoding="utf-8")
    (repository / ".env").write_text("TEST_ONLY_MARKER=hidden\n", encoding="utf-8")
    app.select_workspace_project(second_id)
    app.select_workspace_project(first_id)
    file_tree = app.context_file_tree
    select_context(app.workspace_context, file_tree)
    wait(window, lambda: file_tree.exists("src"), "project explorer did not show the registered project")
    assert not file_tree.exists(".env")
    file_tree.focus("src")
    file_tree.item("src", open=True)
    file_tree.event_generate("<<TreeviewOpen>>")
    relative = "src/workflow.py"
    wait(window, lambda: file_tree.exists(relative), "project explorer did not expand the directory")
    file_tree.selection_set(relative)
    app.preview_workspace_file()
    wait(window, lambda: "changed workflow" in app.context_file_preview.get("1.0", "end"), "file preview absent")
    app.context_file_query.set("workflow")
    app.search_workspace_files()
    wait(window, lambda: file_tree.get_children() == (relative,), "file search did not return the matching project file")
    screen(window, args.screenshots, "project-files-small.png", (940, 650))
    assert app.context_search.winfo_ismapped() and app.context_search.winfo_width() >= 60, "file search collapsed at the smaller viewport"
    assert app.workspace_runtime_status.winfo_y() >= app.workspace_status.winfo_height(), "footer rows overlap"
    for button in (app.workspace_terminal_button, app.workspace_focus_button, app.workspace_layout_button):
        assert button.winfo_ismapped() and button.winfo_rootx() + button.winfo_width() <= window.winfo_rootx() + 940
    app.context_file_query.set("")
    app.search_workspace_files()
    git_tree = app.context_git_tree
    select_context(app.workspace_context, git_tree)
    wait(window, lambda: git_tree.exists(relative), "Git context did not report modified file")
    git_tree.selection_set(relative)
    app.preview_workspace_diff()
    wait(window, lambda: "+print('changed workflow')" in app.context_git_preview.get("1.0", "end"), "read-only Git diff absent")
    screen(window, args.screenshots, "project-git-1440x900.png", (1440, 900))
    app.select_workspace_project(second_id)
    wait(window, lambda: app.workspace_context.index(app.workspace_context.select()) == 0, "second project did not restore Files")
    app.select_workspace_project(first_id)
    wait(window, lambda: app.workspace_context.index(app.workspace_context.select()) == 1, "first project did not restore Git")
    (repository / "src" / "workflow.py").write_text("print('original workflow')\n", encoding="utf-8")
    (repository / ".env").unlink()
    if args.ssh:
        with ssh_profile(root / "ssh-fixture", app.root, repository) as host:
            remote_tab = app.open_ssh_terminal(host)
            assert app.terminal_tabs[remote_tab].recipes[0].project is None, "unrelated local project was assigned to SSH"
            remote_panel = app.terminals[remote_tab][1][0]
            wait(window, lambda: "OpenSSH test fixture connected" in terminal_text(remote_panel), "SSH PTY fixture unavailable")
            remote_panel.send("printf 'remote command verified\\n'\r")
            wait(window, lambda: "\nremote command verified" in terminal_text(remote_panel), "SSH PTY did not execute the command")
            assert "SSH 셸" in app.workspace_runtime_status.cget("text")
            screen(window, args.screenshots, "ssh-terminal-1440x900.png", (1440, 900))
            app.remove_terminal()
            assert remote_panel.closed.is_set()
            app.show("ssh")
            app.ssh_list.selection_set(host)
            results = []
            app.test_saved_host(host, on_result=results.append)
            pending = app.host_probes[host]
            app.test_saved_host(host, on_result=results.append)
            assert app.host_probes[host] is pending
            assert "연결 확인 중…" in app.ssh_details.get("1.0", "end")
            wait(window, lambda: len(results) == 2 and "git.diff" in app.ssh_details.get("1.0", "end"),
                 "SSH management did not show the negotiated Worker capabilities")
            assert results[0] is results[1] and "Supervisor 하트비트 없음" in app.ssh_details.get("1.0", "end")
            screen(window, args.screenshots, "worker-compatibility-1440x900.png", (1440, 900))
            remote_id = put_project(app.root, inspect_project(repository) | {"host": host, "name": "Remote fixture"})
            remote_file = repository / "remote-preview.txt"
            remote_file.write_text("Remote workspace preview\n", encoding="utf-8")
            app.select_workspace_project(remote_id)
            select_context(app.workspace_context, git_tree)
            wait(window, lambda: git_tree.exists(remote_file.name), "remote Workspace Git status absent")
            git_tree.selection_set(remote_file.name)
            app.preview_workspace_diff()
            wait(window, lambda: "+Remote workspace preview" in app.context_git_preview.get("1.0", "end"),
                 "remote Workspace Git diff absent")
            screen(window, args.screenshots, "remote-git-1440x900.png", (1440, 900))
            remote_file.unlink()
            app.select_workspace_project(first_id)
        app.select_workspace_project(remote_id)
        wait(window, lambda: "Worker 연결이 끊겼습니다." in app.context_git_note.cget("text"),
             "remote Git context did not identify a disconnected Worker")
        app.select_workspace_project(first_id)
    workflow(window, app, store, repository, server, args.screenshots)
    assert app.terminal_descriptors() or os.name == "nt"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path, help="Store real screenshots with Pillow at three viewport sizes.")
    parser.add_argument("--ssh", action="store_true", help="Exercise an isolated loopback OpenSSH server.")
    args = parser.parse_args()
    if args.ssh and sys.platform != "linux":
        parser.error("The loopback sshd fixture requires Linux.")
    run_test(args)
