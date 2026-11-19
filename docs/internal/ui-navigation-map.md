# Model Orchestration — UI Navigation Map & Operator Flows

## 1. Global Application Shell (Tk Primary Workspace)

The redesigned Tk application (`WorkspaceDesktop`) organizes every workflow inside a unified dark/light multi-pane shell (`1360x860` default, `920x630` minimum):

### 1.1 Grouped Left Navigation Sidebar (11 Primary Items)

| Group | Nav Key | Korean Label | English Key | Primary Responsibility |
| --- | --- | --- | --- | --- |
| `WORKSPACE` | `home` | `홈` | `Home` | Global KPI summary, active runs, guided empty state, recent activity |
| `WORKSPACE` | `projects` | `프로젝트` | `Projects` | Local/remote Git repos, default routes, QA commands, Git status, runs |
| `WORKSPACE` | `jobs` | `작업` | `Tasks` | Searchable execution list, lifecycle actions, 7-tab Task Detail |
| `WORKSPACE` | `agents` | `Agent 대시보드` | `Agent Dashboard` | Node-level role, stage, route, tokens, tool calls, filtered events |
| `EXECUTION` | `terminals` | `터미널` | `Terminals` | Local & SSH interactive ANSI PTY shells (`pyte` + dark theme) |
| `EXECUTION` | `hosts` | `실행 환경` | `Environments` | Host table, CPU/RAM/GPU metrics, Worker heartbeat inspection |
| `EXECUTION` | `ssh` | `SSH 서버` | `SSH Servers` | Dedicated pinned host fingerprints, Worker check, SSH shell launch |
| `INTEGRATIONS` | `mcp` | `MCP & 도구` | `MCP & Tools` | CLI MCP discovery, Managed Gateway migration, read probes, rollback |
| `INTEGRATIONS` | `providers` | `Provider & 모델` | `Providers & Models` | Runtime/CLI KPI cards, Simple/Advanced setup wizard, profile editor |
| `SYSTEM` | `history` | `실행 기록` | `Execution History` | Searchable archive across states/projects + run report comparison |
| `SYSTEM` | `settings` | `설정` | `Settings` | Theme toggle (`ui_prefs.json`), policy dialog, JSON export & inspection |

Additional contextual/deep-link routes (`nav` button hidden, opened via workflow actions):

- `submit`: In-place 6-step New Task Wizard (`+ 새 작업`, `Ctrl+N`, Home/Projects actions)
- `dag`: Dedicated standalone Interactive DAG Canvas (linked from Home metrics / Task flows)
- `advanced_plan`: Raw `plan_check` JSON editor (opened from Task Wizard `"고급 JSON 편집"`)
- `registry`: Raw `registry.json` editor with backup preservation (opened from Providers / Settings `"고급 JSON"`)
- `remote_runs`: Detached SSH Worker execution monitor (opened from Tasks / SSH / Agents `"원격 작업"`)

### 1.2 Global Top Header Bar (52px)

- **Left Context Strip**:
  - `프로젝트` quick-switcher combobox -> jumps directly to selected project tab or syncs current Task Wizard target
  - Execution environment pill (`환경: 이 PC` or pinned SSH host name)
- **Right Telemetry & Primary Actions**:
  - Live Supervisor pill (`Supervisor 실행 중` / `연결 중` / `종료됨`)
  - Live Worker pill (`로컬 Worker` or `Worker N/M`)
  - Pending Approval / Notification badge (`승인 대기 N` / `알림 0` -> click opens `jobs`)
  - Theme Switcher (`라이트` / `다크` -> live redraw across Tk, ttk, cards, canvas, PTY + saved to `ui_prefs.json`)
  - Global CTA (`+ 새 작업` -> switches to `submit` 6-step wizard)

## 2. Primary Operator Flows

### 2.1 Project Onboarding & Per-Project Workspace (`projects`)

1. Click `로컬 저장소 추가` (folder chooser) or `원격 저장소 추가` (pinned SSH Worker repo query) -> opens `project_dialog` pre-filled via `inspect_project`.
2. Selecting a project opens or focuses its tab card containing target branch, remote origin, runtime environment badge, quick actions (`이 프로젝트에서 작업 만들기`, `터미널 열기`, `폴더 열기`/`원격 파일`), and 3 nested tabs:
   - `개요 및 기본 설정`: resolved stack, frameworks, config files, default model/harness, allowed write/read paths, QA commands
   - `Git 상태`: async non-blocking `git status` summary
   - `최근 실행 (N)`: executions scoped to that repository (double-click jumps to `jobs` detail)

### 2.2 In-Place 6-Step New Task Wizard (`submit`)

Accessible via `+ 새 작업`, `Ctrl+N`, Home empty-state CTA, or Project CTA (with optional `"빠른 팝업 마법사"` and `"고급 JSON 편집"` escape hatches):

1. `1. 프로젝트`: Select registered local/remote project with live metadata preview.
2. `2. 작업 설명`: Natural-language prompt input + 3 strategy cards (`읽기 탐색`, `개발 및 통합 QA`, `QA 명령만 실행`).
3. `3. 실행 설정`: Provider/Model/Harness cascade + background execution checkbox + `CollapsibleSection` for write paths, MCP tools, and QA commands.
4. `4. 실행 계획`: Auto-generated `draft_plan` DAG node list with Add/Edit/Remove/Regenerate actions.
5. `5. 권한 안내`: Explicit read/write/MCP/Git safety guard badges reflecting backend enforcement rules.
6. `6. 검토 및 제출`: Preflight `plan_routes` summary + confirmation -> hands plan directly to `Store` & `Supervisor`.

### 2.3 7-Tab Task Detail & Safe Git Merge Approval (`jobs`)

Selecting any execution populates the summary header card (title, live `StatusBadge`, changed-file count, passing QA count, candidate short SHA) above 7 structured tabs:

1. `개요`: Execution ID, repo, target branch, background/foreground mode, timestamps, QA commands, node states.
2. `실행 계획`: Embedded colored DAG node graph (`_draw_dag`) synced with `execution_state.task_stage`; clicking a node opens its details on `agents`.
3. `Agent`: Node/role/state/route/elapsed/token table (`Agent 대시보드에서 열기` button jumps directly to node timeline).
4. `변경 파일`: Changed-file list + async worktree/commit `git diff --stat` preview.
5. `QA 결과`: Verification revision ID, pass/fail counts, exit codes, and execution durations.
6. `승인`: Authoritative `approval_state_info` status badge (`QA 대기`, `검토 대기`, `승인 준비 완료`, `QA 실패`, `병합 중`, `병합 완료`, `승인 거절`, `완료 (병합 대상 없음)`), candidate SHA, explicit blocker reasons when disabled, and action buttons (`후보 병합 승인`, `승인 거절`, `변경 Diff 보기`).
7. `로그`: Formatted node stages and streaming chronological event log (`self.detail`).

Clicking `병합 승인` (or `후보 병합 승인`) opens the redesigned **`Git 병합 승인`** modal displaying summary KPI cards (`통합 QA 통과`, `통합 QA 실패`, `독립 검토`, `변경 파일`), revision/candidate evidence, `"변경 사항 보기"` async full-diff viewer, `"거절"`, and `"이 후보 승인"`.

### 2.4 Provider Setup & SSH Server Management (`providers`, `ssh`)

- **Provider Wizard**: Starts in **간편 모드** (`kind`, `id`, `found`, `model`, `default`) with one-click discovery/probe (`설치 탐색`, `연결 확인`); switching to **고급 모드** dynamically reveals `endpoint`, `auth_env`, `executable`, `context`, and `trusted` while preserving all 10 form keys cleanly.
- **SSH Servers**: Separates host fingerprint pinning (`신뢰 지문`), connectivity checks (`연결 테스트`), terminal launch (`SSH 터미널`), and remote worker run monitoring (`원격 작업 보기`) cleanly from local execution settings.

## 3. Electron Read-Only Companion Navigation (`apps/desktop`)

1. **Header Bar**: `Model Orchestration` + `Read-only Monitor` pill + live connection pill (`Live Sync` / `Connecting` / `Offline Cache`) + timestamp freshness (`Last refreshed` / `Cached snapshot from`).
2. **KPI Overview Strip (`Execution overview`)**: `Total runs`, `Running`, `Awaiting approval`, `Succeeded`, `Failed / Stopped`.
3. **Search & Multi-Filter Sidebar (`Job history`)**: Free-text query (title or execution ID), `Job state` select, and `Execution mode` select (`All modes`, `Background`, `Foreground`).
4. **Read-Only Detail Workspace**: Selected job header badge, searchable `Workflow dependencies` DAG cards with semantic state borders, `Integration QA` pass/fail summary badge + Candidate SHA + individual exit-code cards, and `Recent activity` timeline. When SQLite history is temporarily unavailable, the UI retains the last valid cached snapshot with a reconnection status banner and never performs writes (`window.orchestration` exposes only `snapshot`).
