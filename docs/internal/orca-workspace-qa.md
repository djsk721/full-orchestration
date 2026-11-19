# Integrated workspace verification

## Commands and execution evidence

Use Node 24 as specified in `package.json`, Python with Tk, and the desktop dependencies. Install OpenSSH client/server and a virtual display for the optional Linux integration tests. The screenshot command requires Pillow. Run the commands from the repository root.

```bash
python -m pip install -r requirements-desktop.txt
npm ci
npm run verify -- --ui --ssh --harness
xvfb-run -a -s '-screen 0 1920x1080x24' python tests/smoke_integrated_workspace.py --ssh --screenshots docs/assets/screenshots/orca-workspace/polish
xvfb-run -a python tests/smoke_workspace_localization.py
xvfb-run -a -s '-screen 0 1920x1080x24' python tests/smoke_installed_workspace_cli.py
npm run verify -- --package
```

On a Linux desktop, launch the primary application with `python ModelOrchestration.pyw` after installing the Python desktop dependencies. The Electron package is the separately built history monitor.

## Onboarding and stability verification

The previous workspace baseline had 49 Python passes, 25 TypeScript passes, four Tk scenarios and 15 Electron cases across three launch targets. This pass recorded 52 Python passes with two Windows-only skips, 25 TypeScript passes, five Tk scenarios, and 15 Electron cases across Linux source, unpacked and AppImage. The English Tk case also exercises administrative forms and small-window toolbar placement. The SSH Worker, installed CLI checks, and the extended resource exercise ran independently.

| Capability | Linux evidence | Windows evidence |
| --- | --- | --- |
| First-run setup and administrative localization | Native Tk using a disposable Git folder, configured loopback Provider, optional SSH profile, genuine terminal and both language settings | Source reviewed. Native first launch and installer unverified. |
| Remote compatibility and safe reconnect | Real loopback OpenSSH with earlier and current Worker handlers; malformed and incompatible responses covered in headless tests | Host-independent protocol cases run on Linux. Native Windows transport and UI unverified. |
| Session, layout and terminal reliability | Thirty native Tk cycles under Xvfb using real PTYs, installed CLI smoke in isolated namespaces, corrupted/newer layout handling, and measured desktop RSS and CPU | ConPTY, Korean IME, clipboard, resizing, long paths and DPI require a native run. |
| Supervisor, SQLite, MCP and Git approval | Real Supervisor recovery, persisted checkpoints, policy and approval regression suites, and task-to-merge with scripted inference | Two Windows-only Python cases remain skipped on Linux. |
| Read-only Electron | Five cases from source, five from unpacked build and five from AppImage | Windows installer and packaged UI unverified. |

Authenticated external inference and GPU behavior were outside the executed verification. The deployed Worker upgrade steps were documented; the comparison used isolated local revisions and did not upgrade any server.

[First-run usability](orca-workspace-onboarding.md) · [Daily workspace E2E](orca-workspace-e2e.md) · [Worker compatibility](orca-worker-compatibility.md) · [Localization](orca-workspace-localization.md) · [Stability and resource usage](orca-workspace-stability.md)

The clean baseline passed strict TypeScript compilation, 25 TypeScript tests, 43 of 45 Python tests with two Windows-dependent skips, five Electron source Playwright tests, two native Tk flows, real loopback OpenSSH Worker recovery and an installed OpenCode smoke using a local scripted API.

The implementation passed strict TypeScript compilation and 25 TypeScript tests. Of 51 Python unit tests, 49 passed and the same two Windows-dependent cases skipped. All three native Tk smokes passed. The real OpenSSH Worker and installed OpenCode tests passed. Electron passed the same five Playwright scenarios from source, as the Linux unpacked build, and as the Linux AppImage in extract-and-run mode. The two packaged runs were executed separately from the main verification command using the generated executable paths.

The integrated smoke adds independent interactive sessions, PTY resizing and history, Unicode clipboard/input, sidebar and project switching, file inspection, task submission, Agent observation, QA, exact Git approval and layout restart. It uses a synthetic repository and never touches registered user projects.

| Capability | Linux evidence | Windows | macOS |
| --- | --- | --- | --- |
| TypeScript core, state contracts, SQLite, DAG, MCP policies, cancellation and QA | TypeScript/Python regression suites. Process, temporary Git and SQLite behavior are real. External service replies use fixtures. | Portable contracts are covered on Linux. Native Windows execution is unverified. | Outside current release scope |
| Tk shell, focus, panel geometry and layout restoration | Native Tk at 1440×900, 1920×1080 and 1024×700 under Xvfb | Unverified on native Windows | Outside current release scope |
| Terminal, TUI behavior and CLI launching | Real Linux PTY, kernel resize, ANSI, Korean input, Ctrl+C, clipboard and scrollback. CLI stand-ins provide deterministic interactive input/output. VT unit tests exercise alternate screen and cursor replies. | ConPTY path retained. It requires Windows execution for verification. | Outside current release scope |
| SSH terminal, pinned transport and Worker | Real loopback OpenSSH and isolated keys, interactive remote command, changed-key rejection, dispatch, offline completion, reconnect, duplicate prevention, Worker restart and cancellation | Windows OpenSSH and native terminal integration unverified | Outside current release scope |
| File/Git context, Agent and approval | Actual temporary repository, scoped explorer, live Supervisor/SQLite events, QA fixture checks and approved Git merge | Native UI, filesystem and junction behavior unverified | Outside current release scope |
| Electron UI and historical monitor | Native Electron Playwright cases for read-only screen, recovery cache, permissions and navigation | Windows Electron/NSIS installation and execution unverified | Outside current release scope |
| Upstream authenticated inference and GPU | No authenticated model inference or GPU validation was performed | Unverified | Outside current release scope |

## Visual QA and UX refinement

The existing baseline reports and captures remain available below. The refinement uses the same 25 TypeScript and 51 Python unit cases, the Tk flows and a new native localization case. Source, unpacked Electron, and AppImage each exercise five Playwright cases. The current display checks cover 940×650, 1440×900 and 1920×1080. See the [before/after visual review](orca-workspace-visual-review.md).

| Result type | Evidence |
| --- | --- |
| Actual installed CLIs with isolated loopback | OpenCode 2.2.7 and Codex 0.170.0 were open simultaneously. Native PTY and the actual CLI TUIs exercised ANSI, English key events, Korean clipboard input, copy, resizing, both split axes, focus, reuse without a new PID, project switching, hide and cleanup. No prompt was submitted. |
| Real isolated OpenSSH and Git | Registered repository status and read-only diff worked in the Worker and in Tk. Integration checked secret paths, traversal, unauthorized repos and transport loss/reconnect. |
| Real execution with scripted inference | Natural-language task flow used the real Python Supervisor, SQLite and Git. The inference fixture made the Agent, QA, candidate SHA approval and post-approval merge reproducible. Closing a task tab left detached work running. |
| Native locale and geometry | Korean continued in the running session when English was saved. Reopening retained English after toggling the theme. Task controls, context tabs, toolbar sizes and workspace error translation were checked. |
| Restored workspace without execution | The fixture checks task and terminal tab order, split direction and sash ratio, panel visibility, per-project context, and absence of automatically launched terminal processes. |

A Linux host must allow user, PID and network namespaces and have `iproute2` to run the optional installed-CLI smoke. The isolated namespace enables only its own loopback for OpenCode's embedded server. On this host the test itself has no configured external account. Windows native and GPU remain outside executed verification.

## Baseline native captures

| View | Capture |
| --- | --- |
| Integrated workspace, dark | [1440×900](../assets/screenshots/orca-workspace/integrated-workspace-1440x900.png) |
| Integrated workspace, light | [1920×1080](../assets/screenshots/orca-workspace/integrated-workspace-light-1920x1080.png) |
| Independent AI terminals | [1440×900](../assets/screenshots/orca-workspace/multiple-ai-tabs-1440x900.png) |
| Side-by-side terminals | [1920×1080](../assets/screenshots/orca-workspace/split-terminals-1920x1080.png) |
| File explorer and preview | [1024×700](../assets/screenshots/orca-workspace/project-files-small.png) |
| Project Git changes | [1440×900](../assets/screenshots/orca-workspace/project-git-1440x900.png) |
| Agent context and DAG | [1440×900](../assets/screenshots/orca-workspace/agent-context-1440x900.png) |
| Model picker | [1440×900](../assets/screenshots/orca-workspace/model-selector-1440x900.png) |
| Pinned SSH session | [1440×900](../assets/screenshots/orca-workspace/ssh-terminal-1440x900.png) |
| Supervisor execution | [1440×900](../assets/screenshots/orca-workspace/task-execution-1440x900.png) |
| Git and QA approval dialog | [800×560 modal](../assets/screenshots/orca-workspace/git-qa-approval.png) |
| Electron read-only monitoring | [1200×793](../assets/screenshots/orca-workspace/electron-read-only.png) |

Compared with the supplied Orca screenshot, the integrated layout keeps project and session access at left, reserves the widest pane for the selected tab, and places navigation and inspection alongside the terminal. Split placement is adjustable and the context panel can be collapsed. Files, Git, Agent and Activity each receive a dedicated tab rather than sharing one exposed list. The 1024×700 smoke verifies that the file query remains usable. Native font rendering depends on the host's Tk build. The Linux capture environment uses its available X11 fonts.

Screenshots use disposable projects, models, localhost SSH profiles and execution IDs. The optional installed OpenCode test uses a scripted localhost API without an external account. In the automated integrated workspace flow, the Supervisor, SQLite, Git approval, OpenSSH and PTY are live components. The inference responses and the interactive AI CLI bodies are fixtures.
