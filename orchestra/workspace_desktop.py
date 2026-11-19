"""Project-oriented desktop presentation for the Supervisor."""
from __future__ import annotations

import json
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from .core import require
from .desktop import BG, MUTED, NAV, PANEL, STATES, Desktop
from .execution_state import LIVE, TERMINAL, merge_candidate_ready
from .mcp import MCPClient, do_call, published
from .observability import EVENT_LABELS, agent_rows
from .ssh import ssh_env
from .supervisor import read_config
from .terminal import TerminalView, operator_shell
from .workspace import format_commands, parse_commands, read_workspace, registry_revision, save_registry
from .workspace_forms import Form, ProjectSettings, one_line, split_names
from .workspace_remote import RemoteWorkspace


class WorkspaceDesktop(ProjectSettings, RemoteWorkspace, Desktop):
    initial_page = "home"

    def __init__(self, window, root):
        self.project_id = None
        self.remote_selected = None
        self.remote_cache = {}
        self.remote_pending = set()
        self.host_evidence = {}
        self.tables = {}
        self.terminals = {}
        self.terminal_retry = {}
        self.agent_job = None
        self.agent_task = None
        self.next_workspace_tick = 0
        self.agent_record = {}
        self.registry_revision = registry_revision(root)
        super().__init__(window, root)
        self.window.geometry("1330x850")
        self.window.minsize(930, 630)

    def style(self):
        super().style()
        style = ttk.Style()
        style.configure("Card.TFrame", background=PANEL, relief="flat")
        style.configure("Card.TLabel", background=PANEL, foreground=MUTED)
        style.configure("CardTitle.TLabel", background=PANEL, foreground="#172b47", font=(self.ui_font, 12, "bold"))
        style.configure("Metric.TLabel", background=PANEL, foreground="#123a75", font=(self.ui_font, 22, "bold"))
        style.configure("TNotebook", background=BG)
        style.configure("TNotebook.Tab", padding=(12, 6))
        style.configure("Treeview", rowheight=31)

    def navigation(self):
        return (
            ("home", "홈", self.home_page), ("projects", "프로젝트", self.projects_page),
            ("jobs", "작업 실행", self.jobs_page), ("agents", "Agent 대시보드", self.agents_page),
            ("terminals", "통합 터미널", self.terminals_page), ("dag", "오케스트레이션", self.graph_page),
            ("hosts", "실행 환경", self.environments_page), ("mcp", "MCP 및 도구", self.mcp_page),
            ("settings", "설정", self.settings_page), ("submit", "", self.guided_page),
            ("advanced_plan", "", self.submit_page), ("registry", "", self.registry_page),
            ("remote_runs", "", self.remote_runs_page),
        )

    def layout(self):
        super().layout()
        nav = self.window.grid_slaves(row=0, column=0)[0]
        tk.Label(nav, text="프로젝트", fg="#a7bcd6", bg=NAV, anchor="w",
                 font=(self.ui_font, 9, "bold")).pack(fill="x", padx=20, pady=(15, 3))
        self.sidebar_project = tk.StringVar(self.window, "프로젝트 선택")
        self.sidebar_picker = ttk.Combobox(nav, textvariable=self.sidebar_project, state="readonly", width=23)
        self.sidebar_picker.pack(fill="x", padx=13, pady=(0, 8))
        self.sidebar_picker.bind("<<ComboboxSelected>>", self.pick_sidebar)
        self.window.bind("<Control-n>", lambda _: self.show("submit"))
        self.action(self.refresh_sidebar)

    def refresh_sidebar(self):
        if not hasattr(self, "sidebar_picker"):
            return
        self.sidebar_items = {f'{profile["name"][:25]} · {key[:5]}': key for key, profile in self.project_rows().items()}
        self.sidebar_picker.configure(values=list(self.sidebar_items))
        self.sidebar_project.set(next((name for name, key in self.sidebar_items.items() if key == self.project_id), "프로젝트 선택"))

    def pick_sidebar(self, _=None):
        key = self.sidebar_items.get(self.sidebar_project.get())
        if key:
            self.show("projects")
            self.open_project(key)

    def show(self, key):
        if key == "registry" and not self.registry.get("1.0", "end-1c").strip():
            self.action(self.reload_registry)
        super().show(key)
        work = {
            "home": self.refresh_home, "projects": self.refresh_projects, "agents": self.refresh_agents,
            "dag": self.refresh_graph, "hosts": self.refresh_hosts, "settings": self.refresh_settings,
            "remote_runs": self.refresh_remote,
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
                elif self.view == "remote_runs" and self.remote_selected:
                    self.pull_remote()
            except (ValueError, OSError, RuntimeError, TypeError, KeyError):
                pass
        super().tick()

    def home_page(self):
        frame = self.base("워크스페이스", "프로젝트와 작업을 열고, 로컬 및 최근 확인한 원격 실행을 확인합니다.")
        frame.rowconfigure(5, weight=1)
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew")
        self.button(bar, "새 작업", lambda: self.show("submit"), True)
        self.button(bar, "저장소 추가", self.add_local_project)
        self.button(bar, "Provider 연결", self.provider_wizard)
        cards = ttk.Frame(frame)
        cards.grid(row=3, column=0, sticky="ew", pady=(14, 12))
        self.metrics_labels = {}
        labels = (("projects", "등록 프로젝트", "projects"), ("running", "실행 중", "jobs"),
                  ("agents", "활성 Agent", "agents"), ("queued", "대기", "jobs"), ("failed", "실패", "jobs"),
                  ("approvals", "승인 대기", "jobs"), ("providers", "Provider 설정", "settings"),
                  ("mcp", "Managed MCP", "mcp"), ("hosts", "실행 환경", "hosts"))
        for i, (key, label, target) in enumerate(labels):
            column = i % 3
            cards.columnconfigure(column, weight=1, uniform="metric")
            card = ttk.Frame(cards, padding=(13, 6), style="Card.TFrame")
            card.grid(row=i // 3, column=column, padx=(0, 7), pady=(0, 6), sticky="ew")
            heading = ttk.Label(card, text=label, style="Card.TLabel", cursor="hand2")
            heading.pack(anchor="w")
            count = ttk.Label(card, style="Metric.TLabel", text="—", cursor="hand2")
            count.pack(anchor="w")
            for widget in (heading, count):
                widget.bind("<Button-1>", lambda _, page=target: self.show(page))
            self.metrics_labels[key] = count
        header = ttk.Frame(frame)
        header.grid(row=4, column=0, sticky="ew", pady=(3, 1))
        ttk.Label(header, text="최근 활동", style="Section.TLabel").pack(side="left")
        self.button(header, "원격 작업 보기", lambda: self.show("remote_runs"), side="right")
        self.activity = self.table(frame, 5, (("job", "작업", 250), ("event", "이벤트", 152),
                                              ("task", "노드", 125), ("time", "시각", 110)))
        self.activity.bind("<Double-1>", self.open_activity)
        self.activity.bind("<Return>", self.open_activity)
        ttk.Label(frame, text="활동을 선택하면 해당 실행으로 이동합니다.", style="Muted.TLabel").grid(row=6, column=0, sticky="w")
        return frame

    def refresh_home(self):
        projects, hosts = self.project_rows(), read_workspace(self.root)["hosts"]
        config = read_config(self.root)
        jobs = self.store.list_jobs()
        counts = {key: 0 for key in ("running", "agents", "queued", "failed", "approvals")}
        labels = {"QUEUED": "queued", "PREPARING": "running", "RUNNING": "running", "VERIFYING": "running",
                  "RETRY_WAIT": "queued", "MERGE_QUEUED": "queued", "MERGING": "running", "FAILED": "failed",
                  "AWAITING_APPROVAL": "approvals", "AWAITING_TOOL": "approvals"}
        for job in jobs:
            key = labels.get(job["state"])
            if key:
                counts[key] += 1
            if key in ("running", "approvals"):
                counts["agents"] += sum(task["state"] in LIVE for task in self.store.tasks(job["id"]).values())
        for remote in self.remote_cache.values():
            if remote.get("error") or time.time() - remote.get("at", 0) > 12:
                continue
            key = labels.get(remote.get("state"))
            if key:
                counts[key] += 1
            if key in ("running", "approvals"):
                counts["agents"] += sum(task["state"] in LIVE for task in remote.get("tasks", []))
        counts |= {"projects": len(projects), "providers": len({model["provider"] for model in config["models"].values()}),
                   "mcp": len(config["mcp"]), "hosts": len(hosts) + 1}
        for key, value in counts.items():
            self.metrics_labels[key].configure(text=str(value))
        titles = {job["id"]: job["plan"]["title"] for job in jobs}
        events = self.store.recent_events(limit=45)
        self.activity_records = {str(event["seq"]): event for event in events}
        self.fill(self.activity, [(key, (titles.get(item["run_id"], item["run_id"][:8]),
                          EVENT_LABELS.get(item["event_type"], item["event_type"]), item["task_id"] or "—",
                          datetime.fromtimestamp(item["timestamp"]).strftime("%H:%M:%S")))
                          for key, item in self.activity_records.items()])

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
        self.open_job(job)

    def jobs_page(self):
        frame = super().jobs_page()
        bar = next(widget for widget in frame.grid_slaves(row=2) if isinstance(widget, ttk.Frame))
        self.job_controls = {button.cget("text"): button for button in bar.winfo_children() if isinstance(button, ttk.Button)}
        self.button(bar, "원격 작업", lambda: self.show("remote_runs"), side="right")
        return frame

    def refresh_jobs(self):
        super().refresh_jobs()
        job = self.store.job(self.selected_job) if self.selected_job else None
        state = job["state"] if job else None
        for label, active in (("중지", state is not None and state not in TERMINAL | {"MERGING"}),
                              ("재시도", state == "FAILED"), ("도구 승인 검토", state == "AWAITING_TOOL"),
                              ("병합 승인", bool(job and merge_candidate_ready(job)))):
            if label in self.job_controls:
                self.job_controls[label].state(["!disabled" if active else "disabled"])

    def _job_picker(self, frame, row, change):
        line = ttk.Frame(frame)
        line.grid(row=row, column=0, sticky="ew")
        line.columnconfigure(1, weight=1)
        ttk.Label(line, text="로컬 작업").grid(row=0, column=0, padx=(0, 7), sticky="w")
        picker = ttk.Combobox(line, state="readonly", width=45)
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
        frame = self.base("Agent 대시보드", "실제 노드 상태, 실행 경로, 도구와 QA 이벤트를 확인합니다.")
        bar, self.agents_jobs = self._job_picker(frame, 2, self.pick_agent_job)
        ttk.Button(bar, text="원격 작업", command=lambda: self.show("remote_runs")).grid(row=0, column=2, padx=3)
        self.agent_search = tk.StringVar(self.window)
        self.agent_search.trace_add("write", lambda *_: self.render_agent())
        self.agent_list = self.table(frame, 3, (("task", "Agent / 노드", 175), ("role", "역할", 90),
                      ("state", "단계", 110), ("model", "모델", 145), ("harness", "Harness", 100), ("tools", "도구", 75)))
        self.agent_list.bind("<<TreeviewSelect>>", self.select_agent)
        frame.rowconfigure(3, weight=1)
        frame.rowconfigure(5, weight=2)
        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, sticky="ew", pady=2)
        ttk.Label(actions, text="이벤트 검색").pack(side="left", padx=(0, 4))
        ttk.Entry(actions, textvariable=self.agent_search, width=20).pack(side="left", padx=(0, 8))
        self.button(actions, "작업 상세", lambda: self.open_job(self.agent_job) if self.agent_job else None)
        self.agent_terminal_button = self.button(actions, "Worktree 터미널", lambda: self.action(self.task_terminal))
        self.agent_output_button = self.button(actions, "결과 열기", lambda: self.action(self.task_result))
        self.agent_detail = self.text(frame, 5)
        self.write(self.agent_detail, "작업 실행 기록이 생성되면 Agent 상태가 표시됩니다.", True)
        return frame

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
        self.fill(self.agent_list, [(key, (item["agent"] or key, item["role"] or "—",
                  STATES.get(item["state"], item["state"]), item["model"] or "—", item["harness"] or "—", item["tools"]))
                  for key, item in self.agent_record.items()], self.agent_task)
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
        if not agent:
            return
        render = lambda value: str(value) if value is not None else "미관측"
        started = datetime.fromtimestamp(agent["started"]).strftime("%H:%M:%S") if agent["started"] else "미관측"
        duration = f'{agent["elapsed"]:.1f}초' if agent["elapsed"] is not None else "미관측"
        lines = [f'{agent["id"]} · {STATES.get(agent["state"], agent["state"])} · 이 PC',
                 f'Provider {render(agent["provider"])}   모델 {render(agent["model"])}   Runtime {render(agent["runtime"])}',
                 f'시작 {started}  ·  경과 {duration}  ·  재시도 {agent["retry_count"]}  ·  도구 {agent["tools"]}회',
                 f'입력 {render(agent["input"])}  ·  출력 {render(agent["output"])}  ·  최근 Prompt 토큰 {render(agent["last_prompt"])}'
                 f'  ·  검증된 Context 한도 {render(agent["context"])}',
                 f'변경 파일 {one_line(agent["changed"])}',
                 f'최근 오류 {agent["last_error"] or "—"}', "", "실행 이벤트"]
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
        require(job and job["state"] in TERMINAL and self.agent_task, "종료된 작업의 Worktree를 선택하세요.")
        path = self.root / "worktrees" / self.agent_job / self.agent_task
        require(path.is_dir(), "이 노드의 Worktree가 남아 있지 않습니다.")
        self.new_terminal(f'{self.agent_task} Worktree', cwd=path)

    def task_result(self):
        agent = self.agent_record.get(self.agent_task)
        require(agent and agent["artifact"], "이 노드에 저장된 결과가 없습니다.")
        path = Path(agent["artifact"]).resolve()
        require(path.is_relative_to(self.root.resolve() / "artifacts" / self.agent_job) and path.is_file(),
                "작업 결과 파일을 찾을 수 없습니다.")
        window = tk.Toplevel(self.window)
        window.title("Agent 작업 결과")
        window.geometry("800x530")
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        field = self.text(window, 0)
        with path.open(encoding="utf-8", errors="replace") as source:
            self.write(field, source.read(60000), True)

    def graph_page(self):
        frame = self.base("오케스트레이션", "워크플로의 선행 노드와 실제 실행 상태를 살펴봅니다.")
        _, self.graph_jobs = self._job_picker(frame, 2, self.pick_agent_job)
        frame.rowconfigure(3, weight=1)
        body = ttk.Frame(frame)
        body.grid(row=3, column=0, sticky="nsew", pady=7)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.graph = tk.Canvas(body, bg=PANEL, highlightthickness=0, height=350)
        self.graph.grid(row=0, column=0, sticky="nsew")
        for direction, axis in (("vertical", "y"), ("horizontal", "x")):
            scroll = ttk.Scrollbar(body, orient=direction, command=getattr(self.graph, axis + "view"))
            self.graph.configure(**{axis + "scrollcommand": scroll.set})
            scroll.grid(row=0 if axis == "y" else 1, column=1 if axis == "y" else 0, sticky="ns" if axis == "y" else "ew")
        self.graph_version = None
        panel = ttk.Frame(frame)
        panel.grid(row=4, column=0, sticky="ew")
        self.button(panel, "작업 실행 기록", lambda: self.open_job(self.agent_job) if self.agent_job else None)
        self.button(panel, "실행 보고서 비교", self.compare_runs)
        return frame

    def refresh_graph(self):
        self.agent_choices = self._choices(self.graph_jobs)
        job = self.store.job(self.agent_job) if self.agent_job else None
        nodes = job["plan"]["tasks"] if job else []
        task_states = self.store.tasks(self.agent_job) if job else {}
        version = (self.agent_job, tuple((key, value["state"]) for key, value in task_states.items()))
        if version == self.graph_version:
            return
        self.graph_version = version
        self.graph.delete("all")
        if not nodes:
            self.graph.create_text(22, 30, anchor="nw", text="작업을 선택하면 노드와 선행 관계를 표시합니다.", fill=MUTED)
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
            positions[key] = 25 + column * 238, 28 + row * 103
        for key, node in by_id.items():
            x, y = positions[key]
            for dep in node.get("depends", []):
                sx, sy = positions[dep]
                self.graph.create_line(sx + 184, sy + 32, x, y + 32, arrow="last", fill="#647fa4", width=2)
        for key, (x, y) in positions.items():
            state = task_states.get(key, {}).get("state", "QUEUED")
            color = {"SUCCEEDED": "#e6f6ed", "RUNNING": "#e2eeff", "FAILED": "#ffe8e8",
                     "AWAITING_TOOL": "#fff1d6"}.get(state, "#edf2f7")
            tag = "node_" + key
            self.graph.create_rectangle(x, y, x + 184, y + 66, fill=color, outline="#b1c3d9", tags=tag)
            self.graph.create_text(x + 9, y + 18, text=key[:23], anchor="w", fill="#172b47", tags=tag)
            self.graph.create_text(x + 9, y + 42, text=f'{by_id[key]["role"]}  ·  {STATES.get(state, state)}',
                                   anchor="w", fill=MUTED, tags=tag)
            self.graph.tag_bind(tag, "<Button-1>", lambda _, task=key: self.open_graph_node(task))
        self.graph.configure(scrollregion=self.graph.bbox("all"))

    def open_graph_node(self, key):
        self.agent_task = key
        self.show("agents")

    def compare_runs(self):
        rows = {f'{row["plan"]["title"][:40]} · {row["id"][:7]}': row["id"] for row in self.store.list_jobs()}
        form = Form(self, "실행 보고서 비교", "두 로컬 실행의 기준 커밋, 상태, 소요 시간과 관측된 토큰을 비교합니다.")
        first = next(iter(rows), "")
        form.field("a", "기준 실행", first, choices=list(rows))
        form.field("b", "비교 실행", next(iter(list(rows)[1:]), first), choices=list(rows))
        result = form.note("")
        def compare():
            require(form.get("a") in rows and form.get("b") in rows, "비교할 실행을 선택하세요.")
            texts = []
            for key in ("a", "b"):
                item = self.store.report(rows[form.get(key)])
                seconds = item["seconds_to_verified"]
                texts.append(f'{form.get(key)} · {STATES.get(item["state"], item["state"])}\n'
                             f'기준 {item["base"] or "—"} · 검증 시간 {f"{seconds:.1f}초" if seconds is not None else "—"} · '
                             f'관측 토큰 {item["tokens_observed"] if item["tokens_observed"] is not None else "미관측"}')
            result.configure(text="\n\n".join(texts))
        form.controls("비교", compare)

    def terminals_page(self):
        frame = self.base("통합 터미널", "로컬 또는 SSH PTY 셸을 열고 탭과 분할 창에서 작업합니다.")
        frame.rowconfigure(3, weight=1)
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew")
        self.button(bar, "로컬 셸 열기", lambda: self.action(self.local_project_shell), True)
        self.button(bar, "SSH 연결로 이동", lambda: self.show("hosts"))
        self.button(bar, "선택한 탭 분할", lambda: self.action(self.split_terminal))
        self.button(bar, "세션 다시 열기", lambda: self.action(self.reopen_terminal))
        self.button(bar, "탭 닫기", self.remove_terminal)
        self.terminal_book = ttk.Notebook(frame)
        self.terminal_book.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        blank = ttk.Frame(self.terminal_book, padding=20)
        ttk.Label(blank, text="셸을 열면 실제 터미널이 여기에 표시됩니다.").pack(anchor="w")
        self.terminal_book.add(blank, text="시작")
        return frame

    def local_project_shell(self):
        project = self.project_rows().get(self.project_id, {})
        cwd = Path(project["path"]) if project and not project.get("host") else None
        self.new_terminal("로컬 셸", cwd=cwd)

    def project_terminal(self, project):
        def open_session():
            if project.get("host"):
                client = self.ssh(project["host"])
                self.new_terminal(project["name"], client.terminal(project["path"]), env=ssh_env())
            else:
                self.new_terminal(project["name"], cwd=Path(project["path"]))
        self.action(open_session)

    def new_terminal(self, title="로컬 셸", argv=None, cwd=None, env=None):
        pane = ttk.Panedwindow(self.terminal_book, orient="horizontal")
        args = argv if argv else operator_shell()
        try:
            view = TerminalView(pane, args, cwd, env, font=self.mono_font)
        except BaseException:
            pane.destroy()
            raise
        pane.add(view, weight=1)
        self.terminals[str(pane)] = pane, [view]
        self.terminal_retry[str(pane)] = title, args, cwd, env
        self.terminal_book.add(pane, text=title[:26])
        self.show("terminals")
        self.terminal_book.select(pane)
        view.surface.focus_set()

    def split_terminal(self):
        selected = self.terminal_book.select()
        require(selected in self.terminals, "분할할 터미널 탭을 선택하세요.")
        title, args, cwd, env = self.terminal_retry[selected]
        pane, sessions = self.terminals[selected]
        require(len(sessions) == 1, "이미 분할된 터미널입니다.")
        view = TerminalView(pane, args, cwd, env, font=self.mono_font)
        sessions.append(view)
        pane.add(view, weight=1)
        view.surface.focus_set()

    def reopen_terminal(self):
        selected = self.terminal_book.select()
        require(selected in self.terminal_retry, "다시 열 터미널 탭을 선택하세요.")
        self.new_terminal(*self.terminal_retry[selected])

    def remove_terminal(self):
        selected = self.terminal_book.select()
        if selected in self.terminals:
            pane, sessions = self.terminals.pop(selected)
            for item in sessions:
                item.close()
            self.terminal_retry.pop(selected)
            self.terminal_book.forget(pane)
            pane.destroy()

    def mcp_page(self):
        frame = super().mcp_page()
        bar = ttk.Frame(frame)
        bar.grid(row=6, column=0, sticky="ew")
        self.button(bar, "Managed 도구 카탈로그", self.managed_mcp, True)
        self.button(bar, "서버와 권한 설정", self.edit_mcp)
        return frame

    def mcp_profile_form(self, title):
        config = read_config(self.root)
        form = Form(self, title)
        form.field("profile", "등록 프로필", next(iter(config["mcp"]), ""), choices=list(config["mcp"]))
        return form, config

    def edit_mcp(self):
        form, config = self.mcp_profile_form("Managed MCP 서버와 권한")
        revision = registry_revision(self.root)
        form.field("id", "저장할 프로필 ID", "")
        form.field("transport", "전송 방식", "http", choices=("http", "stdio"))
        form.field("endpoint", "URL 또는 실행 argv")
        form.field("secret", "인증 환경 변수 참조", help_text="HTTP의 Authorization 값 또는 stdio 전달 변수 이름입니다.")
        form.field("tool", "도구 이름", help_text="저장하면 해당 도구 정책을 새로 추가하거나 수정합니다.")
        form.field("access", "도구 접근", "read", choices=("read", "write"))
        form.field("roles", "허용 역할", "explorer, reviewer", help_text="여러 역할은 쉼표로 구분합니다. write는 기존 승인 절차를 적용합니다.")
        form.field("agents", "허용 Agent ID", help_text="선택 사항 · 역할/노드ID를 쉼표로 구분합니다.")
        form.field("native", "Native Gateway 읽기 노출", False, boolean=True)
        form.field("gateway", "Gateway 토큰 환경 변수")
        def loaded():
            key = form.get("profile")
            require(key in config["mcp"], "불러올 프로필을 선택하세요.")
            value = config["mcp"][key]
            form.set("id", key)
            form.set("transport", value["transport"])
            form.set("endpoint", value.get("url", "") if value["transport"] == "http"
                     else format_commands([value["command"]]))
            form.set("secret", value.get("header_env", {}).get("Authorization", "") if value["transport"] == "http"
                     else one_line(value.get("env")) if value.get("env") else "")
            form.set("gateway", value.get("gateway_token_env", ""))
        self.button(form.footer, "선택 프로필 불러오기", lambda: self.action(loaded))
        def store():
            from .core import ident
            from .runtime import checked_url
            key = ident(form.get("id"))
            value = dict(config["mcp"].get(key, {}))
            old = value.get("transport")
            transport, target = form.get("transport"), form.get("endpoint")
            require(not old or old == transport, "기존 전송 방식을 바꾸려면 별도 프로필을 등록하세요.")
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
                require(len(entries) == 1 and entries[0], "서버 실행 명령을 한 줄에 작성하세요.")
                value.update(command=entries[0], env=split_names(form.get("secret")))
            if form.get("gateway"):
                value["gateway_token_env"] = form.get("gateway")
            else:
                value.pop("gateway_token_env", None)
            if form.get("tool"):
                tools = dict(value.get("tools", {}))
                tool = form.get("tool")
                tools[tool] = dict(tools.get(tool, {})) | {"access": form.get("access"), "roles": split_names(form.get("roles")),
                                                          "agents": split_names(form.get("agents")), "native": form.get("native")}
                value["tools"] = tools
            config["mcp"][key] = value
            save_registry(self.root, config, revision)
            self.restart_supervisor()
            form.destroy()
        form.controls("등록 및 정책 저장", store)

    def managed_mcp(self):
        form, config = self.mcp_profile_form("Managed MCP 도구 카탈로그")
        form.field("tool", "읽기 테스트 도구", choices=[])
        form.field("args", "테스트 인자", "{}", multiline=True)
        summary = form.note("등록된 서버를 선택하고 실제 목록을 요청하세요.")
        form.width = 660
        catalog = {}
        def fetch():
            key = form.get("profile")
            spec = config["mcp"].get(key)
            require(spec, "Managed MCP 프로필을 등록하고 선택하세요.")
            def inspect():
                with MCPClient(spec) as client:
                    return client.catalog()
            def present(value):
                if not form.winfo_exists() or form.get("profile") != key:
                    return
                catalog.clear()
                catalog.update(value)
                marked = [name for name in value if spec.get("tools", {}).get(name, {}).get("access") == "read"
                          and spec["tools"][name].get("roles") and not spec["tools"][name].get("agents")]
                form.set("tool", next(iter(marked), ""), marked)
                lines = []
                for name, tool in list(value.items())[:12]:
                    policy = spec.get("tools", {}).get(name, {})
                    lines.append(f'{name} · {policy.get("access", "차단")} · {one_line(policy.get("roles"))}\n'
                                 f'{str(tool.get("description") or "")[:160]}')
                recent = self.store.recent_events("gateway:" + key, limit=20)
                last = next((event for event in recent if event["event_type"] in ("gateway.call", "gateway.test")), None)
                stamp = datetime.fromtimestamp(last["timestamp"]).strftime("%H:%M:%S") if last else "미관측"
                failures = sum(event["event_type"] in ("gateway.failed", "gateway.denied") for event in recent)
                summary.configure(text=f"카탈로그 확인 성공 · {len(value)}개 · 최근 성공 {stamp} · 최근 실패/거절 {failures}건\n" + "\n".join(lines))
            self.background(inspect, present)
        self.button(form.footer, "목록 조회", lambda: self.action(fetch))
        def probe():
            key, tool = form.get("profile"), form.get("tool")
            spec = config["mcp"].get(key)
            rule = spec and spec.get("tools", {}).get(tool)
            require(rule and rule.get("roles") and rule["access"] == "read" and not rule.get("agents"),
                    "특정 Agent에 제한되지 않은 읽기 도구를 선택하세요.")
            args = json.loads(form.get("args"))
            require(isinstance(args, dict), "도구 인자는 JSON 객체여야 합니다.")
            if not messagebox.askyesno("읽기 도구 호출 승인", f"{tool}을 테스트하시겠습니까?", parent=form):
                return
            def invoke():
                from .mcp import virtual_name
                alias = virtual_name(key, tool)
                with MCPClient(spec) as client:
                    allowed = published(key, spec, client.catalog(), rule["roles"][0], {alias})
                    require(alias in allowed, "도구 권한 또는 입력 스키마를 검증할 수 없습니다.")
                    _, schema, _ = allowed[alias]
                    result = do_call(client, tool, schema, args)
                self.store.event("gateway:" + key, None, "gateway.test", {"name": tool})
                return result
            self.background(invoke, lambda result: summary.configure(text=f"테스트 성공 · {len(result.get('content', []))}개 결과")
                            if form.winfo_exists() else None)
        form.controls("읽기 도구 테스트", probe)

    def close(self):
        for _, sessions in self.terminals.values():
            for session in sessions:
                session.close()
        super().close()
