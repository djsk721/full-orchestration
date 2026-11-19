from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
import uuid
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .core import atomic_json, config_check, plan_check, require
from .discovery import discover, migrate, rollback
from .platform.desktop import open_directory, prepare_dpi
from .store import Store
from .supervisor import read_config, start_supervisor

BG, PANEL, TEXT, MUTED = "#edf2f7", "#ffffff", "#162942", "#53667d"
NAV, NAV_ACTIVE, BLUE = "#142640", "#29425f", "#2459ad"
STATES = {
    "QUEUED": "대기", "PREPARING": "준비 중", "RUNNING": "실행 중", "VERIFYING": "검증 중",
    "RETRY_WAIT": "재시도 대기", "AWAITING_TOOL": "도구 승인 대기", "AWAITING_APPROVAL": "병합 승인 대기",
    "MERGE_QUEUED": "병합 준비", "MERGING": "병합 중", "MERGED": "병합 완료",
    "NOT_EXECUTED": "미실행", "SUCCEEDED": "완료", "FAILED": "실패", "CANCELLED": "중지",
}


def formatted(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def sample_plan():
    return {
        "title": "저장소 구조 분석", "repo": "", "target": "main", "background": False,
        "tasks": [{"id": "explore", "role": "explorer", "depends": [],
                   "prompt": "Inspect the repository and describe its architecture.",
                   "acceptance": "Identify the entry point and the main responsibilities.",
                   "paths": [], "tools": [], "qa": []}],
        "qa": [],
    }


class Desktop:
    initial_page = "jobs"

    def __init__(self, window, root):
        self.window, self.root, self.store = window, root, Store(root)
        self.token = uuid.uuid4().hex
        self.selected_job = None
        self.last_seq = 0
        self.job_cache = None
        self.notice_states = None
        self.notifications = False
        self.scanned = []
        self.scan_project = None
        self.results = queue.Queue()
        self.launch_attempt = 0.0
        self.events_cached = {}
        self.suppress_restart = False
        self.view = ""
        self.pages = {}
        self.nav_buttons = {}
        self.window.title("Model Orchestration")
        self.window.geometry("1240x800")
        self.window.minsize(940, 640)
        self.window.configure(bg=BG)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.style()
        self.layout()
        self.store.presence(self.token)
        try:
            self.notifications = read_config(self.root)["settings"].get("notifications", False)
        except (OSError, ValueError, TypeError):
            pass
        self.show(self.initial_page)
        self.tick()

    def style(self):
        style = ttk.Style()
        style.theme_use("clam")
        names = {family.casefold(): family for family in tkfont.families(self.window)}
        candidates = ("Segoe UI", "Noto Sans CJK KR", "NanumGothic", "DejaVu Sans")
        self.ui_font = next((names[item.casefold()] for item in candidates if item.casefold() in names), "TkDefaultFont")
        mono = ("Consolas", "NanumGothicCoding", "DejaVu Sans Mono")
        self.mono_font = next((names[item.casefold()] for item in mono if item.casefold() in names), "TkFixedFont")
        self.window.option_add("*Font", (self.ui_font, 10))
        style.configure(".", font=(self.ui_font, 10), foreground=TEXT)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Muted.TLabel", foreground=MUTED, background=BG)
        style.configure("Heading.TLabel", font=(self.ui_font, 23, "bold"), background=BG)
        style.configure("Section.TLabel", font=(self.ui_font, 12, "bold"), background=BG)
        style.configure("TButton", padding=(12, 7), background=PANEL, bordercolor="#c3d0df", relief="flat")
        style.map("TButton", background=[("active", "#dfeafa")])
        style.configure("Primary.TButton", background=BLUE, foreground="white", bordercolor=BLUE)
        style.map("Primary.TButton", background=[("active", "#1e488b")])
        style.configure("Treeview", rowheight=34, background=PANEL, fieldbackground=PANEL, bordercolor="#d0dae6")
        style.configure("Treeview.Heading", padding=(8, 8), background="#e1e9f3", foreground=TEXT)
        style.map("Treeview", background=[("selected", "#d4e4fa")], foreground=[("selected", TEXT)])

    def layout(self):
        self.window.columnconfigure(1, weight=1)
        self.window.rowconfigure(0, weight=1)
        nav = tk.Frame(self.window, bg=NAV, width=222)
        nav.grid(row=0, column=0, sticky="nsew")
        nav.grid_propagate(False)
        tk.Label(nav, text="Model\nOrchestration", justify="left", anchor="w", bg=NAV, fg="white",
                 font=(self.ui_font, 21, "bold")).pack(fill="x", padx=22, pady=(27, 27))
        navigation = self.navigation()
        for key, text, _ in navigation:
            if not text:
                continue
            btn = tk.Button(nav, text=text, anchor="w", padx=11, pady=11, bg=NAV, fg="#eff5ff", bd=0,
                            activebackground=NAV_ACTIVE, activeforeground="white", cursor="hand2",
                            relief="flat", highlightthickness=1, highlightbackground=NAV, highlightcolor="#85abdc",
                            command=lambda name=key: self.show(name))
            btn.pack(fill="x", padx=11, pady=2)
            self.nav_buttons[key] = btn
        self.status = tk.Label(nav, text="Supervisor 연결 중", anchor="w", justify="left",
                               bg=NAV, fg="#c7d9ee", padx=5, wraplength=178)
        self.status.pack(side="bottom", fill="x", padx=15, pady=20)
        self.host = ttk.Frame(self.window, padding=(25, 20, 25, 23))
        self.host.grid(row=0, column=1, sticky="nsew")
        self.host.rowconfigure(0, weight=1)
        self.host.columnconfigure(0, weight=1)
        for key, _, factory in navigation:
            self.pages[key] = factory()
            self.pages[key].grid(row=0, column=0, sticky="nsew")

    def navigation(self):
        return (("jobs", "작업 대시보드", self.jobs_page), ("submit", "새 작업", self.submit_page),
                ("registry", "모델 및 실행 설정", self.registry_page), ("mcp", "MCP 연결", self.mcp_page))

    def show(self, key):
        self.view = key
        self.pages[key].tkraise()
        for name, button in self.nav_buttons.items():
            button.configure(bg=NAV_ACTIVE if key == name else NAV)
        if key == "registry" and not self.registry.get("1.0", "end-1c").strip():
            self.write(self.registry, formatted(read_config(self.root)))
        if key == "jobs":
            self.refresh_jobs()

    def base(self, title, description):
        frame = ttk.Frame(self.host)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=title, style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=description, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 15))
        return frame

    @staticmethod
    def button(parent, text, command, primary=False, side="left"):
        button = ttk.Button(parent, text=text, command=command, style="Primary.TButton" if primary else "TButton")
        button.pack(side=side, padx=(0, 6), pady=4)
        return button

    def text(self, parent, row, *, size=10):
        host = ttk.Frame(parent)
        host.grid(row=row, column=0, sticky="nsew", pady=(3, 0))
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)
        field = tk.Text(host, wrap="word", bg=PANEL, fg=TEXT, insertbackground=TEXT, undo=True, padx=12, pady=10,
                        font=(self.mono_font, size), relief="flat", highlightthickness=1, highlightbackground="#cbd7e6")
        scroll = ttk.Scrollbar(host, orient="vertical", command=field.yview)
        field.configure(yscrollcommand=scroll.set)
        field.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        return field

    @staticmethod
    def write(field, value, readonly=False):
        field.configure(state="normal")
        field.delete("1.0", "end")
        field.insert("1.0", value)
        if readonly:
            field.configure(state="disabled")

    @staticmethod
    def table(parent, row, columns, height=6):
        host = ttk.Frame(parent)
        host.grid(row=row, column=0, sticky="nsew", pady=(3, 7))
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)
        table = ttk.Treeview(host, columns=[key for key, _, _ in columns], show="headings", selectmode="browse", height=height)
        for key, label, width in columns:
            table.heading(key, text=label, anchor="w")
            table.column(key, width=width, minwidth=66, anchor="w", stretch=key == columns[0][0])
        scroll = ttk.Scrollbar(host, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        table.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        return table

    def jobs_page(self):
        frame = self.base("작업 대시보드", "실행 경로와 작업 상태를 확인하고, 검증된 변경의 병합을 승인합니다.")
        frame.rowconfigure(3, weight=2)
        frame.rowconfigure(6, weight=3)
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=2, column=0, sticky="ew")
        self.button(toolbar, "새 작업", lambda: self.show("submit"), True)
        self.button(toolbar, "중지", lambda: self.job_action("cancel"))
        self.button(toolbar, "재시도", lambda: self.job_action("retry"))
        self.button(toolbar, "도구 승인 검토", self.tool_decision)
        self.button(toolbar, "병합 승인", lambda: self.job_action("merge"))
        self.jobs = self.table(frame, 3, (("title", "작업", 295), ("state", "상태", 135),
                                         ("mode", "실행 모드", 100), ("updated", "갱신", 140)))
        self.jobs.bind("<<TreeviewSelect>>", self.job_selected)
        toolbar2 = ttk.Frame(frame)
        toolbar2.grid(row=4, column=0, sticky="ew")
        self.button(toolbar2, "JSON 보고서 저장", self.export_report)
        self.button(toolbar2, "결과 폴더 열기", self.open_artifacts)
        self.button(toolbar2, "Supervisor 종료", self.stop_supervisor, side="right")
        self.button(toolbar2, "Supervisor 시작", self.restart_supervisor, side="right")
        self.detail_title = ttk.Label(frame, text="작업 상세", style="Section.TLabel")
        self.detail_title.grid(row=5, column=0, sticky="w", pady=(9, 2))
        self.detail = self.text(frame, 6)
        self.write(self.detail, "작업을 선택하면 상태와 실행 이벤트가 표시됩니다.", True)
        return frame

    def submit_page(self):
        frame = self.base("새 작업", "저장소, 대상 브랜치, DAG 노드, 허용 경로, QA 명령을 작업 정의에 입력합니다.")
        frame.rowconfigure(3, weight=1)
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=2, column=0, sticky="ew")
        self.button(toolbar, "작업 제출", self.submit, True)
        self.button(toolbar, "저장소 선택", self.pick_repo)
        self.button(toolbar, "JSON 열기", lambda: self.import_file(self.plan))
        self.button(toolbar, "기본 작업 불러오기", lambda: self.write(self.plan, formatted(sample_plan())))
        self.plan = self.text(frame, 3)
        self.write(self.plan, formatted(sample_plan()))
        return frame

    def registry_page(self):
        frame = self.base("모델 및 실행 설정", "Provider, Model, Runtime, Harness, MCP를 각각 등록합니다.")
        frame.rowconfigure(3, weight=1)
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=2, column=0, sticky="ew")
        self.button(toolbar, "설정 저장", self.save_registry, True)
        self.button(toolbar, "저장된 설정 열기", lambda: self.write(self.registry, formatted(read_config(self.root))))
        self.button(toolbar, "JSON 가져오기", lambda: self.import_file(self.registry))
        self.registry = self.text(frame, 3)
        return frame

    def mcp_page(self):
        frame = self.base("MCP 연결", "기존 CLI 설정을 탐색하고 선택한 연결의 Gateway 전환과 롤백을 관리합니다.")
        frame.rowconfigure(3, weight=2)
        frame.rowconfigure(5, weight=1)
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew")
        self.button(bar, "사용자 설정 탐색", lambda: self.scan(None), True)
        self.button(bar, "프로젝트 탐색", self.scan_project_folder)
        self.button(bar, "Gateway 전환", self.migrate_binding)
        self.button(bar, "롤백", self.rollback_binding)
        self.button(bar, "Gateway 감사", self.gateway_audit)
        self.connections = self.table(frame, 3, (("name", "서버", 190), ("client", "CLI", 95),
                                                 ("scope", "범위", 85), ("mode", "모드", 100),
                                                 ("transport", "Transport", 100), ("duplicate", "충돌 후보", 100)))
        self.connections.bind("<<TreeviewSelect>>", self.binding_selected)
        ttk.Label(frame, text="연결 상세", style="Section.TLabel").grid(row=4, column=0, sticky="w", pady=(8, 2))
        self.binding = self.text(frame, 5)
        self.write(self.binding, "설정 탐색을 시작하세요.", True)
        return frame

    def action(self, body):
        try:
            return body()
        except (ValueError, OSError, RuntimeError, TypeError) as error:
            messagebox.showerror("Model Orchestration", str(error), parent=self.window)

    def background(self, body, done):
        def work():
            try:
                self.results.put((done, body(), None))
            except Exception as error:
                self.results.put((done, None, error))
        threading.Thread(target=work, daemon=True).start()

    def pick_repo(self):
        folder = filedialog.askdirectory(parent=self.window, title="Git 저장소 선택")
        if folder:
            def apply():
                plan = json.loads(self.plan.get("1.0", "end-1c"))
                plan["repo"] = str(Path(folder).resolve())
                self.write(self.plan, formatted(plan))
            self.action(apply)

    def import_file(self, target):
        filename = filedialog.askopenfilename(parent=self.window, filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if filename:
            self.action(lambda: self.write(target, Path(filename).read_text(encoding="utf-8-sig")))

    def save_registry(self):
        def save():
            cfg = config_check(json.loads(self.registry.get("1.0", "end-1c")))
            atomic_json(self.root / "registry.json", cfg)
            self.write(self.registry, formatted(cfg))
            self.notifications = cfg["settings"].get("notifications", False)
            if cfg["settings"].get("background") or any(row.get("gateway_token_env") for row in cfg["mcp"].values()):
                self.restart_supervisor()
            messagebox.showinfo("저장 완료", str(self.root / "registry.json"), parent=self.window)
        self.action(save)

    def submit(self):
        def enqueue():
            cfg = read_config(self.root)
            plan = plan_check(json.loads(self.plan.get("1.0", "end-1c")), cfg)
            needs_model = any(task["role"] != "qa" or not task.get("qa") or
                              {"model", "harness"} & task.keys() for task in plan["tasks"])
            require(not needs_model or cfg["models"], "모델 및 실행 설정에서 모델을 등록하세요.")
            if any(task.get("qa") for task in plan["tasks"]) or plan.get("qa"):
                if not messagebox.askyesno("QA 명령 실행", "작업 정의의 QA 명령을 Worktree에서 실행하시겠습니까?", parent=self.window):
                    return
            job = self.store.submit(plan, cfg, None if plan.get("background") else self.token)
            self.store.attach_foreground(job, self.token)
            self.restart_supervisor()
            self.show("jobs")
            self.jobs.selection_set(job)
            self.jobs.focus(job)
            self.job_selected()
        self.action(enqueue)

    def refresh_jobs(self):
        rows = self.store.list_jobs()
        current_states = {row["id"]: row["state"] for row in rows}
        if self.notifications and self.notice_states is not None:
            changes = [STATES[state] for job, state in current_states.items()
                       if state != self.notice_states.get(job)
                       and state in ("FAILED", "SUCCEEDED", "MERGED", "AWAITING_TOOL", "AWAITING_APPROVAL")]
            if changes:
                self.notice(changes[0] if len(changes) == 1 else f"작업 상태 변경 {len(changes)}건")
        self.notice_states = current_states
        values = [(row["id"], row["plan"]["title"], STATES.get(row["state"], row["state"]),
                   "백그라운드" if row["plan"].get("background") else "포그라운드",
                   datetime.fromtimestamp(row["updated"]).strftime("%m-%d %H:%M:%S")) for row in rows]
        if values != self.job_cache:
            self.job_cache = values
            selected = self.selected_job
            self.jobs.delete(*self.jobs.get_children())
            for key, *data in values:
                self.jobs.insert("", "end", iid=key, values=data)
            if selected and self.jobs.exists(selected):
                self.jobs.selection_set(selected)
        if not self.selected_job:
            return
        job = self.store.job(self.selected_job)
        if not job:
            return
        rows = self.store.tasks(job["id"])
        state = STATES.get(job["state"], job["state"])
        self.detail_title.configure(text=f'{job["plan"]["title"]}  ·  {state}')
        updates = self.store.events(job["id"], self.last_seq, 250)
        if updates:
            self.last_seq = updates[-1]["seq"]
            for item in updates:
                clock = datetime.fromtimestamp(item["timestamp"]).strftime("%H:%M:%S")
                task = item["task_id"] or "job"
                route = "/".join(item[key] for key in ("model_id", "harness_id") if item[key])
                self.events_cached[item["seq"]] = f"{clock}  {task}  {route}  {item['event_type']}  {json.dumps(item['payload'], ensure_ascii=False)}"
            self.events_cached = dict(list(self.events_cached.items())[-350:])
        if updates or not self.detail.get("1.0", "end-1c"):
            states = "\n".join(f'{key}   {STATES.get(row["state"], row["state"])}   시도 {row["attempt"]}' for key, row in rows.items())
            self.write(self.detail, states + "\n\n" + "\n".join(self.events_cached.values()), True)
            self.detail.see("end")

    def notice(self, text):
        banner = tk.Toplevel(self.window)
        banner.title("Model Orchestration")
        banner.resizable(False, False)
        banner.attributes("-topmost", True)
        banner.geometry("260x92")
        ttk.Label(banner, text=text, style="Section.TLabel").pack(padx=12, pady=23)
        banner.after(5000, banner.destroy)

    def job_selected(self, *_):
        selected = self.jobs.selection()
        if selected and self.selected_job != selected[0]:
            self.selected_job = selected[0]
            self.last_seq = 0
            self.events_cached = {}
            self.write(self.detail, "", True)
            self.refresh_jobs()

    def get_job(self):
        require(self.selected_job, "작업을 먼저 선택하세요.")
        job = self.store.job(self.selected_job)
        require(job, "작업을 찾을 수 없습니다.")
        return job

    def job_action(self, action):
        def apply():
            job = self.get_job()
            candidate = None
            if action == "merge":
                candidate = (job["result"] or {}).get("candidate")
                require(job["state"] == "AWAITING_APPROVAL" and candidate, "통합 QA를 통과한 후보가 필요합니다.")
                if not messagebox.askyesno("Git 병합 승인", f'{job["plan"]["target"]}에 다음 커밋을 병합하시겠습니까?\n\n{candidate}', parent=self.window):
                    return
            if action == "cancel" and not messagebox.askyesno("작업 중지", "선택한 작업을 중지하시겠습니까?", parent=self.window):
                return
            self.store.request(job["id"], action, candidate,
                               approval_revision=(job["result"] or {}).get("approval_revision") if candidate else None)
            if action != "cancel":
                self.store.attach_foreground(job["id"], self.token)
                self.restart_supervisor()
            self.refresh_jobs()
        self.action(apply)

    def tool_decision(self):
        def review():
            job = self.get_job()
            require(job["state"] == "AWAITING_TOOL", "도구 승인을 대기 중인 작업을 선택하세요.")
            pending = self.store.approvals(job["id"])
            for item in pending:
                dialog = tk.Toplevel(self.window)
                dialog.title("외부 도구 쓰기 승인")
                dialog.geometry("680x420")
                dialog.transient(self.window)
                dialog.grab_set()
                dialog.rowconfigure(1, weight=1)
                dialog.columnconfigure(0, weight=1)
                ttk.Label(dialog, text=f'{item["task"]}  /  {item["tool"]}', style="Section.TLabel").grid(
                    row=0, column=0, sticky="w", padx=10, pady=8)
                field = self.text(dialog, 1)
                self.write(field, formatted(item["args"]), True)
                bar = ttk.Frame(dialog)
                bar.grid(row=2, column=0, sticky="ew", padx=8, pady=8)
                def finish(accept):
                    def change():
                        self.store.decide(job["id"], item["task"], item["key"], accept)
                        self.store.attach_foreground(job["id"], self.token)
                        self.restart_supervisor()
                        dialog.destroy()
                    self.action(change)
                self.button(bar, "이 호출 승인", lambda: finish(True), True)
                self.button(bar, "거절", lambda: finish(False))
                self.button(bar, "나중에", dialog.destroy)
                self.window.wait_window(dialog)
                break
        self.action(review)

    def export_report(self):
        def export():
            job = self.get_job()
            filename = filedialog.asksaveasfilename(parent=self.window, defaultextension=".json", initialfile=f'{job["id"]}.json',
                                                    filetypes=[("JSON", "*.json")])
            if filename:
                atomic_json(Path(filename), self.store.report(job["id"]))
        self.action(export)

    def open_artifacts(self):
        def open_result():
            job = self.get_job()
            path = self.root / "artifacts" / job["id"]
            require(path.is_dir(), "저장된 작업 결과가 없습니다.")
            open_directory(path)
        self.action(open_result)

    def scan_project_folder(self):
        folder = filedialog.askdirectory(parent=self.window, title="프로젝트 폴더 선택")
        if folder:
            self.scan(folder)

    def scan(self, folder):
        def done(result):
            records, failures = result
            journals = self.root / "migrations"
            migrated = set()
            if journals.is_dir():
                for file in journals.glob("*/migration.json"):
                    try:
                        item = json.loads(file.read_text(encoding="utf-8"))
                        if item["state"] == "applied":
                            migrated.add((item["path"], "orchestra_" + item["profile"].replace(".", "_").replace("-", "_")))
                    except (OSError, ValueError, KeyError):
                        continue
            self.scan_project, self.scanned = folder, records
            self.connections.delete(*self.connections.get_children())
            for i, item in enumerate(records):
                mode = "Managed" if (item["path"], item["name"]) in migrated else item["mode"]
                self.connections.insert("", "end", iid=str(i), values=(item["name"], item["client"], item["scope"],
                                        mode, item["transport"], item["alternatives"] + item["duplicates"]))
            self.write(self.binding, f"발견된 연결 {len(records)}개\n" + (formatted(failures) if failures else ""), True)
        self.background(lambda: discover(folder), done)

    def binding_selected(self, *_):
        selection = self.connections.selection()
        if selection:
            self.write(self.binding, formatted(self.scanned[int(selection[0])]), True)

    def migrate_binding(self):
        def request():
            selected = self.connections.selection()
            require(selected, "전환할 연결을 선택하세요.")
            record = self.scanned[int(selected[0])]
            cfg = read_config(self.root)
            profile = simpledialog.askstring("Gateway 프로파일", "등록된 MCP 프로파일 ID", parent=self.window)
            if not profile:
                return
            tool = simpledialog.askstring("읽기 전용 Probe", "등록된 원본 읽기 도구 이름", parent=self.window)
            if not tool:
                return
            entered = simpledialog.askstring("Probe 인자", "JSON 객체", initialvalue="{}", parent=self.window)
            if entered is None:
                return
            args = json.loads(entered)
            if not messagebox.askyesno("MCP 전환 승인", f'{record["path"]}\n\n{record["name"]} 연결을 Gateway로 전환하시겠습니까?', parent=self.window):
                return
            folder = self.scan_project
            def done(key):
                messagebox.showinfo("Gateway 전환 완료", "롤백 ID\n" + key, parent=self.window)
                self.scan(folder)
            self.background(lambda: migrate(self.root, cfg, record, profile, tool, args, folder), done)
        self.action(request)

    def rollback_binding(self):
        key = simpledialog.askstring("MCP 롤백", "전환 기록의 롤백 ID", parent=self.window)
        if key and messagebox.askyesno("MCP 롤백 승인", "이 전환의 원본 설정을 다시 적용하시겠습니까?", parent=self.window):
            def perform():
                rollback(self.root, key)
                self.scan(self.scan_project)
            self.action(perform)

    def gateway_audit(self):
        profile = simpledialog.askstring("Gateway 감사", "등록된 MCP 프로파일 ID", parent=self.window)
        if profile:
            self.write(self.binding, formatted(self.store.events("gateway:" + profile)), True)

    def restart_supervisor(self):
        self.suppress_restart = False
        self.launch_attempt = 0

    def stop_supervisor(self):
        if messagebox.askyesno("Supervisor 종료", "실행 중인 작업을 중단하고 Supervisor를 종료하시겠습니까?", parent=self.window):
            self.suppress_restart = True
            (self.root / "supervisor.stop").touch()

    def tick(self):
        try:
            self.store.presence(self.token)
            status_path = self.root / "supervisor.json"
            status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
            active = time.time() - status.get("at", 0) < 5
            if active:
                suffix = " · Gateway 연결됨" if status.get("gateway") else ""
                if status.get("gateway_error"):
                    suffix = "\n" + status["gateway_error"]
                self.status.configure(text="Supervisor 실행 중" + suffix)
            else:
                note = "Supervisor 종료됨" if self.suppress_restart else "Supervisor 연결 중"
                self.status.configure(text=note)
                if not self.suppress_restart and time.monotonic() - self.launch_attempt > 5:
                    self.launch_attempt = time.monotonic()
                    start_supervisor(self.root)
            if self.view == "jobs" or self.notifications:
                self.refresh_jobs()
            while not self.results.empty():
                callback, result, error = self.results.get_nowait()
                if error:
                    messagebox.showerror("Model Orchestration", str(error), parent=self.window)
                else:
                    callback(result)
        except (OSError, ValueError):
            self.status.configure(text="Supervisor 상태 갱신 중")
        finally:
            self.window.after(900, self.tick)

    def close(self):
        self.store.presence(self.token, active=False)
        self.window.destroy()


def launch(root):
    prepare_dpi()
    window = tk.Tk()
    from .workspace_desktop import WorkspaceDesktop

    WorkspaceDesktop(window, root)
    window.mainloop()
