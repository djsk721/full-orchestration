"""One clean Tk profile from initial language selection through Git approval."""
import argparse
import os
import tempfile
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from smoke_integrated_workspace import (
    WorkspaceDesktop, dialog, fixture_repo, http_fixture, press, screen, terminal_fixture, terminal_text, wait, workflow,
)
from orchestra.supervisor import read_config
from orchestra.workspace_onboarding import select_startup_language


def start(window, data, output):
    errors = []

    def choose():
        picker = next(widget for widget in window.winfo_children() if isinstance(widget, tk.Toplevel))
        try:
            screen(picker, output, "language-picker.png")
            press(picker, "English")
        except Exception as error:
            errors.append(error)
            picker.destroy()

    window.after(120, choose)
    with patch.dict(os.environ, {"ORCHESTRA_LANG": ""}):
        selected = select_startup_language(window, data)
    if errors:
        raise errors[0]
    assert selected == "en"
    app = WorkspaceDesktop(window, data, startup_locale=selected)
    window.deiconify()
    return app


def run(output):
    with tempfile.TemporaryDirectory(prefix="orchestra-production-first-run-") as temporary, http_fixture() as (server, endpoint):
        root = Path(temporary)
        repository = fixture_repo(root / "daily project 한글")
        data = root / "clean profile"
        clis = {} if os.name == "nt" else {"Codex": terminal_fixture("Codex", root / "codex")}
        errors = []
        with patch("tkinter.filedialog.askdirectory", return_value=str(repository / "src")), \
                patch("tkinter.messagebox.askyesno", return_value=True), \
                patch("tkinter.messagebox.showerror", side_effect=lambda title, error, **_: errors.append((title, error))), \
                patch("orchestra.workspace_onboarding.scan_clis", return_value=clis), \
                patch("orchestra.workspace_sessions.scan_clis", return_value=clis):
            window = tk.Tk()
            app = start(window, data, output)
            try:
                assert app.locale == "en" and not (data / "registry.json").exists()
                assert not app.project_rows()
                screen(window, output, "clean-workspace-940x650.png", (940, 650))
                app.workspace_setup_button.invoke()
                form = dialog(window, "Get started")
                press(form.body, "Choose folder")
                wait(window, lambda: form.get("branch") == "main" and form.get("cli"), "Git/CLI discovery unavailable")

                press(form.body, "Provider settings")
                provider = dialog(window, "Provider setup")
                provider.set("kind", "llama.cpp")
                provider.fields["kind"][1].event_generate("<<ComboboxSelected>>")
                window.update()
                assert provider.fields["endpoint"][1].winfo_ismapped(), "Simple mode hides the runtime URL"
                provider.set("id", "fixture-model")
                provider.set("endpoint", endpoint)
                press(provider.footer, "Test connection")
                wait(window, lambda: provider.get("model") == "test-model", "loopback runtime did not supply the model")
                press(provider.footer, "Save profile")
                wait(window, lambda: any(value.startswith("fixture-model ·") for value in form.fields["model"][1]["values"]),
                     "setup did not refresh after creating the Provider")
                label = next(value for value in form.fields["model"][1]["values"] if value.startswith("fixture-model ·"))
                form.set("model", label)

                press(form.body, "Add SSH host")
                ssh = dialog(window, "Add SSH host")
                ssh.set("name", "Optional host fixture")
                ssh.set("host", "127.0.0.1")
                ssh.set("user", "fixture")
                press(ssh.footer, "Save host")
                assert "Optional host fixture" in form.get("host")
                form.set("host", "Skip SSH")
                press(form.body, "Test local connection")
                screen(form, output, "configured-setup.png")
                press(form.footer, "Save project and open terminal")
                assert not form.winfo_exists()
                assert app.project_id and app.project_rows()[app.project_id]["model"] == "fixture-model"
                assert read_config(data)["models"]["fixture-model"]["model"] == "test-model"
                terminal = app.terminal_tabs[app.workspace_book.select()].views[0]
                if clis:
                    wait(window, lambda: "Codex" in terminal_text(terminal), "first CLI did not render")
                else:
                    terminal.send("Write-Output 'production-smoke-ready'\r")
                    wait(window, lambda: "production-smoke-ready" in terminal_text(terminal), "local terminal did not render")
                try:
                    workflow(window, app, app.store, repository, server, output, preferred="fixture-model",
                             model="fixture-model", background=False)
                except AssertionError as error:
                    observed = [(row["state"], (row.get("result") or {}).get("reason")) for row in app.store.list_jobs()]
                    raise AssertionError((str(error), errors, observed)) from error
                assert not errors, errors
            finally:
                server.released.set()
                app.close()
                status = data / "supervisor.json"
                if status.exists():
                    (data / "supervisor.stop").touch()
                    stop = time.monotonic() + 12
                    while status.exists() and time.monotonic() < stop:
                        time.sleep(.05)
                    assert not status.exists(), "fixture Supervisor did not stop"
    print("PASS: clean language, Provider creation, CLI discovery, SSH profile, natural-language task, DAG, Agent, QA and Git approval")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path)
    run(parser.parse_args().screenshots)
