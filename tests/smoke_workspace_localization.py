"""Check persisted language preferences and small-window labels with native Tk."""
import argparse
import os
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

from smoke_integrated_workspace import (
    WorkspaceDesktop, descendants, dialog, fixture_repo, inspect_project, press, put_project, screen, wait,
)


def assert_visible(row, window):
    window.update()
    end = window.winfo_rootx() + window.winfo_width()
    for widget in descendants(row):
        if isinstance(widget, (ttk.Button, ttk.Combobox)):
            assert widget.winfo_ismapped() and widget.winfo_rootx() + widget.winfo_width() <= end, widget


def check_admin(app, window, output):
    for page, action in (("providers", "Provider setup"), ("ssh", "Add SSH host"),
                         ("mcp", "Server and permissions"), ("settings", "Export settings")):
        app.show(page)
        window.update()
        button = next(widget for widget in descendants(app.pages[page])
                      if isinstance(widget, ttk.Button) and widget.cget("text") == action)
        assert_visible(button.master, window)
    app.show("providers")
    press(app.pages["providers"], "Provider setup")
    provider = dialog(window, "Provider setup")
    assert "OpenAI-compatible" in provider.fields["kind"][1]["values"]
    advanced = next(widget for widget in descendants(provider)
                    if isinstance(widget, ttk.Radiobutton) and widget.cget("text") == "Advanced")
    screen(provider, output, "admin-provider-en.png")
    advanced.invoke()
    window.update_idletasks()
    assert provider.fields["auth_env"][1].winfo_ismapped()
    provider.destroy()
    app.show("ssh")
    press(app.pages["ssh"], "Add SSH host")
    ssh = dialog(window, "Add SSH host")
    assert ssh.field_rows["host"][0].cget("text") == "Host name or IP"
    screen(ssh, output, "admin-ssh-en.png")
    ssh.destroy()
    app.show("mcp")
    press(app.pages["mcp"], "Server and permissions")
    mcp = dialog(window, "Managed MCP servers and permissions")
    assert mcp.field_rows["transport"][0].cget("text") == "Transport"
    screen(mcp, output, "admin-mcp-en.png")
    mcp.destroy()


def exercise(output):
    with tempfile.TemporaryDirectory(prefix="orchestra-lang-") as temporary:
        root = Path(temporary)
        repo = fixture_repo(root / "locale-fixture")
        data = root / "desktop"
        put_project(data, inspect_project(repo) | {"name": "Locale fixture"})
        environment = dict(os.environ)
        environment.pop("ORCHESTRA_LANG", None)
        with patch.dict(os.environ, environment, clear=True), patch("orchestra.desktop.start_supervisor"), \
                patch("tkinter.messagebox.showinfo") as feedback:
            window = tk.Tk()
            app = WorkspaceDesktop(window, data)
            try:
                assert app.locale == "ko"
                app.workspace_set_language("en")
                assert feedback.called and app.locale == "ko"
            finally:
                window.update_idletasks()
                app.close()
            window = tk.Tk()
            app = WorkspaceDesktop(window, data)
            try:
                assert app.locale == "en"
                assert [app.workspace_context.tab(tab, "text") for tab in app.workspace_context.tabs()] == [
                    "Files", "Git", "Agent", "Activity",
                ]
                app.toggle_theme()
                assert app._read_ui_prefs()["locale"] == "en"
                screen(window, output, "english-light-940x650.png", (940, 650))
                assert_visible(app.workspace_actions, window)
                assert_visible(app.workspace_view_actions, window)
                assert app.workspace_context.winfo_width() >= 258 and app.context_search.winfo_ismapped()
                focus = app.workspace_focus_button
                focus.event_generate("<Enter>")
                hint = wait(window, lambda: next((child for child in focus.winfo_children()
                                                  if isinstance(child, tk.Toplevel)), None), "English tooltip missing")
                assert hint.winfo_children()[0].cget("text") == "Hide the side panels to give the terminal more space."
                focus.event_generate("<Leave>")
                assert not hint.winfo_exists()
                app.workspace_new_task()
                form = dialog(window, "Create a task plan")
                assert form.get("strategy") == "Read-only analysis"
                labels = {widget.cget("text") for widget in descendants(form) if isinstance(widget, (ttk.Button, ttk.Label))}
                assert {"Close", "Review proposed plan", "Task objective", "QA commands"} <= labels
                assert app.workspace_error(ValueError("보호된 경로나 지원하지 않는 파일 이름입니다.")) == (
                    "Protected path or unsupported filename."
                )
                screen(window, output, "english-task-form.png")
                form.destroy()
                check_admin(app, window, output)
            finally:
                app.close()
    print("Native Tk English workspace, task, Provider, SSH, MCP and compact layout passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path)
    exercise(parser.parse_args().screenshots)
