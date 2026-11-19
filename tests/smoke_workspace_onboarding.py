"""Drive first-run setup through real Tk widgets, Git and a loopback Provider."""
import argparse
import os
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

from smoke_integrated_workspace import (
    WorkspaceDesktop, config, descendants, dialog, fixture_repo, http_fixture, press, save_registry,
    screen, terminal_fixture, terminal_text, wait,
)
from orchestra.workspace import read_workspace


def exercise(output):
    with tempfile.TemporaryDirectory(prefix="orchestra-onboarding-") as temporary, http_fixture() as (_, endpoint):
        root = Path(temporary)
        project = fixture_repo(root / "daily-project")
        data = root / "settings"
        save_registry(data, config(endpoint))
        before = (data / "registry.json").read_bytes()
        cli = {"Codex": terminal_fixture("Codex", root / "codex")} if os.name != "nt" else {}
        window = tk.Tk()
        with patch("orchestra.desktop.start_supervisor"), patch("orchestra.workspace_onboarding.scan_clis", return_value=cli), \
                patch("orchestra.workspace_sessions.scan_clis", return_value=cli), \
                patch("tkinter.filedialog.askdirectory", return_value=str(project / "src")):
            app = WorkspaceDesktop(window, data)
            try:
                window.update()
                assert app.workspace_setup_button.winfo_ismapped() and not app.project_rows()
                screen(window, output, "first-run-1440x900.png", (1440, 900))
                app.workspace_setup_button.invoke()
                form = app.workspace_setup
                press(form.body, "폴더 선택")
                wait(window, lambda: form.get("folder") == str(project) and form.get("cli"), "Git or CLI discovery unavailable")
                assert form.get("branch") == "main"
                assert (data / "registry.json").read_bytes() == before and not app.project_rows()
                press(form.body, "SSH 호스트 추가")
                ssh = dialog(window, "SSH 호스트 추가")
                ssh.set("name", "Optional host fixture")
                ssh.set("host", "127.0.0.1")
                ssh.set("user", "fixture")
                press(ssh.footer, "호스트 저장")
                assert "Optional host fixture" in form.get("host")
                form.set("host", "SSH 사용 안 함")
                model = next(value for value in form.fields["model"][1]["values"] if value.startswith("model ·"))
                form.set("model", model)
                press(form.body, "로컬 연결 테스트")
                wait(window, lambda: any("Provider 응답 확인" in str(widget.cget("text"))
                     for widget in descendants(form.body) if isinstance(widget, ttk.Label)), "model metadata test failed")
                screen(form, output, "first-run-setup.png")
                press(form.footer, "프로젝트 저장 및 터미널 열기")
                assert not form.winfo_exists()
                saved = read_workspace(data)["projects"][app.project_id]
                assert saved["path"] == str(project) and saved["model"] == "model"
                assert (data / "registry.json").read_bytes() == before
                view = app.terminal_tabs[app.workspace_book.select()].views[0]
                if cli:
                    wait(window, lambda: "Codex · test fixture" in terminal_text(view), "first Codex session was not interactive")
                screen(window, output, "first-run-terminal-1440x900.png")
            finally:
                app.close()
        empty = root / "no-provider-settings"
        with patch("orchestra.desktop.start_supervisor"), patch("orchestra.workspace_onboarding.scan_clis", return_value={}), \
                patch("tkinter.filedialog.askdirectory", return_value=str(project)):
            window = tk.Tk()
            app = WorkspaceDesktop(window, empty)
            try:
                app.workspace_setup_button.invoke()
                form = app.workspace_setup
                press(form.body, "폴더 선택")
                wait(window, lambda: form.get("branch") and form.get("cli"), "empty setup did not offer a shell")
                assert form.get("cli") == "로컬 셸" and form.get("model") == "자동"
                press(form.footer, "프로젝트 저장 및 터미널 열기")
                assert not form.winfo_exists() and app.terminal_tabs[app.workspace_book.select()].views
                assert not (empty / "registry.json").exists()
            finally:
                app.close()
    print("First-run Git detection, Provider metadata test, unchanged registry and terminal launch passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path)
    exercise(parser.parse_args().screenshots)
