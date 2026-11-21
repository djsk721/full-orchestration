"""First-run setup through the existing project, Provider and pinned SSH services."""
import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from .core import atomic_json, require
from .runtime import RuntimeClient
from .supervisor import read_config
from .workspace import inspect_project, put_project, read_workspace, scan_clis
from .workspace_forms import Form


def select_startup_language(window, root):
    """Ask on a clean profile before building localized workspace widgets."""
    if os.environ.get("ORCHESTRA_LANG") in ("ko", "en") or (root / "workspace.json").exists():
        return
    path = root / "ui_prefs.json"
    try:
        prefs = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        prefs = {}
    except (OSError, ValueError):
        return
    if not isinstance(prefs, dict) or prefs.get("locale") in ("ko", "en"):
        return
    window.withdraw()
    chooser = tk.Toplevel(window)
    chooser.title("Model Orchestration")
    chooser.resizable(False, False)
    body = ttk.Frame(chooser, padding=(20, 16))
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="표시 언어 / Display language").pack(anchor="w", pady=(0, 12))
    selection = "ko"

    def pick(locale):
        nonlocal selection
        selection = locale
        chooser.destroy()

    actions = ttk.Frame(body)
    actions.pack(anchor="w", fill="x")
    default = ttk.Button(actions, text="한국어", command=lambda: pick("ko"))
    default.pack(side="left", padx=(0, 6))
    ttk.Button(actions, text="English", command=lambda: pick("en")).pack(side="left")
    chooser.protocol("WM_DELETE_WINDOW", lambda: pick("ko"))
    chooser.bind("<Escape>", lambda _: pick("ko"))
    chooser.update_idletasks()
    x = max(0, (chooser.winfo_screenwidth() - chooser.winfo_reqwidth()) // 2)
    y = max(0, (chooser.winfo_screenheight() - chooser.winfo_reqheight()) // 2)
    chooser.geometry(f"+{x}+{y}")
    default.focus_set()
    window.wait_window(chooser)
    try:
        atomic_json(path, prefs | {"locale": selection})
    except OSError:
        return selection
    return selection


class WorkspaceOnboarding:
    def open_workspace_setup(self):
        current = getattr(self, "workspace_setup", None)
        if current and current.winfo_exists():
            current.lift()
            current.focus_set()
            return
        w = self.w
        form = self.workspace_setup = Form(self, w("작업 공간 시작"), w("프로젝트를 추가하고 첫 터미널을 여세요. SSH와 모델 설정은 선택 사항입니다."))
        form.field("folder", w("프로젝트 폴더"))
        form.fields["folder"][1].state(["readonly"])
        folder_actions = ttk.Frame(form.body)
        folder_actions.grid(row=form.row, column=0, columnspan=2, sticky="ew")
        form.row += 1
        self.button(folder_actions, w("폴더 선택"), lambda: choose_folder(), True)
        folder_note = form.note(w("Git 저장소 안의 폴더를 선택하세요."))
        form.field("branch", w("대상 브랜치"), choices=[])
        form.note(w("설치된 CLI와 이미 등록된 모델을 찾습니다."))
        cli_picker = form.field("cli", w("첫 터미널"), choices=[])
        model_picker = form.field("model", w("기본 모델"), choices=[])
        inventory_note = form.note("")
        model_actions = ttk.Frame(form.body)
        model_actions.grid(row=form.row, column=0, columnspan=2, sticky="ew")
        form.row += 1
        self.button(model_actions, w("다시 검색"), lambda: scan())
        self.button(model_actions, w("Provider 설정"), lambda: self.provider_wizard(on_saved=scan))
        self.button(model_actions, w("로컬 연결 테스트"), lambda: self.action(test_local))
        local_note = form.note(w("연결 테스트는 모델 응답을 생성하지 않습니다."))
        host_picker = form.field("host", w("SSH 호스트 (선택)"), choices=[])
        connection_note = form.note(w("원격 연결은 선택 사항입니다."))
        selected = {}
        inventory = {}
        models = {w("자동"): ""}
        hosts = {}
        scan_generation = 0
        folder_generation = 0

        def choose_folder():
            chosen = filedialog.askdirectory(parent=form, title=w("로컬 Git 저장소 선택"))
            if chosen:
                detect_folder(Path(chosen))

        def detect_folder(path):
            nonlocal folder_generation
            folder_generation += 1
            generation = folder_generation
            selected.clear()
            form.set("folder", str(path))
            form.set("branch", "", [])
            folder_note.configure(text=w("Git 저장소 확인 중…"))
            update_launch()

            def detect():
                try:
                    return inspect_project(path), None
                except (ValueError, OSError, RuntimeError) as error:
                    return None, error

            def done(result):
                if not form.winfo_exists() or generation != folder_generation:
                    return
                info, error = result
                if error:
                    folder_note.configure(text=self.workspace_error(error))
                    return
                selected.update(info)
                form.set("folder", info["path"])
                form.set("branch", info["branch"], info["branches"])
                folder_note.configure(text=w("Git 저장소 확인 완료. 대상 브랜치를 확인하세요."))
                update_launch()

            self.background(detect, done)

        def scan():
            nonlocal scan_generation
            scan_generation += 1
            generation = scan_generation
            inventory_note.configure(text=w("설치와 모델 설정 확인 중…"))

            def discover():
                return scan_clis(), read_config(self.root)["models"]

            def done(result):
                if not form.winfo_exists() or scan_generation != generation:
                    return
                clis, configured = result
                inventory.clear()
                inventory.update((name, path) for name, path in clis.items() if path and name != "llama.cpp")
                choices = [*inventory, w("로컬 셸")]
                current_cli, current_model = form.get("cli"), models.get(form.get("model"))
                models.clear()
                models.update({w("자동"): ""})
                models.update({f"{key} · {data['provider']} / {data['model']}": key for key, data in configured.items()})
                default = current_model if current_model is not None else read_workspace(self.root).get("default_model")
                form.set("cli", current_cli if current_cli in choices else choices[0], choices)
                form.set("model", next((label for label, key in models.items() if key == default), w("자동")), list(models))
                inventory_note.configure(text=w("설치된 CLI {0}개 · 등록된 모델 {1}개", len(inventory), len(configured)))
                update_launch()

            self.background(discover, done)

        def update_hosts(preferred=None):
            if not form.winfo_exists():
                return
            current = preferred or hosts.get(form.get("host"))
            hosts.clear()
            hosts[w("SSH 사용 안 함")] = None
            hosts.update({f'{profile["name"]} · {key[:6]}': key
                          for key, profile in read_workspace(self.root)["hosts"].items()})
            form.set("host", next((label for label, key in hosts.items() if key == current), w("SSH 사용 안 함")), list(hosts))

        def test_ssh():
            host_label = form.get("host")
            host = hosts.get(host_label)
            require(host, w("SSH 호스트를 선택하세요."))
            connection_note.configure(text=w("SSH 연결을 확인하는 중…"))

            def show(result):
                if form.winfo_exists() and form.get("host") == host_label:
                    connection_note.configure(text=self.worker_connection_summary(result))

            self.test_saved_host(host, on_result=show)

        def test_local():
            model_label = form.get("model")
            config = read_config(self.root)
            model = config["models"].get(models.get(model_label), {})
            settings = config["runtimes"].get(model.get("runtime"))
            if not settings:
                name = form.get("cli")
                require(name in inventory or name == w("로컬 셸"), w("설치된 CLI를 선택하거나 로컬 셸을 여세요."))
                local_note.configure(text=w("로컬 실행 경로를 확인했습니다. CLI 로그인과 추론은 확인하지 않았습니다."))
                return
            local_note.configure(text=w("로컬 Provider 모델 목록 확인 중…"))

            def check():
                try:
                    result = RuntimeClient(settings).request("/v1/models", timeout=8)
                    require(isinstance(result, dict) and isinstance(result.get("data"), list), "Runtime에서 모델 목록을 확인할 수 없습니다.")
                    advertised = any(isinstance(item, dict) and item.get("id") == model["model"] for item in result["data"])
                    return w("Provider 응답 확인 · 선택 모델을 찾았습니다." if advertised else "Provider 응답 확인 · 선택 모델은 목록에 없습니다.")
                except (ValueError, OSError, RuntimeError) as error:
                    return self.workspace_error(error)

            def show(result):
                if form.winfo_exists() and form.get("model") == model_label:
                    local_note.configure(text=result)

            self.background(check, show)

        def trust_host():
            host = hosts.get(form.get("host"))
            require(host, w("SSH 호스트를 선택하세요."))
            self.host_trust(host, on_trusted=lambda: connection_note.configure(
                text=w("지문을 저장했습니다. 연결 테스트를 실행하세요.")) if form.winfo_exists() else None)

        def update_launch(*_):
            launch.state(["!disabled" if selected and form.get("branch") in selected["branches"] and form.get("cli") else "disabled"])

        def finish():
            require(selected and form.get("branch") in selected["branches"], w("Git 브랜치를 선택하세요."))
            existing = next(((key, project) for key, project in self.project_rows().items()
                             if not project.get("host") and project["path"] == selected["path"]), (None, {}))
            key, project = existing
            profile = {"name": Path(selected["path"]).name, **project, **selected,
                       "branch": form.get("branch"), "model": models[form.get("model")]}
            key = put_project(self.root, profile, key)
            defaults = self.workspace_prefs.get("models")
            if isinstance(defaults, dict):
                defaults.pop(key, None)
            name = form.get("cli")
            self.select_workspace_project(key)
            if name == w("로컬 셸"):
                self.local_project_shell()
            else:
                self.workspace_open_ai(name)
            form.destroy()

        ssh_actions = ttk.Frame(form.body)
        ssh_actions.grid(row=form.row, column=0, columnspan=2, sticky="ew")
        form.row += 1
        self.button(ssh_actions, w("SSH 호스트 추가"), lambda: self.host_dialog(on_saved=update_hosts))
        self.button(ssh_actions, w("신뢰 지문"), lambda: self.action(trust_host))
        self.button(ssh_actions, w("SSH 연결 테스트"), lambda: self.action(test_ssh))
        launch = form.controls(w("프로젝트 저장 및 터미널 열기"), finish)
        form.fields["branch"][1].bind("<<ComboboxSelected>>", update_launch)
        cli_picker.bind("<<ComboboxSelected>>", update_launch)
        model_picker.bind("<<ComboboxSelected>>", lambda _: local_note.configure(
            text=w("연결 테스트는 모델 응답을 생성하지 않습니다.")))
        host_picker.bind("<<ComboboxSelected>>", lambda _: connection_note.configure(
            text=w("원격 연결은 선택 사항입니다.")))
        update_hosts()
        update_launch()
        scan()
