"""Exercise installed OpenCode and Codex TUIs without credentials or network access."""
import argparse
import fcntl
import json
import os
import shutil
import struct
import subprocess
import tempfile
import termios
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from smoke_integrated_workspace import (
    WorkspaceDesktop, fixture_repo, inspect_project, put_project, screen, terminal_text, wait,
)


def offline_environment(root, project):
    environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
    for key, name in {
        "HOME": "user", "XDG_CONFIG_HOME": "config", "XDG_DATA_HOME": "data", "XDG_STATE_HOME": "state",
        "XDG_CACHE_HOME": "cache", "CODEX_HOME": "codex",
    }.items():
        path = root / name
        path.mkdir(parents=True)
        environment[key] = str(path)
    (root / "codex" / "config.toml").write_text(
        'model = "workspace-offline"\nmodel_provider = "workspace_offline"\n'
        'check_for_update_on_startup = false\n'
        '[model_providers.workspace_offline]\nname = "Offline UI fixture"\n'
        'base_url = "http://127.0.0.1:1/v1"\nwire_api = "responses"\nrequires_openai_auth = false\n'
        f'[projects.{json.dumps(str(project))}]\ntrust_level = "trusted"\n',
        encoding="utf-8",
    )
    return environment | {"TERM": "xterm-256color", "OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_DISABLE_LSP": "1"}


def tty_size(terminal):
    dimensions = fcntl.ioctl(terminal.pty.master, termios.TIOCGWINSZ, bytes(8))
    return struct.unpack("HHHH", dimensions)[:2]


def main(output):
    unshare = shutil.which("unshare")
    commands = {name: shutil.which(name.lower()) for name in ("OpenCode", "Codex")}
    assert unshare and all(commands.values()), "Linux unshare and both installed CLIs are required"
    ip = shutil.which("ip")
    assert ip, "iproute2 is required for isolated loopback"
    network = [unshare, "--user", "--map-root-user", "--net", "--pid", "--kill-child", "--fork", "--",
               "/bin/sh", "-c", '"$1" link set dev lo up && shift && exec "$@"', "workspace-offline", ip]
    subprocess.run([*network, "true"], check=True)
    with tempfile.TemporaryDirectory(prefix="orchestra-installed-tui-") as temporary:
        root = Path(temporary)
        repository = fixture_repo(root / "interactive-project")
        other = fixture_repo(root / "second-project")
        data = root / "desktop"
        projects = [put_project(data, inspect_project(path) | {"name": path.name}) for path in (repository, other)]
        environment = offline_environment(root / "isolated", repository)
        window = tk.Tk()
        with patch("orchestra.desktop.start_supervisor"):
            app = WorkspaceDesktop(window, data)
            default_args = app._terminal_args

            def arguments(recipe):
                argv, cwd, _ = default_args(recipe)
                return [*network, *argv], cwd, environment

            with patch.object(app, "_terminal_args", side_effect=arguments):
                try:
                    app.select_workspace_project(projects[0])
                    open_tab = app.open_ai_terminal("OpenCode")
                    codex_tab = app.open_ai_terminal("Codex")
                    opened = app.terminal_tabs[open_tab].views[0]
                    codex = app.terminal_tabs[codex_tab].views[0]
                    try:
                        wait(window, lambda: "Trust this folder" in terminal_text(codex) or "Codex" in terminal_text(codex),
                             "installed Codex prompts did not render", timeout=12)
                        if "Trust this folder" in terminal_text(codex):
                            codex.send("\r")  # The trusted directory is the disposable repository created above.
                        app.focus_terminal(open_tab)
                        wait(window, lambda: opened.screen._alternate is not None and len(opened.tags) > 3,
                             "installed OpenCode fullscreen UI did not render", timeout=12)
                        app.focus_terminal(codex_tab)
                        wait(window, lambda: "Codex" in terminal_text(codex) and len(codex.tags) > 3,
                             "installed Codex UI did not render", timeout=12)
                    except AssertionError:
                        for name, terminal in (("OpenCode", opened), ("Codex", codex)):
                            print(name, terminal.pty.process.poll(), len(terminal.tags), terminal_text(terminal).strip()[:1600])
                        raise
                    processes = [opened.pty.process, codex.pty.process]
                    assert all(process.poll() is None for process in processes)
                    assert app.open_ai_terminal("OpenCode") == open_tab
                    assert app.terminal_tabs[open_tab].views[0].pty.process.pid == processes[0].pid
                    app.split_terminal("horizontal", "Codex")
                    assert app.terminal_tabs[open_tab].views == [opened, codex]
                    screen(window, None, "", (1920, 1080))
                    wait(window, lambda: all(terminal.surface.winfo_width() > 470 and
                                             tty_size(terminal) == (terminal.screen.lines, terminal.screen.columns)
                                             for terminal in (opened, codex)),
                         "the native PTYs did not resize at the capture viewport")
                    # Drain asynchronous full-screen redraws after the window resize.
                    ready = time.monotonic() + .7
                    wait(window, lambda: time.monotonic() >= ready, "redraw wait failed")
                    screen(window, output, "installed-cli-split-1920x1080.png", (1920, 1080))
                    before = (opened.screen.lines, opened.screen.columns)
                    app.split_terminal("vertical")
                    window.update()
                    wait(window, lambda: (opened.screen.lines, opened.screen.columns) != before, "real TUI did not resize")
                    assert all(tty_size(terminal) == (terminal.screen.lines, terminal.screen.columns) for terminal in (opened, codex))
                    for index, terminal in enumerate((opened, codex)):
                        app.focus_terminal(open_tab, index)
                        terminal.surface.focus_force()
                        window.update()
                        for key in "wqa":
                            terminal.surface.event_generate("<KeyPress>", keysym=key)
                        wait(window, lambda: "wqa" in terminal_text(terminal), "English keyboard input did not render")
                        terminal.clipboard_clear()
                        terminal.clipboard_append("workspace-input 한국어")
                        terminal.paste()
                        wait(window, lambda: "workspace-input 한국어" in terminal_text(terminal),
                             "clipboard paste with Korean text did not render")
                        selection = terminal.surface.search("workspace-input 한국어", "1.0")
                        terminal.surface.tag_add("sel", selection, f"{selection} + 19 chars")
                        terminal.copy_selection()
                        assert terminal.clipboard_get() == "workspace-input 한국어"
                    app.select_workspace_project(projects[1])
                    assert app.project_id == projects[1]
                    app.focus_terminal(open_tab)
                    wait(window, lambda: app.project_id == projects[0], "terminal did not restore its project")
                    app.hide_terminal(open_tab)
                    window.update()
                    assert all(process.poll() is None for process in processes)
                    app.focus_terminal(open_tab)
                    app.remove_terminal(open_tab)
                    assert all(process.poll() is not None for process in processes), "a removed CLI remained alive"
                    print("Installed OpenCode and Codex: concurrent offline PTYs, input, clipboard, split, focus, resize and cleanup passed.")
                finally:
                    app.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path)
    main(parser.parse_args().screenshots)
