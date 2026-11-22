# Model Orchestration — Unified Orca Workspace Architecture

## 1. Single Authoritative Shell Hierarchy

The consolidated Tk desktop application (`WorkspaceDesktop`) constructs **one** persistent application shell inside `IntegratedWorkspace.build_unified_shell()` during `WorkspaceDesktop.layout()` (without calling `Desktop.layout()`):

```text
UnifiedApplicationShell (WorkspaceDesktop + IntegratedWorkspace)
├── ApplicationHeader (header_bar — row 0, 48px, full width)
│   ├── header_left (workspace_actions)
│   │   ├── sidebar_toggle_btn (≡)
│   │   ├── sidebar_picker (single project selector combobox)
│   │   ├── header_env_badge (이 PC / remote host pill)
│   │   ├── header_new_task (single primary CTA: 새 작업)
│   │   ├── workspace_terminal_button (터미널 ▾)
│   │   └── workspace_model_picker (task default model selector)
│   └── header_right (workspace_view_actions)
│       ├── header_supervisor_badge (● Supervisor status + tooltip)
│       ├── header_notice_badge (pending approvals pill -> jumps to jobs)
│       ├── workspace_layout_button (보기 ▾)
│       ├── workspace_focus_button (집중 / 패널 복원)
│       └── theme_btn (다크 / 라이트)
├── WorkspaceSidebar (nav_frame — row 1, col 0, 236px)
│   ├── brand_box (Model Orchestration)
│   ├── search_wrap (workspace_search_field + 메뉴 / Ctrl+K trigger)
│   ├── primary_nav_box (5 NavRow items from PRIMARY_NAV: workspace, jobs, agents, projects, settings)
│   ├── sidebar_projects_hdr (프로젝트 및 세션 + 추가 menu)
│   ├── workspace_tree (Sidebar.Treeview: hosts, projects, live/archived PTYs, active/recent runs)
│   └── sidebar_utility (2x2 quick jump grid: Provider, SSH, MCP, 기록)
├── WorkspaceContent (main_shell -> workspace_panes — row 1, col 1)
│   ├── Center: workspace_book (ttk.Notebook, style="Workspace.TNotebook")
│   │   ├── workspace_overview (anchored Project Overview / Empty Onboarding)
│   │   ├── TerminalTab views (OpenCode, Codex, Local Shell, SSH Shell, split panes)
│   │   ├── Workspace job tabs (live/remote job monitoring tabs)
│   │   └── Route tabs opened on demand via ROUTE_SPECS (jobs, agents, projects, settings, providers, ssh, hosts, mcp, history, home, submit, dag, remote_runs, advanced_plan, registry, terminals)
│   └── Right: workspace_context (ContextPanel — Files | Git | Agent | Activity)
└── StatusBar (status_bar — row 2, full width)
    ├── workspace_status (active project, observed Git branch, host, default model)
    ├── workspace_runtime_status (active terminal/model, supervisor state, worker status, run/approval counters)
    └── header_workers_badge (Worker count / Local Worker pill)
```

---

## 2. Central Route Registry & Component Ownership

### 2.1 `ROUTE_SPECS` (`orchestra/workspace_shell.py`)

Every route is defined once in `ROUTE_SPECS` as `(label_key, primary_nav_target, refresh_method)`:

- **Primary Nav Targets (`PRIMARY_NAV`)**: `workspace`, `jobs`, `agents`, `projects`, `settings`.
- **Secondary / Contextual Routes**:
  - `providers`, `ssh`, `hosts`, `mcp`, `registry` → highlight `settings`
  - `history`, `submit`, `dag`, `remote_runs`, `advanced_plan` → highlight `jobs`
  - `home`, `terminals` → highlight `workspace`

### 2.2 Ownership Boundaries

| Module | Authoritative Responsibility |
| --- | --- |
| `orchestra/ui/theme.py` | Single source of design tokens (`THEMES`, `SPACING`, `DIMENSIONS`, `TYPE_SCALE`), platform font resolution (`resolve_fonts`), named font alignment (`_apply_named_fonts`), and ttk styling (`apply_ttk_theme`) defaulting to `"light"`. |
| `orchestra/ui/components.py` | Reusable UI primitives (`Card`, `NavRow`, `SettingsSection`, `SearchBox`, `MetricCard`, `EmptyState`, `CollapsibleSection`, `StatusBadge`, `Tooltip`, `retheme_widget_tree`). |
| `orchestra/ui/strings.py` & `workspace_strings.py` | Localized labels (`ko` / `en`), `PRIMARY_NAV`, `NAV_GROUPS`, `STATES_I18N`, `WORKSPACE_EN`. |
| `orchestra/desktop.py` | Window lifecycle, `Store` binding, `ui_prefs.json`, theme/widget tracking (`track_themed`, `apply_theme_widgets`), shared table/text/button helpers, `tick()` loop, modal approval/diff/MCP actions. Legacy `Desktop.layout()` is bypassed by `WorkspaceDesktop`. |
| `orchestra/workspace_shell.py` | `IntegratedWorkspace`: builds the single unified shell (`build_unified_shell`), owns `ROUTE_SPECS`, tab opening/closing/reordering, focus mode, command palette, sidebar tree, and `ui-workspace.json` (`version: 1`) layout persistence including `route_tabs`. |
| `orchestra/workspace_desktop.py` | `WorkspaceDesktop`: authoritative controller coordinating `show()`, `pick_sidebar()`, `tick()`, `jobs_page()`, `agents_page()`, `home_page()`, and `apply_theme_widgets()`. |
| `orchestra/workspace_sessions.py` | `WorkspaceSessions`: PTY/split terminal tabs, session reuse, model flags, non-auto-restarting placeholders on restore. |
| `orchestra/workspace_context.py` | `WorkspaceContext`: background-threaded read-only File Explorer and Git status/diff preview. |
| `orchestra/workspace_forms.py` | `ProjectSettings`: Projects page, 6-step Task Wizard + guided dialog, Providers & Models, Execution History, Unified Settings Hub (`settings_page`). |
| `orchestra/workspace_remote.py` | `RemoteWorkspace`: Environments, SSH Server profiles/pinning/probes, Remote File browser, Remote Worker run control. |

---

## 3. Navigation, Tab Lifecycle & State Invariants

1. **Shell Stability**: `nav_frame`, `header_bar`, `workspace_book`, `workspace_context`, and `status_bar` are constructed once and never recreated or swapped when switching routes.
2. **Deduplicated Route Tabs**: Calling `show(key)` reuses the existing frame in `self.pages[key]`, adding it to `self.workspace_book` if absent and selecting it without opening duplicate copies.
3. **Safe Tab Closing**: Closing a route tab calls `workspace_book.forget(tab)`, keeping the frame intact in `self.pages` so form drafts and filters persist. Closing a terminal tab prompts before terminating processes (`hide` vs `terminate`). Closing a detached job tab never cancels the Supervisor job.
4. **Authoritative UI State**:
   - `self.project_id` is synchronized across `sidebar_picker`, `workspace_tree`, `workspace_context`, `workspace_book` tab switches, and `ui-workspace.json`.
   - `self.theme_name` (`"light"` default) and `self.locale` (`"ko"` default) persist in `ui_prefs.json`.
   - Restored terminals appear as placeholders and never spawn CLI subprocesses automatically on restart.
5. **Security & Authority Invariants**:
   - Python `Supervisor`, `Store`, `gitgate`, `ssh`, and `mcp` retain full execution, Git merge, host-key pinning, and permission authority.
   - `apps/desktop` (Electron) remains strictly read-only.
