"""Structured workspace forms, Project workspace, 6-step Task Wizard, Providers & History."""
from __future__ import annotations

import json
import re
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import atomic_json, require, settings
from .desktop import changed_files, formatted
from .platform.desktop import open_directory
from .processes import env_for_process, run as run_process
from .supervisor import read_config
from .ui import (
    Card,
    CollapsibleSection,
    EmptyState,
    StatusBadge,
    state_label,
    status_tone,
    style_listbox_widget,
    style_text_widget,
    t,
)
from .workspace import (
    RUNTIME_KINDS,
    STRATEGIES,
    add_setup_profile,
    discover_models,
    draft_plan,
    format_commands,
    inspect_project,
    parse_commands,
    plan_routes,
    protect_and_save,
    put_project,
    read_workspace,
    registry_revision,
    remove_profile,
    save_registry,
    scan_clis,
)


class Form(tk.Toplevel):
    def __init__(self, app, title, description="", width=640):
        super().__init__(app.window)
        self.app, self.width = app, width
        self.palette = app.palette
        self.title(title)
        self.transient(app.window)
        self.configure(bg=self.palette["canvas"])
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.fields = {}
        self.field_rows = {}
        self.scroll = tk.Canvas(self, bg=self.palette["canvas"], highlightthickness=0, width=width)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(self, orient="vertical", command=self.scroll.yview)
        self.scroll.configure(yscrollcommand=bar.set)
        bar.grid(row=0, column=1, sticky="ns")
        self.body = ttk.Frame(self.scroll, padding=(18, 14))
        self.body.columnconfigure(1, weight=1)
        self.item = self.scroll.create_window((0, 0), window=self.body, anchor="nw")
        self.scroll.bind("<Configure>", lambda event: self.scroll.itemconfigure(self.item, width=event.width))
        self.body.bind("<Configure>", lambda _: self.scroll.configure(scrollregion=self.scroll.bbox("all")))
        self.footer = ttk.Frame(self, padding=(14, 8))
        self.footer.grid(row=1, column=0, sticky="ew", columnspan=2)
        self.row = 0
        self.scroll.bind("<MouseWheel>", lambda event: self.scroll.yview_scroll(-int(event.delta / 120), "units"))
        if description:
            self.note(description)
        self.bind("<Escape>", lambda _: self.destroy())

    def note(self, text):
        label = ttk.Label(self.body, text=text, wraplength=self.width - 54, justify="left", style="Muted.TLabel")
        label.grid(row=self.row, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        self.row += 1
        return label

    def field(self, key, label, value="", *, choices=None, multiline=False, boolean=False, help_text=""):
        row_idx = self.row
        lbl = ttk.Label(self.body, text=label)
        lbl.grid(row=row_idx, column=0, sticky="nw", pady=6, padx=(0, 12))
        if multiline:
            element = tk.Text(self.body, wrap="word", height=3, width=25, padx=8, pady=6)
            style_text_widget(element, self.palette, self.app.ui_font, 10)
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
        element.grid(row=row_idx, column=1, sticky="ew", pady=4)
        self.fields[key] = var, element
        self.row += 1
        help_lbl = self.note(help_text) if help_text else None
        self.field_rows[key] = (lbl, element, help_lbl)
        return element

    def set_visible(self, key: str, visible: bool):
        lbl, element, help_lbl = self.field_rows[key]
        for w in (lbl, element, help_lbl):
            if w is None:
                continue
            if visible:
                w.grid()
            else:
                w.grid_remove()

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
        self.geometry(f"{self.width + 26}x{min(self.body.winfo_reqheight() + 68, self.winfo_screenheight() - 140, 720)}")
        self.minsize(460, 320)


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
        query = self.project_search.get().strip().casefold() if hasattr(self, "project_search") else ""
        filtered = []
        for key, item in values.items():
            host = self.host_name(item.get("host"))
            if not query or query in item["name"].casefold() or query in item["branch"].casefold() or query in item["path"].casefold():
                filtered.append((key, (item["name"], item["branch"], host)))
        self.fill(self.project_list, filtered, self.project_id)
        self.refresh_sidebar()

    def projects_page(self):
        frame = self.base(t("projects.title", self.locale), t("projects.desc", self.locale))
        frame.rowconfigure(3, weight=1)
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 4))
        self.button(bar, "로컬 저장소 추가", self.add_local_project, True)
        self.button(bar, "원격 저장소 추가", self.add_remote_project)
        self.button(bar, "기본값 편집", lambda: self.action(lambda: self.project_dialog(self.current_project(), self.project_id)))
        self.button(bar, "등록 해제", self.remove_project)
        self.project_search = tk.StringVar(self.window)
        self.project_search.trace_add("write", lambda *_: self.refresh_projects())
        ttk.Entry(bar, textvariable=self.project_search, width=22).pack(side="right", padx=(4, 0), pady=3)
        ttk.Label(bar, text="검색", style="Muted.TLabel").pack(side="right", padx=(8, 4))

        body = ttk.Panedwindow(frame, orient="horizontal")
        body.grid(row=3, column=0, sticky="nsew", pady=(6, 4))
        left, right = ttk.Frame(body, padding=(0, 0, 10, 0)), ttk.Frame(body)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        body.add(left, weight=2)
        body.add(right, weight=5)
        self.project_list = self.table(left, 0, (("project", "프로젝트", 150), ("branch", "브랜치", 90), ("host", "환경", 80)))
        self.project_list.bind("<<TreeviewSelect>>", lambda _: self.open_selected_project())
        self.project_book = ttk.Notebook(right)
        self.project_book.grid(row=0, column=0, sticky="nsew")
        self.project_book.bind("<<NotebookTabChanged>>", self.project_tab_changed)
        self.project_tabs = {}
        empty = ttk.Frame(self.project_book, padding=18)
        empty.columnconfigure(0, weight=1)
        card = EmptyState(
            empty,
            self.palette,
            "등록된 프로젝트가 선택되지 않았습니다",
            "왼쪽에서 프로젝트를 선택하거나 새 로컬/원격 Git 저장소를 추가하면 기본 실행 환경, Git 상태 및 최근 실행을 확인할 수 있습니다.",
            self.ui_font,
            actions=(("첫 로컬 저장소 열기", self.add_local_project, True),),
        )
        card.grid(row=0, column=0, sticky="ew")
        self._themed_cards.append(card)
        self.project_book.add(empty, text="시작 안내")
        ttk.Label(frame, text=t("projects.remove_hint", self.locale), style="Muted.TLabel").grid(row=4, column=0, sticky="w")
        return frame

    def host_name(self, host):
        return read_workspace(self.root)["hosts"].get(host, {}).get("name", "삭제된 SSH 호스트") if host else "이 PC"

    def open_selected_project(self):
        selected = self.project_list.selection()
        if selected:
            self.open_project(selected[0])

    def _local_git_status(self, repo_path: str) -> str:
        path = Path(repo_path)
        if not path.is_dir():
            return "저장소 디렉터리를 찾을 수 없습니다."
        code1, status_out = run_process(
            ["git", "-c", "core.fsmonitor=false", "-C", str(path), "status", "-sb"],
            env=env_for_process(), timeout=6, limit=120000,
        )
        code2, log_out = run_process(
            ["git", "-c", "core.fsmonitor=false", "-C", str(path), "log", "--oneline", "-n", "6"],
            env=env_for_process(), timeout=6, limit=120000,
        )
        lines = []
        if code1 == 0:
            lines.append("[작업 트리 상태]")
            lines.append(status_out.decode("utf-8", errors="replace").strip() or "clean")
        else:
            lines.append("Git 상태를 조회할 수 없습니다.")
        if code2 == 0 and log_out:
            lines.append("")
            lines.append("[최근 커밋]")
            lines.append(log_out.decode("utf-8", errors="replace").strip())
        return "\n".join(lines)

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

        p = self.palette
        panel = ttk.Frame(self.project_book, padding=14)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)

        header = Card(panel, p, padding=(14, 10))
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._themed_cards.append(header)
        top = tk.Frame(header.body, bg=p["panel"])
        top.pack(fill="x")
        StatusBadge(top, p, text=self.host_name(project.get("host")), tone="running" if project.get("host") else "success", ui_font=self.ui_font).pack(side="right", padx=(10, 0))
        tk.Label(
            top, text=project["name"], bg=p["panel"], fg=p["text"],
            font=(self.ui_font, 12, "bold"), wraplength=480, justify="left", anchor="w",
        ).pack(side="left", fill="x", expand=True)
        tk.Label(
            header.body,
            text=f'{project["path"]}   ·   브랜치 {project["branch"]}   ·   원격 {project.get("origin") or "—"}',
            bg=p["panel"], fg=p["muted"], font=(self.ui_font, 9), anchor="w",
        ).pack(fill="x", pady=(4, 0))

        panel_bar = ttk.Frame(panel)
        panel_bar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.button(panel_bar, "이 프로젝트에서 작업 만들기", lambda: self.start_project_wizard(key), True)
        self.button(panel_bar, "터미널 열기", lambda: self.project_terminal(project))
        if project.get("host"):
            self.button(panel_bar, "원격 파일", lambda: self.remote_files(project))
        else:
            self.button(panel_bar, "폴더 열기", lambda: self.action(lambda: open_directory(Path(project["path"]))))

        sub_book = ttk.Notebook(panel)
        sub_book.grid(row=2, column=0, sticky="nsew")

        # Sub-tab 1: Overview & Defaults
        ov_tab = ttk.Frame(sub_book, padding=10)
        ov_tab.columnconfigure(0, weight=1)
        ov_tab.rowconfigure(0, weight=1)
        field = self.text(ov_tab, 0)
        text = "\n".join([
            f'실행 환경     {self.host_name(project.get("host"))}',
            f'저장소        {project["path"]}',
            f'대상 브랜치   {project["branch"]}',
            f'원격 origin   {project.get("origin") or "—"}',
            f'언어          {one_line(project.get("stack"))}',
            f'프레임워크    {one_line(project.get("frameworks"))}',
            f'프로젝트 설정 {one_line(project.get("config_files"))}',
            f'기본 모델     {project.get("model") or "자동 선택"}',
            f'기본 Harness  {project.get("harness") or "자동 선택"}',
            f'기본 변경 범위 {one_line(project.get("paths"))}',
            f'기본 읽기 범위 {one_line(project.get("read_paths"))}',
            f'검증 명령     {format_commands(project.get("qa", [])) or "직접 추가 가능"}',
            f'탐지된 검증   {format_commands(project.get("qa_hints", [])) or "—"}',
            f'탐지된 빌드   {format_commands(project.get("build_hints", [])) or "—"}',
        ])
        self.write(field, text, True)
        sub_book.add(ov_tab, text="개요 및 기본 설정")

        # Sub-tab 2: Git Status
        git_tab = ttk.Frame(sub_book, padding=10)
        git_tab.columnconfigure(0, weight=1)
        git_tab.rowconfigure(0, weight=1)
        git_box = self.text(git_tab, 0)
        if project.get("host"):
            self.write(git_box, "원격 SSH 프로젝트입니다. 원격 작업 실행 시 서버 Worker가 저장소 및 Worktree 상태를 검증합니다.", True)
        else:
            self.write(git_box, "Git 상태를 불러오는 중…", True)
            self.background(
                lambda rp=project["path"]: self._local_git_status(rp),
                lambda out: self.write(git_box, out, True) if git_box.winfo_exists() else None,
            )
        sub_book.add(git_tab, text="Git 상태")

        # Sub-tab 3: Recent Executions for this project
        runs_tab = ttk.Frame(sub_book, padding=10)
        runs_tab.columnconfigure(0, weight=1)
        runs_tab.rowconfigure(0, weight=1)
        runs_tbl = self.table(runs_tab, 0, (("title", "작업", 240), ("state", "상태", 110), ("updated", "갱신", 135)), height=6)
        matching = [
            (
                row["id"],
                (row["plan"]["title"], state_label(row["state"], self.locale), datetime.fromtimestamp(row["updated"]).strftime("%m-%d %H:%M:%S")),
            )
            for row in self.store.list_jobs()
            if (row.get("plan") or {}).get("repo") == project["path"]
        ]
        self.fill(runs_tbl, matching)
        runs_tbl.bind("<Double-1>", lambda _e, tbl=runs_tbl: self.open_job(tbl.selection()[0]) if tbl.selection() else None)
        sub_book.add(runs_tab, text=f"최근 실행 ({len(matching)})")

        self.project_tabs[key] = panel
        self.project_book.add(panel, text=project["name"][:25])
        self.project_book.select(panel)

    def start_project_wizard(self, key: str):
        self.project_id = key
        self.refresh_sidebar()
        self.show("submit")

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
            if messagebox.askyesno(
                "프로젝트 등록 해제",
                f'{project["name"]}의 프로젝트 등록을 해제하시겠습니까?\n\n실제 저장소 파일({project["path"]})은 삭제되지 않습니다.',
                parent=self.window,
            ):
                remove_profile(self.root, "projects", self.project_id)
                self.project_id = None
                self.refresh_projects()
        self.action(remove)

    # ------------------------------------------------------------------
    # Phase 8: In-place 6-Step Guided Task Creation Wizard (submit page)
    # ------------------------------------------------------------------
    def guided_page(self):
        frame = self.base(t("submit.title", self.locale), t("submit.desc", self.locale))
        frame.rowconfigure(3, weight=1)
        self.wizard_step = 0
        self.wizard_draft = None
        self.wizard_remote_catalog = {}
        self.wizard_project_map = {}

        top_bar = ttk.Frame(frame)
        top_bar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.wizard_step_btns = []
        step_keys = ("wizard.step1", "wizard.step2", "wizard.step3", "wizard.step4", "wizard.step5", "wizard.step6")
        for idx, sk in enumerate(step_keys):
            b = ttk.Button(top_bar, text=t(sk, self.locale), command=lambda i=idx: self._wizard_go(i))
            b.pack(side="left", padx=(0, 4), pady=2)
            self.wizard_step_btns.append(b)
        self.button(top_bar, "고급 JSON 편집", lambda: self.show("advanced_plan"), side="right")
        self.button(top_bar, "빠른 팝업 마법사", self.guided_dialog, side="right", subtle=True)

        self.wizard_stage = ttk.Frame(frame)
        self.wizard_stage.grid(row=3, column=0, sticky="nsew")
        self.wizard_stage.columnconfigure(0, weight=1)
        self.wizard_stage.rowconfigure(0, weight=1)
        self.wizard_panels = []

        # Step 1: Project Selection
        p1 = Card(self.wizard_stage, self.palette, padding=(18, 14))
        self._themed_cards.append(p1)
        self._build_wizard_step1(p1.body)
        self.wizard_panels.append(p1)

        # Step 2: Natural Language Description & Strategy
        p2 = Card(self.wizard_stage, self.palette, padding=(18, 14))
        self._themed_cards.append(p2)
        self._build_wizard_step2(p2.body)
        self.wizard_panels.append(p2)

        # Step 3: Execution Configuration + Collapsible Advanced
        p3 = Card(self.wizard_stage, self.palette, padding=(18, 14))
        self._themed_cards.append(p3)
        self._build_wizard_step3(p3.body)
        self.wizard_panels.append(p3)

        # Step 4: Execution Plan (Coordinator / Agents / DAG / Tools / QA)
        p4 = Card(self.wizard_stage, self.palette, padding=(18, 14))
        self._themed_cards.append(p4)
        self._build_wizard_step4(p4.body)
        self.wizard_panels.append(p4)

        # Step 5: Permissions & Safety
        p5 = Card(self.wizard_stage, self.palette, padding=(18, 14))
        self._themed_cards.append(p5)
        self._build_wizard_step5(p5.body)
        self.wizard_panels.append(p5)

        # Step 6: Review & Submit
        p6 = Card(self.wizard_stage, self.palette, padding=(18, 14))
        self._themed_cards.append(p6)
        self._build_wizard_step6(p6.body)
        self.wizard_panels.append(p6)

        for panel in self.wizard_panels:
            panel.grid(row=0, column=0, sticky="nsew")

        footer = ttk.Frame(frame)
        footer.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.wiz_prev_btn = self.button(footer, "이전 단계", lambda: self._wizard_go(self.wizard_step - 1))
        self.wiz_next_btn = self.button(footer, "다음 단계", lambda: self.action(lambda: self._wizard_go(self.wizard_step + 1)), True, side="right")
        self.wiz_submit_btn = ttk.Button(footer, text="실행 제출", style="Primary.TButton", command=lambda: self.action(self._wizard_submit))

        self._wizard_sync_projects()
        self._wizard_show_step(0)
        return frame

    def _build_wizard_step1(self, parent):
        p = self.palette
        parent.columnconfigure(1, weight=1)
        tk.Label(parent, text="1단계 · 작업을 실행할 프로젝트 선택", bg=p["panel"], fg=p["text"], font=(self.ui_font, 13, "bold"), anchor="w").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(parent, text="대상 프로젝트", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        self.wiz_project_var = tk.StringVar(self.window)
        self.wiz_project_combo = ttk.Combobox(parent, textvariable=self.wiz_project_var, state="readonly", width=42)
        self.wiz_project_combo.grid(row=1, column=1, sticky="ew", pady=6)
        self.wiz_project_combo.bind("<<ComboboxSelected>>", lambda _e: self._wizard_project_changed())

        self.wiz_project_preview = tk.Label(
            parent, text="등록된 프로젝트가 없으면 먼저 저장소를 추가하세요.",
            bg=p["elevated"], fg=p["text_secondary"], justify="left", anchor="nw", padx=14, pady=12,
            font=(self.ui_font, 10), wraplength=660,
        )
        self.wiz_project_preview.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 12))

        btns = tk.Frame(parent, bg=p["panel"])
        btns.grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Button(btns, text="로컬 저장소 추가", command=self.add_local_project).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="원격 저장소 추가", command=self.add_remote_project).pack(side="left")

    def _build_wizard_step2(self, parent):
        p = self.palette
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        tk.Label(parent, text="2단계 · 목표를 자연어로 설명하고 실행 전략을 선택하세요", bg=p["panel"], fg=p["text"], font=(self.ui_font, 13, "bold"), anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 8))
        tk.Label(parent, text="예시: '로그인 모듈의 오류 원인을 분석하고 테스트를 추가해 주세요' 또는 'QA 명령만 실행하여 상태를 검증하세요'", bg=p["panel"], fg=p["muted"], font=(self.ui_font, 9), anchor="w").grid(row=1, column=0, sticky="w", pady=(0, 6))

        self.wiz_intent = tk.Text(parent, wrap="word", height=6, padx=10, pady=8)
        style_text_widget(self.wiz_intent, p, self.ui_font, 10)
        self._text_widgets.append(self.wiz_intent)
        self.wiz_intent.grid(row=2, column=0, sticky="nsew", pady=(0, 12))

        self.wiz_strategy_var = tk.StringVar(self.window, STRATEGIES[0])
        strat_row = ttk.Frame(parent)
        strat_row.grid(row=3, column=0, sticky="ew")
        descriptions = (
            "파일을 수정하지 않고 저장소를 분석해 근거를 보고합니다.",
            "허용 경로 내에서 개발 후 독립 검토와 통합 QA를 실행합니다.",
            "모델 호출 없이 승인된 QA 검증 명령만 실행합니다.",
        )
        for idx, (name, desc) in enumerate(zip(STRATEGIES, descriptions)):
            strat_row.columnconfigure(idx, weight=1, uniform="wiz_strat")
            c = Card(strat_row, p, padding=(12, 10), bg_key="elevated")
            c.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 8, 0))
            self._themed_cards.append(c)
            rb = ttk.Radiobutton(c.body, text=name, variable=self.wiz_strategy_var, value=name)
            rb.pack(anchor="w")
            tk.Label(c.body, text=desc, bg=p["elevated"], fg=p["muted"], font=(self.ui_font, 9), wraplength=210, justify="left", anchor="w").pack(fill="x", pady=(6, 0))

    def _build_wizard_step3(self, parent):
        p = self.palette
        parent.columnconfigure(1, weight=1)
        tk.Label(parent, text="3단계 · 실행 환경과 모델 설정", bg=p["panel"], fg=p["text"], font=(self.ui_font, 13, "bold"), anchor="w").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.wiz_provider_var = tk.StringVar(self.window, "")
        self.wiz_model_var = tk.StringVar(self.window, "")
        self.wiz_harness_var = tk.StringVar(self.window, "")
        self.wiz_bg_var = tk.BooleanVar(self.window, False)

        ttk.Label(parent, text="Provider", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=5)
        self.wiz_provider_combo = ttk.Combobox(parent, textvariable=self.wiz_provider_var, state="readonly")
        self.wiz_provider_combo.grid(row=1, column=1, sticky="ew", pady=5)
        self.wiz_provider_combo.bind("<<ComboboxSelected>>", lambda _e: self._wizard_refresh_models())

        ttk.Label(parent, text="모델 (비워 두면 자동 선택)", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=5)
        self.wiz_model_combo = ttk.Combobox(parent, textvariable=self.wiz_model_var, state="readonly")
        self.wiz_model_combo.grid(row=2, column=1, sticky="ew", pady=5)
        self.wiz_model_combo.bind("<<ComboboxSelected>>", lambda _e: self._wizard_refresh_harnesses())

        ttk.Label(parent, text="Harness", style="Card.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=5)
        self.wiz_harness_combo = ttk.Combobox(parent, textvariable=self.wiz_harness_var, state="readonly")
        self.wiz_harness_combo.grid(row=3, column=1, sticky="ew", pady=5)

        ttk.Checkbutton(parent, text="앱을 닫아도 Supervisor가 백그라운드에서 계속 실행", variable=self.wiz_bg_var, style="Card.TCheckbutton").grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 10))

        self.wiz_adv = CollapsibleSection(parent, "고급 설정 (변경 허용 경로 · MCP 도구 · QA 명령)", p, self.ui_font, expanded=False)
        self.wiz_adv.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.wiz_paths_var = tk.StringVar(self.window, "")
        self.wiz_tools_var = tk.StringVar(self.window, "")
        ttk.Label(self.wiz_adv.content, text="변경 허용 경로 (쉼표 구분)", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(self.wiz_adv.content, textvariable=self.wiz_paths_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(self.wiz_adv.content, text="MCP 도구 가상 이름", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(self.wiz_adv.content, textvariable=self.wiz_tools_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(self.wiz_adv.content, text="QA 명령 (한 줄에 하나)", style="Card.TLabel").grid(row=2, column=0, sticky="nw", padx=(0, 10), pady=4)
        self.wiz_qa_text = tk.Text(self.wiz_adv.content, wrap="word", height=3, padx=8, pady=5)
        style_text_widget(self.wiz_qa_text, p, self.mono_font, 9)
        self._text_widgets.append(self.wiz_qa_text)
        self.wiz_qa_text.grid(row=2, column=1, sticky="ew", pady=4)

    def _build_wizard_step4(self, parent):
        p = self.palette
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        tk.Label(parent, text="4단계 · 생성된 실행 계획 및 DAG 의존성 검토", bg=p["panel"], fg=p["text"], font=(self.ui_font, 13, "bold"), anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.wiz_plan_summary = tk.Label(parent, text="", bg=p["panel"], fg=p["muted"], font=(self.ui_font, 9), anchor="w")
        self.wiz_plan_summary.grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.wiz_nodes_list = tk.Listbox(parent, height=7)
        style_listbox_widget(self.wiz_nodes_list, p, self.ui_font, 10)
        self.wiz_nodes_list.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        bar = ttk.Frame(parent)
        bar.grid(row=3, column=0, sticky="ew")
        self.button(bar, "계획 다시 생성", lambda: self.action(self._wizard_generate_plan))
        self.button(bar, "노드 추가", lambda: self.action(lambda: self._wizard_edit_node(None)))
        self.button(bar, "노드 편집", lambda: self.action(self._wizard_edit_selected_node))
        self.button(bar, "노드 제거", lambda: self.action(self._wizard_delete_node))

    def _build_wizard_step5(self, parent):
        p = self.palette
        parent.columnconfigure(0, weight=1)
        tk.Label(parent, text="5단계 · 작업 권한 및 안전장치 안내", bg=p["panel"], fg=p["text"], font=(self.ui_font, 13, "bold"), anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 10))
        items = (
            ("읽기 전용 작업", t("wizard.perm_read", self.locale), "neutral"),
            ("파일 수정 및 Worktree 격리", t("wizard.perm_write", self.locale), "running"),
            ("외부 MCP 쓰기 승인", t("wizard.perm_mcp", self.locale), "warning"),
            ("Git 병합 안전 검증", t("wizard.perm_git", self.locale), "success"),
        )
        for idx, (title, desc, tone) in enumerate(items, 1):
            c = Card(parent, p, padding=(12, 9), bg_key="elevated")
            c.grid(row=idx, column=0, sticky="ew", pady=(0, 8))
            self._themed_cards.append(c)
            top = tk.Frame(c.body, bg=p["elevated"])
            top.pack(fill="x")
            tk.Label(top, text=title, bg=p["elevated"], fg=p["text"], font=(self.ui_font, 10, "bold")).pack(side="left")
            StatusBadge(top, p, text="정책 적용", tone=tone, ui_font=self.ui_font).pack(side="right")
            tk.Label(c.body, text=desc, bg=p["elevated"], fg=p["text_secondary"], font=(self.ui_font, 9), anchor="w", wraplength=680, justify="left").pack(fill="x", pady=(4, 0))

    def _build_wizard_step6(self, parent):
        p = self.palette
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        tk.Label(parent, text="6단계 · 최종 검토 및 Supervisor 제출", bg=p["panel"], fg=p["text"], font=(self.ui_font, 13, "bold"), anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.wiz_review_box = self.text(parent, 1)
        self.write(self.wiz_review_box, "앞 단계를 완료하면 실행 계획과 경로 검증 요약이 여기에 표시됩니다.", True)

    def _wizard_sync_projects(self):
        if not hasattr(self, "wiz_project_combo"):
            return
        projects = self.project_rows()
        self.wizard_project_map = {f'{value["name"]} · {key[:5]}': key for key, value in projects.items()}
        self.wiz_project_combo.configure(values=list(self.wizard_project_map))
        if self.wizard_project_map:
            current = next((label for label, key in self.wizard_project_map.items() if key == self.project_id), next(iter(self.wizard_project_map)))
            self.wiz_project_var.set(current)
            self._wizard_project_changed()
        else:
            self.wiz_project_var.set("")
            self.wiz_project_preview.configure(text="등록된 프로젝트가 없습니다. 먼저 로컬 또는 원격 저장소를 추가하세요.")

    def _wizard_project_changed(self):
        label = self.wiz_project_var.get()
        key = self.wizard_project_map.get(label)
        if not key:
            return
        self.project_id = key
        project = self.project_rows().get(key)
        if not project:
            return
        self.wiz_project_preview.configure(
            text=(
                f'저장소: {project["path"]}\n'
                f'대상 브랜치: {project["branch"]}  ·  실행 환경: {self.host_name(project.get("host"))}\n'
                f'언어: {one_line(project.get("stack"))}  ·  기본 모델: {project.get("model") or "자동"}  ·  기본 Harness: {project.get("harness") or "자동"}'
            )
        )
        self.wiz_paths_var.set(", ".join(project.get("paths", [])))
        self.wiz_tools_var.set(", ".join(project.get("tools", [])))
        self.write(self.wiz_qa_text, format_commands(project.get("qa", [])))
        if not project.get("host"):
            self._wizard_apply_catalog(read_config(self.root), project)
        else:
            host = project["host"]
            self._wizard_apply_catalog(self.wizard_remote_catalog.get(host, {}), project)
            self.background(
                lambda h=host: self.ssh(h).call("info"),
                lambda res, h=host, lbl=label: self._wizard_remote_catalog_ready(h, lbl, res),
            )

    def _wizard_remote_catalog_ready(self, host, label, result):
        self.wizard_remote_catalog[host] = result
        if hasattr(self, "wiz_project_var") and self.wiz_project_var.get() == label:
            key = self.wizard_project_map.get(label)
            if key and key in self.project_rows():
                self._wizard_apply_catalog(result, self.project_rows()[key])

    def _wizard_apply_catalog(self, catalog: dict, project: dict):
        self._wizard_catalog = catalog
        providers = sorted({value["provider"] for value in catalog.get("models", {}).values()})
        self.wiz_provider_combo.configure(values=["", *providers])
        if self.wiz_provider_var.get() not in providers:
            self.wiz_provider_var.set("")
        self._wizard_refresh_models(project)

    def _wizard_refresh_models(self, project=None):
        project = project or self.project_rows().get(self.wizard_project_map.get(self.wiz_project_var.get()), {})
        catalog = getattr(self, "_wizard_catalog", read_config(self.root))
        available = catalog.get("models", {})
        provider = self.wiz_provider_var.get()
        allowed = [""] + [key for key, value in available.items() if not provider or value.get("provider") == provider]
        self.wiz_model_combo.configure(values=allowed)
        default_choice = self.wiz_model_var.get() or project.get("model") or read_workspace(self.root).get("default_model")
        self.wiz_model_var.set(default_choice if default_choice in allowed else "")
        self._wizard_refresh_harnesses(project)

    def _wizard_refresh_harnesses(self, project=None):
        project = project or self.project_rows().get(self.wizard_project_map.get(self.wiz_project_var.get()), {})
        catalog = getattr(self, "_wizard_catalog", read_config(self.root))
        allowed = list(catalog.get("harnesses", {}))
        selected = catalog.get("models", {}).get(self.wiz_model_var.get())
        if selected is not None and not project.get("host"):
            allowed = [key for key in allowed if key in selected.get("harnesses", ["managed"])]
        self.wiz_harness_combo.configure(values=["", *allowed])
        cur = self.wiz_harness_var.get() or project.get("harness", "")
        self.wiz_harness_var.set(cur if cur in allowed else "")

    def _wizard_generate_plan(self):
        key = self.wizard_project_map.get(self.wiz_project_var.get())
        require(key and key in self.project_rows(), "먼저 프로젝트를 등록하고 선택하세요.")
        project = self.project_rows()[key]
        intent = self.wiz_intent.get("1.0", "end-1c")
        if self.wiz_strategy_var.get() == STRATEGIES[1] and (not split_names(self.wiz_paths_var.get()) or not parse_commands(self.wiz_qa_text.get("1.0", "end-1c"))):
            self.wiz_adv.toggle(True)
        self.wizard_draft = draft_plan(
            project,
            intent,
            self.wiz_strategy_var.get(),
            model=self.wiz_model_var.get(),
            harness=self.wiz_harness_var.get(),
            paths=split_names(self.wiz_paths_var.get()),
            qa=parse_commands(self.wiz_qa_text.get("1.0", "end-1c")),
            tools=split_names(self.wiz_tools_var.get()),
            background=self.wiz_bg_var.get(),
        )
        self._wizard_render_plan()

    def _wizard_render_plan(self):
        if not self.wizard_draft:
            return
        plan = self.wizard_draft
        self.wiz_plan_summary.configure(
            text=f'제목: {plan["title"]}   ·   브랜치: {plan["target"]}   ·   통합 QA: {format_commands(plan.get("qa", [])) or "없음"}'
        )
        self.wiz_nodes_list.delete(0, "end")
        for task in plan["tasks"]:
            self.wiz_nodes_list.insert(
                "end",
                f'{task["id"]} · {task["role"]} · 모델 {task.get("model") or "자동"} · '
                f'Harness {task.get("harness") or "자동"} · 선행 {one_line(task.get("depends"))} · '
                f'쓰기 {one_line(task.get("paths"))}',
            )

    def _wizard_edit_node(self, index):
        require(self.wizard_draft, "먼저 실행 계획을 생성하세요.")
        nodes = self.wizard_draft["tasks"]
        raw = nodes[index] if index is not None else {}
        child = Form(self, "실행 노드", "Agent 역할, 선행 노드 및 작업 권한을 편집합니다.", width=590)
        for key, label, value in (
            ("id", "노드 ID", raw.get("id", "")),
            ("model", "모델 ID", raw.get("model", "")),
            ("harness", "Harness ID", raw.get("harness", "")),
            ("depends", "선행 노드", one_line(raw.get("depends"))),
            ("paths", "허용 쓰기 경로", one_line(raw.get("paths"))),
            ("tools", "허용 MCP 도구", one_line(raw.get("tools"))),
            ("read_paths", "읽기 경로", one_line(raw.get("read_paths"))),
            ("context", "최소 Context", str(raw.get("min_context", 1024))),
        ):
            child.field(key, label, value if value != "—" else "")
        child.field("role", "역할", raw.get("role", "explorer"), choices=("planner", "developer", "explorer", "reviewer", "qa", "diagnostic"))
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
            self._wizard_render_plan()
            child.destroy()

        child.controls("노드 적용", apply)

    def _wizard_edit_selected_node(self):
        require(self.wiz_nodes_list.curselection(), "수정할 노드를 선택하세요.")
        self._wizard_edit_node(self.wiz_nodes_list.curselection()[0])

    def _wizard_delete_node(self):
        require(self.wiz_nodes_list.curselection(), "제거할 노드를 선택하세요.")
        del self.wizard_draft["tasks"][self.wiz_nodes_list.curselection()[0]]
        self._wizard_render_plan()

    def _wizard_prepare_review(self):
        if not self.wizard_draft:
            self._wizard_generate_plan()
        plan = self.wizard_draft
        key = self.wizard_project_map.get(self.wiz_project_var.get())
        project = self.project_rows()[key]
        lines = [
            f'프로젝트        {project["name"]} ({self.host_name(project.get("host"))})',
            f'저장소 / 브랜치  {plan["repo"]} · {plan["target"]}',
            f'작업 제목        {plan["title"]}',
            f'실행 전략        {self.wiz_strategy_var.get()}',
            f'백그라운드 실행  {"예" if plan.get("background") else "아니오"}',
            f'통합 QA          {format_commands(plan.get("qa", [])) or "없음"}',
            "",
            f'실행 노드 ({len(plan["tasks"])}개)',
        ]
        for task in plan["tasks"]:
            lines.append(f'  - {task["id"]} ({task["role"]}) · 선행 {one_line(task.get("depends"))} · 경로 {one_line(task.get("paths"))}')
        if not project.get("host"):
            try:
                routes = plan_routes(plan, read_config(self.root))
                lines.extend(["", "예상 실행 경로 (Preflight 통과)"])
                for tid, choices in routes.items():
                    lines.append(f'  - {tid}: {choices[0] if choices else "검증 명령 직접 실행"}')
            except (ValueError, KeyError) as exc:
                lines.extend(["", f"실행 경로 사전 확인 필요: {exc}"])
        self.write(self.wiz_review_box, "\n".join(lines), True)

    def _wizard_go(self, idx: int):
        idx = max(0, min(5, idx))
        if idx >= 3 and self.wizard_step < 3:
            self._wizard_generate_plan()
        if idx == 5:
            self._wizard_prepare_review()
        self._wizard_show_step(idx)

    def _wizard_show_step(self, idx: int):
        self.wizard_step = idx
        self.wizard_panels[idx].tkraise()
        for i, btn in enumerate(self.wizard_step_btns):
            btn.configure(style="Primary.TButton" if i == idx else "TButton")
        self.wiz_prev_btn.state(["!disabled" if idx > 0 else "disabled"])
        if idx == 5:
            self.wiz_next_btn.pack_forget()
            self.wiz_submit_btn.pack(side="right", padx=(0, 6), pady=3)
        else:
            self.wiz_submit_btn.pack_forget()
            self.wiz_next_btn.pack(side="right", padx=(0, 6), pady=3)

    def _wizard_submit(self):
        if not self.wizard_draft:
            self._wizard_generate_plan()
        plan = self.wizard_draft
        key = self.wizard_project_map.get(self.wiz_project_var.get())
        require(key and key in self.project_rows(), "프로젝트를 선택하세요.")
        project = self.project_rows()[key]
        host = project.get("host")

        def confirm_and_send(routes_map):
            resolved = "\n".join(f"{tid} · {choices[0] if choices else '검증 명령만'}" for tid, choices in routes_map.items())
            if not messagebox.askyesno(
                "계획 제출 승인",
                f'실행 경로 후보\n{resolved}\n\n이 계획의 검증 명령과 작업 실행을 승인하시겠습니까?',
                parent=self.window,
            ):
                return
            if host:
                self.submit_remote_run(host, plan)
            else:
                self.accept_local_plan(plan)
            self.wizard_draft = None

        if host:
            snap = json.loads(json.dumps(plan))
            self.background(lambda: self.ssh(host).call("validate", plan=snap), lambda routes_map: confirm_and_send(routes_map))
        else:
            confirm_and_send(plan_routes(plan, read_config(self.root)))

    # ------------------------------------------------------------------
    # Preserved Modal Guided Dialog & Review Plan (test contract intact)
    # ------------------------------------------------------------------
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
        listing = tk.Listbox(form.body, height=7)
        style_listbox_widget(listing, self.palette, self.ui_font, 10)
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
            for key, label, value in (
                ("id", "노드 ID", raw.get("id", "")),
                ("model", "모델 ID", raw.get("model", "")),
                ("harness", "Harness ID", raw.get("harness", "")),
                ("depends", "선행 노드", one_line(raw.get("depends"))),
                ("paths", "허용 쓰기 경로", one_line(raw.get("paths"))),
                ("tools", "허용 MCP 도구", one_line(raw.get("tools"))),
                ("read_paths", "읽기 경로", one_line(raw.get("read_paths"))),
                ("context", "최소 Context", str(raw.get("min_context", 1024))),
            ):
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
            confirm = messagebox.askyesno(
                "계획 제출 승인",
                f'실행 경로 후보\n{resolved}\n\n이 계획의 검증 명령과 작업 실행을 승인하시겠습니까?',
                parent=form,
            )
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

    # ------------------------------------------------------------------
    # Phase 11: Providers, Execution History & Settings Pages
    # ------------------------------------------------------------------
    def providers_page(self):
        frame = self.base(t("providers.title", self.locale), t("providers.desc", self.locale))
        frame.rowconfigure(4, weight=1)
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.button(bar, "Provider 설정 마법사", self.provider_wizard, True)
        self.button(bar, "모델·Runtime 편집", lambda: self.action(self._edit_provider_model))
        self.button(bar, "고급 JSON", lambda: self.show("registry"))

        summary_row = ttk.Frame(frame)
        summary_row.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.provider_summary_cards = []
        for idx, title in enumerate(("로컬 Runtime", "CLI Harness", "등록된 모델 프로필")):
            summary_row.columnconfigure(idx, weight=1, uniform="prov_kpi")
            c = Card(summary_row, self.palette, padding=(12, 9))
            c.grid(row=0, column=idx, sticky="ew", padx=(0 if idx == 0 else 8, 0))
            self._themed_cards.append(c)
            tk.Label(c.body, text=title, bg=self.palette["panel"], fg=self.palette["muted"], font=(self.ui_font, 9, "bold"), anchor="w").pack(fill="x")
            val = tk.Label(c.body, text="0", bg=self.palette["panel"], fg=self.palette["text"], font=(self.ui_font, 16, "bold"), anchor="w")
            val.pack(fill="x", pady=(2, 0))
            self.provider_summary_cards.append(val)

        self.provider_models_list = self.table(frame, 4, (
            ("profile", "모델 프로필", 170), ("provider", "Provider", 105),
            ("model", "모델 ID", 210), ("harnesses", "Harness", 140), ("roles", "허용 역할", 200),
        ))
        return frame

    def refresh_providers(self):
        if not hasattr(self, "provider_models_list"):
            return
        cfg = read_config(self.root)
        if hasattr(self, "provider_summary_cards"):
            self.provider_summary_cards[0].configure(text=str(len(cfg.get("runtimes", {}))))
            self.provider_summary_cards[1].configure(text=str(len(cfg.get("harnesses", {}))))
            self.provider_summary_cards[2].configure(text=str(len(cfg.get("models", {}))))
        rows = [
            (key, (key, model["provider"], model["model"], one_line(model.get("harnesses", ["managed"])),
                   one_line(model.get("roles", ["전체"]))))
            for key, model in cfg["models"].items()
        ]
        self.fill(self.provider_models_list, rows)

    def _edit_provider_model(self):
        selected = self.provider_models_list.selection()
        require(selected, "편집할 모델 프로필을 선택하세요.")
        self._open_model_editor(selected[0])

    def history_page(self):
        frame = self.base(t("history.title", self.locale), t("history.desc", self.locale))
        frame.rowconfigure(3, weight=1)
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(bar, text="검색", style="Muted.TLabel").pack(side="left", padx=(0, 4))
        self.history_query = tk.StringVar(self.window)
        self.history_query.trace_add("write", lambda *_: self.refresh_history())
        ttk.Entry(bar, textvariable=self.history_query, width=22).pack(side="left", padx=(0, 10))
        ttk.Label(bar, text="상태", style="Muted.TLabel").pack(side="left", padx=(0, 4))
        self.history_state = tk.StringVar(self.window, "전체")
        state_box = ttk.Combobox(
            bar, textvariable=self.history_state, state="readonly", width=15,
            values=("전체", "실행 중", "병합 승인 대기", "병합 완료", "완료", "실패", "중지"),
        )
        state_box.pack(side="left", padx=(0, 10))
        state_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh_history())
        ttk.Label(bar, text="프로젝트", style="Muted.TLabel").pack(side="left", padx=(0, 4))
        self.history_project = tk.StringVar(self.window, "전체")
        self.history_project_box = ttk.Combobox(bar, textvariable=self.history_project, state="readonly", width=18, values=("전체",))
        self.history_project_box.pack(side="left", padx=(0, 10))
        self.history_project_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh_history())
        self.button(bar, "실행 보고서 비교", self.compare_runs, side="right")
        self.button(bar, "상세 열기", lambda: self.open_job(self.history_table.selection()[0]) if self.history_table.selection() else None, True, side="right")

        self.history_table = self.table(frame, 3, (
            ("title", "작업", 250), ("repo", "저장소", 185), ("state", "상태", 115),
            ("mode", "모드", 90), ("updated", "갱신", 135),
        ))
        self.history_table.bind("<Double-1>", lambda _e: self.open_job(self.history_table.selection()[0]) if self.history_table.selection() else None)
        return frame

    def refresh_history(self):
        if not hasattr(self, "history_table"):
            return
        jobs = self.store.list_jobs()
        projects = self.project_rows()
        repo_names = {p["path"]: p["name"] for p in projects.values()}
        proj_choices = ["전체", *sorted({repo_names.get((j.get("plan") or {}).get("repo"), Path((j.get("plan") or {}).get("repo", "")).name or "—") for j in jobs})]
        self.history_project_box.configure(values=proj_choices)
        q = self.history_query.get().strip().casefold()
        sf = self.history_state.get()
        pf = self.history_project.get()
        rows = []
        for row in jobs:
            title = (row.get("plan") or {}).get("title", "")
            repo = (row.get("plan") or {}).get("repo", "")
            repo_label = repo_names.get(repo, Path(repo).name or "—")
            st_label = state_label(row["state"], self.locale)
            if sf != "전체" and st_label != sf:
                continue
            if pf != "전체" and repo_label != pf:
                continue
            if q and q not in title.casefold() and q not in row["id"].casefold() and q not in repo.casefold():
                continue
            rows.append((
                row["id"],
                (title, repo_label, st_label, "백그라운드" if row["plan"].get("background") else "포그라운드",
                 datetime.fromtimestamp(row["updated"]).strftime("%m-%d %H:%M:%S")),
            ))
        self.fill(self.history_table, rows)

    def settings_page(self):
        frame = self.base(t("settings.title", self.locale), t("settings.desc", self.locale))
        frame.rowconfigure(4, weight=1)
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.button(bar, "Provider 설정 마법사", self.provider_wizard, True)
        self.button(bar, "모델·Runtime 편집", lambda: self.action(self.edit_model))
        self.button(bar, "실행·알림 정책", self.policy_dialog)
        self.button(bar, "고급 JSON", lambda: self.show("registry"))
        self.button(bar, "설정 내보내기", self.export_settings)

        pref_card = Card(frame, self.palette, padding=(14, 10))
        pref_card.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self._themed_cards.append(pref_card)
        pref_row = tk.Frame(pref_card.body, bg=self.palette["panel"])
        pref_row.pack(fill="x")
        self.settings_policy_label = tk.Label(
            pref_row, text="", bg=self.palette["panel"], fg=self.palette["text_secondary"],
            font=(self.ui_font, 9), anchor="w",
        )
        self.settings_policy_label.pack(side="left", fill="x", expand=True)
        ttk.Button(pref_row, text="다크 / 라이트 전환", style="Subtle.TButton", command=self.toggle_theme).pack(side="right", padx=(8, 0))
        ttk.Button(pref_row, text="데이터 폴더 열기", style="Subtle.TButton", command=lambda: self.action(lambda: open_directory(self.root))).pack(side="right")

        self.settings_list = self.table(frame, 4, (
            ("profile", "모델 프로필", 170), ("provider", "Provider", 105),
            ("model", "모델 ID", 210), ("route", "실행 경로", 210),
        ))
        ttk.Label(frame, text=f"설정·보고서·백업 위치   {self.root}", style="Muted.TLabel").grid(row=5, column=0, sticky="w", pady=(6, 0))
        return frame

    def refresh_settings(self):
        cfg = read_config(self.root)
        self.fill(self.settings_list, [(key, (key, model["provider"], model["model"],
                      one_line(model.get("harnesses", ["managed"])))) for key, model in cfg["models"].items()])
        if hasattr(self, "settings_policy_label"):
            s = settings(cfg)
            self.settings_policy_label.configure(
                text=f'현재 테마: {self.theme_name}  ·  동시 작업 {s["parallel_jobs"]} / 노드 {s["parallel_tasks"]}  ·  백그라운드 {"허용" if s["background"] else "끔"}  ·  알림 {"켬" if s["notifications"] else "끔"}'
            )

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
        self._open_model_editor(selected[0])

    def _open_model_editor(self, key: str):
        config, revision = read_config(self.root), registry_revision(self.root)
        model = config["models"][key]
        runtime = config["runtimes"].get(model.get("runtime"))
        form = Form(self, "모델과 실행 설정", f'{key} · {model["provider"]}')
        form.field("model", "실제 모델 ID", model["model"])
        form.field("roles", "허용 역할", ", ".join(model.get("roles", ["planner", "developer", "explorer", "reviewer", "qa", "diagnostic"])))
        form.field("harnesses", "허용 Harness ID", ", ".join(model.get("harnesses", ["managed"])))
        for name, label in (
            ("token_budget", "토큰 예산 (0은 제한 없음)"), ("quality", "품질 점수"),
            ("tool_score", "도구 점수"), ("reliability", "신뢰도 점수"), ("cost", "비용 점수"),
        ):
            form.field(name, label, model.get(name, 0))
        if runtime is not None:
            for name, label, default in (
                ("url", "Runtime 주소", "http://127.0.0.1:8080"),
                ("auth_env", "자격 증명 환경 변수", ""),
                ("context", "Context 한도", 32768),
                ("max_output", "최대 출력", 2048),
                ("slots", "동시 슬롯", 1),
                ("ram_mb", "RAM 예약(MB)", 0),
            ):
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
            self.refresh_providers()
            form.destroy()

        form.controls("변경 저장", save)

    def export_settings(self):
        name = filedialog.asksaveasfilename(defaultextension=".json", parent=self.window, initialfile="registry.json")
        if name:
            self.action(lambda: atomic_json(Path(name), read_config(self.root)))

    def save_registry(self):
        def save():
            config = save_registry(self.root, json.loads(self.registry.get("1.0", "end-1c")), self.registry_revision)
            self.registry_revision = registry_revision(self.root)
            self.write(self.registry, formatted(config))
            self.notifications = settings(config)["notifications"]
            self.restart_supervisor()
            self.refresh_settings()
            self.refresh_providers()
            messagebox.showinfo("설정 저장", "레지스트리를 저장했습니다. 이전 설정은 backups 폴더에 보관합니다.", parent=self.window)
        self.action(save)

    def policy_dialog(self):
        config = read_config(self.root)
        revision = registry_revision(self.root)
        cfg = settings(config)
        form = Form(self, "실행과 알림 정책", "새 작업에는 저장 시점의 실행 정책을 적용합니다.")
        labels = {
            "background": "앱을 닫아도 실행",
            "allow_background_write": "백그라운드 Worktree 쓰기",
            "notifications": "앱 내 상태 알림",
            "parallel_jobs": "동시 작업 수",
            "parallel_tasks": "동시 노드 수",
            "attempts": "최대 실행 시도",
            "job_timeout_sec": "작업 제한 시간(초)",
            "heartbeat_sec": "하트비트(초)",
            "lease_sec": "리스 만료(초)",
        }
        for key, label in labels.items():
            form.field(key, label, cfg[key], boolean=type(cfg[key]) is bool)

        def save():
            for key, value in form.values().items():
                config["settings"][key] = value if type(value) is bool else int(value)
            save_registry(self.root, config, revision)
            self.notifications = config["settings"]["notifications"]
            self.restart_supervisor()
            self.refresh_settings()
            form.destroy()

        form.controls("정책 저장", save)

    def provider_wizard(self):
        from .discovery import discover
        form = Form(self, "Provider 설정 마법사", "설치 탐색 → 연결 확인 → 모델 선택 → 등록 (간편 / 고급 모드 전환 가능)")
        choices = [*RUNTIME_KINDS, "OpenCode", "Codex", "OpenAI", "Google Gemini", "Anthropic",
                   "Antigravity", "Claude Code", "Gemini CLI", "Custom"]

        mode_var = tk.StringVar(form, "simple")
        mode_bar = ttk.Frame(form.body)
        mode_bar.grid(row=form.row, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        form.row += 1
        mode_hint = form.note(t("provider.simple_hint", self.locale))

        provider = form.field("kind", "연결 방식", "Ollama", choices=choices)
        form.field("id", "프로필 ID", "my-model", help_text="작업 및 프로젝트 기본값에서 참조하는 고유 이름입니다.")
        form.field("endpoint", "로컬 Runtime 주소", "http://127.0.0.1:11434")
        form.field("auth_env", "자격 증명 환경 변수", help_text="비밀값은 직접 저장하지 않고 환경 변수 이름만 기록합니다.")
        form.field("executable", "CLI 실행 파일")
        model_list = form.field("found", "관측된 모델", choices=[])
        form.field("model", "모델 ID")
        form.field("context", "설정 Context", "32768", help_text="관측 가능할 때만 감지된 한도를 채웁니다. 실행 시 실제 한도를 다시 검사합니다.")
        form.field("trusted", "선택한 CLI 실행을 허용", False, boolean=True)
        form.field("default", "기본 모델로 사용", True, boolean=True)
        details = form.note("연결을 확인하면 설치 또는 응답에서 확인한 정보가 표시됩니다.")
        form.note("Runtime, OpenCode, Codex는 실행 프로필로 등록할 수 있습니다. 나머지 연결 방식은 설치 탐색을 제공합니다.")

        advanced_keys = ("endpoint", "auth_env", "executable", "context", "trusted")

        def apply_mode():
            show_adv = mode_var.get() == "advanced"
            for k in advanced_keys:
                form.set_visible(k, show_adv)
            mode_hint.configure(text=t("provider.advanced_hint" if show_adv else "provider.simple_hint", self.locale))

        ttk.Radiobutton(mode_bar, text="간편 모드", variable=mode_var, value="simple", command=apply_mode).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(mode_bar, text="고급 모드", variable=mode_var, value="advanced", command=apply_mode).pack(side="left")
        apply_mode()

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
            self.refresh_providers()

        form.controls("프로필 저장", save)
