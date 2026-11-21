"""Orca-inspired project-centric desktop workspace for the Model Orchestration Supervisor."""
from __future__ import annotations

import json
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from .core import require
from .desktop import Desktop, changed_files
from .execution_state import LIVE, MERGE_EVIDENCE, TERMINAL, merge_candidate_ready, task_stage
from .mcp import MCPClient, do_call, published
from .observability import EVENT_LABELS, agent_rows
from .supervisor import read_config
from .ui import (
    Card,
    EmptyState,
    MetricCard,
    StatusBadge,
    approval_state_info,
    state_label,
    t,
)
from .workspace import format_commands, parse_commands, read_workspace, registry_revision, save_registry
from .workspace_forms import Form, ProjectSettings, one_line, split_names
from .workspace_remote import RemoteWorkspace
from .workspace_context import WorkspaceContext
from .workspace_sessions import WorkspaceSessions
from .workspace_shell import IntegratedWorkspace
from .workspace_onboarding import WorkspaceOnboarding


class WorkspaceDesktop(WorkspaceOnboarding, IntegratedWorkspace, WorkspaceSessions, WorkspaceContext, ProjectSettings,
                       RemoteWorkspace, Desktop):
    initial_page = "workspace"

    def __init__(self, window, root, *, startup_locale=None):
        self.project_id = None
        self.remote_selected = None
        self.remote_cache = {}
        self.remote_pending = set()
        self.host_evidence = {}
        self.host_probes = {}
        self.tables = {}
        self.terminals = {}
        self.agent_job = None
        self.agent_task = None
        self.next_workspace_tick = 0
        self.agent_record = {}
        self.home_active_map = {}
        self._metric_cards = []
        self._inline_approval_job = None
        self._inline_diff_job = None
        self.registry_revision = registry_revision(root)
        super().__init__(window, root, startup_locale=startup_locale)
        self.window.geometry("1360x860")
        self.window.minsize(920, 630)

    def apply_theme_widgets(self):
        super().apply_theme_widgets()
        p = self.palette
        for card in self._metric_cards:
            if card.winfo_exists():
                card.apply_palette(p)
        if hasattr(self, "home_empty_card") and self.home_empty_card.winfo_exists():
            self.home_empty_card.apply_palette(p)
        for canvas_attr in ("graph", "detail_dag_canvas"):
            canvas = getattr(self, canvas_attr, None)
            if canvas and canvas.winfo_exists():
                canvas.configure(bg=p["graph_bg"])
        self.graph_version = None
        self._detail_dag_version = None
        if hasattr(self, "header_env_badge"):
            self.header_env_badge.set_status(self.header_env_badge.cget("text"), tone=self.header_env_badge._tone, palette=p)
        if hasattr(self, "detail_badge"):
            self.detail_badge.set_status(self.detail_badge.cget("text"), tone=self.detail_badge._tone, palette=p)
        if hasattr(self, "inline_approval_badge"):
            self.inline_approval_badge.set_status(self.inline_approval_badge.cget("text"), tone=self.inline_approval_badge._tone, palette=p)
        if hasattr(self, "wizard_draft"):
            if hasattr(self, "wiz_nodes_list"):
                from .ui import style_listbox_widget
                style_listbox_widget(self.wiz_nodes_list, p, self.ui_font, 10)
            if hasattr(self, "wiz_project_preview"):
                self.wiz_project_preview.configure(bg=p["elevated"], fg=p["text_secondary"])
        for _, terminals in self.terminals.values():
            for terminal in terminals:
                terminal.apply_palette(p)
        if self.view == "workspace":
            self.refresh_workspace()
        if self.view == "home":
            self.refresh_home()
        elif self.view == "jobs":
            self.refresh_jobs()
        elif self.view == "dag":
            self.refresh_graph()
        elif self.view == "settings":
            self.refresh_settings()

    def navigation(self):
        return (
            ("workspace", t("nav.workspace", self.locale), self.workspace_page),
            ("home", t("nav.home", self.locale), self.home_page),
            ("projects", t("nav.projects", self.locale), self.projects_page),
            ("jobs", t("nav.jobs", self.locale), self.jobs_page),
            ("agents", t("nav.agents", self.locale), self.agents_page),
            ("terminals", t("nav.terminals", self.locale), self.terminals_page),
            ("hosts", t("nav.hosts", self.locale), self.environments_page),
            ("ssh", t("nav.ssh", self.locale), self.ssh_page),
            ("mcp", t("nav.mcp", self.locale), self.mcp_page),
            ("providers", t("nav.providers", self.locale), self.providers_page),
            ("history", t("nav.history", self.locale), self.history_page),
            ("settings", t("nav.settings", self.locale), self.settings_page),
            ("dag", "", self.graph_page),
            ("submit", "", self.guided_page),
            ("advanced_plan", "", self.submit_page),
            ("registry", "", self.registry_page),
            ("remote_runs", "", self.remote_runs_page),
        )

    def layout(self):
        super().layout()
        p = self.palette
        tk.Label(
            self.header_left, text=self.w("프로젝트"), bg=p["header"], fg=p["muted"],
            font=(self.ui_font, 9, "bold"),
        ).pack(side="left", padx=(0, 8))
        self.sidebar_project = tk.StringVar(self.window, t("header.project_unselected", self.locale))
        self.sidebar_picker = ttk.Combobox(self.header_left, textvariable=self.sidebar_project, state="readonly", width=17)
        self.sidebar_picker.pack(side="left", padx=(0, 8))
        self.sidebar_picker.bind("<<ComboboxSelected>>", self.pick_sidebar)

        self.header_env_badge = StatusBadge(self.header_left, p, text=self.host_name(None),
                                            tone="neutral", ui_font=self.ui_font)
        self.header_env_badge.pack(side="left")

        self.build_workspace_sidebar()
        self.restore_workspace()
        self.window.bind("<Control-k>", lambda _: self.workspace_command_palette())
        self.window.bind("<Control-n>", lambda _: self.workspace_new_task() if self.view == "workspace" else self.show("submit"))
        self.window.bind("<Control-t>", lambda _: self.action(self.local_project_shell))
        self.window.bind("<Control-p>", lambda _: self.workspace_find_file())
        self.window.bind("<Control-Tab>", lambda _: self.workspace_switch_tab(1) if self.view == "workspace" else None)
        def previous_tab(_):
            if self.view == "workspace":
                self.workspace_switch_tab(-1)

        self.window.bind("<Control-Shift-Tab>", previous_tab)
        if self.window.tk.call("tk", "windowingsystem") == "x11":
            self.window.bind("<Control-ISO_Left_Tab>", previous_tab)
        self.action(self.refresh_sidebar)
        self.update_header_context()

    def update_header_context(self):
        p = self.palette
        if hasattr(self, "header_env_badge"):
            project = self.project_rows().get(self.project_id) if self.project_id else None
            env_name = self.host_name(project.get("host") if project else None)
            self.header_env_badge.set_status(
                env_name if len(env_name) <= 24 else env_name[:23] + "…",
                tone="running" if project and project.get("host") else "neutral",
                palette=p,
            )
        if hasattr(self, "header_workers_badge"):
            ws = read_workspace(self.root)
            hosts = ws.get("hosts", {})
            live_workers = sum(1 for key in hosts if self.host_evidence.get(key, {}).get("worker"))
            self.header_workers_badge.set_status(
                f"Worker {live_workers}/{len(hosts)}" if hosts else self.w("로컬 Worker"),
                tone="success" if live_workers else "neutral",
                palette=p,
            )

    def refresh_sidebar(self):
        if not hasattr(self, "sidebar_picker"):
            return
        self.sidebar_items = {f'{profile["name"][:25]} · {key[:5]}': key for key, profile in self.project_rows().items()}
        self.sidebar_picker.configure(values=list(self.sidebar_items))
        self.sidebar_project.set(next((name for name, key in self.sidebar_items.items() if key == self.project_id), t("header.project_unselected", self.locale)))
        self.update_header_context()

    def pick_sidebar(self, _=None):
        key = self.sidebar_items.get(self.sidebar_project.get())
        if key:
            if self.view == "workspace":
                self.select_workspace_project(key)
                return
            self.project_id = key
            self.update_header_context()
            if self.view == "submit" and hasattr(self, "_wizard_sync_projects"):
                self._wizard_sync_projects()
            else:
                self.show("projects")
                self.open_project(key)

    def show(self, key):
        if key == "registry" and not self.registry.get("1.0", "end-1c").strip():
            self.action(self.reload_registry)
        super().show(key)
        self.workspace_show(key == "workspace")
        work = {
            "home": self.refresh_home,
            "projects": self.refresh_projects,
            "agents": self.refresh_agents,
            "dag": self.refresh_graph,
            "hosts": self.refresh_hosts,
            "ssh": self.refresh_ssh,
            "providers": self.refresh_providers,
            "history": self.refresh_history,
            "settings": self.refresh_settings,
            "remote_runs": self.refresh_remote,
            "submit": self._wizard_sync_projects,
        }.get(key)
        if work:
            self.action(work)

    def fill(self, table, rows, selected=None):
        current = tuple((key, tuple(map(str, data))) for key, data in rows)
        if self.tables.get(table) != current:
            self.tables[table] = current
            keep = set()
            for index, (key, values) in enumerate(current):
                keep.add(key)
                if table.exists(key):
                    table.item(key, values=values)
                    table.move(key, "", index)
                else:
                    table.insert("", index, iid=key, values=values)
            obsolete = [key for key in table.get_children() if key not in keep]
            if obsolete:
                table.delete(*obsolete)
        if selected and table.exists(selected) and table.selection() != (selected,):
            table.selection_set(selected)

    def tick(self):
        if time.monotonic() >= self.next_workspace_tick:
            self.next_workspace_tick = time.monotonic() + 2
            try:
                if self.view == "home":
                    self.refresh_home()
                elif self.view == "agents":
                    self.refresh_agents()
                elif self.view == "dag":
                    self.refresh_graph()
                elif self.view == "history":
                    self.refresh_history()
                elif self.view == "remote_runs" and self.remote_selected:
                    self.pull_remote()
                elif self.view == "workspace":
                    self.refresh_workspace()
                self.update_header_context()
            except (ValueError, OSError, RuntimeError, TypeError, KeyError):
                pass
        super().tick()

    # ------------------------------------------------------------------
    # Phase 6: Home Dashboard
    # ------------------------------------------------------------------
    def home_page(self):
        frame = self.base(t("home.title", self.locale), t("home.desc", self.locale))
        frame.rowconfigure(4, weight=1)

        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.button(bar, self.w("새 작업 만들기"), lambda: self.show("submit"), True)
        self.button(bar, self.w("저장소 추가"), self.add_local_project)
        self.button(bar, self.w("Provider 연결"), self.provider_wizard)
        self.button(bar, self.w("SSH Worker 연결"), lambda: self.show("ssh"))
        self.button(bar, self.w("원격 작업 보기"), lambda: self.show("remote_runs"), side="right")

        cards = ttk.Frame(frame)
        cards.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        self.metrics_labels = {}
        labels = (
            ("projects", self.w("등록 프로젝트"), "projects"),
            ("running", self.w("실행 중 작업"), "jobs"),
            ("agents", self.w("활성 Agent"), "agents"),
            ("approvals", self.w("승인 대기"), "jobs"),
            ("queued", self.w("대기 중"), "jobs"),
            ("failed", self.w("실패"), "jobs"),
            ("providers", self.w("연결 Provider"), "providers"),
            ("hosts", self.w("실행 환경 / Worker"), "hosts"),
            ("mcp", "Managed MCP", "mcp"),
        )
        for i, (key, label, target) in enumerate(labels):
            col = i % 5 if i < 5 else (i - 5)
            row_idx = 0 if i < 5 else 1
            cards.columnconfigure(col, weight=1, uniform="metric")
            card = MetricCard(cards, self.palette, label, self.ui_font, on_click=lambda page=target: self.show(page))
            card.grid(row=row_idx, column=col, padx=(0 if col == 0 else 8, 0), pady=(0, 8 if row_idx == 0 else 0), sticky="ew")
            self._metric_cards.append(card)
            self.metrics_labels[key] = card

        split = ttk.Panedwindow(frame, orient="horizontal")
        split.grid(row=4, column=0, sticky="nsew")

        # Left: Active Work / Empty State
        left_pane = ttk.Frame(split, padding=(0, 0, 8, 0))
        left_pane.columnconfigure(0, weight=1)
        left_pane.rowconfigure(1, weight=1)
        ttk.Label(left_pane, text=t("home.active_work", self.locale), style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.home_work_stack = ttk.Frame(left_pane)
        self.home_work_stack.grid(row=1, column=0, sticky="nsew")
        self.home_work_stack.columnconfigure(0, weight=1)
        self.home_work_stack.rowconfigure(0, weight=1)

        self.home_active_wrap = ttk.Frame(self.home_work_stack)
        self.home_active_wrap.grid(row=0, column=0, sticky="nsew")
        self.home_active_wrap.columnconfigure(0, weight=1)
        self.home_active_wrap.rowconfigure(0, weight=1)
        self.home_active_table = self.table(
            self.home_active_wrap, 0,
            (("project", self.w("프로젝트"), 88), ("title", self.w("작업"), 145), ("stage", self.w("단계 · 상태"), 92), ("agents", "Agent", 82), ("env", self.w("환경"), 54), ("updated", self.w("갱신"), 72)),
            height=8,
        )
        self.home_active_table.bind("<Double-1>", lambda _e: self._open_selected_home_job())
        self.home_active_table.bind("<Return>", lambda _e: self._open_selected_home_job())

        self.home_empty_wrap = ttk.Frame(self.home_work_stack)
        self.home_empty_wrap.grid(row=0, column=0, sticky="nsew")
        self.home_empty_wrap.columnconfigure(0, weight=1)
        self.home_empty_card = EmptyState(
            self.home_empty_wrap,
            self.palette,
            t("home.empty_title", self.locale),
            t("home.empty_body", self.locale),
            self.ui_font,
            actions=(
                (self.w("첫 프로젝트 추가"), self.add_local_project, True),
                (self.w("Provider 설정"), self.provider_wizard, False),
                (self.w("새 작업 만들기"), lambda: self.show("submit"), False),
                (self.w("원격 Worker 연결"), lambda: self.show("ssh"), False),
            ),
        )
        self.home_empty_card.grid(row=0, column=0, sticky="new")

        # Right: Recent Activity
        right_pane = ttk.Frame(split, padding=(8, 0, 0, 0))
        right_pane.columnconfigure(0, weight=1)
        right_pane.rowconfigure(1, weight=1)
        ttk.Label(right_pane, text=t("home.recent_activity", self.locale), style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.activity = self.table(
            right_pane, 1,
            (("job", self.w("작업"), 136), ("event", self.w("이벤트"), 92), ("task", self.w("노드"), 58), ("time", self.w("시각"), 76)),
            height=8,
        )
        self.activity.bind("<Double-1>", self.open_activity)
        self.activity.bind("<Return>", self.open_activity)
        ttk.Label(right_pane, text=self.w("활동을 선택하면 해당 실행으로 이동합니다."), style="Muted.TLabel").grid(row=2, column=0, sticky="w")

        split.add(left_pane, weight=3)
        split.add(right_pane, weight=2)
        return frame

    def _open_selected_home_job(self):
        sel = self.home_active_table.selection()
        if not sel:
            return
        iid = sel[0]
        if iid in self.home_active_map:
            kind, key = self.home_active_map[iid]
            if kind == "remote":
                self.remote_selected = key
                self.show("remote_runs")
            else:
                self.open_job(key)

    def refresh_home(self):
        projects, hosts = self.project_rows(), read_workspace(self.root)["hosts"]
        config = read_config(self.root)
        jobs = self.store.list_jobs()
        counts = {key: 0 for key in ("running", "agents", "queued", "failed", "approvals")}
        labels = {
            "QUEUED": "queued", "PREPARING": "running", "RUNNING": "running", "VERIFYING": "running",
            "RETRY_WAIT": "queued", "MERGE_QUEUED": "queued", "MERGING": "running", "FAILED": "failed",
            "AWAITING_APPROVAL": "approvals", "AWAITING_TOOL": "approvals",
        }
        repo_names = {p["path"]: p["name"] for p in projects.values()}
        active_rows = []
        self.home_active_map = {}

        for job in jobs:
            key = labels.get(job["state"])
            tasks = self.store.tasks(job["id"]) if key in ("running", "approvals", "queued") else {}
            if key:
                counts[key] += 1
            if key in ("running", "approvals"):
                counts["agents"] += sum(task["state"] in LIVE for task in tasks.values())
            if job["state"] not in TERMINAL or len(active_rows) < 6:
                if job["state"] not in TERMINAL or job["state"] == "AWAITING_APPROVAL":
                    plan = job.get("plan") or {}
                    proj_name = repo_names.get(plan.get("repo"), Path(plan.get("repo", "")).name or self.w("로컬"))
                    agent_names = ", ".join(t["id"] for t in plan.get("tasks", [])[:3]) or "—"
                    iid = f'local:{job["id"]}'
                    self.home_active_map[iid] = ("local", job["id"])
                    active_rows.append((
                        iid,
                        (proj_name, f'{plan.get("title", "")} ({job["id"][:6]})', state_label(job["state"], self.locale),
                         agent_names, self.w("이 PC"), datetime.fromtimestamp(job["updated"]).strftime("%H:%M:%S")),
                    ))

        for rkey, remote in self.remote_cache.items():
            if remote.get("error") or time.time() - remote.get("at", 0) > 12:
                continue
            key = labels.get(remote.get("state"))
            if key:
                counts[key] += 1
            if key in ("running", "approvals"):
                counts["agents"] += sum(task["state"] in LIVE for task in remote.get("tasks", []))

        counts |= {
            "projects": len(projects),
            "providers": len({model["provider"] for model in config["models"].values()}),
            "mcp": len(config["mcp"]),
            "hosts": len(hosts) + 1,
        }
        for key, value in counts.items():
            card = self.metrics_labels[key]
            if isinstance(card, MetricCard):
                card.set_value(str(value))
            else:
                card.configure(text=str(value))

        if not active_rows and (not projects or not jobs):
            self.home_empty_wrap.tkraise()
        else:
            self.home_active_wrap.tkraise()
            self.fill(self.home_active_table, active_rows)

        titles = {job["id"]: job["plan"]["title"] for job in jobs}
        events = self.store.recent_events(limit=45)
        self.activity_records = {str(event["seq"]): event for event in events}
        self.fill(
            self.activity,
            [(key, (titles.get(item["run_id"], item["run_id"][:8]),
                    EVENT_LABELS.get(item["event_type"], item["event_type"]),
                    item["task_id"] or "—",
                    datetime.fromtimestamp(item["timestamp"]).strftime("%H:%M:%S")))
             for key, item in self.activity_records.items()],
        )

    def open_activity(self, _=None):
        if self.activity.selection():
            item = self.activity_records[self.activity.selection()[0]]
            if item["task_id"]:
                self.agent_job, self.agent_task = item["run_id"], item["task_id"]
                self.show("agents")
            else:
                self.open_job(item["run_id"])

    def open_job(self, key):
        self.show("jobs")
        if self.jobs.exists(key):
            self.jobs.selection_set(key)
            self.jobs.see(key)
            self.job_selected()

    def accept_local_plan(self, plan):
        config = read_config(self.root)
        from .workspace import plan_routes
        plan_routes(plan, config)
        job = self.store.submit(plan, config, None if plan.get("background") else self.token)
        self.store.attach_foreground(job, self.token)
        self.restart_supervisor()
        if self.view == "workspace":
            self.open_workspace_job(job)
        else:
            self.open_job(job)

    # ------------------------------------------------------------------
    # Phase 9 & 10: Tasks Page with 7-Tab Detail & Inline Git Approval
    # ------------------------------------------------------------------
    def jobs_page(self):
        frame = self.base(t("jobs.title", self.locale), t("jobs.desc", self.locale))
        frame.rowconfigure(3, weight=1)

        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.button(bar, self.w("새 작업"), lambda: self.show("submit"), True)
        self.button(bar, self.w("중지"), lambda: self.job_action("cancel"))
        self.button(bar, self.w("재시도"), lambda: self.job_action("retry"))
        self.button(bar, self.w("도구 승인 검토"), self.tool_decision)
        self.button(bar, self.w("병합 승인"), lambda: self.job_action("merge"))
        self.job_controls = {button.cget("text"): button for button in bar.winfo_children() if isinstance(button, ttk.Button)}

        self.job_filter_var = tk.StringVar(self.window, "")
        self.job_filter_var.trace_add("write", lambda *_: self.refresh_jobs())
        self.button(bar, self.w("원격 작업"), lambda: self.show("remote_runs"), side="right")
        ttk.Entry(bar, textvariable=self.job_filter_var, width=18).pack(side="right", padx=(4, 8), pady=3)
        ttk.Label(bar, text=self.w("검색"), style="Muted.TLabel").pack(side="right", padx=(6, 0))

        split = ttk.Panedwindow(frame, orient="horizontal")
        split.grid(row=3, column=0, sticky="nsew")

        left = ttk.Frame(split, padding=(0, 0, 8, 0))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.jobs = self.table(
            left, 0,
            (("title", self.w("작업"), 170), ("state", self.w("상태"), 92), ("mode", self.w("모드"), 76), ("updated", self.w("갱신"), 86)),
            height=12,
        )
        self.jobs.bind("<<TreeviewSelect>>", self.job_selected)

        toolbar2 = ttk.Frame(left)
        toolbar2.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        toolbar2.columnconfigure(0, weight=1)
        row_a = ttk.Frame(toolbar2)
        row_a.grid(row=0, column=0, sticky="ew")
        self.button(row_a, self.w("JSON 보고서 저장"), self.export_report, subtle=True)
        self.button(row_a, self.w("결과 폴더 열기"), self.open_artifacts, subtle=True)
        self.button(row_a, self.w("Supervisor 시작"), self.restart_supervisor, side="right", subtle=True)
        row_b = ttk.Frame(toolbar2)
        row_b.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.button(row_b, self.w("Supervisor 종료"), self.stop_supervisor, side="right", subtle=True)

        right = ttk.Frame(split, padding=(8, 0, 0, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        p = self.palette
        header_card = Card(right, p, padding=(12, 9))
        header_card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._themed_cards.append(header_card)
        title_row = tk.Frame(header_card.body, bg=p["panel"])
        title_row.pack(fill="x")
        self.detail_badge = StatusBadge(title_row, p, text=self.w("선택 대기"), tone="neutral", ui_font=self.ui_font)
        self.detail_badge.pack(side="right", padx=(8, 0))
        self.detail_title = ttk.Label(title_row, text=self.w("작업 상세"), style="CardTitle.TLabel", wraplength=440, justify="left", anchor="w")
        self.detail_title.pack(side="left", fill="x", expand=True)
        self.detail_evidence = ttk.Label(header_card.body, text="", style="Card.TLabel", wraplength=540, justify="left", anchor="w")
        self.detail_evidence.pack(fill="x", pady=(6, 0))

        self.detail_book = ttk.Notebook(right)
        self.detail_book.grid(row=1, column=0, sticky="nsew")

        # Tab 1: Overview
        t1 = ttk.Frame(self.detail_book, padding=8)
        t1.columnconfigure(0, weight=1)
        t1.rowconfigure(0, weight=1)
        self.detail_overview = self.text(t1, 0)
        self.write(self.detail_overview, self.w("작업을 선택하면 실행 요약과 단계 현황이 표시됩니다."), True)
        self.detail_book.add(t1, text=self.w("개요"))

        # Tab 2: Execution Plan (Visual DAG)
        t2 = ttk.Frame(self.detail_book, padding=8)
        t2.columnconfigure(0, weight=1)
        t2.rowconfigure(0, weight=1)
        self.detail_dag_canvas = tk.Canvas(t2, bg=p["graph_bg"], highlightthickness=0, height=260)
        self.detail_dag_canvas.grid(row=0, column=0, sticky="nsew")
        self._detail_dag_version = None
        self.detail_book.add(t2, text=self.w("실행 계획"))

        # Tab 3: Agents
        t3 = ttk.Frame(self.detail_book, padding=8)
        t3.columnconfigure(0, weight=1)
        t3.rowconfigure(0, weight=1)
        self.detail_agents_table = self.table(
            t3, 0,
            (("task", self.w("노드"), 110), ("role", self.w("역할"), 85), ("state", self.w("상태"), 90),
             ("route", self.w("모델 / Harness"), 170), ("elapsed", self.w("경과"), 70), ("tokens", self.w("토큰"), 80)),
            height=8,
        )
        t3_bar = ttk.Frame(t3)
        t3_bar.grid(row=1, column=0, sticky="ew")
        self.button(t3_bar, self.w("Agent 대시보드에서 열기"), self._open_selected_task_agent, True)
        self.detail_book.add(t3, text="Agent")

        # Tab 4: Changed Files
        t4 = ttk.Frame(self.detail_book, padding=8)
        t4.columnconfigure(0, weight=1)
        t4.rowconfigure(1, weight=1)
        self.detail_files_list = self.table(t4, 0, (("file", self.w("변경된 파일 경로"), 420),), height=5)
        self.detail_diff_text = self.text(t4, 1)
        self.write(self.detail_diff_text, self.w("변경된 파일이 있는 작업의 diff 요약이 표시됩니다."), True)
        self.detail_book.add(t4, text=self.w("변경 파일"))

        # Tab 5: QA Results
        t5 = ttk.Frame(self.detail_book, padding=8)
        t5.columnconfigure(0, weight=1)
        t5.rowconfigure(1, weight=1)
        self.detail_qa_summary = ttk.Label(t5, text=self.w("통합 QA 기록이 없습니다."), style="Muted.TLabel")
        self.detail_qa_summary.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.detail_qa_table = self.table(
            t5, 1,
            (("index", self.w("점검"), 80), ("status", self.w("결과"), 100), ("code", self.w("종료 코드"), 95), ("elapsed", self.w("소요 시간"), 110)),
            height=7,
        )
        self.detail_book.add(t5, text=self.w("QA 결과"))

        # Tab 6: Approval (Phase 10 Inline Git & QA Approval UX)
        t6 = ttk.Frame(self.detail_book, padding=8)
        t6.columnconfigure(0, weight=1)
        t6.rowconfigure(1, weight=1)
        app_card = Card(t6, p, padding=(12, 10))
        app_card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._themed_cards.append(app_card)
        app_top = tk.Frame(app_card.body, bg=p["panel"])
        app_top.pack(fill="x")
        tk.Label(app_top, text=self.w("Git & QA 병합 승인 상태"), bg=p["panel"], fg=p["text"], font=(self.ui_font, 11, "bold")).pack(side="left")
        self.inline_approval_badge = StatusBadge(app_top, p, text=self.w("QA 대기"), tone="neutral", ui_font=self.ui_font)
        self.inline_approval_badge.pack(side="right")
        self.inline_approval_info = self.text(t6, 1)
        self.write(self.inline_approval_info, self.w("작업을 선택하면 대상 브랜치, 후보 SHA, QA 검증 회차 및 병합 차단 사유가 표시됩니다."), True)
        app_btns = ttk.Frame(t6)
        app_btns.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.inline_approve_btn = self.button(app_btns, self.w("후보 병합 승인"), lambda: self.job_action("merge"), True)
        self.inline_reject_btn = self.button(app_btns, self.w("승인 거절"), lambda: self.action(self._reject_selected_job), danger=True)
        self.inline_diff_btn = self.button(app_btns, self.w("변경 Diff 보기"), lambda: self.action(lambda: self.show_diff_dialog(self.get_job())))
        self.detail_book.add(t6, text=self.w("승인"))

        # Tab 7: Logs (keeps self.detail exact text output for smoke tests)
        t7 = ttk.Frame(self.detail_book, padding=8)
        t7.columnconfigure(0, weight=1)
        t7.rowconfigure(0, weight=1)
        self.detail = self.text(t7, 0)
        self.write(self.detail, self.w("작업을 선택하면 상태와 실행 이벤트가 표시됩니다."), True)
        self.detail_book.add(t7, text=self.w("로그"))

        split.add(left, weight=2)
        split.add(right, weight=3)
        return frame

    def _open_selected_task_agent(self):
        if self.selected_job:
            self.agent_job = self.selected_job
            sel = self.detail_agents_table.selection()
            if sel:
                self.agent_task = sel[0]
            self.show("agents")

    def _reject_selected_job(self):
        job = self.get_job()
        require(job["state"] not in TERMINAL, self.w("이미 종료된 작업입니다."))
        if messagebox.askyesno(self.w("승인 거절"), self.w("{0}\n\n병합 승인을 거절하고 작업을 중지하시겠습니까?", job['plan']['title']), parent=self.window):
            self.store.request(job["id"], "cancel")
            self.refresh_jobs()

    def refresh_jobs(self):
        all_rows = self.store.list_jobs()
        current_states = {row["id"]: row["state"] for row in all_rows}
        if self.notifications and self.notice_states is not None:
            changes = [state_label(state, self.locale) for job, state in current_states.items()
                       if state != self.notice_states.get(job)
                       and state in ("FAILED", "SUCCEEDED", "MERGED", "AWAITING_TOOL", "AWAITING_APPROVAL")]
            if changes:
                self.notice(changes[0] if len(changes) == 1 else self.w("작업 상태 변경 {0}건", len(changes)))
        self.notice_states = current_states

        pending_count = sum(1 for st in current_states.values() if st in ("AWAITING_TOOL", "AWAITING_APPROVAL"))
        if hasattr(self, "header_notice_badge"):
            self.header_notice_badge.set_status(
                self.w("승인 대기 {0}", pending_count) if pending_count else self.w("알림 0"),
                tone="warning" if pending_count else "neutral",
                palette=self.palette,
            )

        query = self.job_filter_var.get().strip().casefold() if hasattr(self, "job_filter_var") else ""
        rows = [
            row for row in all_rows
            if not query or query in (row.get("plan") or {}).get("title", "").casefold() or query in row["id"].casefold()
        ]
        values = [
            (row["id"], (row["plan"]["title"], state_label(row["state"], self.locale),
                         self.w("백그라운드") if row["plan"].get("background") else self.w("포그라운드"),
                         datetime.fromtimestamp(row["updated"]).strftime("%m-%d %H:%M:%S")))
            for row in rows
        ]
        if values != self.job_cache:
            self.job_cache = values
            self.fill(self.jobs, values, self.selected_job)

        job = self.store.job(self.selected_job) if self.selected_job else None
        state = job["state"] if job else None
        for label, active in (
            (self.w("중지"), state is not None and state not in TERMINAL | {"MERGING"}),
            (self.w("재시도"), state == "FAILED"),
            (self.w("도구 승인 검토"), state == "AWAITING_TOOL"),
            (self.w("병합 승인"), bool(job and merge_candidate_ready(job))),
        ):
            if label in self.job_controls:
                self.job_controls[label].state(["!disabled" if active else "disabled"])

        if not job:
            return

        tasks = self.store.tasks(job["id"])
        st_label = state_label(job["state"], self.locale)
        self.detail_title.configure(text=f'{job["plan"]["title"]}  ·  {st_label}')
        if hasattr(self, "detail_badge"):
            self.detail_badge.set_status(st_label, job["state"], palette=self.palette)

        result = (job["result"] or {}) if job["state"] in (*MERGE_EVIDENCE, "SUCCEEDED") else {}
        candidate = result.get("candidate")
        files = result["changed"] if "changed" in result else changed_files(tasks)
        evidence = []
        if files:
            listed = ", ".join(files[:5])
            evidence.append(self.w("변경 파일 {0}개 · {1}", len(files), listed) + (self.w(" 외") if len(files) > 5 else ""))
        if checks := result.get("qa"):
            evidence.append(self.w("통합 QA {0}개 통과", len(checks)))
        if candidate:
            evidence.append(self.w("병합 후보 {0} · {1}", candidate[:12], job['plan']['target']))
        self.detail_evidence.configure(text="   |   ".join(evidence))

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
            stages = ((key, task_stage(job["state"], row["state"]), row["attempt"]) for key, row in tasks.items())
            states = "\n".join(self.w("{0}   {1}   시도 {2}", key, state_label(stage, self.locale), attempt) for key, stage, attempt in stages)
            top, bottom = self.detail.yview()
            self.write(self.detail, states + "\n\n" + "\n".join(self.events_cached.values()), True)
            if bottom >= .99:
                self.detail.see("end")
            else:
                self.detail.yview_moveto(top)

        self._refresh_detail_tabs(job, tasks)

    def _refresh_detail_tabs(self, job: dict, tasks: dict):
        all_events = self.store.recent_events(job["id"], limit=600)
        # Tab 1: Overview
        plan = job.get("plan") or {}
        ov_lines = [
            self.w("실행 ID       {0}", job['id']),
            self.w("저장소        {0}", plan.get('repo', '—')),
            self.w("대상 브랜치   {0}", plan.get('target', '—')),
            self.w("실행 모드     {0}", (self.w('백그라운드') if plan.get('background') else self.w('포그라운드'))),
            self.w("생성 시각     {0}", datetime.fromtimestamp(job['created']).strftime('%Y-%m-%d %H:%M:%S')),
            self.w("최근 갱신     {0}", datetime.fromtimestamp(job['updated']).strftime('%Y-%m-%d %H:%M:%S')),
            self.w("통합 QA 명령  {0}", format_commands(plan.get('qa', [])) or self.w('없음')),
            "",
            self.w("노드별 현재 단계"),
        ]
        for tid, row in tasks.items():
            stage = task_stage(job["state"], row["state"])
            ov_lines.append(self.w("  - {0}: {1} (시도 {2})", tid, state_label(stage, self.locale), row['attempt']))
        ov_text = "\n".join(ov_lines)
        if hasattr(self, "detail_overview") and self.detail_overview.get("1.0", "end-1c") != ov_text:
            self.write(self.detail_overview, ov_text, True)

        # Tab 2: Visual DAG Canvas
        if hasattr(self, "detail_dag_canvas"):
            version = (job["id"], tuple((k, v["state"]) for k, v in tasks.items()))
            if version != getattr(self, "_detail_dag_version", None):
                self._detail_dag_version = version
                self._draw_dag(self.detail_dag_canvas, job, tasks)

        # Tab 3: Agents
        if hasattr(self, "detail_agents_table"):
            rows = agent_rows(job, tasks, all_events)
            self.fill(
                self.detail_agents_table,
                [(a["id"], (
                    a["agent"] or a["id"],
                    a["role"] or "—",
                    state_label(a["state"], self.locale),
                    f'{a["model"] or "—"} / {a["harness"] or "—"}',
                    f'{a["elapsed"]:.1f}s' if a["elapsed"] is not None else "—",
                    str(a["input"] + (a["output"] or 0)) if a["input"] is not None else "—",
                )) for a in rows],
            )

        # Tab 4: Changed files & diff
        if hasattr(self, "detail_files_list"):
            result = job.get("result") or {}
            files = result.get("changed") if "changed" in result else changed_files(tasks)
            self.fill(self.detail_files_list, [(f, (f,)) for f in files])
            diff_key = (job["id"], job["state"], tuple(files))
            if self._inline_diff_job != diff_key:
                self._inline_diff_job = diff_key
                if files and result.get("candidate"):
                    self.background(
                        lambda j=job: self.diff_summary_for_job(j),
                        lambda text: self.write(self.detail_diff_text, text, True) if self.detail_diff_text.winfo_exists() else None,
                    )
                else:
                    self.write(self.detail_diff_text, self.w("커밋된 변경 파일이 없습니다.") if not files else "\n".join(files), True)

        # Tab 5: QA Results
        if hasattr(self, "detail_qa_table"):
            qa_events = [e for e in reversed(all_events) if e["event_type"] in ("qa.result", "qa.interrupted")]
            result_qa = (job.get("result") or {}).get("qa") or []
            qa_rows = []
            if result_qa:
                for idx, chk in enumerate(result_qa, 1):
                    passed = chk.get("exit_code") == 0
                    qa_rows.append((
                        f"r:{idx}",
                        (f"Check {idx}", self.w("통과") if passed else self.w("실패"), chk.get("exit_code", "—"),
                         f'{chk.get("elapsed_sec", "—")}s' if chk.get("elapsed_sec") is not None else "—"),
                    ))
            else:
                for idx, ev in enumerate(qa_events, 1):
                    pl = ev["payload"]
                    if ev["event_type"] == "qa.interrupted":
                        qa_rows.append((f"e:{idx}", (f"Check {pl.get('index', idx)}", self.w("중단 ({0})", pl.get('status')), "—", f"{pl.get('elapsed_sec', '—')}s")))
                    else:
                        passed = pl.get("exit_code") == 0
                        qa_rows.append((f"e:{idx}", (f"Check {pl.get('index', idx)}", self.w("통과") if passed else self.w("실패"), pl.get("exit_code", "—"), f"{pl.get('elapsed_sec', '—')}s")))
            self.fill(self.detail_qa_table, qa_rows)
            revision = (job.get("result") or {}).get("approval_revision") or "—"
            self.detail_qa_summary.configure(text=self.w("QA 기록 {0}건  ·  검증 회차 {1}", len(qa_rows), revision))

        # Tab 6: Inline Git & QA Approval
        if hasattr(self, "inline_approval_badge"):
            code_key, label, tone, eligible, blockers = approval_state_info(job, tasks, all_events)
            self.inline_approval_badge.set_status(label, tone=tone, palette=self.palette)
            result = job.get("result") or {}
            checks = result.get("qa") or []
            passed_cnt = sum(1 for c in checks if c.get("exit_code") == 0)
            failed_cnt = len(checks) - passed_cnt
            review_ev = [e for e in all_events if e["event_type"] == "review.result"]
            review_txt = review_ev[-1]["payload"].get("status", self.w("미기록")) if review_ev else self.w("해당 없음")
            files = result.get("changed") if "changed" in result else changed_files(tasks)
            info_lines = [
                self.w("대상 브랜치     {0}", plan.get('target', '—')),
                self.w("후보 커밋 SHA   {0}", result.get('candidate') or '미생성'),
                self.w("QA 검증 회차    {0}", result.get('approval_revision') or '—'),
                self.w("통합 QA 결과    통과 {0}건 / 실패 {1}건", passed_cnt, failed_cnt),
                self.w("독립 검토 결과  {0}", review_txt),
                self.w("병합 가능 여부  {0}", ('승인 가능 (실행 시 SHA·브랜치 재검증)' if eligible else '차단됨')),
            ]
            if blockers:
                info_lines.extend(["", self.w("차단/대기 사유"), *[f"  - {b}" for b in blockers]])
            if files:
                info_lines.extend(["", self.w("변경 파일 ({0}개)", len(files)), *[f"  - {f}" for f in files[:25]]])
            text_val = "\n".join(info_lines)
            if self.inline_approval_info.get("1.0", "end-1c") != text_val:
                self.write(self.inline_approval_info, text_val, True)
            self.inline_approve_btn.state(["!disabled" if eligible else "disabled"])
            self.inline_reject_btn.state(["!disabled" if job["state"] not in TERMINAL else "disabled"])

    # ------------------------------------------------------------------
    # Phase 9: Agent Dashboard & Upgraded DAG Canvas
    # ------------------------------------------------------------------
    def _job_picker(self, frame, row, change):
        line = ttk.Frame(frame)
        line.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        line.columnconfigure(1, weight=1)
        ttk.Label(line, text=self.w("로컬 작업"), style="Muted.TLabel").grid(row=0, column=0, padx=(0, 7), sticky="w")
        picker = ttk.Combobox(line, state="readonly", width=48)
        picker.grid(row=0, column=1, sticky="w")
        picker.bind("<<ComboboxSelected>>", lambda _: change(picker.get()))
        return line, picker

    def _choices(self, picker):
        values = {f'{row["plan"]["title"][:60]} · {row["id"][:7]}': row["id"] for row in self.store.list_jobs()}
        picker.configure(values=list(values))
        item = next((name for name, key in values.items() if key == self.agent_job), "")
        if not item and values:
            item = next(iter(values))
            self.agent_job = values[item]
        if picker.get() != item:
            picker.set(item)
        return values

    def pick_agent_job(self, name):
        self.agent_job = self.agent_choices.get(name)
        self.agent_task = None
        if self.view == "agents":
            self.refresh_agents()
        else:
            self.refresh_graph()

    def agents_page(self):
        frame = self.base(t("agents.title", self.locale), t("agents.desc", self.locale))
        bar, self.agents_jobs = self._job_picker(frame, 2, self.pick_agent_job)
        ttk.Button(bar, text=self.w("원격 작업"), command=lambda: self.show("remote_runs")).grid(row=0, column=2, padx=4)
        self.agent_search = tk.StringVar(self.window)
        self.agent_search.trace_add("write", lambda *_: self.render_agent())
        self.agent_list = self.table(frame, 3, (
            ("task", self.w("Agent / 노드"), 175), ("role", self.w("역할"), 90),
            ("state", self.w("단계"), 110), ("model", self.w("모델"), 145),
            ("harness", "Harness", 100), ("tools", self.w("도구"), 75),
        ))
        self.agent_list.bind("<<TreeviewSelect>>", self.select_agent)
        frame.rowconfigure(3, weight=1)
        frame.rowconfigure(5, weight=2)
        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, sticky="ew", pady=4)
        ttk.Label(actions, text=self.w("이벤트 검색"), style="Muted.TLabel").pack(side="left", padx=(0, 4))
        ttk.Entry(actions, textvariable=self.agent_search, width=20).pack(side="left", padx=(0, 10))
        self.button(actions, self.w("작업 상세"), lambda: self.open_job(self.agent_job) if self.agent_job else None)
        self.agent_terminal_button = self.button(actions, self.w("Worktree 터미널"), lambda: self.action(self.task_terminal))
        self.agent_output_button = self.button(actions, self.w("결과 열기"), lambda: self.action(self.task_result))
        self.agent_stop_button = self.button(actions, self.w("작업 중지"), lambda: self.action(self._stop_agent_job))
        self.agent_retry_button = self.button(actions, self.w("실패 재시도"), lambda: self.action(self._retry_agent_job))
        self.agent_detail = self.text(frame, 5)
        self.write(self.agent_detail, self.w("작업 실행 기록이 생성되면 Agent 상태가 표시됩니다."), True)
        return frame

    def _stop_agent_job(self):
        require(self.agent_job, self.w("작업을 선택하세요."))
        self.selected_job = self.agent_job
        self.job_action("cancel")
        self.refresh_agents()

    def _retry_agent_job(self):
        require(self.agent_job, self.w("작업을 선택하세요."))
        self.selected_job = self.agent_job
        self.job_action("retry")
        self.refresh_agents()

    def refresh_agents(self):
        self.agent_choices = self._choices(self.agents_jobs)
        if not self.agent_job:
            self.render_agent()
            return
        job = self.store.job(self.agent_job)
        if not job:
            return
        rows = self.store.tasks(self.agent_job)
        events = self.store.recent_events(self.agent_job, limit=1400)
        self.agent_events = events
        self.agent_record = {row["id"]: row for row in agent_rows(job, rows, events)}
        if self.agent_task not in self.agent_record:
            self.agent_task = next(iter(self.agent_record), None)
        self.fill(
            self.agent_list,
            [(key, (item["agent"] or key, item["role"] or "—",
                    state_label(item["state"], self.locale), item["model"] or "—", item["harness"] or "—", item["tools"]))
             for key, item in self.agent_record.items()],
            self.agent_task,
        )
        self.render_agent()

    def select_agent(self, _):
        selected = self.agent_list.selection()
        if selected:
            self.agent_task = selected[0]
            self.render_agent()

    def render_agent(self):
        if not hasattr(self, "agent_detail"):
            return
        agent = self.agent_record.get(self.agent_task)
        job = self.store.job(self.agent_job) if agent and self.agent_job else None
        self.agent_terminal_button.state(["!disabled" if job and job["state"] in TERMINAL else "disabled"])
        self.agent_output_button.state(["!disabled" if agent and agent["artifact"] else "disabled"])
        if hasattr(self, "agent_stop_button"):
            self.agent_stop_button.state(["!disabled" if job and job["state"] not in TERMINAL | {"MERGING"} else "disabled"])
        if hasattr(self, "agent_retry_button"):
            self.agent_retry_button.state(["!disabled" if job and job["state"] == "FAILED" else "disabled"])
        if not agent:
            return
        render = lambda value: str(value) if value is not None else self.w("미관측")
        started = datetime.fromtimestamp(agent["started"]).strftime("%H:%M:%S") if agent["started"] else self.w("미관측")
        duration = self.w("{0:.1f}초", agent['elapsed']) if agent["elapsed"] is not None else self.w("미관측")
        lines = [
            self.w("{0} · {1} · 이 PC", agent['id'], state_label(agent['state'], self.locale)),
            self.w("요청 Provider {0}   모델 {1}   Runtime {2}", render(agent['provider_requested'] or agent['provider']),
                   render(agent['model_requested'] or agent['model']), render(agent['runtime'])),
            self.w("시작 {0}  ·  경과 {1}  ·  재시도 {2}  ·  도구 {3}회", started, duration, agent['retry_count'], agent['tools']),
            self.w("입력 {0}  ·  출력 {1}  ·  최근 Prompt 토큰 {2}  ·  검증된 Context 한도 {3}", render(agent['input']), render(agent['output']), render(agent['last_prompt']), render(agent['context'])),
            self.w("변경 파일 {0}", one_line(agent['changed'])),
            self.w("최근 오류 {0}", agent['last_error'] or '—'),
            "",
            self.w("실행 이벤트"),
        ]
        query = self.agent_search.get().strip().casefold()
        for event in getattr(self, "agent_events", []):
            if event["task_id"] != agent["id"]:
                continue
            label = EVENT_LABELS.get(event["event_type"], event["event_type"])
            stamp = datetime.fromtimestamp(event["timestamp"]).strftime("%H:%M:%S")
            summary = json.dumps(event["payload"], ensure_ascii=False)
            line = f'{stamp}  {label} ({event["event_type"]})  {summary}'
            if query in line.casefold():
                lines.append(line)
        text = "\n".join(lines)
        if self.agent_detail.get("1.0", "end-1c") != text:
            position = self.agent_detail.yview()[0]
            self.write(self.agent_detail, text, True)
            self.agent_detail.yview_moveto(position)

    def task_terminal(self):
        job = self.store.job(self.agent_job) if self.agent_job else None
        require(job and job["state"] in TERMINAL and self.agent_task, self.w("종료된 작업의 Worktree를 선택하세요."))
        path = self.root / "worktrees" / self.agent_job / self.agent_task
        require(path.is_dir(), self.w("이 노드의 Worktree가 남아 있지 않습니다."))
        self.new_terminal(f'{self.agent_task} Worktree', cwd=path)

    def task_result(self):
        agent = self.agent_record.get(self.agent_task)
        require(agent and agent["artifact"], self.w("이 노드에 저장된 결과가 없습니다."))
        path = Path(agent["artifact"]).resolve()
        require(path.is_relative_to(self.root.resolve() / "artifacts" / self.agent_job) and path.is_file(),
                self.w("작업 결과 파일을 찾을 수 없습니다."))
        window = tk.Toplevel(self.window)
        window.title(self.w("Agent 작업 결과"))
        window.geometry("800x530")
        window.configure(bg=self.palette["canvas"])
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        field = self.text(window, 0)
        with path.open(encoding="utf-8", errors="replace") as source:
            self.write(field, source.read(60000), True)

    def graph_page(self):
        frame = self.base(self.w("오케스트레이션 DAG"), self.w("워크플로의 선행 노드와 실제 실행 상태를 살펴봅니다."))
        _, self.graph_jobs = self._job_picker(frame, 2, self.pick_agent_job)
        frame.rowconfigure(3, weight=1)
        body = ttk.Frame(frame)
        body.grid(row=3, column=0, sticky="nsew", pady=7)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.graph = tk.Canvas(body, bg=self.palette["graph_bg"], highlightthickness=1, highlightbackground=self.palette["border"], height=360)
        self.graph.grid(row=0, column=0, sticky="nsew")
        for direction, axis in (("vertical", "y"), ("horizontal", "x")):
            scroll = ttk.Scrollbar(body, orient=direction, command=getattr(self.graph, axis + "view"))
            self.graph.configure(**{axis + "scrollcommand": scroll.set})
            scroll.grid(row=0 if axis == "y" else 1, column=1 if axis == "y" else 0, sticky="ns" if axis == "y" else "ew")
        self.graph_version = None
        panel = ttk.Frame(frame)
        panel.grid(row=4, column=0, sticky="ew")
        self.button(panel, self.w("작업 실행 기록"), lambda: self.open_job(self.agent_job) if self.agent_job else None)
        self.button(panel, self.w("실행 보고서 비교"), self.compare_runs)
        return frame

    def _draw_dag(self, canvas: tk.Canvas, job: dict | None, task_states: dict):
        p = self.palette
        canvas.configure(bg=p["graph_bg"])
        canvas.delete("all")
        nodes = (job.get("plan") or {}).get("tasks", []) if job else []
        if not nodes:
            canvas.create_text(24, 30, anchor="nw", text=self.w("작업을 선택하면 노드와 선행 관계를 표시합니다."), fill=p["muted"], font=(self.ui_font, 10))
            return
        from .supervisor import ordered
        sequence, _ = ordered(nodes)
        by_id = {node["id"]: node for node in nodes}
        stages, positions, rows = {}, {}, {}
        for key in sequence:
            deps = by_id[key].get("depends", [])
            column = max((stages[dep] + 1 for dep in deps), default=0)
            row = rows.get(column, 0)
            stages[key] = column
            rows[column] = row + 1
            positions[key] = 28 + column * 246, 28 + row * 102
        for key, node in by_id.items():
            x, y = positions[key]
            for dep in node.get("depends", []):
                sx, sy = positions[dep]
                canvas.create_line(sx + 198, sy + 35, x, y + 35, arrow="last", fill=p["graph_edge"], width=2)
        node_styles = p["graph_nodes"]
        for key, (x, y) in positions.items():
            raw_state = task_states.get(key, {}).get("state", "QUEUED")
            stage = task_stage(job["state"], raw_state) if job else raw_state
            fill_c, border_c, fg_c = node_styles.get(stage, node_styles["QUEUED"])
            tag = "node_" + key
            canvas.create_rectangle(x, y, x + 198, y + 70, fill=fill_c, outline=border_c, width=2, tags=tag)
            canvas.create_text(x + 12, y + 22, text=key[:24], anchor="w", fill=fg_c, font=(self.ui_font, 10, "bold"), tags=tag)
            canvas.create_text(
                x + 12, y + 48,
                text=f'{by_id[key]["role"]}  ·  {state_label(stage, self.locale)}',
                anchor="w", fill=fg_c, font=(self.ui_font, 9), tags=tag,
            )
            canvas.tag_bind(tag, "<Button-1>", lambda _, task=key: self.open_graph_node(task))
        canvas.configure(scrollregion=canvas.bbox("all"))

    def refresh_graph(self):
        self.agent_choices = self._choices(self.graph_jobs)
        job = self.store.job(self.agent_job) if self.agent_job else None
        task_states = self.store.tasks(self.agent_job) if job else {}
        version = (self.agent_job, tuple((key, value["state"]) for key, value in task_states.items()))
        if version == self.graph_version:
            return
        self.graph_version = version
        self._draw_dag(self.graph, job, task_states)

    def open_graph_node(self, key):
        self.agent_task = key
        self.show("agents")

    def compare_runs(self):
        rows = {f'{row["plan"]["title"][:40]} · {row["id"][:7]}': row["id"] for row in self.store.list_jobs()}
        form = Form(self, self.w("실행 보고서 비교"), self.w("두 로컬 실행의 기준 커밋, 상태, 소요 시간과 관측된 토큰을 비교합니다."))
        first = next(iter(rows), "")
        form.field("a", self.w("기준 실행"), first, choices=list(rows))
        form.field("b", self.w("비교 실행"), next(iter(list(rows)[1:]), first), choices=list(rows))
        result = form.note("")

        def compare():
            require(form.get("a") in rows and form.get("b") in rows, self.w("비교할 실행을 선택하세요."))
            texts = []
            for key in ("a", "b"):
                item = self.store.report(rows[form.get(key)])
                seconds = item["seconds_to_verified"]
                texts.append(
                    self.w("{0} · {1}\n기준 {2} · 검증 시간 {3} · 관측 토큰 {4}", form.get(key), state_label(item['state'], self.locale), item['base'] or '—', (f'{seconds:.1f}초' if seconds is not None else '—'), (item['tokens_observed'] if item['tokens_observed'] is not None else self.w('미관측')))
                )
            result.configure(text="\n\n".join(texts))

        form.controls(self.w("비교"), compare)

    # ------------------------------------------------------------------
    # Terminals & MCP
    # ------------------------------------------------------------------
    def terminals_page(self):
        frame = self.base(t("terminals.title", self.locale), self.w("작업 공간에서 로컬·SSH 셸과 AI CLI 탭을 관리합니다."))
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="w")
        self.button(bar, self.w("작업 공간 열기"), lambda: self.show("workspace"), True)
        self.button(bar, self.w("로컬 셸 열기"), lambda: self.action(self.local_project_shell))
        self.button(bar, self.w("SSH 연결로 이동"), lambda: self.show("ssh"))
        return frame

    def mcp_page(self):
        frame = super().mcp_page()
        bar = ttk.Frame(frame)
        bar.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        self.button(bar, self.w("Managed 도구 카탈로그"), self.managed_mcp, True)
        self.button(bar, self.w("서버와 권한 설정"), self.edit_mcp)
        return frame

    def mcp_profile_form(self, title):
        config = read_config(self.root)
        form = Form(self, title)
        form.field("profile", self.w("등록 프로필"), next(iter(config["mcp"]), ""), choices=list(config["mcp"]))
        return form, config

    def edit_mcp(self):
        form, config = self.mcp_profile_form(self.w("Managed MCP 서버와 권한"))
        revision = registry_revision(self.root)
        form.field("id", self.w("저장할 프로필 ID"), "")
        form.field("transport", self.w("전송 방식"), "http", choices=("http", "stdio"))
        form.field("endpoint", self.w("URL 또는 실행 argv"))
        form.field("secret", self.w("인증 환경 변수 참조"), help_text=self.w("HTTP의 Authorization 값 또는 stdio 전달 변수 이름입니다."))
        form.field("tool", self.w("도구 이름"), help_text=self.w("저장하면 해당 도구 정책을 새로 추가하거나 수정합니다."))
        form.field("access", self.w("도구 접근"), "read", choices=("read", "write"))
        form.field("roles", self.w("허용 역할"), "explorer, reviewer", help_text=self.w("여러 역할은 쉼표로 구분합니다. write는 기존 승인 절차를 적용합니다."))
        form.field("agents", self.w("허용 Agent ID"), help_text=self.w("선택 사항 · 역할/노드ID를 쉼표로 구분합니다."))
        form.field("native", self.w("Native Gateway 읽기 노출"), False, boolean=True)
        form.field("gateway", self.w("Gateway 토큰 환경 변수"))

        def loaded():
            key = form.get("profile")
            require(key in config["mcp"], self.w("불러올 프로필을 선택하세요."))
            value = config["mcp"][key]
            form.set("id", key)
            form.set("transport", value["transport"])
            form.set("endpoint", value.get("url", "") if value["transport"] == "http"
                     else format_commands([value["command"]]))
            form.set("secret", value.get("header_env", {}).get("Authorization", "") if value["transport"] == "http"
                     else one_line(value.get("env")) if value.get("env") else "")
            form.set("gateway", value.get("gateway_token_env", ""))

        self.button(form.footer, self.w("선택 프로필 불러오기"), lambda: self.action(loaded))

        def store():
            from .core import ident
            from .runtime import checked_url
            key = ident(form.get("id"))
            value = dict(config["mcp"].get(key, {}))
            old = value.get("transport")
            transport, target = form.get("transport"), form.get("endpoint")
            require(not old or old == transport, self.w("기존 전송 방식을 바꾸려면 별도 프로필을 등록하세요."))
            value["transport"] = transport
            if transport == "http":
                checked_url(target)
                value["url"] = target
                headers = dict(value.get("header_env", {}))
                if form.get("secret"):
                    headers["Authorization"] = form.get("secret")
                else:
                    headers.pop("Authorization", None)
                value["header_env"] = headers
            else:
                entries = parse_commands(target)
                require(len(entries) == 1 and entries[0], self.w("서버 실행 명령을 한 줄에 작성하세요."))
                value.update(command=entries[0], env=split_names(form.get("secret")))
            if form.get("gateway"):
                value["gateway_token_env"] = form.get("gateway")
            else:
                value.pop("gateway_token_env", None)
            if form.get("tool"):
                tools = dict(value.get("tools", {}))
                tool = form.get("tool")
                tools[tool] = dict(tools.get(tool, {})) | {
                    "access": form.get("access"),
                    "roles": split_names(form.get("roles")),
                    "agents": split_names(form.get("agents")),
                    "native": form.get("native"),
                }
                value["tools"] = tools
            config["mcp"][key] = value
            save_registry(self.root, config, revision)
            self.restart_supervisor()
            form.destroy()

        form.controls(self.w("등록 및 정책 저장"), store)

    def managed_mcp(self):
        form, config = self.mcp_profile_form(self.w("Managed MCP 도구 카탈로그"))
        form.field("tool", self.w("읽기 테스트 도구"), choices=[])
        form.field("args", self.w("테스트 인자"), "{}", multiline=True)
        summary = form.note(self.w("등록된 서버를 선택하고 실제 목록을 요청하세요."))
        form.width = 660
        catalog = {}

        def fetch():
            key = form.get("profile")
            spec = config["mcp"].get(key)
            require(spec, self.w("Managed MCP 프로필을 등록하고 선택하세요."))

            def inspect():
                with MCPClient(spec) as client:
                    return client.catalog()

            def present(value):
                if not form.winfo_exists() or form.get("profile") != key:
                    return
                catalog.clear()
                catalog.update(value)
                marked = [
                    name for name in value
                    if spec.get("tools", {}).get(name, {}).get("access") == "read"
                    and spec["tools"][name].get("roles") and not spec["tools"][name].get("agents")
                ]
                form.set("tool", next(iter(marked), ""), marked)
                lines = []
                for name, tool in list(value.items())[:12]:
                    policy = spec.get("tools", {}).get(name, {})
                    lines.append(
                        f'{name} · {policy.get("access", self.w("차단"))} · {one_line(policy.get("roles"))}\n'
                        f'{str(tool.get("description") or "")[:160]}'
                    )
                recent = self.store.recent_events("gateway:" + key, limit=20)
                last = next((event for event in recent if event["event_type"] in ("gateway.call", "gateway.test")), None)
                stamp = datetime.fromtimestamp(last["timestamp"]).strftime("%H:%M:%S") if last else self.w("미관측")
                failures = sum(event["event_type"] in ("gateway.failed", "gateway.denied") for event in recent)
                summary.configure(text=self.w("카탈로그 확인 성공 · {0}개 · 최근 성공 {1} · 최근 실패/거절 {2}건\n", len(value), stamp, failures) + "\n".join(lines))

            self.background(inspect, present)

        self.button(form.footer, self.w("목록 조회"), lambda: self.action(fetch))

        def probe():
            key, tool = form.get("profile"), form.get("tool")
            spec = config["mcp"].get(key)
            rule = spec and spec.get("tools", {}).get(tool)
            require(rule and rule.get("roles") and rule["access"] == "read" and not rule.get("agents"),
                    self.w("특정 Agent에 제한되지 않은 읽기 도구를 선택하세요."))
            args = json.loads(form.get("args"))
            require(isinstance(args, dict), self.w("도구 인자는 JSON 객체여야 합니다."))
            if not messagebox.askyesno(self.w("읽기 도구 호출 승인"), self.w("{0}을 테스트하시겠습니까?", tool), parent=form):
                return

            def invoke():
                from .mcp import virtual_name
                alias = virtual_name(key, tool)
                with MCPClient(spec) as client:
                    allowed = published(key, spec, client.catalog(), rule["roles"][0], {alias})
                    require(alias in allowed, self.w("도구 권한 또는 입력 스키마를 검증할 수 없습니다."))
                    _, schema, _ = allowed[alias]
                    result = do_call(client, tool, schema, args)
                self.store.event("gateway:" + key, None, "gateway.test", {"name": tool})
                return result

            self.background(
                invoke,
                lambda result: summary.configure(text=self.w("테스트 성공 · {0}개 결과", len(result.get('content', [])))) if form.winfo_exists() else None,
            )

        form.controls(self.w("읽기 도구 테스트"), probe)

    def close(self):
        self.save_workspace_layout()
        self.close_workspace_sessions()
        super().close()
