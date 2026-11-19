# Integrated workspace implementation

| Files | Change |
| --- | --- |
| `orchestra/workspace_shell.py`, `orchestra/workspace_desktop.py` | Primary Tk shell, project and session tree, resizable workspace, task tabs, Agent and Activity context, quick actions, status and layout persistence |
| `orchestra/workspace_sessions.py`, `orchestra/terminal.py`, `orchestra/terminal_screen.py` | Session reuse, split axes and sash controls, explicit process lifecycle, keyboard and clipboard handling, alternate screen, cursor status, and scrollback-preserving resize |
| `orchestra/workspace_context.py`, `orchestra/project_files.py`, `orchestra/remote.py` | Local and remote file tree, bounded search and previews, shared Git status and diff logic. The Worker exposes two read-only methods on its approved repositories via pinned SSH. |
| `orchestra/workspace_forms.py`, `orchestra/workspace_remote.py`, `orchestra/desktop.py`, `orchestra/ui/strings.py` | Guided submission with workspace defaults, pinned remote connection and work tabs, existing job actions by exact job ID, shutdown timer cleanup and navigation integration |
| `apps/desktop/src/styles.css` | Color and density alignment, light mode and layout at narrow widths |
| `scripts/qa/verify.mjs`, `tests/smoke_integrated_workspace.py`, `tests/smoke_workspace_flow.py`, `tests/test_terminal_screen.py`, `tests/test_workspace_context.py` | Unified fixture-driven integration, real PTY and optional loopback SSH, existing operator-flow regression, new terminal and explorer tests |

The terminal launcher discovers Local Shell, saved SSH profiles, OpenCode, Codex, Gemini CLI, Antigravity and Claude Code. Missing local executables receive a setup message. An SSH terminal for a registered remote project uses its configured working directory. Closing it leaves Worker execution under the detached Supervisor.

The right Agent panel gets role, Harness, route, timing, tool counts and token counts from actual recorded events. Local Agent details select that stage's structured logs inside the task's tab. The task tab also opens the full Agent Dashboard. Stop and retry target the Supervisor job, which is the operation exposed by the existing contract. Remote job controls open the existing Worker operator page.

The Electron launcher prefers a discoverable executable or local packaged build and can fall back to the built preview in a repository checkout. It passes the same `ORCHESTRA_DATA` directory. Electron's existing snapshot bridge, IPC surface and read-only security remain in place.

The polish adds a visible Focus action, terminal titles and focus outlines, a responsive toolbar with an open-tabs menu, and a remembered context tab per project. Workspace text, task and merge dialogs, and terminal controls have English and Korean display strings. The language preference takes effect on the next launch. See the [UX changes](orca-workspace-ux-polish.md) and [visual review](orca-workspace-visual-review.md).

## Remaining boundaries

- A noninteractive Supervisor Agent exposes structured logs. Attaching arbitrary worker processes to an interactive PTY and per-stage execution controls would require additional Supervisor contracts.
- Standalone interactive CLI login, active model and reasoning effort are unknown unless the CLI reports them through a supported interface. Interactive OpenCode v2 on the verification host did not advertise a top-level model startup flag. Codex's compatible startup profiles are selectable, and successful authenticated inference requires separate verification.
- Git observations can be refreshed in the Files or Git panel. Remote Git previews require the updated Worker. The File Explorer's remote search covers loaded paths.
- Restored sessions require an explicit start. Cross-restart terminal history is excluded from persisted layout to avoid retaining sensitive terminal text. Custom commands and in-memory archives are excluded from restoration.
- Korean is the default. The workspace and administrative screen language coverage is described in the [localization report](orca-workspace-localization.md). Upstream CLI language is controlled by the CLI itself.
- The existing desktop has task creation and execution records. A separate Automations page would require another product workflow.

See the [QA report](orca-workspace-qa.md) for platform verification and real screenshots.
