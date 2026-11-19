# Model Orchestration — UI/UX Redesign Architecture & Comparison

## 1. Scope & Architectural Boundary Preservation

The redesign modernizes both desktop surfaces to an Orca-inspired workspace while preserving the platform's backend engines, execution contracts, and security boundaries:

- **Preserved Backend Engines (`orchestra/`)**: `core.py`, `supervisor.py`, `store.py`, `gitgate.py`, `harness.py`, `runtime.py`, `ssh.py`, `remote.py`, and `mcp.py` were kept intact without rewriting scheduling, checkpointing, SQLite transactional state, or Git merge safety logic.
- **Primary Operator Application (`Tk`)**: Remains the full control plane for projects, providers, guided task submission, DAG review, agent monitoring, changed-file inspection, QA checks, and Git merge approvals.
- **Strictly Read-Only Monitor (`Electron`)**: `apps/desktop/electron/main.ts`, `preload.ts`, `legacy-store.ts`, and `src/contracts.ts` remain untouched; `window.orchestration` exposes only `["snapshot"]`, Node `require` stays `undefined`, `window.open` is denied, and SQLite databases remain opened read-only.

## 2. Orca-Inspired Design System (`orchestra/ui/`)

| Module | Responsibilities |
| --- | --- |
| `orchestra/ui/__init__.py` | Public exports for themes, localization helpers, and UI widgets |
| `orchestra/ui/theme.py` | `THEMES["dark"]` and `THEMES["light"]` token palettes (`#0d1117` canvas, `#111827` sidebar/header, `#161d2b` panels, `#1e293b` elevated cards, `#3b82f6` primary accent), semantic status tones (`success`, `running`, `warning`, `danger`, `neutral`), `resolve_fonts`, `approval_state_info`, and `apply_ttk_theme` including dark-slate `clam` scrollbars |
| `orchestra/ui/strings.py` | `NAV_GROUPS` (`11` items across `4` groups), `STATES_I18N` and `STRINGS` with `1:1` Korean/English key parity (`t()`, `state_label()`) |
| `orchestra/ui/components.py` | Reusable `Card`, `StatusBadge`, `MetricCard`, `EmptyState`, `CollapsibleSection`, and text/listbox theming helpers (`style_text_widget`, `style_listbox_widget`) |

Dark/light preference persistence is stored exclusively in `ui_prefs.json` under the application data directory so `registry.json` strict schema validation (`config_check`) remains unaffected. The Electron renderer CSS (`apps/desktop/src/styles.css`) shares the exact dark hex tokens and semantic pill colors.

## 3. Redesigned Surfaces

### 3.1 Tk Primary Workspace (`orchestra/`)

- **Application Shell (`desktop.py`, `workspace_desktop.py`)**: `252px` grouped sidebar (`WORKSPACE`, `EXECUTION`, `INTEGRATIONS`, `SYSTEM`) with 3px active accent indicator, `52px` global header bar (project switcher, runtime environment badge, Supervisor/Worker status pills, pending approval counter, live Light/Dark theme switch, `+ 새 작업` CTA), and live ANSI terminal theming (`terminal.py` `palette` argument).
- **Home Dashboard (`workspace_desktop.py`)**: Quick-action strip, 9 clickable KPI cards (2 rows), active-work table, guided `EmptyState` onboarding card on clean workspaces, and double-click recent activity feed.
- **Projects Workspace (`workspace_forms.py`)**: Project search filter, rich project header card with environment `StatusBadge`, quick CTA (`이 프로젝트에서 작업 만들기`), and 3 sub-tabs (`개요 및 기본 설정`, async `Git 상태`, `최근 실행 (N)`).
- **In-Place 6-Step Task Wizard (`workspace_forms.py`)**: Guided linear steps (`1. 프로젝트` -> `2. 작업 설명` -> `3. 실행 설정` -> `4. 실행 계획` -> `5. 권한 안내` -> `6. 검토 및 제출`) alongside preserved modal wizard and advanced JSON routes.
- **Jobs Workspace & 7-Tab Detail (`workspace_desktop.py`)**: Searchable job list with non-clipping 2-row action footer, wrapped title header card with live `StatusBadge`, 7 detail tabs (`개요`, interactive `실행 계획` DAG canvas, `Agent`, `변경 파일`, `QA 결과`, inline `승인` with `approval_state_info` blocker explanations, and streaming `로그`), plus redesigned `Git 병합 승인` modal with 4 KPI cards, `"변경 사항 보기"` diff viewer, `"거절"`, and `"이 후보 승인"`.
- **Agents, Providers, SSH & History (`workspace_forms.py`, `workspace_remote.py`, `workspace_desktop.py`)**: Filtered event log on `Agent 대시보드`, dedicated `SSH 서버` page (`hosts` vs `ssh`), KPI-backed `Provider & 모델` page with Simple/Advanced wizard mode toggle (`10` fields always registered), and searchable/filterable `실행 기록` page.

### 3.2 Electron Read-Only History Monitor (`apps/desktop/src/`)

- **Header & Status Pills**: Shows `Model Orchestration`, `Read-only Monitor`, live state badge (`Live Sync` / `Connecting` / `Offline Cache`), and snapshot freshness timestamp.
- **Overview KPI Strip (`Execution overview`)**: Displays live totals for Total runs, Running, Awaiting approval, Succeeded, and Failed/Stopped.
- **Multi-Filter Job Sidebar**: Combines text search (title or ID), `Job state`, and `Execution mode` (`All modes`, `Background`, `Foreground`).
- **Structured Detail View**: Renders tone-bordered DAG cards, `Integration QA` pass/fail summary badge (`passed`/`total` + `PASS`/`FAIL` check pills), Candidate SHA box, and aligned `Recent activity` timeline.

## 4. Before / After Screenshot Comparison

| Surface | Before (Release Candidate) | After (Redesigned Workspace) | Key UX Improvements |
| --- | --- | --- | --- |
| Primary Home & Workspace | [Previous Workspace](../assets/screenshots/workspace.png) | [Redesigned Home Dashboard](../assets/screenshots/ui-ux-redesign/01-tk-home-dashboard.png) | Grouped Orca dark shell, KPI strip, global context header, active & activity split |
| Projects & Task Creation | — | [Projects](../assets/screenshots/ui-ux-redesign/02-tk-projects.png) · [6-Step Wizard](../assets/screenshots/ui-ux-redesign/03-tk-task-creation.png) | Project search, 3-tab repo inspection, linear natural-language wizard |
| Task Detail & Agents | — | [7-Tab Task Detail](../assets/screenshots/ui-ux-redesign/04-tk-task-detail.png) · [Agent Dashboard](../assets/screenshots/ui-ux-redesign/05-tk-agent-monitor.png) | Structured tabs replacing flat text dumps; filtered node telemetry |
| Git Merge Approval | [Previous Approval Dialog](../assets/screenshots/tk-release-approval.png) | [Redesigned Approval Modal](../assets/screenshots/ui-ux-redesign/06-tk-git-approval.png) | KPI cards, explicit ready/blocked reasons, async diff dialog, reject button |
| Provider Configuration | — | [Providers & Models](../assets/screenshots/ui-ux-redesign/07-tk-provider-settings.png) | Runtime/CLI/Model KPIs and Simple/Advanced setup wizard separation |
| Electron Read-Only History | [Previous Electron Monitor](../assets/screenshots/electron-release-history.png) | [Redesigned Electron History](../assets/screenshots/ui-ux-redesign/08-electron-execution-history.png) · [QA Detail View](../assets/screenshots/ui-ux-redesign/09-electron-qa-details.png) | Aligned dark palette, KPI strip, Execution mode filter, QA pass/fail pills |

## 5. Added & Modified Files Summary

| Status | Path | Purpose |
| --- | --- | --- |
| Added | `orchestra/ui/__init__.py`, `theme.py`, `strings.py`, `components.py` | Shared dark/light design tokens, localization strings, status helpers, reusable cards/badges |
| Modified | `orchestra/terminal.py` | Optional `palette` integration for ANSI PTY surface theming |
| Modified | `orchestra/desktop.py` | Grouped sidebar, 52px header bar, live dark/light switching, enhanced `Git 병합 승인` modal |
| Modified | `orchestra/workspace_forms.py` | `Form.set_visible`, enhanced `projects`, 6-step in-place `guided_page`, `providers_page`, Simple/Advanced wizard, `history_page`, `settings_page` |
| Modified | `orchestra/workspace_remote.py` | Localized states and dedicated `SSH 서버` (`ssh_page`) view |
| Modified | `orchestra/workspace_desktop.py` | Header context bindings, KPI `Home`, 7-tab Task Detail + inline Approval, upgraded `Agents` & `DAG` canvas |
| Modified | `apps/desktop/src/main.tsx`, `apps/desktop/src/styles.css` | Orca dark tokens, Read-only/Live pills, KPI strip, Execution mode filter, QA summary badges |
| Added / Updated | `tests/test_ui_contracts.py`, `tests/smoke_ui_redesign.py`, `apps/desktop/tests/desktop.spec.ts` | Headless UI contract tests, Tk multi-screen smoke & screenshot capture, extended Playwright E2E |
| Added | `docs/assets/screenshots/ui-ux-redesign/*.png` (`01`..`09`) | 9 verified dark-mode application screenshots |
| Added | `docs/internal/ui-ux-audit.md`, `ui-ux-redesign.md`, `ui-navigation-map.md`, `ui-qa-report.md` | Redesign documentation and QA deliverables |
