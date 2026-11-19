# Integrated workspace design

## Ownership and data flow

| Layer | Responsibility |
| --- | --- |
| Tk workspace | Select projects and sessions, launch operator terminals, guide task submission and present observed job state |
| Python Supervisor and SQLite | Authoritative queue, DAG, task state, checkpoints, recovery and approvals |
| OpenSSH Worker | Pinned transport, remote job state and allowlisted repository operations |
| Electron and TypeScript | Read-only monitoring, search, execution details, QA history and cached snapshots |

The workspace reads the same job and event records as the existing operator pages. Plan review uses the existing guided form, and exact-SHA approval uses the existing approval dialog and Supervisor check. Closing a job view affects the open tab only. A disconnected SSH view can show its last observation with a disconnect label while the Worker owns the job lifecycle.

## Workspace positions and session lifecycle

The left tree groups projects by host and presents open sessions, in-progress runs or approvals, and recent executions. The center notebook contains an overview, independent PTY tabs, and task views for progress, DAG, structured logs, QA and changes. Files, Git, Agent and Activity remain accessible at right when a center tab changes. The footer indicates the current project, observed branch, execution location, configured task model, Supervisor status, Worker observation and counts from available run records.

A session keeps its process, working directory, pending terminal input, screen and scrollback while its view is hidden. Layout changes can combine existing sessions in one tab or separate them into tabs with the same processes. A foreground terminal offers explicit hide, terminate, and cancel choices. Reopening a stopped or previously saved session starts a new process. Layout preferences record project associations, supported launch recipes, mixed tab order, the selected tab, pane ratios and visibility in `ui-workspace.json`. Program arguments, credentials, in-memory terminal text, and live processes are excluded from that file.

## Models, file context and controls

The quick selector sets a task-model preference using the verified local registry or the selected Worker catalog. The toolbar links to the existing Provider wizard for testing, discovery and defaults. Codex supports the verified `--model` startup option when a compatible profile exists. Applying it to a running session asks for confirmation and archives its previous output in memory. Other CLI tools keep model and authentication interaction in their own UI. An unknown actual model is shown as unobserved, and reasoning control is omitted unless the integration can confirm and apply it.

The local explorer performs bounded, UTF-8 read-only inspection with protected path filtering and link handling. Git context uses the repository's observed branch, status and diff. Remote tree and preview use the existing pinned Worker file interfaces. Remote file search is limited to loaded paths, and the Git panel identifies the lack of a general remote status/diff operation.

The command palette exposes actions supported by the application. `Ctrl+K`, `Ctrl+N`, `Ctrl+T`, `Ctrl+P`, and `Ctrl+Tab` with or without Shift work out of the terminal. The terminal receives interactive control keys while it has focus. Existing administrative screens remain available from the palette and grouped navigation.
