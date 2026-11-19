# Model Orchestration — UI/UX Redesign QA Report

## 1. Baseline vs. Post-Redesign Verification Matrix

All verification commands below were executed on Linux x64 (`feature/ui-ux-redesign`) inside the isolated QA Python virtual environment (`pyte==0.8.2`, Pillow `9.4.0`, Tk `8.6.12`) with `env -u ELECTRON_RUN_AS_NODE` and `xvfb-run`.

| Suite | Pre-Redesign Baseline (`422a826`) | Post-Redesign Result | Timing / Evidence |
| --- | --- | --- | --- |
| Strict TypeScript + Vite build | PASS (`230ms`) | **PASS** (`164ms`) | `vite v8.3.8`, `dist`/`build/renderer` clean |
| Node.js core & store contract tests | `25/25 PASS` (`728.38ms`) | **25/25 PASS** (`817.58ms`) | `node --test "build/main/tests/*.test.js"` |
| Python regression + UI contract tests | `41` ran (`39 PASS`, `2` Windows-only skipped) | **45 ran (`43 PASS`, `2` Windows-only skipped)** | `58.317s` including `test_ui_contracts.py` (`4/4 PASS`) |
| Electron Playwright E2E (from source) | `4/4 PASS` (`19.8s`) | **5/5 PASS** (`22.9s`) | Includes new KPI/mode-filter/QA/overflow test |
| Packaged `linux-unpacked` Playwright E2E | `4/4 PASS` (`19.7s`) | **5/5 PASS** (`23.3s`) | Built cleanly with `electron-builder 26.18.0` |
| AppImage `--appimage-extract-and-run` E2E | `4/4 PASS` (`27.7s`) | **5/5 PASS** (`33.3s`) | `Model Orchestration Preview-0.1.0.AppImage` |
| Tk legacy UI smoke (`smoke_workspace_ui.py`) | PASS | **PASS** | Guided QA form, Agent events, DAG, ANSI PTY |
| Tk end-to-end flow (`smoke_workspace_flow.py`) | PASS | **PASS** | Submission, live Agents, HTTP fixture, QA, Git merge |
| Tk UI/UX redesign smoke (`smoke_ui_redesign.py`) | — | **PASS** | All `11` nav views, `3` sizes, light/dark toggle, 6-step wizard, 7 tabs, diff & merge |
| `npm audit` & `npm audit --omit=dev` | `0 vulnerabilities` | **0 vulnerabilities** | Production and dev dependency trees clean |

Skipped tests in Python (`2` total):

- `test_windows_atomic_save_keeps_read_only_file`: requires native Windows read-only file attributes.
- `test_worktree_guard_rejects_a_real_windows_junction`: requires a native Windows directory junction.

## 2. Responsive Layout & Usability Verification Matrix

| Surface | Viewport / Geometry | Verified Assertions | Result |
| --- | --- | --- | --- |
| Tk Primary Workspace | `940x650`, `1280x800`, `1440x900` | Zero uncaught Tk callbacks, sidebar `> 150px`, header `>= 48px`, main shell `> 600px` | **PASS** |
| Tk Dark <-> Light Theme Switch | `1360x860` | Palette flips cleanly (`#0d1117` <-> `#f4f6fa`), persists to `ui_prefs.json`, `registry.json` remains valid | **PASS** |
| Tk Empty State & Error Discovery | `1360x860` | Guided `EmptyState` card shown on empty workspace; QA failure disables approve actions cleanly | **PASS** |
| Electron Read-Only Desktop Monitor | `1360x860` | KPI counts, foreground/background mode filter, QA pass/fail badges, zero horizontal overflow | **PASS** |
| Electron Read-Only Narrow Viewport | `760x760` | Single-column collapse via CSS media query; `document.documentElement.scrollWidth <= window.innerWidth` | **PASS** |

## 3. Visual Screenshot Verification & Polish Fixes

All `9` application screenshots under `docs/assets/screenshots/ui-ux-redesign/` were captured from live Tk/Electron instances using real SQLite databases, real temporary Git repositories, and scripted inference at `1360x860`, then inspected directly:

| Screenshot | Captured State | Visual QA Result |
| --- | --- | --- |
| [01-tk-home-dashboard.png](../assets/screenshots/ui-ux-redesign/01-tk-home-dashboard.png) | Dark Home dashboard with populated KPIs, active job & event feed | **PASS** |
| [02-tk-projects.png](../assets/screenshots/ui-ux-redesign/02-tk-projects.png) | Selected project workspace with environment badge & nested tabs | **PASS** |
| [03-tk-task-creation.png](../assets/screenshots/ui-ux-redesign/03-tk-task-creation.png) | In-place 6-step New Task Wizard at Step 4 (DAG plan review) | **PASS** |
| [04-tk-task-detail.png](../assets/screenshots/ui-ux-redesign/04-tk-task-detail.png) | `AWAITING_APPROVAL` task selected with 7-tab detail & candidate evidence | **PASS** |
| [05-tk-agent-monitor.png](../assets/screenshots/ui-ux-redesign/05-tk-agent-monitor.png) | Agent Dashboard showing `developer` & `reviewer` rows, tokens & events | **PASS** |
| [06-tk-git-approval.png](../assets/screenshots/ui-ux-redesign/06-tk-git-approval.png) | Centered `Git 병합 승인` modal with KPI cards, QA pass check & actions | **PASS** |
| [07-tk-provider-settings.png](../assets/screenshots/ui-ux-redesign/07-tk-provider-settings.png) | `Provider & 모델` page with runtime/harness/model KPIs & profile row | **PASS** |
| [08-electron-execution-history.png](../assets/screenshots/ui-ux-redesign/08-electron-execution-history.png) | Electron Monitor showing `3` jobs (`Awaiting approval`, `Failed`, `Succeeded`) | **PASS** |
| [09-electron-qa-details.png](../assets/screenshots/ui-ux-redesign/09-electron-qa-details.png) | Electron Monitor inspecting real Python QA exit code `7` failure evidence | **PASS** |

Visual issues caught during screenshot inspection and resolved prior to final verification:

1. Expanded Tk sidebar width (`228px` -> `252px`) and tuned brand font size (`11pt` bold) so `Model Orchestration` renders cleanly without right-edge truncation on Linux bitmap fonts.
2. Configured active/normal state style maps on `Vertical.TScrollbar` / `Horizontal.TScrollbar` so Linux `clam` scrollbars render dark slate instead of default light beige.
3. Packed right-aligned `StatusBadge` widgets before wrapped title labels in Project headers, Task Detail headers, and the Git Merge Approval modal.
4. Adjusted Home/Jobs `Treeview` column widths, split the Task List footer toolbar cleanly into two rows (`JSON 보고서 저장` / `결과 폴더 열기` + `Supervisor 시작` / `Supervisor 종료`), and compacted the global header project combobox so `환경: 이 PC` never collides with right header pills.

## 4. Backend & Read-Only Contract Non-Regression

- All backend orchestration tests in `test_orchestra.py`, `test_platform_contracts.py`, and `test_workspace.py` continue to pass (`43/43` runnable on Linux; `2` Windows-specific skipped).
- Electron security assertions in `desktop.spec.ts` confirm `window.orchestration` exposes strictly `["snapshot"]`, `window.require === "undefined"`, `window.open === null`, invalid path requests reject cleanly, and the inspected SQLite file remains byte-for-byte unmodified.

## 5. Remaining Limitations & Environment Notes

- **Linux Anaconda Tk Bitmap Fonts**: This Linux environment lacks scalable Xft system fonts inside Anaconda Tk `8.6.12`, so text falls back to X11 bitmap fonts (`fixed`/`gothic`). Windows and Xft-enabled desktop distributions will render with sharper vector fonts (`Segoe UI`, `Malgun Gothic`, `Noto Sans CJK KR`).
- **Windows Native UI / NSIS Re-Verification**: Core cross-platform and read-only contracts are verified on Linux; visual layout and installer smoke checks on Windows native (`verify-windows-installer.ps1`) remain to be re-run on a Windows host before a Windows release tag.

## 6. Local Git Branch & Working-Tree State

- Active branch: `feature/ui-ux-redesign` (branched from `422a826` on `codex/bilingual-documentation`).
- Per project safety policy, UI/UX redesign modifications, new tests, captured screenshots, and redesign reports remain **uncommitted** in the local working tree for operator review (no automatic commits, pushes, or merges to `develop` / `main`).
