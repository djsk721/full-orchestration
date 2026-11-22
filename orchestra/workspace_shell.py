"""Project workspace shell built over the existing Tk operator services."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from .core import atomic_json, require
from .execution_state import MERGE_EVIDENCE, TERMINAL, merge_candidate_ready
from .observability import EVENT_LABELS, agent_rows
from .supervisor import read_config
from .ui import DIMENSIONS, NavRow, PRIMARY_NAV, STRINGS, StatusBadge, Tooltip, state_label, t
from .workspace import format_commands, read_workspace, scan_clis


INTERACTIVE_CLIS = ("OpenCode", "Codex", "Gemini CLI", "Antigravity", "Claude Code")

ROUTE_SPECS = {
    "workspace": ("nav.workspace", "workspace", None),
    "jobs": ("nav.jobs", "jobs", "refresh_jobs"),
    "agents": ("nav.agents", "agents", "refresh_agents"),
    "projects": ("nav.projects", "projects", "refresh_projects"),
    "settings": ("nav.settings", "settings", "refresh_settings"),
    "providers": ("nav.providers", "settings", "refresh_providers"),
    "ssh": ("nav.ssh", "settings", "refresh_ssh"),
    "hosts": ("nav.hosts", "settings", "refresh_hosts"),
    "mcp": ("nav.mcp", "settings", None),
    "history": ("nav.history", "jobs", "refresh_history"),
    "home": ("nav.home", "workspace", "refresh_home"),
    "submit": ("submit.title", "jobs", "_wizard_sync_projects"),
    "dag": ("DAG", "jobs", "refresh_graph"),
    "remote_runs": ("원격 작업", "jobs", "refresh_remote"),
    "advanced_plan": ("고급 JSON 편집", "jobs", None),
    "registry": ("고급 레지스트리", "settings", "_ensure_registry_loaded"),
    "terminals": ("nav.terminals", "workspace", None),
}


def same_repository(left, right):
    return bool(left and right and os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right)))


def read_layout(path):
    try:
        with path.open("rb") as source:
            data = source.read(256 * 1024 + 1)
        if len(data) > 256 * 1024:
            return {}
        value = json.loads(data)
        return value if isinstance(value, dict) and type(value.get("version")) is int and value["version"] == 1 else {}
    except (OSError, ValueError):
        return {}


class IntegratedWorkspace:
    def _route_tab_title(self, key: str) -> str:
        spec = ROUTE_SPECS.get(key)
        label_key = spec[0] if spec else key
        if label_key in STRINGS.get("ko", {}):
            return t(label_key, self.locale)[:25]
        return self.w(label_key)[:25]

    def _update_nav_highlight(self, view_key: str) -> None:
        nav_target = ROUTE_SPECS.get(view_key, (None, view_key, None))[1]
        for name, row in getattr(self, "nav_rows", {}).items():
            if isinstance(row, NavRow):
                row.set_active(name == nav_target)

    def _ensure_registry_loaded(self) -> None:
        if hasattr(self, "registry") and not self.registry.get("1.0", "end-1c").strip():
            self.reload_registry()

    def _run_route_refresh(self, key: str) -> None:
        spec = ROUTE_SPECS.get(key)
        method_name = spec[2] if spec else None
        if method_name and hasattr(self, method_name):
            self.action(getattr(self, method_name))

    def _fit_header(self, event=None) -> None:
        if not hasattr(self, "header_left") or not hasattr(self, "header_right"):
            return
        width = event.width if event else self.header_bar.winfo_width()
        if width < 100:
            return
        required = self.header_left.winfo_reqwidth() + self.header_right.winfo_reqwidth() + 12
        info = self.header_right.grid_info()
        row = int(info.get("row", 0)) if info else 0
        if width < required and row == 0:
            self.header_right.grid_configure(row=1, column=0, sticky="w")
        elif width >= required and row != 0:
            self.header_right.grid_configure(row=0, column=1, sticky="e")

    def build_unified_shell(self):
        p = self.palette
        self.workspace_layout_path = self.root / "ui-workspace.json"
        self.workspace_prefs = read_layout(self.workspace_layout_path)
        self.workspace_layout_writable = bool(self.workspace_prefs) or not self.workspace_layout_path.exists()
        self.workspace_tabs = {}
        self.workspace_agent_keys = {}
        self.workspace_sidebar_rows = ()
        self.workspace_sidebar_actions = {}
        self.workspace_palette = None
        self.workspace_save_timer = None
        self.workspace_restore_done = False
        self.workspace_focus_panels = None
        self.route_tab_frames = {}
        self.workspace_context_fraction = .71
        saved = self.workspace_prefs.get("center_fraction")
        if type(saved) in (float, int) and .42 <= saved <= .83:
            self.workspace_context_fraction = saved
        self.workspace_set_sash = True
        self.workspace_sash_width = None

        self.window.columnconfigure(0, weight=0)
        self.window.columnconfigure(1, weight=1)
        self.window.rowconfigure(0, weight=0)
        self.window.rowconfigure(1, weight=1)
        self.window.rowconfigure(2, weight=0)

        # Row 0: ONE Global Header
        self.header_bar = tk.Frame(
            self.window, bg=p["header"], height=DIMENSIONS["header_height"],
            highlightthickness=1, highlightbackground=p["border"], bd=0,
        )
        self.header_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.header_bar.columnconfigure(0, weight=1)
        self.header_bar.rowconfigure(0, minsize=DIMENSIONS["header_height"])

        self.header_left = tk.Frame(self.header_bar, bg=p["header"], padx=8, pady=5)
        self.header_left.grid(row=0, column=0, sticky="w")
        self.workspace_actions = ttk.Frame(self.header_left, style="Header.TFrame")
        self.workspace_actions.pack(side="left")

        self.sidebar_toggle_btn = ttk.Button(
            self.workspace_actions, text="≡", style="Icon.TButton", width=2,
            command=self.workspace_toggle_sidebar,
        )
        self.sidebar_toggle_btn.pack(side="left", padx=(0, 6))
        self.workspace_tooltip(self.sidebar_toggle_btn, lambda: self.w("사이드바 접기 / 열기"))

        self.sidebar_project = tk.StringVar(self.window, t("header.project_unselected", self.locale))
        self.sidebar_picker = ttk.Combobox(
            self.workspace_actions, textvariable=self.sidebar_project, state="readonly", width=14,
        )
        self.sidebar_picker.pack(side="left", padx=(0, 6))
        self.sidebar_picker.bind("<<ComboboxSelected>>", self.pick_sidebar)

        self.header_env_badge = StatusBadge(
            self.workspace_actions, p, text=self.host_name(None), tone="neutral", ui_font=self.ui_font,
        )
        self.header_env_badge.pack(side="left", padx=(0, 6))

        self.header_new_task = ttk.Button(
            self.workspace_actions, text=self.w("새 작업"), style="Primary.TButton",
            command=self.workspace_new_task,
        )
        self.header_new_task.pack(side="left", padx=(0, 5))

        self.workspace_terminal_button = ttk.Button(
            self.workspace_actions, text=self.w("터미널 ▾"), style="Compact.TButton",
            command=self.workspace_terminal_menu,
        )
        self.workspace_terminal_button.pack(side="left", padx=(0, 5))

        self.workspace_models = tk.StringVar(self.window)
        self.workspace_model_picker = ttk.Combobox(
            self.workspace_actions, textvariable=self.workspace_models, state="readonly", width=18,
        )
        self.workspace_model_picker.pack(side="left", padx=(0, 4))
        self.workspace_model_picker.bind("<<ComboboxSelected>>", self.workspace_choose_model)
        self.workspace_tooltip(
            self.workspace_model_picker,
            lambda: self.w("새 작업의 기본 모델입니다.") + "\n" + self.workspace_models.get(),
        )

        self.header_right = tk.Frame(self.header_bar, bg=p["header"], padx=8, pady=5)
        self.header_right.grid(row=0, column=1, sticky="e")
        self.workspace_view_actions = ttk.Frame(self.header_right, style="Header.TFrame")
        self.workspace_view_actions.pack(side="right")

        self.header_supervisor_badge = StatusBadge(
            self.workspace_view_actions, p, text="● Supervisor", tone="warning", ui_font=self.ui_font,
        )
        self.header_supervisor_badge.pack(side="left", padx=(0, 5))
        self.workspace_tooltip(self.header_supervisor_badge, lambda: self.status.cget("text") if hasattr(self, "status") else "Supervisor")

        self.header_notice_badge = StatusBadge(
            self.workspace_view_actions, p, text="0", tone="neutral", ui_font=self.ui_font,
        )
        self.header_notice_badge.pack(side="left", padx=(0, 6))
        self.header_notice_badge.configure(cursor="hand2")
        self.header_notice_badge.bind("<Button-1>", lambda _e: self.show("jobs"))

        self.workspace_layout_button = ttk.Button(
            self.workspace_view_actions, text=self.w("보기 ▾"), style="Compact.TButton",
            command=self.workspace_layout_menu,
        )
        self.workspace_layout_button.pack(side="left", padx=(0, 4))

        self.workspace_focus_button = ttk.Button(
            self.workspace_view_actions, text=self.w("집중"), style="Compact.TButton",
            command=self.workspace_toggle_focus,
        )
        self.workspace_focus_button.pack(side="left", padx=(0, 4))
        self.workspace_tooltip(
            self.workspace_focus_button,
            lambda: self.w(
                "숨기기 전의 패널 배치로 돌아갑니다." if self.workspace_focus_panels is not None
                else "옆 패널을 접어 터미널에 더 넓은 공간을 줍니다."
            ),
        )

        theme_label = t("header.theme_light", self.locale) if self.theme_name == "dark" else t("header.theme_dark", self.locale)
        self.theme_btn = ttk.Button(
            self.workspace_view_actions, text=theme_label, style="Compact.TButton",
            command=self.toggle_theme,
        )
        self.theme_btn.pack(side="left")
        self.header_bar.bind("<Configure>", self._fit_header)

        # Row 1, Col 0: ONE Unified Orca Sidebar
        self.nav_frame = tk.Frame(
            self.window, bg=p["sidebar"], width=DIMENSIONS["sidebar_width"],
            highlightthickness=1, highlightbackground=p["sidebar_border"], bd=0,
        )
        self.nav_frame.grid(row=1, column=0, sticky="nsew")
        self.nav_frame.grid_propagate(False)
        self.nav_frame.columnconfigure(0, weight=1)
        self.nav_frame.rowconfigure(4, weight=1)
        self.workspace_sidebar = self.nav_frame

        self.brand_box = tk.Frame(self.nav_frame, bg=p["sidebar"], padx=12, pady=8)
        self.brand_box.grid(row=0, column=0, sticky="ew")
        self.brand_title = tk.Label(
            self.brand_box, text=t("app.brand", self.locale), anchor="w", justify="left",
            bg=p["sidebar"], fg=p["text"], font=(self.ui_font, 10, "bold"),
        )
        self.brand_title.pack(fill="x")

        search_wrap = ttk.Frame(self.nav_frame, style="Sidebar.TFrame", padding=(10, 0, 10, 6))
        search_wrap.grid(row=1, column=0, sticky="ew")
        search_wrap.columnconfigure(0, weight=1)
        self.workspace_search = tk.StringVar(self.window)
        self.workspace_search_field = ttk.Entry(search_wrap, textvariable=self.workspace_search)
        self.workspace_search_field.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.workspace_search.trace_add("write", lambda *_: self.refresh_workspace_sidebar())
        self.workspace_tooltip(self.workspace_search_field, lambda: self.w("프로젝트·세션 검색"))
        cmd_btn = ttk.Button(search_wrap, text=self.w("메뉴"), style="Compact.TButton", command=self.workspace_command_palette)
        cmd_btn.grid(row=0, column=1)
        self.workspace_tooltip(cmd_btn, lambda: t("nav.search_placeholder", self.locale))

        self.primary_nav_box = self.track_themed(tk.Frame(self.nav_frame, bg=p["sidebar"], pady=2), bg_key="sidebar")
        self.primary_nav_box.grid(row=2, column=0, sticky="ew")
        self.nav_rows = {}
        self.nav_buttons = {}
        for key, str_key, glyph in PRIMARY_NAV:
            row = NavRow(
                self.primary_nav_box, p, t(str_key, self.locale), icon=glyph,
                ui_font=self.ui_font, command=lambda name=key: self.show(name),
            )
            row.pack(fill="x", padx=6, pady=1)
            self.nav_rows[key] = row
            self.nav_buttons[key] = row

        heading_wrap = ttk.Frame(self.nav_frame, style="Sidebar.TFrame", padding=(10, 6, 8, 2))
        heading_wrap.grid(row=3, column=0, sticky="ew")
        heading_wrap.columnconfigure(0, weight=1)
        ttk.Separator(heading_wrap).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(heading_wrap, text=self.w("프로젝트 및 세션"), style="SidebarSection.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Button(heading_wrap, text=self.w("+ 추가"), style="Compact.TButton", command=self.workspace_add_menu).grid(row=1, column=1, sticky="e")

        tree_wrap = ttk.Frame(self.nav_frame, style="Sidebar.TFrame", padding=(6, 2, 4, 4))
        tree_wrap.grid(row=4, column=0, sticky="nsew")
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)
        tree = ttk.Treeview(tree_wrap, style="Sidebar.Treeview", show="tree", selectmode="browse", height=12)
        tree.column("#0", width=205, minwidth=90, stretch=True)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)
        tree.bind("<Double-1>", self.workspace_sidebar_open)
        tree.bind("<Return>", self.workspace_sidebar_open)
        tree.bind("<Button-3>", self.workspace_sidebar_menu)
        tree.bind("<ButtonRelease-1>", self.workspace_sidebar_click)
        self.workspace_tree = tree

        self.sidebar_utility = self.track_themed(
            tk.Frame(self.nav_frame, bg=p["sidebar"], padx=8, pady=6, highlightthickness=1, highlightbackground=p["sidebar_border"], bd=0),
            bg_key="sidebar", border_key="sidebar_border",
        )
        self.sidebar_utility.grid(row=5, column=0, sticky="ew")
        self.sidebar_utility.columnconfigure(0, weight=1, uniform="sidebar_util")
        self.sidebar_utility.columnconfigure(1, weight=1, uniform="sidebar_util")
        for idx, (label_text, route) in enumerate((
            (self.w("Provider"), "providers"),
            (self.w("SSH"), "ssh"),
            (self.w("MCP"), "mcp"),
            (self.w("기록"), "history"),
        )):
            ttk.Button(
                self.sidebar_utility, text=label_text, style="Compact.TButton",
                command=lambda r=route: self.show(r),
            ).grid(row=idx // 2, column=idx % 2, sticky="ew", padx=2, pady=2)

        # Row 1, Col 1: ONE Unified Workspace Content + Context Panel
        self.main_shell = ttk.Frame(self.window)
        self.main_shell.grid(row=1, column=1, sticky="nsew")
        self.main_shell.columnconfigure(0, weight=1)
        self.main_shell.rowconfigure(0, weight=1)

        self.workspace_panes = ttk.Panedwindow(self.main_shell, orient="horizontal")
        self.workspace_panes.grid(row=0, column=0, sticky="nsew")

        center = ttk.Frame(self.workspace_panes)
        center.rowconfigure(0, weight=1)
        center.columnconfigure(0, weight=1)
        self.workspace_book = ttk.Notebook(center, style="Workspace.TNotebook")
        self.workspace_book.grid(row=0, column=0, sticky="nsew")
        self.workspace_panes.add(center, weight=4)

        self.host = self.workspace_book
        self.init_workspace_sessions(self.workspace_book)
        self.workspace_book.bind("<<NotebookTabChanged>>", self.workspace_tab_changed, add="+")
        self.workspace_book.bind("<Button-2>", self._workspace_tab_middle_click, add="+")
        self.workspace_book.bind("<Button-3>", self._workspace_tab_context_menu, add="+")

        self.workspace_context = self.build_workspace_context(self.workspace_panes)
        self.workspace_panes.add(self.workspace_context, weight=1)
        self.workspace_panes.bind("<Configure>", self.workspace_restore_sash)
        self.workspace_panes.bind("<ButtonRelease-1>", self.workspace_capture_sash, add="+")
        self.build_workspace_observation()
        self.workspace_context.bind("<<NotebookTabChanged>>", self.workspace_context_tab_changed, add="+")

        # Row 2, Col 0..1: ONE Unified Status Bar
        self.status_bar = tk.Frame(
            self.window, bg=p["status_bar"], highlightthickness=1, highlightbackground=p["status_border"], bd=0,
        )
        self.status_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.status_bar.columnconfigure(0, weight=1)
        self.workspace_status = ttk.Label(
            self.status_bar, style="StatusBar.TLabel", text=self.w("프로젝트를 선택하세요."), padding=(10, 2),
        )
        self.workspace_status.grid(row=0, column=0, sticky="ew")
        self.workspace_runtime_status = ttk.Label(
            self.status_bar, style="StatusBar.TLabel", padding=(10, 2),
        )
        self.workspace_runtime_status.grid(row=1, column=0, sticky="ew")
        self.header_workers_badge = StatusBadge(
            self.status_bar, p, text=self.w("로컬 Worker"), tone="neutral", ui_font=self.ui_font,
        )
        self.header_workers_badge.grid(row=0, column=1, rowspan=2, sticky="e", padx=(6, 10), pady=3)
        self.status = ttk.Label(self.status_bar, text=t("header.supervisor_connecting", self.locale), style="StatusBar.TLabel")
        for widget in (self.workspace_status, self.workspace_runtime_status):
            self.status_bar.bind(
                "<Configure>",
                lambda event, label=widget: label.configure(wraplength=max(200, event.width - 140)),
                add="+",
            )

        # Build Overview tab + All unified workspace route pages
        self.workspace_overview = self._build_workspace_overview()
        self.workspace_book.add(self.workspace_overview, text=self.w("프로젝트 개요"))
        self.pages = {"workspace": self.workspace_overview}
        for key, _, factory in self.navigation():
            if key == "workspace":
                continue
            self.pages[key] = factory()
        self.route_tab_frames = {str(frame): key for key, frame in self.pages.items() if key != "workspace"}
        return self.workspace_overview

    def _build_workspace_overview(self):
        overview = ttk.Frame(self.workspace_book, padding=(18, 14))
        overview.columnconfigure(0, weight=1)
        overview.rowconfigure(2, weight=1)
        self.workspace_title = ttk.Label(overview, text=self.w("프로젝트 선택"), style="PageHeading.TLabel")
        self.workspace_title.grid(row=0, column=0, sticky="w")
        project_actions = ttk.Frame(overview)
        project_actions.grid(row=1, column=0, sticky="ew", pady=(10, 6))
        self.workspace_setup_button = self.button(project_actions, self.w("작업 공간 설정"), self.open_workspace_setup, True)
        self.workspace_add_repo = self.button(project_actions, self.w("저장소 추가"), self.add_local_project)
        self.workspace_project_cli = self.button(
            project_actions, self.w("터미널 열기 ▾"),
            lambda: self.workspace_terminal_menu(self.workspace_project_cli), True,
        )
        self.workspace_overview_text = self.text(overview, 2, height=11)
        self.write(self.workspace_overview_text, self.w("왼쪽에서 프로젝트를 열거나 Git 저장소를 등록하세요."), True)
        return overview

    def workspace_page(self):
        if hasattr(self, "workspace_overview"):
            return self.workspace_overview
        return self.build_unified_shell()

    def _workspace_tab_middle_click(self, event):
        try:
            index = self.workspace_book.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        tab = self.workspace_book.tabs()[index]
        if tab != str(self.workspace_overview):
            self.close_workspace_tab(tab)

    def _workspace_tab_context_menu(self, event):
        try:
            index = self.workspace_book.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        tab = self.workspace_book.tabs()[index]
        menu = tk.Menu(self.window, tearoff=False)
        if tab != str(self.workspace_overview):
            menu.add_command(label=self.w("현재 탭 닫기"), command=lambda t_id=tab: self.close_workspace_tab(t_id))
        menu.add_command(label=self.w("다른 탭 닫기"), command=lambda t_id=tab: self._close_other_workspace_tabs(t_id))
        menu.add_separator()
        menu.add_command(label=self.w("탭 왼쪽으로 이동"), command=lambda: (self.workspace_book.select(tab), self.workspace_move_tab(-1)))
        menu.add_command(label=self.w("탭 오른쪽으로 이동"), command=lambda: (self.workspace_book.select(tab), self.workspace_move_tab(1)))
        menu.tk_popup(event.x_root, event.y_root)

    def _close_other_workspace_tabs(self, keep_tab):
        for tab in list(self.workspace_book.tabs()):
            if tab in (keep_tab, str(self.workspace_overview)):
                continue
            self.close_workspace_tab(tab)

    def workspace_tooltip(self, widget, message):
        Tooltip(widget, message)

    def workspace_toggle_focus(self):
        panels = self.workspace_focus_panels
        current = (bool(self.workspace_prefs.get("sidebar_hidden")), len(self.workspace_panes.panes()) == 1)
        self.workspace_focus_panels = current if panels is None else None
        target = (True, True) if panels is None else panels
        if current[0] != target[0]:
            self.workspace_toggle_sidebar()
        if current[1] != target[1]:
            self.workspace_toggle_context()
        self.workspace_focus_button.configure(text=self.w("패널 복원") if panels is None else self.w("집중"))

    def workspace_context_tab_changed(self, _=None):
        tab = self.workspace_context.select()
        if self.project_id and tab:
            positions = self.workspace_prefs.setdefault("project_context", {})
            if not isinstance(positions, dict):
                positions = self.workspace_prefs["project_context"] = {}
            if len(positions) < 200 or self.project_id in positions:
                positions[self.project_id] = self.workspace_context.index(tab)
                self.workspace_save_later()

    def build_workspace_sidebar(self):
        # Sidebar is built once inside build_unified_shell(); kept for API compatibility.
        return getattr(self, "nav_frame", None)

    def restore_workspace(self):
        if self.workspace_restore_done:
            return
        self.workspace_restore_done = True
        projects = self.project_rows()
        saved = self.workspace_prefs.get("project")
        selected = saved if isinstance(saved, str) and saved in projects else next(iter(projects), None)
        self.project_id = selected
        restored = self.restore_terminal_descriptors(self.workspace_prefs.get("terminals", []))
        saved_tabs = self.workspace_prefs.get("job_tabs")
        remote_runs = {row["id"]: row for row in self.store.remote_runs()}
        for saved_tab in saved_tabs[:16] if isinstance(saved_tabs, list) else []:
            key = saved_tab.get("id") if isinstance(saved_tab, dict) else saved_tab
            if isinstance(key, str):
                if key in remote_runs:
                    self.open_workspace_remote(key, activate=False)
                elif self.store.job(key):
                    self.open_workspace_job(key, activate=False)
                if key in self.workspace_tabs:
                    restored["job/" + key] = str(self.workspace_tabs[key]["frame"])
        saved_routes = self.workspace_prefs.get("route_tabs")
        for key in saved_routes[:16] if isinstance(saved_routes, list) else []:
            if isinstance(key, str) and key in self.pages and key != "workspace":
                frame = self.pages[key]
                if str(frame) not in self.workspace_book.tabs():
                    self.workspace_book.add(frame, text=self._route_tab_title(key))
                restored["route/" + key] = str(frame)
        restored["overview"] = str(self.workspace_overview)
        order = self.workspace_prefs.get("tab_order")
        if isinstance(order, list):
            ordered = dict.fromkeys(restored[item] for item in order[:57] if isinstance(item, str) and item in restored)
            for index, tab in enumerate(ordered):
                self.workspace_book.insert(index, tab)
        if self.workspace_prefs.get("context_hidden") is True:
            self.workspace_panes.forget(self.workspace_context)
        self.workspace_show(True)
        active = self.workspace_prefs.get("active_tab")
        tab = restored.get(active) if isinstance(active, str) else None
        target = tab if tab and self.workspace_book.tab(tab, "state") != "hidden" else self.workspace_overview
        self.workspace_book.select(target)
        route_key = self.route_tab_frames.get(str(target))
        if route_key:
            self.view = route_key
            self._update_nav_highlight(route_key)
            self._run_route_refresh(route_key)
        else:
            self.view = "workspace"
            self._update_nav_highlight("workspace")
        self.refresh_workspace()

    def workspace_show(self, _active=True):
        if not hasattr(self, "nav_frame"):
            return
        if self.workspace_prefs.get("sidebar_hidden") is True:
            self.nav_frame.grid_remove()
        else:
            self.nav_frame.grid()

    def workspace_restore_sash(self, _=None):
        width = self.workspace_panes.winfo_width()
        if len(self.workspace_panes.panes()) == 2 and width >= 490 and (
            self.workspace_set_sash or width != self.workspace_sash_width
        ):
            minimum_context = 265 if self.locale == "en" else 230
            self.workspace_panes.sashpos(0, min(width - minimum_context, max(225, round(width * self.workspace_context_fraction))))
            self.workspace_set_sash = False
            self.workspace_sash_width = width

    def workspace_capture_sash(self, _=None):
        if len(self.workspace_panes.panes()) == 2 and self.workspace_panes.winfo_width() > 440:
            self.workspace_context_fraction = min(.83, max(.42, self.workspace_panes.sashpos(0) / self.workspace_panes.winfo_width()))
            self.workspace_save_later()

    def workspace_toggle_sidebar(self):
        hidden = not self.workspace_prefs.get("sidebar_hidden", False)
        self.workspace_prefs["sidebar_hidden"] = hidden
        self.workspace_show(True)
        self.workspace_save_later()

    def workspace_toggle_context(self):
        if len(self.workspace_panes.panes()) == 2:
            self.workspace_capture_sash()
            self.workspace_panes.forget(self.workspace_context)
            self.workspace_prefs["context_hidden"] = True
        else:
            self.workspace_panes.add(self.workspace_context, weight=1)
            self.workspace_prefs["context_hidden"] = False
            self.workspace_set_sash = True
            self.workspace_panes.after_idle(self.workspace_restore_sash)
        self.workspace_save_later()

    def workspace_reset_layout(self):
        self.workspace_layout_writable = True
        self.workspace_focus_panels = None
        self.workspace_focus_button.configure(text=self.w("집중"))
        self.workspace_prefs["sidebar_hidden"] = False
        self.workspace_show(True)
        if len(self.workspace_panes.panes()) == 1:
            self.workspace_toggle_context()
        self.workspace_context_fraction = .71
        self.workspace_set_sash = True
        self.workspace_panes.after_idle(self.workspace_restore_sash)
        self.workspace_save_later()

    def workspace_save_later(self):
        if not self.workspace_restore_done or self.workspace_save_timer is not None:
            return
        self.workspace_save_timer = self.window.after(220, self.save_workspace_layout)

    def save_workspace_layout(self):
        if self.workspace_save_timer is not None:
            self.window.after_cancel(self.workspace_save_timer)
            self.workspace_save_timer = None
        if not self.workspace_layout_writable:
            return
        terminals = list(self.terminal_layout_entries())[:40]
        jobs = list(self.workspace_tabs)[:16]
        routes = [key for tab in self.workspace_book.tabs() if (key := self.route_tab_frames.get(tab))][:16]
        references = {key: f"terminal/{index}" for index, (key, _) in enumerate(terminals)}
        references.update({str(self.workspace_tabs[key]["frame"]): "job/" + key for key in jobs})
        references.update({str(self.pages[key]): "route/" + key for key in routes})
        references[str(self.workspace_overview)] = "overview"
        self.workspace_prefs.update(
            version=1,
            project=self.project_id,
            center_fraction=self.workspace_context_fraction,
            terminals=[descriptor for _, descriptor in terminals],
            job_tabs=jobs,
            route_tabs=routes,
            tab_order=[references[tab] for tab in self.workspace_book.tabs() if tab in references],
            active_tab=references.get(self.workspace_book.select()),
        )
        saved = dict(self.workspace_prefs)
        if self.workspace_focus_panels is not None:
            saved["sidebar_hidden"], saved["context_hidden"] = self.workspace_focus_panels
        try:
            atomic_json(self.workspace_layout_path, saved)
        except OSError as error:
            self.status.configure(text=self.w("레이아웃 저장 실패 · {0}", error.strerror or type(error).__name__))
            self.workspace_update_runtime_footer()

    def workspace_session_changed(self):
        self.workspace_save_later()
        if hasattr(self, "workspace_tree"):
            self.workspace_update_runtime_footer()
            self.refresh_workspace_sidebar()

    def workspace_tab_changed(self, _=None):
        if not hasattr(self, "workspace_tree") or not self.workspace_restore_done:
            return
        tab = self.workspace_book.select()
        route_key = self.route_tab_frames.get(tab)
        if route_key:
            self.view = route_key
            self._update_nav_highlight(route_key)
            self._run_route_refresh(route_key)
            self.workspace_update_runtime_footer()
            self.workspace_save_later()
            return
        self.view = "workspace"
        self._update_nav_highlight("workspace")
        session = self.terminal_tabs.get(tab)
        if session and session.views:
            session.views[session.active_panel].surface.focus_set()
        project = session.recipes[0].project if session else next(
            (item.get("project") for item in self.workspace_tabs.values() if str(item["frame"]) == tab), None,
        )
        if project and project != self.project_id and project in self.project_rows():
            self.project_id = project
            self.refresh_sidebar()
        self.refresh_workspace()
        self.workspace_save_later()

    def select_workspace_project(self, key, *, overview=True):
        require(key in self.project_rows(), self.w("등록한 프로젝트를 선택하세요."))
        self.project_id = key
        recent = self.workspace_prefs.get("recent_projects", [])
        self.workspace_prefs["recent_projects"] = [key, *[item for item in recent if item != key and isinstance(item, str)][:5]] if isinstance(recent, list) else [key]
        self.show("workspace", keep_tab=not overview)
        self.refresh_sidebar()
        self.refresh_workspace()
        self.workspace_save_later()

    def workspace_data(self, projects):
        local = self.store.list_jobs() if any(not project.get("host") for project in projects.values()) else []
        remote = self.store.remote_runs() if any(project.get("host") for project in projects.values()) else []
        return {
            key: [row for row in remote if row["host"] == project["host"] and row["plan"]["repo"] == project["path"]]
            if project.get("host") else [row for row in local if same_repository(row["plan"]["repo"], project["path"])]
            for key, project in projects.items()
        }

    def workspace_model_options(self, project):
        host = project.get("host") if project else None
        try:
            catalog = self.host_evidence.get(host, {}).get("worker", {}) if host else read_config(self.root)
        except (OSError, ValueError, TypeError):
            return {}
        return catalog.get("models", {})

    def workspace_selected_model(self, project_id):
        choices = self.workspace_prefs.get("models")
        choices = choices if isinstance(choices, dict) else {}
        project = self.project_rows().get(project_id, {})
        default = project.get("model")
        if not default and not project.get("host"):
            default = read_workspace(self.root).get("default_model")
        value = choices.get(project_id, default or "")
        return value if isinstance(value, str) else ""

    def workspace_refresh_models(self, project):
        models = self.workspace_model_options(project)
        options = {self.w("작업 기본 모델 · 자동"): ""}
        options.update({f'{key} · {value.get("model", "—")}': key for key, value in models.items()})
        model = self.workspace_selected_model(self.project_id)
        if model and model not in models:
            options[self.w("{0} · 구성 미확인", model)] = model
        if getattr(self, "workspace_model_keys", {}) != options:
            self.workspace_model_keys = options
            self.workspace_model_picker.configure(values=list(options))
        self.workspace_model_picker.state(["!disabled" if project else "disabled"])
        display = next((label for label, key in options.items() if key == model), self.w("작업 기본 모델 · 자동"))
        if self.workspace_models.get() != display:
            self.workspace_models.set(display)
        return models.get(model)

    def workspace_choose_model(self, _=None):
        if not self.project_id:
            return
        models = self.workspace_prefs.get("models")
        if not isinstance(models, dict):
            models = {}
        models[self.project_id] = self.workspace_model_keys.get(self.workspace_models.get(), "")
        self.workspace_prefs["models"] = models
        self.workspace_save_later()
        self.refresh_workspace()

    def workspace_new_task(self):
        if not self.project_rows():
            self.open_workspace_setup()
            return
        model = self.workspace_selected_model(self.project_id)
        self.action(lambda: self.guided_dialog(preferred_model=model))

    def workspace_open_ai(self, name, model=None):
        project = self.project_rows().get(self.project_id, {})
        require(not project.get("host"), self.w("원격 CLI는 SSH 셸에서 설치 상태와 작업 디렉터리를 확인한 뒤 실행하세요."))
        if model is None and name != "OpenCode":
            preferred = self.workspace_selected_model(self.project_id)
            if preferred in self.available_terminal_models(name):
                model = preferred
        return self.open_ai_terminal(name, project_id=self.project_id, model=model)

    def workspace_terminal_menu(self, anchor=None):
        menu = tk.Menu(self.window, tearoff=False)
        menu.add_command(label=self.w("로컬 셸"), command=lambda: self.action(self.local_project_shell))
        project = self.project_rows().get(self.project_id, {})
        if project.get("host"):
            menu.add_command(label=self.w("이 프로젝트 SSH 셸"), command=lambda: self.project_terminal(project))
        cli = tk.Menu(menu, tearoff=False)
        paths = scan_clis()
        for name in INTERACTIVE_CLIS:
            note = "" if paths.get(name) else self.w(" · 설치 미탐지")
            cli.add_command(label=name + note, command=lambda pick=name: self.action(lambda: self.workspace_open_ai(pick)))
        if (options := self.available_terminal_models("OpenCode")) and not project.get("host"):
            opencode = tk.Menu(cli, tearoff=False)
            for key, option in options.items():
                opencode.add_command(label=f"{key} · {option.identifier}",
                                     command=lambda pick=key: self.action(lambda: self.workspace_open_ai("OpenCode", pick)))
            cli.add_cascade(label=self.w("OpenCode 시작 모델"), menu=opencode)
        menu.add_cascade(label="AI CLI", menu=cli)
        ssh = tk.Menu(menu, tearoff=False)
        for key, profile in read_workspace(self.root)["hosts"].items():
            ssh.add_command(label=profile["name"], command=lambda host=key: self.action(lambda: self.open_ssh_terminal(host)))
        if host := project.get("host"):
            ssh.add_command(label=self.w("현재 Worker 연결 확인"), command=lambda: self.action(lambda: self.workspace_probe_host(host)))
        ssh.add_command(label=self.w("SSH 프로필 관리"), command=lambda: self.show("ssh"))
        menu.add_cascade(label=self.w("저장된 SSH"), menu=ssh)
        menu.add_separator()
        for label, orient in ((self.w("좌우 분할"), "horizontal"), (self.w("상하 분할"), "vertical")):
            group = tk.Menu(menu, tearoff=False)
            group.add_command(label=self.w("보조 터미널"), command=lambda value=orient: self.action(lambda: self.split_terminal(value)))
            group.add_command(label=self.w("로컬 셸"), command=lambda value=orient: self.action(lambda: self.split_terminal(value, "local")))
            for name in INTERACTIVE_CLIS:
                if paths.get(name):
                    group.add_command(label=name, command=lambda value=orient, kind=name: self.action(lambda: self.split_terminal(value, kind)))
            menu.add_cascade(label=label, menu=group)
        menu.add_command(label=self.w("세션 다시 열기 / 재연결"), command=lambda: self.action(self.reopen_terminal))
        session = self.terminal_tabs.get(self.workspace_book.select())
        if session and not session.archived:
            models = tk.Menu(menu, tearoff=False)
            for name in dict.fromkeys(recipe.profile for recipe in session.recipes if recipe.kind == "ai"):
                for key, option in self.available_terminal_models(name).items():
                    label = option.identifier if name == "OpenCode" else f"{option.provider} / {option.identifier}"
                    models.add_command(label=f"{name} · {label}",
                                       command=lambda cli=name, model=key: self.action(lambda: self.change_terminal_model(cli, model)))
            if models.index("end") is not None:
                menu.add_cascade(label=self.w("모델을 변경해 다시 열기"), menu=models)
        menu.add_command(label=self.w("터미널 단축키"), command=lambda: messagebox.showinfo(
            self.w("터미널 단축키"), self.w("복사 Ctrl+Shift+C\n붙여넣기 Ctrl+Shift+V\n스크롤 Shift+PgUp/PgDn"), parent=self.window))
        self.workspace_popup(menu, anchor or self.workspace_terminal_button)

    def workspace_probe_host(self, host):
        self.refresh_hosts()
        self.hosts_list.selection_set(host)
        self.test_host()

    def workspace_add_menu(self):
        menu = tk.Menu(self.window, tearoff=False)
        menu.add_command(label=self.w("로컬 Git 저장소"), command=self.add_local_project)
        menu.add_command(label=self.w("원격 Worker의 저장소"), command=self.add_remote_project)
        menu.tk_popup(self.window.winfo_pointerx(), self.window.winfo_pointery())

    @staticmethod
    def workspace_popup(menu, widget):
        menu.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())

    def workspace_layout_menu(self):
        menu = tk.Menu(self.window, tearoff=False)
        tabs = tk.Menu(menu, tearoff=False)
        for tab in self.visible_workspace_tabs():
            tabs.add_command(label=self.workspace_book.tab(tab, "text"), command=lambda key=tab: self.workspace_book.select(key))
        menu.add_cascade(label=self.w("열린 탭"), menu=tabs)
        menu.add_command(label=self.w("작업 공간 설정"), command=self.open_workspace_setup)
        menu.add_command(label=self.w("Provider 설정"), command=lambda: self.show("providers"))
        menu.add_command(label=self.w("현재 탭 닫기"), command=self.close_workspace_tab)
        menu.add_command(label=self.w("탭 왼쪽으로 이동"), command=lambda: self.workspace_move_tab(-1))
        menu.add_command(label=self.w("탭 오른쪽으로 이동"), command=lambda: self.workspace_move_tab(1))
        menu.add_separator()
        menu.add_command(label=self.w("왼쪽 패널 접기 / 열기"), command=self.workspace_toggle_sidebar)
        menu.add_command(label=self.w("오른쪽 패널 접기 / 열기"), command=self.workspace_toggle_context)
        menu.add_command(label=self.w("터미널 분할 균등 배치"), command=lambda: self.action(self.reset_terminal_split))
        menu.add_command(label=self.w("터미널 분할 해제"), command=lambda: self.action(self.reset_terminal_layout))
        menu.add_command(label=self.w("기본 작업 공간 배치"), command=self.workspace_reset_layout)
        menu.add_command(label=self.w("읽기 전용 모니터 열기"), command=lambda: self.action(self.workspace_open_monitor))
        languages = tk.Menu(menu, tearoff=False)
        for code, name in (("ko", "한국어"), ("en", "English")):
            languages.add_command(label=name, command=lambda choice=code: self.action(lambda: self.workspace_set_language(choice)))
        menu.add_cascade(label=self.w("언어 · 다음 실행에 적용"), menu=languages)
        self.workspace_popup(menu, self.workspace_layout_button)

    def workspace_set_language(self, locale):
        self.save_ui_prefs(locale=locale)
        messagebox.showinfo(self.w("언어 설정"),
                            self.w("다음에 앱을 열 때 적용됩니다. 현재 세션은 계속 실행됩니다."), parent=self.window)

    def workspace_open_monitor(self):
        root = Path(__file__).resolve().parents[1]
        desktop = root / "apps" / "desktop"
        package = desktop / "release" / ("win-unpacked" if os.name == "nt" else "linux-unpacked")
        name = "model-orchestration-preview.exe" if os.name == "nt" else "model-orchestration-preview"
        binary = shutil.which(name)
        if binary or (package / name).is_file():
            argv = [str(binary or package / name)]
        else:
            electron = root / "node_modules" / "electron" / "dist" / ("electron.exe" if os.name == "nt" else "electron")
            require(sys.platform in ("linux", "win32") and electron.is_file()
                    and (desktop / "build" / "renderer" / "index.html").is_file(),
                    self.w("읽기 전용 모니터를 먼저 빌드하거나 설치하세요. 개발 환경에서는 npm ci 후 npm run build를 실행하세요."))
            argv = [str(electron), str(desktop)]
        process = subprocess.Popen(argv, env=os.environ | {"ORCHESTRA_DATA": str(self.root)}, stdin=subprocess.DEVNULL)
        threading.Thread(target=process.wait, daemon=True).start()

    def workspace_move_tab(self, delta):
        tabs = self.visible_workspace_tabs()
        selected = self.workspace_book.select()
        if selected in tabs:
            index = min(len(tabs) - 1, max(0, tabs.index(selected) + delta))
            self.workspace_book.insert(self.workspace_book.index(tabs[index]), selected)
            self.workspace_save_later()

    def visible_workspace_tabs(self):
        return [tab for tab in self.workspace_book.tabs() if self.workspace_book.tab(tab, "state") != "hidden"]

    def workspace_switch_tab(self, delta):
        tabs = self.visible_workspace_tabs()
        selected = self.workspace_book.select()
        if tabs:
            self.workspace_book.select(tabs[(tabs.index(selected) + delta) % len(tabs)] if selected in tabs else tabs[0])

    def close_workspace_tab(self, tab=None):
        tab = tab or self.workspace_book.select()
        if tab in self.terminals:
            self.close_terminal_view(tab)
            return
        for key, item in list(self.workspace_tabs.items()):
            if str(item["frame"]) == tab:
                self.workspace_tabs.pop(key)
                self.workspace_book.forget(tab)
                item["frame"].destroy()
                self.workspace_save_later()
                return
        if tab in getattr(self, "route_tab_frames", {}):
            self.workspace_book.forget(tab)
            self.workspace_save_later()

    def workspace_command_palette(self):
        if self.workspace_palette and self.workspace_palette.winfo_exists():
            self.workspace_palette.lift()
            return
        palette = tk.Toplevel(self.window)
        self.workspace_palette = palette
        palette.title(self.w("명령 검색"))
        palette.geometry("490x390")
        palette.transient(self.window)
        palette.columnconfigure(0, weight=1)
        palette.rowconfigure(1, weight=1)
        query = tk.StringVar(palette)
        field = ttk.Entry(palette, textvariable=query)
        field.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        listing = ttk.Treeview(palette, show="tree", selectmode="browse")
        listing.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        options = [(self.w("작업 공간"), lambda: self.show("workspace")), (self.w("새 작업   Ctrl+N"), self.workspace_new_task),
                   (self.w("새 로컬 셸   Ctrl+T"), self.local_project_shell), (self.w("파일 검색   Ctrl+P"), self.workspace_find_file),
                   (self.w("프로젝트 / 세션 검색"), self.workspace_focus_search), (self.w("작업 목록"), lambda: self.show("jobs")),
                   (self.w("Agent 대시보드"), lambda: self.show("agents")), (self.w("보관된 실행 이력"), lambda: self.show("history")),
                   (self.w("Provider 설정"), lambda: self.show("providers")), (self.w("SSH 프로필"), lambda: self.show("ssh")),
                   (self.w("원격 작업"), lambda: self.show("remote_runs")), (self.w("MCP 연결"), lambda: self.show("mcp")),
                   (self.w("앱 설정"), lambda: self.show("settings")), (self.w("홈 대시보드"), lambda: self.show("home")),
                   (self.w("읽기 전용 모니터 열기"), self.workspace_open_monitor),
                   (self.w("기본 작업 공간 배치"), self.workspace_reset_layout)]

        def rebuild(*_):
            listing.delete(*listing.get_children())
            for index, (label, _) in enumerate(options):
                if query.get().casefold() in label.casefold():
                    listing.insert("", "end", iid=str(index), text=label)
            children = listing.get_children()
            if children:
                listing.selection_set(children[0])
                listing.focus(children[0])

        def execute(_=None):
            selected = listing.selection()
            if selected:
                palette.destroy()
                self.action(options[int(selected[0])][1])

        query.trace_add("write", rebuild)
        for widget in (field, listing):
            widget.bind("<Return>", execute)
            widget.bind("<Escape>", lambda _: palette.destroy())
        listing.bind("<Double-1>", execute)
        field.bind("<Down>", lambda _: listing.focus_set())
        rebuild()
        field.focus_set()

    def workspace_focus_search(self):
        self.show("workspace")
        if self.workspace_prefs.get("sidebar_hidden"):
            self.workspace_toggle_sidebar()
        self.workspace_search_field.focus_set()

    def workspace_find_file(self):
        self.show("workspace", keep_tab=True)
        if len(self.workspace_panes.panes()) == 1:
            self.workspace_toggle_context()
        self.focus_workspace_file_search()

    def refresh_workspace_sidebar(self, projects=None, runs=None):
        if not hasattr(self, "workspace_tree"):
            return
        projects = self.project_rows() if projects is None else projects
        runs = self.workspace_data(projects) if runs is None else runs
        query = self.workspace_search.get().strip().casefold()
        session_rows = self.terminal_rows()
        rows = []
        actions = {}

        def add(key, parent, title, action=None, opened=False):
            rows.append((key, parent, title, opened))
            if action:
                actions[key] = action

        groups = set()
        for key, profile in projects.items():
            sessions = [row for row in session_rows if row["project"] == key]
            project_matches = not query or query in (profile["name"] + " " + profile["path"]).casefold()
            matching = [row for row in sessions if project_matches or query in row["title"].casefold()]
            records = runs.get(key, [])
            recent = [row for row in records if project_matches or query in row["plan"]["title"].casefold()
                      or query in row["id"].casefold()]
            if not project_matches and not matching and not recent:
                continue
            host = profile.get("host")
            group = "host/" + (host or "local")
            if group not in groups:
                groups.add(group)
                add(group, "", self.host_name(host), opened=True)
            label = ("● " if self.project_id == key else "") + profile["name"]
            add("project/" + key, group, label, ("project", key), opened=self.project_id == key)
            for row in matching:
                row_id = row.get("row_id", row["id"])
                add("session/" + row_id, "project/" + key, f'{row["title"]} · {row["status"]}',
                    ("terminal", row["id"], row.get("panel", 0), key))
            active, history = [], []
            for row in recent:
                observed = self.remote_cache.get(row["id"], {}) if host else row
                state = observed.get("state")
                label = self.w("연결 미확인") if observed.get("error") else state_label(state, self.locale) if state else self.w("미관측")
                group_rows = active if state and state not in TERMINAL else history
                group_rows.append((row, label))
            for name, title, group_rows in (("active", self.w("진행 중·승인 대기"), active), ("runs", self.w("최근 실행"), history)):
                if group_rows:
                    parent = name + "/" + key
                    add(parent, "project/" + key, title, opened=True)
                    for row, label in group_rows[:6]:
                        add(f'job/{key}/{row["id"]}', parent, f'{row["plan"]["title"][:40]} · {label}',
                            ("remote" if host else "job", row["id"]))
        if not query:
            saved = self.workspace_prefs.get("recent_projects")
            recent_projects = [key for key in saved if isinstance(key, str) and key in projects] if isinstance(saved, list) else []
            if recent_projects:
                add("recent", "", self.w("최근 프로젝트"), opened=False)
                for key in dict.fromkeys(recent_projects[:6]):
                    add("recent/" + key, "recent", projects[key]["name"], ("project", key))
        unassigned = [row for row in session_rows if row["project"] not in projects and query in row["title"].casefold()]
        if unassigned:
            add("shells", "", self.w("독립 셸"), opened=True)
            for row in unassigned:
                add("session/" + row.get("row_id", row["id"]), "shells", f'{row["title"]} · {row["status"]}',
                    ("terminal", row["id"], row.get("panel", 0), None))
        if not rows:
            add("empty", "", self.w("일치하는 항목 없음") if query else self.w("등록된 프로젝트 없음"))
        state = tuple(rows)
        self.workspace_sidebar_actions = actions
        if self.workspace_sidebar_rows == state:
            return
        tree = self.workspace_tree
        selected = tree.selection()
        old_open = {uid: tree.item(uid, "open") for uid, *_ in self.workspace_sidebar_rows if tree.exists(uid)}
        old_project = getattr(self, "workspace_sidebar_project", None)
        self.workspace_sidebar_project = self.project_id
        tree.delete(*tree.get_children())
        for uid, parent, title, opened in rows:
            force_open = bool(query) or old_project != self.project_id and uid == "project/" + (self.project_id or "")
            tree.insert(parent, "end", iid=uid, text=title, open=force_open or old_open.get(uid, opened))
        active_project = "project/" + (self.project_id or "")
        if old_project != self.project_id and tree.exists(active_project):
            tree.selection_set(active_project)
        elif selected and tree.exists(selected[0]):
            tree.selection_set(selected[0])
        self.workspace_sidebar_rows = state

    def workspace_sidebar_open(self, event=None):
        if event and event.type == tk.EventType.ButtonPress and self.workspace_tree.identify_element(event.x, event.y).endswith("indicator"):
            return
        selection = self.workspace_tree.selection()
        action = self.workspace_sidebar_actions.get(selection[0]) if selection else None
        if action:
            self.action(lambda: self.activate_workspace_item(action))
        return "break"

    def workspace_sidebar_click(self, event):
        row = self.workspace_tree.identify_row(event.y)
        action = self.workspace_sidebar_actions.get(row)
        if action and action[0] == "terminal":
            self.action(lambda: self.activate_workspace_item(action))

    def workspace_sidebar_menu(self, event):
        item = self.workspace_tree.identify_row(event.y)
        action = self.workspace_sidebar_actions.get(item)
        if not action:
            return
        menu = tk.Menu(self.window, tearoff=False)
        menu.add_command(label=self.w("열기"), command=lambda: self.action(lambda: self.activate_workspace_item(action)))
        if action[0] == "project":
            profile = self.project_rows().get(action[1])
            if profile:
                menu.add_command(label=self.w("프로젝트 셸"), command=lambda: self.project_terminal(profile))
                menu.add_command(label=self.w("이 프로젝트에서 작업 만들기"), command=lambda: (
                    self.select_workspace_project(action[1]), self.workspace_new_task()))
        elif action[0] == "terminal":
            menu.add_command(label=self.w("탭 숨기기"), command=lambda: self.hide_terminal(action[1]))
        menu.tk_popup(event.x_root, event.y_root)

    def activate_workspace_item(self, action):
        kind, key, *extra = action
        if kind == "project":
            self.select_workspace_project(key)
        elif kind == "terminal":
            panel, project = extra
            if project and project != self.project_id:
                self.select_workspace_project(project, overview=False)
            self.focus_terminal(key, panel)
        elif kind == "remote":
            self.open_workspace_remote(key)
        else:
            self.open_workspace_job(key)

    def refresh_workspace(self):
        if not self.workspace_restore_done or not hasattr(self, "workspace_tree"):
            return
        projects = self.project_rows()
        project = projects.get(self.project_id)
        previous = self.context_project
        self.set_workspace_context(self.project_id, project)
        if previous != self.context_project:
            positions = self.workspace_prefs.get("project_context")
            index = positions.get(self.project_id, 0) if isinstance(positions, dict) else 0
            if type(index) is int and 0 <= index < len(self.workspace_context.tabs()):
                self.workspace_context.select(index)
        recent_by_project = self.workspace_data(projects)
        runs = recent_by_project.get(self.project_id, [])
        model = self.workspace_refresh_models(project)
        if project:
            self.workspace_setup_button.pack_forget()
            if not self.workspace_add_repo.winfo_manager():
                self.workspace_add_repo.pack(side="left", padx=(0, 6), pady=3)
                self.workspace_project_cli.pack(side="left", padx=(0, 6), pady=3)
            host = project.get("host")
            branch = getattr(self, "context_git_branch", None)
            branch_status = self.w("조회한 Git 브랜치 {0}", branch) if branch else self.w("현재 브랜치 미관측")
            self.workspace_title.configure(text=project["name"])
            info = [project["path"], self.w("실행 위치  {0}", self.host_name(host)), self.w("대상 브랜치  {0}", project['branch']),
                    "", self.w("최근 실행")]
            for row in runs[:10]:
                state = self.remote_cache.get(row["id"], {}).get("state") if host else row["state"]
                info.append(f'{state_label(state, self.locale) if state else self.w("미관측")}  ·  {row["plan"]["title"]}')
            if not runs:
                info.append(self.w("기록된 실행이 없습니다."))
            self.workspace_write(self.workspace_overview_text, "\n".join(info))
            worker = self.host_evidence.get(host, {}).get("worker") if host else None
            worker_note = ""
            if host:
                at = self.host_evidence.get(host, {}).get("at")
                worker_seen = datetime.fromtimestamp(at).strftime("%H:%M") if at else None
                worker_note = (self.w("Worker 최근 조회 {0}", worker_seen) if worker and worker_seen else self.w("Worker 미확인"))
            states = [self.remote_cache.get(run["id"], {}).get("state") if host else run["state"] for run in runs]
            active = sum(state is not None and state not in TERMINAL and state not in ("AWAITING_TOOL", "AWAITING_APPROVAL") for state in states)
            approval = sum(state in ("AWAITING_TOOL", "AWAITING_APPROVAL") for state in states)
            model_status = (self.w("작업 기본 {0} / {1}", model.get('provider', '—'), model.get('model', '—')) if model
                            else self.workspace_models.get())
            counters = self.w("{0}실행 {1} · 승인 대기 {2}", (self.w('관측된 ') if host else self.w('최근 기록 ')), active, approval)
            context = (project["name"], branch_status, self.host_name(host), model_status)
            runtime = (self.status.cget("text"), worker_note, counters)
        else:
            self.workspace_add_repo.pack_forget()
            self.workspace_project_cli.pack_forget()
            if not self.workspace_setup_button.winfo_manager():
                self.workspace_setup_button.pack(side="left", padx=(0, 6), pady=3)
            self.workspace_title.configure(text=self.w("첫 프로젝트를 설정하세요" if not projects else "프로젝트 선택"))
            self.workspace_write(self.workspace_overview_text,
                                 self.w("작업 공간 설정에서 Git 폴더를 선택하고 첫 터미널을 열 수 있습니다."
                                        if not projects else "왼쪽에서 프로젝트를 열거나 Git 저장소를 등록하세요."))
            context = (self.w("프로젝트를 선택하세요."),)
            runtime = (self.status.cget("text"),)
        self.workspace_status.configure(text="   │   ".join(context))
        if not self.workspace_layout_writable:
            runtime += (self.w("이전 배치를 읽을 수 없습니다. 저장하려면 보기에서 배치를 초기화하세요."),)
        self.workspace_runtime_observations = runtime
        self.workspace_update_runtime_footer()
        self.refresh_workspace_sidebar(projects, recent_by_project)
        self.refresh_workspace_tasks(runs, bool(project and project.get("host")))

    def workspace_update_runtime_footer(self):
        items = (self.workspace_active_terminal_status(), *getattr(self, "workspace_runtime_observations", ()))
        text = "   │   ".join(filter(None, items))
        if self.workspace_runtime_status.cget("text") != text:
            self.workspace_runtime_status.configure(text=text)

    def workspace_active_terminal_status(self):
        tab = self.terminal_tabs.get(self.workspace_book.select())
        if not tab or tab.archived:
            return ""
        panel = tab.active_panel
        recipe = tab.recipes[panel]
        running = tab.views and not tab.views[panel].closed.is_set()
        if recipe.kind == "ssh":
            state = self.w("프로세스 실행 중") if running else self.w("연결 종료") if tab.views else self.w("복원 대기")
            return self.w("SSH 셸 {0} · {1}", self.host_name(recipe.profile), state)
        if recipe.kind != "ai" or not running:
            return ""
        return (self.w("{0} 시작 모델 {1}", recipe.profile, tab.args[panel][0][-1]) if recipe.model
                else self.w("{0} 모델 미관측", recipe.profile))

    def workspace_write(self, widget, value):
        if widget.get("1.0", "end-1c") != value:
            top, bottom = widget.yview()
            self.write(widget, value, True)
            if top > 0 and bottom >= .995:
                widget.see("end")
            else:
                widget.yview_moveto(top)

    def build_workspace_observation(self):
        agents = ttk.Frame(self.workspace_context, padding=6)
        agents.columnconfigure(0, weight=1)
        agents.rowconfigure(1, weight=2)
        agents.rowconfigure(2, weight=3)
        self.workspace_context.add(agents, text="Agent")
        action_bar = ttk.Frame(agents)
        action_bar.grid(row=0, column=0, sticky="ew")
        ttk.Button(action_bar, text=self.w("상세"), width=5, padding=3, command=self.workspace_open_agent_details).pack(side="left")
        self.workspace_agent_stop = ttk.Button(action_bar, text=self.w("작업 중지"), width=8, padding=3,
                                               command=lambda: self.workspace_agent_action("cancel"))
        self.workspace_agent_stop.pack(side="left", padx=3)
        self.workspace_agent_retry = ttk.Button(action_bar, text=self.w("재시도"), width=6, padding=3,
                                                command=lambda: self.workspace_agent_action("retry"))
        self.workspace_agent_retry.pack(side="left")
        self.workspace_agents = self.table(agents, 1, (("agent", "Agent", 100), ("state", self.w("상태"), 85)), height=5)
        self.workspace_agents.bind("<<TreeviewSelect>>", self.render_workspace_agent)
        self.workspace_agents.bind("<Double-1>", lambda _: self.workspace_open_agent_details())
        self.workspace_agent_detail = self.text(agents, 2, size=9)
        activity = ttk.Frame(self.workspace_context, padding=6)
        activity.columnconfigure(0, weight=1)
        activity.rowconfigure(0, weight=1)
        self.workspace_context.add(activity, text=self.w("활동"))
        self.workspace_activity = self.text(activity, 0, size=9)

    def workspace_event_lines(self, events, *, payload=False):
        lines = []
        for item in events:
            clock = datetime.fromtimestamp(item["timestamp"]).strftime("%H:%M:%S")
            detail = "  " + json.dumps(item["payload"], ensure_ascii=False)[:1200] if payload else ""
            event = item["event_type"]
            label = event.replace(".", " ").replace("_", " ").title() if self.locale == "en" else EVENT_LABELS.get(event, event)
            lines.append(f'{clock}  {item["task_id"] or self.w("작업")}  {label}{detail}')
        return "\n".join(lines)

    def refresh_workspace_tasks(self, runs, remote):
        tab = self.workspace_book.select()
        focused = next((key for key, value in self.workspace_tabs.items() if str(value["frame"]) == tab), None)
        if focused:
            self.render_workspace_job(focused)
        observed = [row for row in runs if (self.remote_cache.get(row["id"], {}).get("state") if remote else row.get("state")) not in TERMINAL]
        records = [row["id"] for row in (observed or runs)[:5]]
        if focused and focused not in records:
            visible = self.workspace_tabs.get(focused)
            if visible and visible["remote"] == remote and any(row["id"] == focused for row in runs):
                records.insert(0, focused)
        rows = []
        details = {}
        current_events = []
        for key in records:
            if remote:
                cached = self.remote_cache.get(key, {})
                if cached.get("error"):
                    continue
                plan = next(row["plan"] for row in runs if row["id"] == key)
                job = {"plan": plan, "state": cached.get("state")}
                tasks = {item["id"]: item for item in cached.get("tasks", [])}
                events = cached.get("events", [])[-300:]
            else:
                job = self.store.job(key)
                if not job:
                    continue
                tasks = self.store.tasks(key)
                events = self.store.recent_events(key, limit=300)
            if focused in (None, key):
                current_events.extend(events)
            for item in agent_rows(job, tasks, events):
                row_id = key + "/" + item["id"]
                details[row_id] = (key, item, job, remote)
                rows.append((row_id, (item["agent"] or item["id"], state_label(item["state"], self.locale))))
        selection = self.workspace_agents.selection()
        selected = selection[0] if selection and selection[0] in details else (rows[0][0] if rows else None)
        self.workspace_agent_keys = details
        self.fill(self.workspace_agents, rows, selected)
        self.render_workspace_agent()
        activity = self.workspace_event_lines(sorted(current_events, key=lambda event: event["timestamp"])[-100:])
        self.workspace_write(self.workspace_activity, activity or self.w("조회된 실행 이벤트가 없습니다."))

    def render_workspace_agent(self, _=None):
        selection = self.workspace_agents.selection()
        value = self.workspace_agent_keys.get(selection[0]) if selection else None
        eligible = bool(value and not value[3])
        state = value[2]["state"] if value else None
        self.workspace_agent_stop.state(["!disabled" if eligible and state not in TERMINAL | {"MERGING"} else "disabled"])
        self.workspace_agent_retry.state(["!disabled" if eligible and state == "FAILED" else "disabled"])
        if not value:
            self.workspace_write(self.workspace_agent_detail, self.w("조회된 Agent가 없습니다."))
            return
        _, agent, job, remote = value
        measured = lambda field: agent[field] if agent[field] is not None else self.w("미관측")
        time_text = self.w("{0:.1f}초", agent['elapsed']) if agent["elapsed"] is not None else self.w("미관측")
        lines = [job["plan"]["title"], f'{agent["agent"] or agent["id"]} · {measured("role")}',
                 f'Provider {measured("provider")}', self.w("모델 {0} · Harness {1}", measured('model'), measured('harness')),
                 self.w("경과 {0} · 도구 {1}회", time_text, agent['tools']), self.w("토큰 · 입력 {0} / 출력 {1}", measured('input'), measured('output')),
                 self.w("최근 이벤트 {0}", measured('last_event')), "", self.w("구조화된 실행 로그"),
                 *[str(name) for name in agent["changed"][:20]]]
        if remote:
            lines.append(self.w("원격 작업 페이지에서 Worker 작업을 제어할 수 있습니다."))
        self.workspace_write(self.workspace_agent_detail, "\n".join(lines))

    def workspace_open_agent_details(self):
        selection = self.workspace_agents.selection()
        value = self.workspace_agent_keys.get(selection[0]) if selection else None
        if value:
            job, agent, _, remote = value
            if remote:
                self.open_workspace_remote(job)
            else:
                self.open_workspace_job(job)
                view = self.workspace_tabs[job]
                view["agent_filter"] = agent["id"]
                view["detail"].select(view["logs_page"])
                self.render_workspace_job(job)
                self.agent_job, self.agent_task = job, agent["id"]

    def workspace_agent_action(self, action):
        selection = self.workspace_agents.selection()
        value = self.workspace_agent_keys.get(selection[0]) if selection else None
        if value and not value[3]:
            self.job_action(action, job_id=value[0])

    def open_workspace_job(self, key, *, activate=True):
        job = self.store.job(key)
        require(job, self.w("작업을 찾을 수 없습니다."))
        if key not in self.workspace_tabs:
            project = self.workspace_project_for_run(job)
            self.build_workspace_task(key, job["plan"]["title"], project=project)
        if activate:
            self.show("workspace")
            self.workspace_book.select(self.workspace_tabs[key]["frame"])
            self.render_workspace_job(key)
            self.workspace_save_later()

    def open_workspace_remote(self, key, *, activate=True):
        row = next((item for item in self.store.remote_runs() if item["id"] == key), None)
        require(row, self.w("원격 작업을 찾을 수 없습니다."))
        if key not in self.workspace_tabs:
            self.build_workspace_task(key, row["plan"]["title"], remote=True, project=self.workspace_project_for_run(row))
        if activate:
            self.remote_selected = key
            self.show("workspace")
            self.workspace_book.select(self.workspace_tabs[key]["frame"])
            self.render_workspace_job(key)
            self.workspace_save_later()

    def workspace_project_for_run(self, row):
        repo, host = row["plan"]["repo"], row.get("host")
        candidates = [key for key, profile in self.project_rows().items() if profile.get("host") == host
                      and (profile["path"] == repo if host else same_repository(profile["path"], repo))]
        return self.project_id if self.project_id in candidates else next(iter(candidates), None)

    def build_workspace_task(self, key, title, remote=False, project=None):
        frame = ttk.Frame(self.workspace_book, padding=8)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        heading = ttk.Label(frame, text=title, style="Section.TLabel")
        heading.grid(row=0, column=0, sticky="w", pady=(0, 4))
        bar = ttk.Frame(frame)
        bar.grid(row=1, column=0, sticky="ew")
        controls = {}
        if remote:
            self.button(bar, self.w("다시 연결"), lambda: self.action(lambda: self.pull_remote(reconnect=True)))
            self.button(bar, self.w("원격 작업 제어"), lambda: self.show("remote_runs"))
        else:
            for action, label in (("cancel", self.w("중지")), ("retry", self.w("재시도")), ("merge", self.w("병합 검토"))):
                controls[action] = self.button(bar, label, lambda pick=action: self.job_action(pick, job_id=key))
            self.button(bar, self.w("Agent 상세"), lambda: self.workspace_show_full_agents(key))
        book = ttk.Notebook(frame)
        book.grid(row=2, column=0, sticky="nsew", pady=(4, 0))
        item = {"frame": frame, "detail": book, "title": heading, "remote": remote, "controls": controls, "project": project}
        for name, label in (("overview", self.w("진행")), ("dag", "DAG"), ("logs", self.w("실행 로그")), ("qa", "QA"), ("changes", self.w("변경"))):
            page = ttk.Frame(book, padding=6)
            page.rowconfigure(1 if name == "logs" else 0, weight=1)
            page.columnconfigure(0, weight=1)
            book.add(page, text=label)
            if name == "dag":
                canvas = tk.Canvas(page, bg=self.palette["graph_bg"], highlightthickness=0)
                canvas.grid(row=0, column=0, sticky="nsew")
                vs = ttk.Scrollbar(page, command=canvas.yview)
                hs = ttk.Scrollbar(page, orient="horizontal", command=canvas.xview)
                canvas.configure(xscrollcommand=hs.set, yscrollcommand=vs.set)
                vs.grid(row=0, column=1, sticky="ns")
                hs.grid(row=1, column=0, sticky="ew")
                item[name] = canvas
            else:
                item[name] = self.text(page, 1 if name == "logs" else 0, size=9)
                if name == "logs":
                    item["logs_page"] = page
                    actions = ttk.Frame(page)
                    actions.grid(row=0, column=0, sticky="ew")
                    self.button(actions, self.w("전체 로그"), lambda: self.workspace_clear_agent_filter(key))
                    item["log_filter_label"] = ttk.Label(actions, style="Muted.TLabel")
                    item["log_filter_label"].pack(side="left")
                if name == "changes" and not remote:
                    actions = ttk.Frame(page)
                    actions.grid(row=1, column=0, sticky="ew")
                    self.button(actions, self.w("통합 Diff 열기"), lambda: self.action(lambda: self.show_diff_dialog(self.store.job(key))))
        self.workspace_tabs[key] = item
        self.workspace_book.add(frame, text=title[:25])

    def workspace_show_full_agents(self, key):
        self.agent_job = key
        self.show("agents")

    def workspace_clear_agent_filter(self, key):
        self.workspace_tabs[key].pop("agent_filter", None)
        self.render_workspace_job(key)

    def render_workspace_job(self, key):
        view = self.workspace_tabs[key]
        if view["remote"]:
            row = next((item for item in self.store.remote_runs() if item["id"] == key), None)
            if not row:
                return
            cached = self.remote_cache.get(key, {})
            self.remote_selected = key
            self.pull_remote()
            job = {"plan": row["plan"], "state": cached.get("state"), "result": {"candidate": cached.get("candidate")}}
            tasks = {row["id"]: row for row in cached.get("tasks", [])}
            events = cached.get("events", [])[-180:]
            error = cached.get("error")
        else:
            job, tasks, _ = self.store.status_snapshot(key, 0, 0)
            events = list(reversed(self.store.recent_events(key, limit=180)))
            error = None
        state = job["state"]
        observed = self.w("연결 끊김 · 마지막 관측: {0}", (state_label(state, self.locale) if state else self.w('없음'))) if error else state_label(state, self.locale) if state else self.w("미관측")
        view["title"].configure(text=f'{job["plan"]["title"]} · {observed}')
        for action, enabled in (("cancel", state not in TERMINAL | {"MERGING"}), ("retry", state == "FAILED"),
                                ("merge", merge_candidate_ready(job))):
            if action in view["controls"]:
                view["controls"][action].state(["!disabled" if enabled else "disabled"])
        mode = self.w("독립 백그라운드 실행") if job["plan"].get("background") else self.w("앱 연결 실행")
        overview = [job["plan"]["repo"], self.w("대상 브랜치  {0}", job["plan"]["target"]), self.w("실행 ID  {0}", key), mode, ""]
        for item in agent_rows(job, tasks, events):
            stage = f'{item["id"]} · {item["role"]} · {state_label(item["state"], self.locale)}'
            route = [item["provider_requested"] or item["provider"], item["model_requested"] or item["model"], item["harness"]]
            overview.append(" · ".join([stage, *(value for value in route if value)]))
        if error:
            overview.append(self.workspace_error(error))
        self.workspace_write(view["overview"], "\n".join(overview))
        agent_filter = view.get("agent_filter")
        view["log_filter_label"].configure(text=f"Agent {agent_filter}" if agent_filter else self.w("작업 전체"))
        log_events = [item for item in events if item["task_id"] == agent_filter] if agent_filter else events
        self.workspace_write(view["logs"], self.workspace_event_lines(log_events, payload=True) or self.w("아직 기록된 실행 로그가 없습니다."))
        result = (job.get("result") or {}) if state in (*MERGE_EVIDENCE, "SUCCEEDED") else {}
        candidate = result.get("candidate")
        checks = result.get("qa") or []
        current_qa = [self.w("검증 {0} · 종료 코드 {1}", item.get('index', '—'), item.get('exit_code', '—')) for item in checks]
        interruptions = [item for item in events if item["event_type"] in ("qa.result", "qa.interrupted")]
        if candidate:
            current_qa.append(self.w("후보 {0}", candidate))
        if job["plan"].get("qa"):
            current_qa.insert(0, format_commands(job["plan"]["qa"]))
        self.workspace_write(view["qa"], "\n".join([*current_qa,
                             "", self.w("최근 QA 이벤트 (병합 승인 근거는 승인 화면에서 확인)"),
                             self.workspace_event_lines(interruptions, payload=True) or self.w("기록 없음")]))
        files = result.get("changed", sorted({name for task in tasks.values() for name in
                                              (task.get("result") or task).get("changed", [])}))
        self.workspace_write(view["changes"], "\n".join(files) if files else self.w("기록된 변경 파일이 없습니다."))
        graph = (state, tuple((key, row["state"]) for key, row in tasks.items()), self.theme_name)
        if view.get("graph_key") != graph:
            self._draw_dag(view["dag"], job, tasks)
            view["graph_key"] = graph
