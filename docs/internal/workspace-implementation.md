# Workspace expansion audit

Baseline `49e5062` on `codex/bilingual-documentation`. The working tree was clean. The separately checked out `codex/typescript-migration` branch has a read-only Electron preview and was inspected for architectural context. The production Windows launcher and package still enter `ModelOrchestration.pyw`. The existing Tk application can support native form dialogs, a project sidebar, notebooks, resizable panes and a terminal emulator backed by a PTY. Continue on the maintained Python entry point.

## Initial implementation inventory

| Area | Source and baseline behavior | Expansion and regression boundary |
| --- | --- | --- |
| Windows entry points | `ModelOrchestration.pyw`, `Launch-Windows.cmd`, PyInstaller, Scheduler helper; Win32 Job Objects for children | Keep launcher; verify package and native terminal separately |
| UI / workflow | `desktop.py` submits a raw JSON plan; raw registry, jobs, MCP and approval screens are connected | Add first-run, projects and guided forms; retain advanced editor and exact approval actions |
| Provider and models | `core.py`, `runtime.py` validate profiles and score routes; loopback llama.cpp, Ollama and compatible runtime; runtime tools probed at execution | Display observed and configured model data separately; connection test must not activate unselected models |
| Attached harness | `harness.py` runs OpenCode and Codex in noninteractive subprocesses, with CLI-specific permissions. Discovery includes additional CLI settings | Detect additional executables, keep real integrations explicit; do not infer login or wire undocumented execution |
| Managed harness | Context budgeting, checkpoints, scoped file tools and MCP policies exist | Preserve checkpoint and no-replay behavior; surface recorded metrics and events |
| DAG and roles | `core.plan_check`, `supervisor.JobRunner`, worktree per task, dependency order, Reviewer and deterministic QA | Generated plans use the same validators and role constraints; show actual DAG state |
| Git integration | `gitgate.py` protects write scope, checks QA, pins exact candidate SHA and uses fast-forward | Reuse locally and on each remote Worker; never merge between unrelated repositories |
| MCP | `discovery.py`, `mcp.py` implement Federated discovery, Managed authorization, native loopback Gateway and supported migration/rollback | Use existing client, policies and approvals; tests must preserve client configs |
| Persistence and recovery | SQLite WAL stores stable job/task IDs, sequence, approvals, leases, heartbeats and checkpoints | Keep schema additive; distinguish transport failure from job failure and deduplicate remote submits atomically |
| Runtime evidence | Store records lifecycle, route and usage events. QA failure evidence is an event even when no successful integration result is committed | Show state and available evidence; never invent activity, usage or percentages |
| Workspace and remote | Baseline has no persisted projects, operator terminal, SSH host management, or independently hosted Worker | Add profiles, host verification, PTY, and use a detached per-user Supervisor on Linux; keep deployment explicit |

Baseline QA on Linux, before modifications, passed all 10 existing cases. They cover runtime gates, actual temporary Git worktrees and approval merge, tool approval/no replay, MCP transition/rollback, simulated CLI output and Supervisor detach/crash recovery. Network endpoints were localhost fixtures. GPU, actual external accounts and Windows packaging were outside baseline verification.

## Implementation sequence

1. Preserve the existing Python execution path and add project and configuration services, guided submission, and workspace UI.
2. Read Agent and DAG views from actual work and event records, add user-controlled PTY sessions.
3. Add strict SSH profiles and test/discovery, then ship a narrow Worker protocol using the existing detached Supervisor and an independent remote state directory.
4. Surface managed MCP catalogs and observed execution evidence. Run the original tests again plus targeted CPU-only unit, process and UI tests.

## Implementation and preservation

The Windows launcher still enters the Python desktop. The existing DAG scheduler, Git and QA gates, Managed Harness, MCP transition and rollback, approvals and Supervisor remain the execution path. The UI uses the same plan validation and policy checks. New SQLite tables are additive; old run IDs, checkpoints and approval records keep their schema and ownership. Registry version 0 is accepted on read and written as version 1 on an explicit save. Previous bytes are backed up. Unsupported top-level versions and fields produce an error.

| Area | Status | Main files and evidence |
| --- | --- | --- |
| Project workspace, navigation and activity | Implemented, Linux UI smoke verified | `workspace_desktop.py`, `workspace_forms.py`, `workspace.py`, `observability.py`. A native dashboard, recent events, project tabs, real Git inspection and per-project defaults. Two window sizes exercised. Screenshot in `docs/assets/screenshots/workspace.png`. |
| Simple and Advanced setup, proposal and QA | Implemented for supported strategies | `workspace_forms.py`, `workspace.py`, `core.py`. Strategy-based draft from user text, editable DAG nodes, routing preflight, explicit execution/QA approval, preserved Advanced JSON, schema migration and backups. Workspace QA and configuration tests passed. |
| Provider/model setup | Partially implemented | `workspace.py`, `workspace_forms.py`. Attached local Runtime catalog and timing, configured vs. reported Context, CLI installation/version checks, credential references and model/Runtime form. Existing OpenCode/Codex and managed local execution remain. Direct hosted APIs, additional CLI execution and live login/capability checks are pending. |
| Agent dashboard | Partially implemented | `observability.py`, `workspace_desktop.py`, `harness.py`, `supervisor.py`. Real lifecycle, structured CLI events, route scores and manual overrides, filterable events, changed files and permitted artifacts. UI and metric projection smoke passed. Controls act on the job, which remains the unit of stop/retry. |
| Integrated terminal | Implemented for operator sessions on Linux, Windows source path implemented | `terminal.py`, `workspace_desktop.py`, `Build-Windows.ps1`. Real Linux PTY and Windows pywinpty ConPTY adapter, ANSI emulator, tabs, split, resize, scrollback and cleanup. Linux input/output and resizing verified. Reopen starts a new shell. Existing noninteractive Agents expose events; completed Worktrees can open an independent shell. |
| SSH and remote execution | Partially implemented and verified on local Linux OpenSSH | `ssh.py`, `workspace_remote.py`, `remote.py`. Profile editing/grouping, key or Agent authentication, independently verified key pinning, SSH terminal route, allowlisted Git projects, server-side Worker validation and job control, status/event polling, file listing/download and authorized staging upload. Windows SSH convenience and split terminal route need native verification. |
| Detached Worker | Implemented for a single selected Linux host per DAG | `remote.py`, `store.py`, existing `supervisor.py`. Atomic request receipt, server-side durable queue, independent lifecycle, status and recovery. Real loopback SSH confirmed job continuity after closing the submission connection, reconnecting and returning one execution for the same request ID. |
| MCP | Partially expanded | `workspace_desktop.py`, `mcp.py`, `harness.py`, `core.py`. Real catalog, explicit read test, policy forms and Agent-ID filter, existing Federated discovery, Gateway/rollback and write approval. Agent constraint test and existing MCP regressions passed. |
| DAG and observability | Partially expanded | `workspace_desktop.py`, `observability.py`, `store.py`. Actual graph and linked node details, run comparison, structured tool/QA/Git events, model counts, optional CPU/RAM and explicit NVIDIA metrics request. Cross-host DAG scheduling, automatic resource-aware host selection, persistent comparison history and live GPU verification are pending. |

## Security and regression notes

- SSH uses a profile-specific OpenSSH config and host pin. Unknown or changed hosts are rejected prior to authentication. The keyscan fingerprint is only saved after operator confirmation through an independent channel. The transport disables password and interactive server authentication, agent forwarding, proxy commands and forwarding.
- The remote API is carried inside authenticated SSH and is restricted to explicitly registered Git roots. Remote Worker execution has the same worktree scopes, review, QA and exact-SHA merge approval as local execution. A repeated submission verifies the original plan hash. Action requests are reconciled via status after a connection error.
- Secrets remain in the external CLI store, SSH Agent/key file, or environment reference. Terminal output is operator-visible session data; Agent activity stores selected event types and structured observations. Tester and upload paths require explicit actions. Linux path scopes now distinguish case.
- Git supports a DAG on one selected Worker so all dependencies share their canonical repository and candidate SHA. A mixed-host DAG needs a separate artifact transfer protocol and verification of ref ancestry on each host.
- Existing configuration and source changes are local to this working tree. The Electron preview is independently maintained in its migration worktree.

## Verification

| Check | Result |
| --- | --- |
| Before implementation | Existing Python suite 10/10 on Linux using temporary Git directories and mock Runtime/MCP fixtures |
| After implementation | Python suite 18/18 on Linux, including the original 10 |
| SSH | Real Linux loopback OpenSSH with generated keys and a temporary per-user Worker. Host pin, changed-key rejection, public-key login, interactive SSH PTY, detached execution, reconnect and duplicate prevention |
| Desktop | Native Tk startup at 940×650 and 1330×850 under Xvfb, guided QA plan review, live Agent and DAG data, ANSI/input and terminal cleanup |
| Documentation | Link/structure, bilingual manifest and feature-source consistency checks |
| Windows and external integrations | Windows package, native ConPTY and task scheduler, Windows OpenSSH host, real provider accounts, external server deployment and GPU behavior not verified here |

Run the Python suite with `python -m unittest discover -s tests -v`. On Linux, `python tests/smoke_workspace_ssh.py` starts an isolated sshd bound to loopback with disposable keys. Install `requirements-desktop.txt` before `xvfb-run -a python tests/smoke_workspace_ui.py`. The optional `--screenshot PATH` argument requires Pillow. Linux QA made no GPU queries or requests to real model servers.

## Remaining acceptance criteria

A live noninteractive Agent terminal, node-level stop/reassign semantics, mixed-Worker DAGs, truly automatic resource-aware worker selection, direct OpenAI/Gemini/Anthropic connections, additional Harness adapters, model-generated plan proposals, and Windows installation and live-provider verification remain open. See the [workspace guide](../ko/user-guide/workspace.md) for user workflows and server deployment.
