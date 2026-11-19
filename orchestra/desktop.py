from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
import uuid
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .core import atomic_json, config_check, plan_check, require
from .discovery import discover, migrate, rollback
from .execution_state import MERGE_EVIDENCE, merge_candidate_ready, task_stage
from .platform.desktop import open_directory, prepare_dpi
from .processes import env_for_process, run as run_process
from .store import Store
from .supervisor import read_config, start_supervisor
from .ui import (
    NAV_GROUPS,
    Card,
    StatusBadge,
    THEMES,
    apply_ttk_theme,
    approval_state_info,
    resolve_fonts,
    state_label,
    style_text_widget,
    t,
)
from .ui.strings import STATES_I18N

_DEFAULT_PALETTE = THEMES["dark"]
BG, PANEL = _DEFAULT_PALETTE["canvas"], _DEFAULT_PALETTE["panel"]
TEXT, MUTED = _DEFAULT_PALETTE["text"], _DEFAULT_PALETTE["muted"]
NAV, NAV_ACTIVE, BLUE = _DEFAULT_PALETTE["sidebar"], _DEFAULT_PALETTE["active"], _DEFAULT_PALETTE["accent"]
STATES = STATES_I18N["ko"]


def formatted(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def changed_files(rows):
    return sorted({path for row in rows.values() for path in (row["result"] or {}).get("changed", [])})


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
        self.locale = "ko"
        self.theme_name = self._load_theme_pref()
        self.palette = THEMES[self.theme_name]
        self.pages = {}
        self.nav_buttons = {}
        self.nav_indicators = {}
        self._text_widgets = []
        self._themed_cards = []
        self.window.title("Model Orchestration")
        self.window.geometry("1280x820")
        self.window.minsize(920, 630)
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

    def _prefs_path(self) -> Path:
        return self.root / "ui_prefs.json"

    def _load_theme_pref(self) -> str:
        try:
            path = self._prefs_path()
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("theme") in THEMES:
                    return data["theme"]
        except (OSError, ValueError, TypeError):
            pass
        return "dark"

    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.palette = THEMES[self.theme_name]
        try:
            atomic_json(self._prefs_path(), {"theme": self.theme_name})
        except OSError:
            pass
        self.style()
        self.apply_theme_widgets()

    def style(self):
        self.ui_font, self.mono_font = resolve_fonts(self.window)
        self.palette = apply_ttk_theme(self.window, self.theme_name, self.ui_font, self.mono_font)

    def apply_theme_widgets(self):
        p = self.palette
        if hasattr(self, "nav_frame"):
            self.nav_frame.configure(bg=p["sidebar"], highlightbackground=p["sidebar_border"])
            self.brand_box.configure(bg=p["sidebar"])
            self.brand_title.configure(bg=p["sidebar"], fg=p["text"] if self.theme_name == "light" else "#ffffff")
            self.brand_sub.configure(bg=p["sidebar"], fg=p["nav_muted"])
            self.nav_scroll_canvas.configure(bg=p["sidebar"])
            self.nav_inner.configure(bg=p["sidebar"])
            for lbl in getattr(self, "_nav_group_labels", []):
                lbl.configure(bg=p["sidebar"], fg=p["nav_muted"])
            for key, row in getattr(self, "nav_rows", {}).items():
                active = key == self.view
                bg = p["active"] if active else p["sidebar"]
                fg = p["nav_active_fg"] if active else p["nav_fg"]
                row.configure(bg=bg)
                self.nav_buttons[key].configure(bg=bg, fg=fg, activebackground=p["hover"], activeforeground=p["nav_active_fg"])
                self.nav_indicators[key].configure(bg=p["accent"] if active else bg)
            self.sidebar_footer.configure(bg=p["sidebar"], highlightbackground=p["sidebar_border"])
            self.status.configure(bg=p["sidebar"], fg=p["muted"])
        if hasattr(self, "header_bar"):
            self.header_bar.configure(bg=p["header"], highlightbackground=p["border"])
            self.header_left.configure(bg=p["header"])
            self.header_right.configure(bg=p["header"])
            if hasattr(self, "theme_btn"):
                label = t("header.theme_light", self.locale) if self.theme_name == "dark" else t("header.theme_dark", self.locale)
                self.theme_btn.configure(text=label)
        for widget in list(self._text_widgets):
            if widget.winfo_exists():
                style_text_widget(widget, p, self.mono_font)
            else:
                self._text_widgets.remove(widget)
        for card in list(self._themed_cards):
            if card.winfo_exists():
                card.apply_palette(p)
            else:
                self._themed_cards.remove(card)
        self._apply_badge_themes()

    def _apply_badge_themes(self):
        p = self.palette
        if hasattr(self, "header_supervisor_badge"):
            self.header_supervisor_badge.set_status(self.header_supervisor_badge.cget("text"), tone=self.header_supervisor_badge._tone, palette=p)
        if hasattr(self, "header_workers_badge"):
            self.header_workers_badge.set_status(self.header_workers_badge.cget("text"), tone=self.header_workers_badge._tone, palette=p)
        if hasattr(self, "header_notice_badge"):
            self.header_notice_badge.set_status(self.header_notice_badge.cget("text"), tone=self.header_notice_badge._tone, palette=p)

    def layout(self):
        p = self.palette
        self.window.columnconfigure(0, weight=0)
        self.window.columnconfigure(1, weight=1)
        self.window.rowconfigure(0, weight=1)

        # Left Navigation Sidebar
        self.nav_frame = tk.Frame(
            self.window, bg=p["sidebar"], width=252,
            highlightthickness=1, highlightbackground=p["sidebar_border"], bd=0,
        )
        self.nav_frame.grid(row=0, column=0, sticky="nsew")
        self.nav_frame.grid_propagate(False)
        self.nav_frame.rowconfigure(1, weight=1)
        self.nav_frame.columnconfigure(0, weight=1)

        self.brand_box = tk.Frame(self.nav_frame, bg=p["sidebar"], padx=14, pady=15)
        self.brand_box.grid(row=0, column=0, sticky="ew")
        self.brand_title = tk.Label(
            self.brand_box, text=t("app.brand", self.locale), anchor="w", justify="left",
            bg=p["sidebar"], fg="#ffffff" if self.theme_name == "dark" else p["text"],
            font=(self.ui_font, 11, "bold"),
        )
        self.brand_title.pack(fill="x")
        self.brand_sub = tk.Label(
            self.brand_box, text=t("app.subtitle", self.locale), anchor="w",
            bg=p["sidebar"], fg=p["nav_muted"], font=(self.ui_font, 9),
        )
        self.brand_sub.pack(fill="x", pady=(2, 0))

        self.nav_scroll_canvas = tk.Canvas(self.nav_frame, bg=p["sidebar"], highlightthickness=0, bd=0)
        self.nav_scroll_canvas.grid(row=1, column=0, sticky="nsew")
        self.nav_inner = tk.Frame(self.nav_scroll_canvas, bg=p["sidebar"])
        self._nav_canvas_win = self.nav_scroll_canvas.create_window((0, 0), window=self.nav_inner, anchor="nw")
        self.nav_scroll_canvas.bind(
            "<Configure>",
            lambda e: self.nav_scroll_canvas.itemconfigure(self._nav_canvas_win, width=e.width),
        )
        self.nav_inner.bind(
            "<Configure>",
            lambda _e: self.nav_scroll_canvas.configure(scrollregion=self.nav_scroll_canvas.bbox("all")),
        )

        navigation = self.navigation()
        page_map = {key: (label, factory) for key, label, factory in navigation}
        self._nav_group_labels = []
        self.nav_rows = {}

        if all(key in page_map for group_items in NAV_GROUPS for key, _ in group_items[1]):
            for group_name, items in NAV_GROUPS:
                glbl = tk.Label(
                    self.nav_inner, text=group_name, anchor="w",
                    bg=p["sidebar"], fg=p["nav_muted"], font=(self.ui_font, 8, "bold"),
                )
                glbl.pack(fill="x", padx=18, pady=(10, 3))
                self._nav_group_labels.append(glbl)
                for key, label_key in items:
                    self._add_nav_item(key, t(label_key, self.locale))
        else:
            for key, label, _ in navigation:
                if label:
                    self._add_nav_item(key, label)

        self.sidebar_footer = tk.Frame(
            self.nav_frame, bg=p["sidebar"], padx=14, pady=12,
            highlightthickness=1, highlightbackground=p["sidebar_border"], bd=0,
        )
        self.sidebar_footer.grid(row=2, column=0, sticky="ew")
        self.status = tk.Label(
            self.sidebar_footer, text=t("header.supervisor_connecting", self.locale),
            anchor="w", justify="left", bg=p["sidebar"], fg=p["muted"],
            font=(self.ui_font, 9), wraplength=220,
        )
        self.status.pack(fill="x")

        # Right Main Area: Header + Stacked Pages
        self.main_shell = ttk.Frame(self.window)
        self.main_shell.grid(row=0, column=1, sticky="nsew")
        self.main_shell.columnconfigure(0, weight=1)
        self.main_shell.rowconfigure(1, weight=1)

        self.header_bar = tk.Frame(
            self.main_shell, bg=p["header"], height=52,
            highlightthickness=1, highlightbackground=p["border"], bd=0,
        )
        self.header_bar.grid(row=0, column=0, sticky="ew")
        self.header_bar.grid_propagate(False)
        self.header_bar.columnconfigure(0, weight=1)
        self.header_bar.rowconfigure(0, weight=1)

        self.header_left = tk.Frame(self.header_bar, bg=p["header"], padx=18)
        self.header_left.grid(row=0, column=0, sticky="w")
        self.header_right = tk.Frame(self.header_bar, bg=p["header"], padx=16)
        self.header_right.grid(row=0, column=1, sticky="e")

        self.header_supervisor_badge = StatusBadge(
            self.header_right, p, text=t("header.supervisor_connecting", self.locale),
            tone="warning", ui_font=self.ui_font,
        )
        self.header_supervisor_badge.pack(side="left", padx=(0, 6))
        self.header_workers_badge = StatusBadge(
            self.header_right, p, text="Worker 0", tone="neutral", ui_font=self.ui_font,
        )
        self.header_workers_badge.pack(side="left", padx=(0, 6))
        self.header_notice_badge = StatusBadge(
            self.header_right, p, text="알림 0", tone="neutral", ui_font=self.ui_font,
        )
        self.header_notice_badge.pack(side="left", padx=(0, 8))
        self.header_notice_badge.bind("<Button-1>", lambda _e: self.show("jobs"))

        theme_label = t("header.theme_light", self.locale) if self.theme_name == "dark" else t("header.theme_dark", self.locale)
        self.theme_btn = ttk.Button(self.header_right, text=theme_label, style="Subtle.TButton", command=self.toggle_theme)
        self.theme_btn.pack(side="left", padx=(0, 6))

        ttk.Button(
            self.header_right, text=t("header.new_task", self.locale),
            style="Primary.TButton", command=lambda: self.show("submit"),
        ).pack(side="left")

        self.host = ttk.Frame(self.main_shell, padding=(22, 16, 22, 18))
        self.host.grid(row=1, column=0, sticky="nsew")
        self.host.rowconfigure(0, weight=1)
        self.host.columnconfigure(0, weight=1)

        for key, _, factory in navigation:
            self.pages[key] = factory()
            self.pages[key].grid(row=0, column=0, sticky="nsew")

    def _add_nav_item(self, key: str, label: str):
        p = self.palette
        row = tk.Frame(self.nav_inner, bg=p["sidebar"])
        row.pack(fill="x", padx=10, pady=1)
        indicator = tk.Frame(row, bg=p["sidebar"], width=3)
        indicator.pack(side="left", fill="y")
        btn = tk.Button(
            row, text=label, anchor="w", padx=11, pady=7,
            bg=p["sidebar"], fg=p["nav_fg"], bd=0,
            activebackground=p["hover"], activeforeground=p["nav_active_fg"],
            cursor="hand2", relief="flat", highlightthickness=0,
            font=(self.ui_font, 10),
            command=lambda name=key: self.show(name),
        )
        btn.pack(side="left", fill="x", expand=True)
        self.nav_rows[key] = row
        self.nav_buttons[key] = btn
        self.nav_indicators[key] = indicator

    def navigation(self):
        return (
            ("jobs", "작업 대시보드", self.jobs_page),
            ("submit", "새 작업", self.submit_page),
            ("registry", "모델 및 실행 설정", self.registry_page),
            ("mcp", "MCP 연결", self.mcp_page),
        )

    def show(self, key):
        self.view = key
        self.pages[key].tkraise()
        p = self.palette
        for name, button in self.nav_buttons.items():
            active = key == name
            bg = p["active"] if active else p["sidebar"]
            fg = p["nav_active_fg"] if active else p["nav_fg"]
            button.configure(bg=bg, fg=fg)
            if name in self.nav_rows:
                self.nav_rows[name].configure(bg=bg)
            if name in self.nav_indicators:
                self.nav_indicators[name].configure(bg=p["accent"] if active else bg)
        if key == "registry" and not self.registry.get("1.0", "end-1c").strip():
            self.write(self.registry, formatted(read_config(self.root)))
        if key == "jobs":
            self.refresh_jobs()

    def base(self, title, description):
        frame = ttk.Frame(self.host)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=title, style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=description, style="Subheading.TLabel").grid(row=1, column=0, sticky="w", pady=(3, 12))
        return frame

    @staticmethod
    def button(parent, text, command, primary=False, side="left", danger=False, subtle=False):
        style_name = "Primary.TButton" if primary else "Danger.TButton" if danger else "Subtle.TButton" if subtle else "TButton"
        button = ttk.Button(parent, text=text, command=command, style=style_name)
        button.pack(side=side, padx=(0, 6), pady=3)
        return button

    def text(self, parent, row, *, size=10, height=None):
        host = ttk.Frame(parent)
        host.grid(row=row, column=0, sticky="nsew", pady=(3, 0))
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)
        kwargs = {
            "wrap": "word", "undo": True, "padx": 12, "pady": 10,
            "font": (self.mono_font, size), "relief": "flat",
        }
        if height is not None:
            kwargs["height"] = height
        field = tk.Text(host, **kwargs)
        style_text_widget(field, self.palette, self.mono_font, size)
        self._text_widgets.append(field)
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
        frame.rowconfigure(7, weight=3)
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=2, column=0, sticky="ew")
        self.button(toolbar, "새 작업", lambda: self.show("submit"), True)
        self.button(toolbar, "중지", lambda: self.job_action("cancel"))
        self.button(toolbar, "재시도", lambda: self.job_action("retry"))
        self.button(toolbar, "도구 승인 검토", self.tool_decision)
        self.button(toolbar, "병합 승인", lambda: self.job_action("merge"))
        self.jobs = self.table(frame, 3, (
            ("title", "작업", 295), ("state", "상태", 135),
            ("mode", "실행 모드", 100), ("updated", "갱신", 140),
        ))
        self.jobs.bind("<<TreeviewSelect>>", self.job_selected)
        toolbar2 = ttk.Frame(frame)
        toolbar2.grid(row=4, column=0, sticky="ew")
        self.button(toolbar2, "JSON 보고서 저장", self.export_report)
        self.button(toolbar2, "결과 폴더 열기", self.open_artifacts)
        self.button(toolbar2, "Supervisor 종료", self.stop_supervisor, side="right")
        self.button(toolbar2, "Supervisor 시작", self.restart_supervisor, side="right")
        self.detail_title = ttk.Label(frame, text="작업 상세", style="Section.TLabel")
        self.detail_title.grid(row=5, column=0, sticky="w", pady=(9, 2))
        self.detail_evidence = ttk.Label(frame, style="Muted.TLabel", wraplength=620, justify="left")
        self.detail_evidence.grid(row=6, column=0, sticky="nw", pady=(2, 2))
        self.detail = self.text(frame, 7)
        self.write(self.detail, "작업을 선택하면 상태와 실행 이벤트가 표시됩니다.", True)
        return frame

    def submit_page(self):
        frame = self.base("고급 JSON 작업 편집", "저장소, 대상 브랜치, DAG 노드, 허용 경로, QA 명령을 JSON으로 직접 편집합니다.")
        frame.rowconfigure(3, weight=1)
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=2, column=0, sticky="ew")
        self.button(toolbar, "작업 제출", self.submit, True)
        self.button(toolbar, "저장소 선택", self.pick_repo)
        self.button(toolbar, "JSON 열기", lambda: self.import_file(self.plan))
        self.button(toolbar, "기본 작업 불러오기", lambda: self.write(self.plan, formatted(sample_plan())))
        if "submit" in self.pages:
            self.button(toolbar, "마법사로 돌아가기", lambda: self.show("submit"), side="right")
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
        frame = self.base(t("mcp.title", self.locale), t("mcp.desc", self.locale))
        frame.rowconfigure(3, weight=2)
        frame.rowconfigure(5, weight=1)
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 4))
        self.button(bar, "사용자 설정 탐색", lambda: self.scan(None), True)
        self.button(bar, "프로젝트 탐색", self.scan_project_folder)
        self.button(bar, "Gateway 전환", self.migrate_binding)
        self.button(bar, "롤백", self.rollback_binding)
        self.button(bar, "Gateway 감사", self.gateway_audit)
        self.connections = self.table(frame, 3, (
            ("name", "서버", 200), ("client", "CLI", 95),
            ("scope", "범위", 85), ("mode", "모드", 105),
            ("transport", "Transport", 105), ("duplicate", "충돌 후보", 95),
        ))
        self.connections.bind("<<TreeviewSelect>>", self.binding_selected)
        ttk.Label(frame, text="연결 상세", style="Section.TLabel").grid(row=4, column=0, sticky="w", pady=(8, 2))
        self.binding = self.text(frame, 5)
        self.write(self.binding, "사용자 또는 프로젝트 MCP 설정 탐색을 실행하면 연결 목록과 정책 상태가 표시됩니다.", True)
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
            changes = [state_label(state, self.locale) for job, state in current_states.items()
                       if state != self.notice_states.get(job)
                       and state in ("FAILED", "SUCCEEDED", "MERGED", "AWAITING_TOOL", "AWAITING_APPROVAL")]
            if changes:
                self.notice(changes[0] if len(changes) == 1 else f"작업 상태 변경 {len(changes)}건")
        self.notice_states = current_states
        pending_count = sum(1 for st in current_states.values() if st in ("AWAITING_TOOL", "AWAITING_APPROVAL"))
        if hasattr(self, "header_notice_badge"):
            self.header_notice_badge.set_status(
                f"승인 대기 {pending_count}" if pending_count else "알림 0",
                tone="warning" if pending_count else "neutral",
                palette=self.palette,
            )
        values = [(row["id"], row["plan"]["title"], state_label(row["state"], self.locale),
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
        state = state_label(job["state"], self.locale)
        self.detail_title.configure(text=f'{job["plan"]["title"]}  ·  {state}')
        result = (job["result"] or {}) if job["state"] in (*MERGE_EVIDENCE, "SUCCEEDED") else {}
        candidate = result.get("candidate")
        files = result["changed"] if "changed" in result else changed_files(rows)
        evidence = []
        if files:
            listed = ", ".join(files[:5])
            evidence.append(f"변경 파일 {len(files)}개 · {listed}" + (" 외" if len(files) > 5 else ""))
        if checks := result.get("qa"):
            evidence.append(f"통합 QA {len(checks)}개 통과")
        if candidate:
            evidence.append(f'병합 후보 {candidate[:12]} · {job["plan"]["target"]}')
        self.detail_evidence.configure(text="\n".join(evidence))
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
            stages = ((key, task_stage(job["state"], row["state"]), row["attempt"]) for key, row in rows.items())
            states = "\n".join(f'{key}   {state_label(stage, self.locale)}   시도 {attempt}' for key, stage, attempt in stages)
            top, bottom = self.detail.yview()
            self.write(self.detail, states + "\n\n" + "\n".join(self.events_cached.values()), True)
            if bottom >= .99:
                self.detail.see("end")
            else:
                self.detail.yview_moveto(top)

    def notice(self, text):
        p = self.palette
        banner = tk.Toplevel(self.window)
        banner.title("Model Orchestration")
        banner.resizable(False, False)
        banner.attributes("-topmost", True)
        banner.configure(bg=p["panel"])
        banner.geometry("290x96")
        tk.Label(banner, text=text, bg=p["panel"], fg=p["text"], font=(self.ui_font, 11, "bold"), wraplength=250).pack(padx=16, pady=24)
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
                job, tasks, events = self.store.status_snapshot(job["id"], 0, 0)
                require(merge_candidate_ready(job), "통합 QA를 통과한 후보가 필요합니다.")
                candidate = job["result"]["candidate"]
                decision = self.review_merge(job, tasks, events)
                if decision == "reject":
                    self.store.request(job["id"], "cancel")
                    self.refresh_jobs()
                    return
                if not decision:
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

    def diff_summary_for_job(self, job):
        """Read-only git diff --stat / diff summary for an integration worktree."""
        result = job.get("result") or {}
        candidate = result.get("candidate")
        base = result.get("base")
        repo_path = (job.get("plan") or {}).get("repo")
        integration = self.root / "worktrees" / job["id"] / "_integration"
        cwd = integration if integration.is_dir() else (Path(repo_path) if repo_path and Path(repo_path).is_dir() else None)
        if not cwd or not candidate or not base:
            return "통합 Worktree 또는 기준 SHA를 찾을 수 없어 변경 파일 목록만 표시합니다."
        code, stat_out = run_process(
            ["git", "-c", "core.fsmonitor=false", "-C", str(cwd), "diff", "--stat", "--no-ext-diff", base, candidate],
            env=env_for_process(), timeout=8, limit=200000,
        )
        code2, diff_out = run_process(
            ["git", "-c", "core.fsmonitor=false", "-C", str(cwd), "diff", "--no-ext-diff", base, candidate],
            env=env_for_process(), timeout=8, limit=300000,
        )
        parts = []
        if code == 0 and stat_out:
            parts.append(stat_out.decode("utf-8", errors="replace").strip())
        if code2 == 0 and diff_out:
            parts.append(diff_out.decode("utf-8", errors="replace").strip())
        return "\n\n".join(parts) or "표시할 diff 내용이 없습니다."

    def show_diff_dialog(self, job, parent=None):
        p = self.palette
        win = tk.Toplevel(parent or self.window)
        win.title("변경 사항 보기")
        win.geometry("760x520")
        win.configure(bg=p["canvas"])
        win.transient(parent or self.window)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)
        ttk.Label(win, text=f'{job["plan"]["title"]} · 변경 Diff', style="Section.TLabel").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 6))
        box = self.text(win, 1)
        box.master.grid(padx=14, pady=(0, 8))
        self.write(box, "diff를 불러오는 중…", True)
        bar = ttk.Frame(win, padding=(14, 6))
        bar.grid(row=2, column=0, sticky="ew")
        self.button(bar, "닫기", win.destroy, side="right")
        self.background(lambda: self.diff_summary_for_job(job), lambda text: self.write(box, text, True) if win.winfo_exists() else None)

    def review_merge(self, job, tasks, events=None):
        p = self.palette
        result = job["result"]
        dialog = tk.Toplevel(self.window)
        dialog.title("Git 병합 승인")
        dialog.geometry("800x560")
        dialog.configure(bg=p["canvas"])
        dialog.transient(self.window)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(2, weight=1)

        code_key, state_txt, tone, eligible, _blockers = approval_state_info(job, tasks, events)
        header = Card(dialog, p, padding=(14, 10))
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        top_row = tk.Frame(header.body, bg=p["panel"])
        top_row.pack(fill="x")
        StatusBadge(top_row, p, text=state_txt, tone=tone, ui_font=self.ui_font).pack(side="right", padx=(10, 0))
        tk.Label(
            top_row, text=job["plan"]["title"], bg=p["panel"], fg=p["text"],
            font=(self.ui_font, 12, "bold"), wraplength=540, justify="left", anchor="w",
        ).pack(side="left", fill="x", expand=True)
        tk.Label(
            header.body,
            text=f'저장소 {job["plan"].get("repo", "—")}  ·  대상 브랜치 {job["plan"]["target"]}  ·  후보 {result["candidate"][:12]}',
            bg=p["panel"], fg=p["muted"], font=(self.ui_font, 9), anchor="w",
        ).pack(fill="x", pady=(4, 0))

        qa_checks = result.get("qa", [])
        passed_cnt = sum(1 for c in qa_checks if c.get("exit_code") == 0)
        failed_cnt = len(qa_checks) - passed_cnt
        review_events = [e for e in (events or []) if e.get("event_type") == "review.result"]
        review_status = review_events[-1]["payload"].get("status", "미기록") if review_events else "해당 없음"

        kpi = ttk.Frame(dialog)
        kpi.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        files = result["changed"] if "changed" in result else changed_files(tasks)
        for idx, (lbl, val) in enumerate((
            ("통합 QA 통과", f"{passed_cnt}건"),
            ("통합 QA 실패", f"{failed_cnt}건"),
            ("독립 검토", str(review_status)),
            ("변경 파일", f"{len(files)}개"),
        )):
            kpi.columnconfigure(idx, weight=1, uniform="merge_kpi")
            c = Card(kpi, p, padding=(10, 8))
            c.grid(row=0, column=idx, sticky="ew", padx=(0 if idx == 0 else 6, 0))
            tk.Label(c.body, text=lbl, bg=p["panel"], fg=p["muted"], font=(self.ui_font, 8, "bold"), anchor="w").pack(fill="x")
            tk.Label(c.body, text=val, bg=p["panel"], fg=p["text"], font=(self.ui_font, 12, "bold"), anchor="w").pack(fill="x")

        notes = self.text(dialog, 2)
        notes.master.grid(padx=14, pady=(0, 6))
        revision = result.get("approval_revision") or "이전 실행 기록 (회차 ID 없음)"
        checks = [f'{index}. 통과 (종료 코드 {check["exit_code"]})' if check.get("exit_code") == 0
                  else f'{index}. 실패 (종료 코드 {check.get("exit_code")})'
                  for index, check in enumerate(qa_checks, 1)]
        lines = [
            "병합 신청 가능 · 실행 시 후보와 대상 브랜치를 다시 검증합니다.",
            f'대상 브랜치  {job["plan"]["target"]}',
            f'후보 SHA  {result["candidate"]}',
            f"QA 검증 회차  {revision}",
            "",
            "현재 통합 QA",
            *checks,
            "",
            "변경 파일",
            *[json.dumps(name, ensure_ascii=False) for name in files],
        ]
        self.write(notes, "\n".join(lines), True)

        buttons = ttk.Frame(dialog, padding=(14, 8))
        buttons.grid(row=3, column=0, sticky="ew")
        decision = None

        def approve():
            nonlocal decision
            decision = True
            dialog.destroy()

        def reject():
            nonlocal decision
            if messagebox.askyesno("병합 거절", "이 후보의 병합 승인을 거절하고 작업을 중지하시겠습니까?", parent=dialog):
                decision = "reject"
                dialog.destroy()

        approve_btn = self.button(buttons, "이 후보 승인", approve, True)
        if not eligible:
            approve_btn.state(["disabled"])
        self.button(buttons, "거절", reject, danger=True)
        self.button(buttons, "변경 사항 보기", lambda: self.show_diff_dialog(job, dialog))
        dismiss = self.button(buttons, "닫기", dialog.destroy, side="right")
        dialog.bind("<Escape>", lambda _: dialog.destroy())
        dialog.grab_set()
        dismiss.focus_set()
        dialog.wait_window()
        return decision

    def tool_decision(self):
        def review():
            job = self.get_job()
            require(job["state"] == "AWAITING_TOOL", "도구 승인을 대기 중인 작업을 선택하세요.")
            pending = self.store.approvals(job["id"])
            for item in pending:
                dialog = tk.Toplevel(self.window)
                dialog.title("외부 도구 쓰기 승인")
                dialog.geometry("680x420")
                dialog.configure(bg=self.palette["canvas"])
                dialog.transient(self.window)
                dialog.grab_set()
                dialog.rowconfigure(1, weight=1)
                dialog.columnconfigure(0, weight=1)
                ttk.Label(dialog, text=f'{item["task"]}  /  {item["tool"]}', style="Section.TLabel").grid(
                    row=0, column=0, sticky="w", padx=14, pady=10)
                field = self.text(dialog, 1)
                field.master.grid(padx=14)
                self.write(field, formatted(item["args"]), True)
                bar = ttk.Frame(dialog)
                bar.grid(row=2, column=0, sticky="ew", padx=14, pady=10)

                def finish(accept):
                    def change():
                        self.store.decide(job["id"], item["task"], item["key"], accept)
                        self.store.attach_foreground(job["id"], self.token)
                        self.restart_supervisor()
                        dialog.destroy()
                    self.action(change)

                self.button(bar, "이 호출 승인", lambda: finish(True), True)
                self.button(bar, "거절", lambda: finish(False), danger=True)
                self.button(bar, "나중에", dialog.destroy, side="right")
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
                self.connections.insert("", "end", iid=str(i), values=(
                    item["name"], item["client"], item["scope"],
                    mode, item["transport"], item["alternatives"] + item["duplicates"],
                ))
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
                self.status.configure(text=t("header.supervisor_running", self.locale) + suffix)
                if hasattr(self, "header_supervisor_badge"):
                    self.header_supervisor_badge.set_status("● Supervisor 실행 중", tone="success", palette=self.palette)
            else:
                note = t("header.supervisor_stopped", self.locale) if self.suppress_restart else t("header.supervisor_connecting", self.locale)
                self.status.configure(text=note)
                if hasattr(self, "header_supervisor_badge"):
                    self.header_supervisor_badge.set_status(
                        f"● {note}", tone="danger" if self.suppress_restart else "warning", palette=self.palette,
                    )
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
