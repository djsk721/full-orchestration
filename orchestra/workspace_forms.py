"""Native structured forms for workspace setup and task review."""
from __future__ import annotations

import json
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import require, settings
from .desktop import formatted
from .supervisor import read_config
from .workspace import (
    RUNTIME_KINDS, STRATEGIES, add_setup_profile, discover_models, draft_plan, format_commands,
    inspect_project, parse_commands, plan_routes, protect_and_save, put_project, read_workspace, registry_revision,
    remove_profile, save_registry, scan_clis,
)


class Form(tk.Toplevel):
    def __init__(self, app, title, description="", width=620):
        super().__init__(app.window)
        self.app, self.width = app, width
        self.title(title)
        self.transient(app.window)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.fields = {}
        self.scroll = tk.Canvas(self, bg="#edf2f7", highlightthickness=0, width=width)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(self, orient="vertical", command=self.scroll.yview)
        self.scroll.configure(yscrollcommand=bar.set)
        bar.grid(row=0, column=1, sticky="ns")
        self.body = ttk.Frame(self.scroll, padding=(18, 12))
        self.body.columnconfigure(1, weight=1)
        self.item = self.scroll.create_window((0, 0), window=self.body, anchor="nw")
        self.scroll.bind("<Configure>", lambda event: self.scroll.itemconfigure(self.item, width=event.width))
        self.body.bind("<Configure>", lambda _: self.scroll.configure(scrollregion=self.scroll.bbox("all")))
        self.footer = ttk.Frame(self, padding=(12, 6))
        self.footer.grid(row=1, column=0, sticky="ew", columnspan=2)
        self.row = 0
        self.scroll.bind("<MouseWheel>", lambda event: self.scroll.yview_scroll(-int(event.delta / 120), "units"))
        if description:
            self.note(description)
        self.bind("<Escape>", lambda _: self.destroy())

    def note(self, text):
        label = ttk.Label(self.body, text=text, wraplength=self.width - 50, justify="left", style="Muted.TLabel")
        label.grid(row=self.row, column=0, columnspan=2, sticky="ew", pady=(5, 8))
        self.row += 1
        return label

    def field(self, key, label, value="", *, choices=None, multiline=False, boolean=False, help_text=""):
        ttk.Label(self.body, text=label).grid(row=self.row, column=0, sticky="nw", pady=6, padx=(0, 12))
        if multiline:
            element = tk.Text(self.body, wrap="word", height=3, width=25, font=(self.app.ui_font, 10), padx=6, pady=5)
            element.insert("1.0", value)
            var = None
        else:
            var = tk.BooleanVar(self, value=value) if boolean else tk.StringVar(self, value=value)
            if boolean:
                element = ttk.Checkbutton(self.body, variable=var)
            elif choices is not None:
                element = ttk.Combobox(self.body, textvariable=var, values=choices, state="readonly")
            else:
                element = ttk.Entry(self.body, textvariable=var)
        element.grid(row=self.row, column=1, sticky="ew", pady=3)
        self.fields[key] = var, element
        self.row += 1
        if help_text:
            self.note(help_text)
        return element

    def get(self, key):
        var, element = self.fields[key]
        return var.get() if var is not None else element.get("1.0", "end-1c")

    def values(self):
        return {key: self.get(key) for key in self.fields}

    def set(self, key, value, choices=None):
        var, element = self.fields[key]
        if choices is not None:
            element.configure(values=choices)
        if var is not None:
            var.set(value)
        else:
            element.delete("1.0", "end")
            element.insert("1.0", value)

    def controls(self, label, command):
        self.app.button(self.footer, label, lambda: self.app.action(command), True)
        self.app.button(self.footer, "닫기", self.destroy, side="right")
        self.update_idletasks()
        self.geometry(f"{self.width + 24}x{min(self.body.winfo_reqheight() + 50, self.winfo_screenheight() - 150, 700)}")
        self.minsize(440, 300)


def one_line(values):
    return ", ".join(values or ()) or "—"


def split_names(text):
    return [item.strip() for item in re.split(r"[,\n]", text) if item.strip()]


class ProjectSettings:
    def project_rows(self):
        return read_workspace(self.root)["projects"]

    def current_project(self):
        project = self.project_rows().get(self.project_id)
        require(project, "프로젝트를 먼저 등록하고 선택하세요.")
        return project

    def refresh_projects(self):
        values = self.project_rows()
        for key in tuple(self.project_tabs):
            if key not in values:
                self.project_book.forget(self.project_tabs.pop(key))
        self.fill(self.project_list, [(key, (item["name"], item["branch"], self.host_name(item.get("host"))))
                                      for key, item in values.items()], self.project_id)
        self.refresh_sidebar()

    def projects_page(self):
        frame = self.base("프로젝트", "저장소와 기본 실행 환경을 등록하고 프로젝트별 작업을 시작합니다.")
        frame.rowconfigure(3, weight=1)
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew")
        self.button(bar, "로컬 저장소 추가", self.add_local_project, True)
        self.button(bar, "원격 저장소 추가", self.add_remote_project)
        self.button(bar, "기본값 편집", lambda: self.action(lambda: self.project_dialog(self.current_project(), self.project_id)))
        self.button(bar, "등록 해제", self.remove_project)
        body = ttk.Panedwindow(frame, orient="horizontal")
        body.grid(row=3, column=0, sticky="nsew", pady=(7, 0))
        left, right = ttk.Frame(body, padding=(0, 0, 10, 0)), ttk.Frame(body)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        body.add(left, weight=1)
        body.add(right, weight=4)
        self.project_list = self.table(left, 0, (("project", "등록된 프로젝트", 160), ("branch", "브랜치", 100),
                                                ("host", "환경", 85)))
        self.project_list.bind("<<TreeviewSelect>>", lambda _: self.open_selected_project())
        self.project_book = ttk.Notebook(right)
        self.project_book.grid(row=0, column=0, sticky="nsew")
        self.project_book.bind("<<NotebookTabChanged>>", self.project_tab_changed)
        self.project_tabs = {}
        empty = ttk.Frame(self.project_book, padding=18)
        ttk.Label(empty, text="저장소를 추가하면 프로젝트 정보와 실행을 여기서 열 수 있습니다.", wraplength=370).pack(anchor="w")
        self.project_book.add(empty, text="시작")
        return frame

    def host_name(self, host):
        return read_workspace(self.root)["hosts"].get(host, {}).get("name", "삭제된 SSH 호스트") if host else "이 PC"

    def open_selected_project(self):
        selected = self.project_list.selection()
        if selected:
            self.open_project(selected[0])

    def open_project(self, key):
        project = self.project_rows().get(key)
        if project is None:
            return
        self.project_id = key
        self.refresh_sidebar()
        if key in self.project_tabs:
            previous = self.project_tabs.pop(key)
            self.project_book.forget(previous)
            previous.destroy()
        panel = ttk.Frame(self.project_book, padding=18)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)
        panel_bar = ttk.Frame(panel)
        panel_bar.grid(row=0, column=0, sticky="ew")
        self.button(panel_bar, "이 프로젝트에서 시작", lambda: self.show("submit"), True)
        self.button(panel_bar, "터미널 열기", lambda: self.project_terminal(project))
        if project.get("host"):
            self.button(panel_bar, "원격 파일", lambda: self.remote_files(project))
        ttk.Label(panel, text=project["name"], style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=(9, 2))
        field = self.text(panel, 2)
        text = "\n".join([
            f'실행 환경  {self.host_name(project.get("host"))}',
            f'저장소      {project["path"]}', f'대상 브랜치  {project["branch"]}',
            f'원격 origin  {project.get("origin") or "—"}', f'언어        {one_line(project.get("stack"))}',
            f'프레임워크   {one_line(project.get("frameworks"))}', f'프로젝트 설정 {one_line(project.get("config_files"))}',
            f'기본 모델    {project.get("model") or "자동 선택"}', f'기본 Harness {project.get("harness") or "자동 선택"}',
            f'검증 명령    {format_commands(project.get("qa", [])) or "직접 추가 가능"}',
            f'탐지된 검증  {format_commands(project.get("qa_hints", [])) or "—"}',
            f'탐지된 빌드  {format_commands(project.get("build_hints", [])) or "—"}',
        ])
        self.write(field, text, True)
        self.project_tabs[key] = panel
        self.project_book.add(panel, text=project["name"][:25])
        self.project_book.select(panel)

    def project_tab_changed(self, _=None):
        active = self.project_book.select()
        match = next((key for key, tab in self.project_tabs.items() if str(tab) == active), None)
        if match:
            self.project_id = match
            self.refresh_sidebar()

    def add_local_project(self):
        folder = filedialog.askdirectory(parent=self.window, title="로컬 Git 저장소 선택")
        if folder:
            self.background(lambda: inspect_project(folder), self.project_dialog)

    def add_remote_project(self):
        hosts = read_workspace(self.root)["hosts"]
        form = Form(self, "원격 저장소 추가", "Worker에 등록된 Git 저장소 목록을 가져옵니다.")
        names = {f'{value["name"]} · {key[:5]}': key for key, value in hosts.items() if value.get("os") == "linux"}
        form.field("host", "호스트", next(iter(names), ""), choices=list(names))
        form.field("repo", "허용 저장소", choices=[])
        notice = form.note("호스트를 선택하고 저장소를 조회하세요.")
        def fetch():
            host = names.get(form.get("host"))
            require(host, "실행 환경에서 Linux SSH 호스트를 등록하세요.")
            client = self.ssh(host)
            label = form.get("host")
            notice.configure(text="Worker 조회 중…")
            def done(result):
                if form.winfo_exists() and form.get("host") == label:
                    paths = result["repos"]
                    form.set("repo", next(iter(paths), ""), paths)
                    notice.configure(text=f"허용 저장소 {len(paths)}개")
            self.background(lambda: client.call("info"), done)
        self.button(form.footer, "호스트 조회", lambda: self.action(fetch))
        def choose():
            host, repo = names.get(form.get("host")), form.get("repo")
            require(host and repo, "원격 저장소를 조회하여 선택하세요.")
            client = self.ssh(host)
            def done(value):
                if form.winfo_exists():
                    form.destroy()
                    self.project_dialog(value | {"host": host})
            self.background(lambda: client.call("project", repo=repo), done)
        form.controls("저장소 선택", choose)

    def project_dialog(self, project, key=None):
        initial = dict(project)
        cfg = read_config(self.root)
        form = Form(self, "프로젝트 기본값" if key else "프로젝트 등록",
                    f'{initial["path"]} · {self.host_name(initial.get("host"))}')
        form.field("name", "표시 이름", initial.get("name") or initial["path"].rstrip("/").replace("\\", "/").split("/")[-1])
        form.field("branch", "대상 브랜치", initial.get("branch") or "", choices=initial.get("branches", []))
        if not initial.get("host"):
            form.field("model", "기본 모델", initial.get("model", ""), choices=["", *cfg["models"]])
            form.field("harness", "기본 Harness", initial.get("harness", ""), choices=["", *cfg["harnesses"]])
        form.field("paths", "기본 변경 범위", ", ".join(initial.get("paths", [])), help_text="상대 파일 또는 디렉터리를 쉼표로 구분합니다.")
        form.field("read_paths", "기본 읽기 범위", ", ".join(initial.get("read_paths", [])))
        form.field("tools", "기본 MCP 도구", ", ".join(initial.get("tools", [])), help_text="등록된 도구의 가상 이름을 쉼표로 구분합니다.")
        form.field("qa", "기본 QA 명령", format_commands(initial.get("qa", []) or initial.get("qa_hints", [])), multiline=True,
                   help_text="실행을 승인할 명령만 한 줄에 하나씩 입력하세요. 셸 연산자는 사용하지 않습니다.")
        def save():
            values = form.values()
            values.update(qa=parse_commands(values["qa"]), paths=split_names(values["paths"]), tools=split_names(values["tools"]),
                          read_paths=split_names(values["read_paths"]))
            self.project_id = put_project(self.root, initial | values, key)
            form.destroy()
            self.show("projects")
            self.open_project(self.project_id)
        form.controls("프로젝트 저장", save)

    def remove_project(self):
        def remove():
            project = self.current_project()
            if messagebox.askyesno("등록 해제", f'{project["name"]}의 프로젝트 등록을 해제하시겠습니까?', parent=self.window):
                remove_profile(self.root, "projects", self.project_id)
                self.project_id = None
                self.refresh_projects()
        self.action(remove)

    def guided_page(self):
        frame = self.base("새 작업", "프로젝트와 전략을 고르고 자연어로 작업을 설명하면, 실행 전에 계획을 검토할 수 있습니다.")
        frame.rowconfigure(3, weight=1)
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew")
        self.button(bar, "계획 만들기", self.guided_dialog, True)
        self.button(bar, "고급 JSON 편집", lambda: self.show("advanced_plan"))
        note = ttk.Frame(frame, padding=30, style="Card.TFrame")
        note.grid(row=3, column=0, sticky="new", pady=12)
        ttk.Label(note, text="작업을 시작하는 세 가지 방법", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 14))
        for name, description in zip(STRATEGIES, ("저장소를 살펴보고 결과를 보고합니다.", "허용 경로 안에서 변경하고 독립 검토와 통합 QA를 거칩니다.",
                                                   "모델 호출 없이 사용자가 승인한 검증 명령을 실행합니다.")):
            ttk.Label(note, text=name, style="CardTitle.TLabel").pack(anchor="w", pady=(6, 0))
            ttk.Label(note, text=description, style="Card.TLabel", wraplength=500).pack(anchor="w", pady=(2, 8))
        return frame

    def guided_dialog(self):
        projects = self.project_rows()
        if not projects:
            self.show("projects")
            self.add_local_project()
            return
        cfg = read_config(self.root)
        indices = {f'{value["name"]} · {key[:5]}': key for key, value in projects.items()}
        selected = next((name for name, key in indices.items() if key == self.project_id), next(iter(indices)))
        form = Form(self, "작업 계획 만들기", "실행 위치는 프로젝트에서 선택합니다. 모델을 비워 두면 서버의 라우팅 정책을 사용합니다.")
        selector = form.field("project", "프로젝트", selected, choices=list(indices))
        form.field("strategy", "실행 전략", STRATEGIES[0], choices=STRATEGIES)
        form.field("intent", "작업 설명", multiline=True, help_text="예시 · 백엔드 구조를 분석하고 개선할 부분을 근거와 함께 알려줘.")
        provider = form.field("provider", "Provider", choices=[])
        model = form.field("model", "모델", choices=[])
        form.field("harness", "Harness", choices=[])
        form.field("background", "앱을 닫아도 계속", False, boolean=True)
        form.field("paths", "변경 범위")
        form.field("tools", "MCP 도구", help_text="여러 도구의 가상 이름은 쉼표로 구분합니다.")
        form.field("qa", "QA 명령", multiline=True, help_text="한 줄에 하나씩 입력하세요. 변경 전략에는 통합 QA가 필요합니다.")
        remote_catalog = {}
        location = form.note("")
        def harness_choices(_=None):
            project = projects[indices[form.get("project")]]
            host = project.get("host")
            catalog = remote_catalog.get(host, {}) if host else cfg
            allowed = list(catalog.get("harnesses", {}))
            selection = catalog.get("models", {}).get(form.get("model"))
            if selection is not None and not host:
                allowed = [key for key in allowed if key in selection.get("harnesses", ["managed"])]
            current = form.get("harness")
            form.set("harness", current if current in allowed else "", ["", *allowed])

        def model_choices(_=None):
            project = projects[indices[form.get("project")]]
            catalog = remote_catalog.get(project.get("host"), {}) if project.get("host") else cfg
            available = catalog.get("models", {})
            allowed = [""] + [key for key, value in available.items()
                              if not form.get("provider") or value.get("provider") == form.get("provider")]
            selected_model = form.get("model") or project.get("model") or read_workspace(self.root).get("default_model")
            form.set("model", selected_model if selected_model in allowed else "", allowed)
            harness_choices()
        def set_catalog(project_label, catalog):
            if not form.winfo_exists() or form.get("project") != project_label:
                return
            ids = sorted({value["provider"] for value in catalog.get("models", {}).values()})
            form.set("provider", "", ["", *ids])
            project = projects[indices[project_label]]
            harness = project.get("harness", "")
            form.set("harness", harness if harness in catalog.get("harnesses", {}) else "", ["", *catalog.get("harnesses", {})])
            model_choices()
        def changed(_=None):
            label = form.get("project")
            project = projects[indices[label]]
            form.set("paths", ", ".join(project.get("paths", [])))
            form.set("tools", ", ".join(project.get("tools", [])))
            form.set("qa", format_commands(project.get("qa", [])))
            location.configure(text=f'실행 위치 · {self.host_name(project.get("host"))}')
            if not project.get("host"):
                set_catalog(label, cfg)
                return
            host = project["host"]
            set_catalog(label, remote_catalog.get(host, {}))
            def receive(result):
                remote_catalog[host] = result
                set_catalog(label, result)
            self.action(lambda: self.background(lambda: self.ssh(host).call("info"), receive))
        selector.bind("<<ComboboxSelected>>", changed)
        provider.bind("<<ComboboxSelected>>", model_choices)
        model.bind("<<ComboboxSelected>>", harness_choices)
        changed()
        def build():
            self.project_id = indices[form.get("project")]
            project = projects[self.project_id]
            plan = draft_plan(project, form.get("intent"), form.get("strategy"), model=form.get("model"),
                              harness=form.get("harness"), paths=split_names(form.get("paths")),
                              qa=parse_commands(form.get("qa")), tools=split_names(form.get("tools")),
                              background=form.get("background"))
            form.destroy()
            self.review_plan(plan, self.project_id, project.get("host"))
        form.controls("검토할 계획 생성", build)

    def review_plan(self, plan, project_id, host=None):
        form = Form(self, "실행 계획 검토", f'실행 위치 · {self.host_name(host)}   브랜치 · {plan["target"]}', width=680)
        form.field("title", "작업 제목", plan["title"])
        form.field("qa", "통합 QA", format_commands(plan.get("qa", [])), multiline=True)
        nodes = [dict(task) for task in plan["tasks"]]
        listing = tk.Listbox(form.body, height=7, font=(self.ui_font, 10))
        listing.grid(row=form.row, column=0, columnspan=2, sticky="ew", pady=8)
        form.row += 1
        actions = ttk.Frame(form.body)
        actions.grid(row=form.row, column=0, columnspan=2, sticky="ew")
        form.row += 1
        notice = form.note("계획의 노드와 의존성, 파일 범위, 검증 명령을 확인하세요.")

        def rebuild():
            listing.delete(0, "end")
            for task in nodes:
                listing.insert("end", f'{task["id"]} · {task["role"]} · {task.get("model") or "자동"} · '
                               f'{task.get("harness") or "자동"} · 선행 {one_line(task.get("depends"))} · '
                               f'변경 {one_line(task.get("paths"))}')
        rebuild()
        def edit(index):
            raw = nodes[index] if index is not None else {}
            child = Form(self, "실행 노드", "Agent 역할, 선행 노드 및 작업 권한을 편집합니다.", width=590)
            for key, label, value in (("id", "노드 ID", raw.get("id", "")), ("model", "모델 ID", raw.get("model", "")),
                                       ("harness", "Harness ID", raw.get("harness", "")), ("depends", "선행 노드", one_line(raw.get("depends"))),
                                       ("paths", "허용 쓰기 경로", one_line(raw.get("paths"))), ("tools", "허용 MCP 도구", one_line(raw.get("tools"))),
                                       ("read_paths", "읽기 경로", one_line(raw.get("read_paths"))),
                                       ("context", "최소 Context", str(raw.get("min_context", 1024)))):
                child.field(key, label, value if value != "—" else "")
            child.field("role", "역할", raw.get("role", "explorer"),
                        choices=("planner", "developer", "explorer", "reviewer", "qa", "diagnostic"))
            child.field("prompt", "작업", raw.get("prompt", ""), multiline=True)
            child.field("acceptance", "완료 조건", raw.get("acceptance", ""), multiline=True)
            child.field("qa", "노드 QA", format_commands(raw.get("qa", [])), multiline=True)
            def apply():
                updated = raw | {key: child.get(key) for key in ("id", "role", "prompt", "acceptance")}
                for key in ("depends", "paths", "tools"):
                    updated[key] = split_names(child.get(key))
                updated["qa"] = parse_commands(child.get("qa"))
                updated["min_context"] = int(child.get("context"))
                for key in ("model", "harness", "read_paths"):
                    if child.get(key):
                        updated[key] = split_names(child.get(key)) if key == "read_paths" else child.get(key)
                    else:
                        updated.pop(key, None)
                if index is None:
                    nodes.append(updated)
                else:
                    nodes[index] = updated
                rebuild()
                child.destroy()
            child.controls("노드 적용", apply)
        def edit_selected():
            require(listing.curselection(), "수정할 노드를 선택하세요.")
            edit(listing.curselection()[0])
        def delete():
            require(listing.curselection(), "제거할 노드를 선택하세요.")
            del nodes[listing.curselection()[0]]
            rebuild()
        self.button(actions, "노드 추가", lambda: edit(None))
        self.button(actions, "노드 편집", lambda: self.action(edit_selected))
        self.button(actions, "노드 제거", lambda: self.action(delete))
        def confirmed(value, candidates):
            if not form.winfo_exists():
                return
            resolved = "\n".join(f"{key} · {choices[0] if choices else '검증 명령만'}" for key, choices in candidates.items())
            confirm = messagebox.askyesno("계획 제출 승인",
                f'실행 경로 후보\n{resolved}\n\n이 계획의 검증 명령과 작업 실행을 승인하시겠습니까?', parent=form)
            if not confirm:
                return
            if host:
                self.submit_remote_run(host, value)
            else:
                self.accept_local_plan(value)
            form.destroy()
        def submit():
            value = plan | {"title": form.get("title"), "qa": parse_commands(form.get("qa")), "tasks": nodes}
            if host:
                form_snapshot = json.loads(json.dumps(value))
                notice.configure(text="원격 Worker에서 계획을 검증하는 중…")
                self.background(lambda: self.ssh(host).call("validate", plan=form_snapshot),
                                lambda routes: confirmed(form_snapshot, routes))
            else:
                confirmed(value, plan_routes(value, read_config(self.root)))
        form.controls("검증 후 실행", submit)

    def settings_page(self):
        frame = self.base("설정", "Provider와 모델을 안내에 따라 등록하고, 실행 정책과 저장 위치를 관리합니다.")
        frame.rowconfigure(3, weight=1)
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew")
        self.button(bar, "Provider 설정 마법사", self.provider_wizard, True)
        self.button(bar, "모델·Runtime 편집", lambda: self.action(self.edit_model))
        self.button(bar, "실행·알림 정책", self.policy_dialog)
        self.button(bar, "고급 JSON", lambda: self.show("registry"))
        self.button(bar, "설정 내보내기", self.export_settings)
        self.settings_list = self.table(frame, 3, (("profile", "모델 프로필", 170), ("provider", "Provider", 100),
                                                   ("model", "모델 ID", 200), ("route", "실행 경로", 200)))
        ttk.Label(frame, text=f"설정·보고서·백업 위치   {self.root}", style="Muted.TLabel").grid(row=4, column=0, sticky="w", pady=6)
        return frame

    def refresh_settings(self):
        cfg = read_config(self.root)
        self.fill(self.settings_list, [(key, (key, model["provider"], model["model"],
                      one_line(model.get("harnesses", ["managed"])))) for key, model in cfg["models"].items()])

    def registry_page(self):
        frame = self.base("고급 레지스트리", "선택적으로 JSON 설정을 직접 가져오거나 편집합니다.")
        frame.rowconfigure(3, weight=1)
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=2, column=0, sticky="ew")
        self.button(toolbar, "설정 저장", self.save_registry, True)
        self.button(toolbar, "저장된 설정 열기", lambda: self.action(self.reload_registry))
        self.button(toolbar, "JSON 가져오기", lambda: self.import_file(self.registry))
        self.button(toolbar, "설정으로", lambda: self.show("settings"), side="right")
        self.registry = self.text(frame, 3)
        return frame

    def reload_registry(self):
        revision = registry_revision(self.root)
        path = self.root / "registry.json"
        source = path.read_text(encoding="utf-8-sig") if path.is_file() else formatted(read_config(self.root))
        self.write(self.registry, source)
        self.registry_revision = revision

    def edit_model(self):
        selected = self.settings_list.selection()
        require(selected, "편집할 모델 프로필을 선택하세요.")
        config, revision = read_config(self.root), registry_revision(self.root)
        key = selected[0]
        model = config["models"][key]
        runtime = config["runtimes"].get(model.get("runtime"))
        form = Form(self, "모델과 실행 설정", f'{key} · {model["provider"]}')
        form.field("model", "실제 모델 ID", model["model"])
        form.field("roles", "허용 역할", ", ".join(model.get("roles", ["planner", "developer", "explorer", "reviewer", "qa", "diagnostic"])))
        form.field("harnesses", "허용 Harness ID", ", ".join(model.get("harnesses", ["managed"])))
        for name, label in (("token_budget", "토큰 예산 (0은 제한 없음)"), ("quality", "품질 점수"),
                            ("tool_score", "도구 점수"), ("reliability", "신뢰도 점수"), ("cost", "비용 점수")):
            form.field(name, label, model.get(name, 0))
        if runtime is not None:
            for name, label, default in (("url", "Runtime 주소", "http://127.0.0.1:8080"),
                                         ("auth_env", "자격 증명 환경 변수", ""), ("context", "Context 한도", 32768),
                                         ("max_output", "최대 출력", 2048), ("slots", "동시 슬롯", 1),
                                         ("ram_mb", "RAM 예약(MB)", 0)):
                form.field(name, label, runtime.get(name, default))
        def save():
            for name in ("token_budget", "quality", "tool_score", "reliability", "cost"):
                model[name] = int(form.get(name))
            model.update(model=form.get("model"), roles=split_names(form.get("roles")), harnesses=split_names(form.get("harnesses")))
            if runtime is not None:
                from .runtime import checked_url
                checked_url(form.get("url"), local_only=True)
                runtime["url"] = form.get("url")
                for name in ("context", "max_output", "slots", "ram_mb"):
                    runtime[name] = int(form.get(name))
                reference = form.get("auth_env")
                require(not reference or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", reference), "환경 변수 이름을 입력하세요.")
                if reference:
                    runtime["auth_env"] = reference
                else:
                    runtime.pop("auth_env", None)
            save_registry(self.root, config, revision)
            self.refresh_settings()
            form.destroy()
        form.controls("변경 저장", save)

    def export_settings(self):
        name = filedialog.asksaveasfilename(defaultextension=".json", parent=self.window, initialfile="registry.json")
        if name:
            from .core import atomic_json
            self.action(lambda: atomic_json(Path(name), read_config(self.root)))

    def save_registry(self):
        def save():
            config = save_registry(self.root, json.loads(self.registry.get("1.0", "end-1c")), self.registry_revision)
            self.registry_revision = registry_revision(self.root)
            self.write(self.registry, formatted(config))
            self.notifications = settings(config)["notifications"]
            self.restart_supervisor()
            messagebox.showinfo("설정 저장", "레지스트리를 저장했습니다. 이전 설정은 backups 폴더에 보관합니다.", parent=self.window)
        self.action(save)

    def policy_dialog(self):
        config = read_config(self.root)
        revision = registry_revision(self.root)
        cfg = settings(config)
        form = Form(self, "실행과 알림 정책", "새 작업에는 저장 시점의 실행 정책을 적용합니다.")
        labels = {"background": "앱을 닫아도 실행", "allow_background_write": "백그라운드 Worktree 쓰기",
                  "notifications": "앱 내 상태 알림", "parallel_jobs": "동시 작업 수", "parallel_tasks": "동시 노드 수",
                  "attempts": "최대 실행 시도", "job_timeout_sec": "작업 제한 시간(초)",
                  "heartbeat_sec": "하트비트(초)", "lease_sec": "리스 만료(초)"}
        for key, label in labels.items():
            form.field(key, label, cfg[key], boolean=type(cfg[key]) is bool)
        def save():
            for key, value in form.values().items():
                config["settings"][key] = value if type(value) is bool else int(value)
            save_registry(self.root, config, revision)
            self.notifications = config["settings"]["notifications"]
            self.restart_supervisor()
            form.destroy()
        form.controls("정책 저장", save)

    def provider_wizard(self):
        from .discovery import discover
        form = Form(self, "Provider 설정 마법사", "설치 탐색 → 연결 확인 → 모델 선택 → 등록")
        choices = [*RUNTIME_KINDS, "OpenCode", "Codex", "OpenAI", "Google Gemini", "Anthropic",
                   "Antigravity", "Claude Code", "Gemini CLI", "Custom"]
        provider = form.field("kind", "연결 방식", "Ollama", choices=choices)
        form.field("id", "프로필 ID", "my-model", help_text="프로필을 작업 및 프로젝트에서 찾을 때 쓰는 고유 이름입니다.")
        form.field("endpoint", "로컬 Runtime 주소", "http://127.0.0.1:11434")
        form.field("auth_env", "자격 증명 환경 변수", help_text="비밀값 대신 환경 변수 이름을 사용합니다.")
        form.field("executable", "CLI 실행 파일")
        model_list = form.field("found", "관측된 모델", choices=[])
        form.field("model", "모델 ID")
        form.field("context", "설정 Context", "32768", help_text="관측 가능할 때만 감지된 한도를 채웁니다. 실행 시 실제 한도를 다시 검사합니다.")
        form.field("trusted", "선택한 CLI 실행을 허용", False, boolean=True)
        form.field("default", "기본 모델로 사용", True, boolean=True)
        details = form.note("연결을 확인하면 설치 또는 응답에서 확인한 정보가 표시됩니다.")
        form.note("Runtime, OpenCode, Codex는 실행 프로필로 등록할 수 있습니다. 나머지 연결 방식은 설치 탐색을 제공합니다.")
        observed = {}
        def select_model(_=None):
            key = form.get("found")
            if key:
                form.set("model", key)
                context = observed.get(key)
                if context:
                    form.set("context", str(context))
        model_list.bind("<<ComboboxSelected>>", select_model)
        def kind_changed(_=None):
            kind = form.get("kind")
            if kind in RUNTIME_KINDS:
                form.set("endpoint", "http://127.0.0.1:11434" if kind == "Ollama" else "http://127.0.0.1:8080")
            form.set("found", "", [])
            details.configure(text="설치 경로와 Runtime 모델 목록을 선택적으로 확인할 수 있습니다.")
        provider.bind("<<ComboboxSelected>>", kind_changed)
        def probe():
            values = form.values()
            kind = values["kind"]
            details.configure(text="연결을 확인하는 중…")
            def check():
                if kind in RUNTIME_KINDS:
                    return discover_models(kind, values["endpoint"], values["auth_env"])
                found = scan_clis().get(kind)
                from .processes import run, env_for_process
                if kind in ("OpenCode", "Codex") and values["trusted"] and (values["executable"] or found):
                    found = values["executable"] or found
                    code, _ = run([found, "--version"], env=env_for_process(), timeout=8)
                    return {"path": found, "cli_ok": code == 0}
                return {"path": found}
            def done(result):
                if not form.winfo_exists() or form.get("kind") != kind:
                    return
                if "models" in result:
                    observed.clear()
                    observed.update((item["id"], item["context"]) for item in result["models"])
                    form.set("found", next(iter(observed), ""), list(observed))
                    select_model()
                    details.configure(text=f'목록 응답 {result["ms"]} ms · 모델 {len(observed)}개. 도구·비전·추론 지원은 목록에서 검증되지 않았습니다.')
                else:
                    if result["path"]:
                        form.set("executable", result["path"])
                    status = ("버전 명령 성공" if result.get("cli_ok") else
                              "버전 확인 실패" if "cli_ok" in result else "설치 탐색 완료")
                    unsupported = " · 실행 어댑터 미지원" if kind not in ("OpenCode", "Codex") else ""
                    details.configure(text=f'{status} · {result["path"] or "경로 미탐지"} · 로그인 및 모델 가용성 미검증{unsupported}')
            self.background(check, done)
        def scan():
            def done(records):
                if form.winfo_exists():
                    paths, servers = records
                    details.configure(text=" · ".join(f"{key}: {'탐지됨' if path else '미탐지'}" for key, path in paths.items())
                                      + f"\n기존 MCP 설정 {servers}개 탐지")
            self.background(lambda: (scan_clis(), len(discover()[0])), done)
        self.button(form.footer, "설치 탐색", scan)
        self.button(form.footer, "연결 확인", lambda: self.action(probe))
        def save():
            values = form.values()
            revision = registry_revision(self.root)
            cfg = add_setup_profile(read_config(self.root), values)
            save_registry(self.root, cfg, revision)
            if values["default"]:
                ws = read_workspace(self.root)
                ws["default_model"] = values["id"]
                protect_and_save(self.root, "workspace.json", ws)
            form.destroy()
            self.refresh_settings()
        form.controls("프로필 저장", save)
