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
from orchestra.ssh_config import local_ssh_hosts
from orchestra.workspace import read_workspace


def exercise(output):
    with tempfile.TemporaryDirectory(prefix="orchestra-onboarding-") as temporary, http_fixture() as (_, endpoint):
        root = Path(temporary)
        local_config = root / ".ssh"
        local_config.mkdir()
        ssh_config = local_config / "config"
        ssh_config.write_text(
            "Host saved-dev\n HostName dev.example.test\n User deploy\n Port 2222\n IdentityFile ~/.ssh/deploy-key\n",
            encoding="utf-8",
        )
        config_before = ssh_config.read_bytes()
        project = fixture_repo(root / "daily-project").resolve()
        data = root / "settings"
        save_registry(data, config(endpoint))
        before = (data / "registry.json").read_bytes()
        cli = {"Codex": terminal_fixture("Codex", root / "codex")} if os.name != "nt" else {}
        window = tk.Tk()
        with patch("orchestra.desktop.start_supervisor"), patch("orchestra.workspace_onboarding.scan_clis", return_value=cli), \
                patch("orchestra.workspace_sessions.scan_clis", return_value=cli), \
                patch("orchestra.workspace_remote.local_ssh_hosts", side_effect=lambda: local_ssh_hosts(root)), \
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
                assert not ssh.fields["worker_dir"][1].winfo_ismapped()
                ssh.set("config_alias", "saved-dev")
                ssh.fields["config_alias"][1].event_generate("<<ComboboxSelected>>")
                assert (ssh.get("host"), ssh.get("user"), ssh.get("port"), ssh.get("identity")) == (
                    "dev.example.test", "deploy", "2222", str(local_config / "deploy-key"))
                press(ssh.footer, "호스트 저장")
                assert "saved-dev" in form.get("host")
                hosts = read_workspace(data)["hosts"]
                host_id, saved_host = next(iter(hosts.items()))
                assert saved_host["auth"] == "agent+key" and "config_alias" not in saved_host
                assert ssh_config.read_bytes() == config_before and not (data / "ssh").exists()

                ssh_config.write_text("Host saved-dev\n HostName dev.example.test\n User deploy\n Port 2200\n", encoding="utf-8")
                app.host_dialog(host_id)
                ssh = dialog(window, "SSH 호스트 편집")
                assert ssh.get("port") == "2222"
                ssh.set("config_alias", "saved-dev")
                ssh.fields["config_alias"][1].event_generate("<<ComboboxSelected>>")
                press(ssh.footer, "호스트 저장")
                assert read_workspace(data)["hosts"][host_id]["port"] == 2200

                with patch("orchestra.workspace_remote.local_ssh_hosts", return_value={}):
                    press(form.body, "SSH 호스트 추가")
                ssh = dialog(window, "SSH 호스트 추가")
                assert "config_alias" not in ssh.fields and ssh.get("port") == "22"
                ssh.set("host", "127.0.0.1")
                ssh.set("user", "fixture")
                press(ssh.body, "고급 설정 ▾")
                assert ssh.fields["worker_dir"][1].winfo_ismapped()
                press(ssh.footer, "호스트 저장")
                assert "127.0.0.1" in form.get("host")
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
