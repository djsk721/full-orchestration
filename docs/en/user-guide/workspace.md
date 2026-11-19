# Project workspace

Start with `Launch-Windows.cmd` on Windows. When running from source, install terminal rendering and system metrics with `py -3 -m pip install -r requirements-desktop.txt`. Build the Windows distributable with `.\Build-Windows.ps1 -InstallBuildDependency`. SSH requires the Windows OpenSSH Client with `ssh.exe` and `ssh-keyscan.exe` available.

## Start a project and a run

1. Select a Git folder under **Projects → Add local repository**. The app reads the repository root, branch, origin, technology markers, and suggested QA commands.
2. Save the default model, harness, file scope, MCP tools, and QA commands from the project tab. Review discovered QA commands before submitting work.
3. Open **New task → Create a plan**. Enter a description and select **Read-only investigation**, **Change, review and QA**, or **Run checks only**. The selected strategy and project defaults generate the plan.
4. Review the nodes and dependencies. Change permissions through the node editor as needed, then approve the proposed execution paths and QA commands. Advanced JSON editing is available for tasks and the registry.

For example, “Inspect the backend and explain what can be improved” can start an Explorer plan. A change plan requires a file scope and integration QA. A QA-only plan can run `git --version` without a model.

## Providers and models

The **Provider setup wizard** can register Ollama, llama.cpp, a local OpenAI-compatible endpoint, OpenCode, or Codex. The connection test requests the runtime model list and shows the response time. The form distinguishes a reported context limit from its configured value. Execution still runs the existing runtime checks.

CLI discovery can locate executables. For supported CLIs, operators can authorize a version check for a trusted executable. Login, vision, and reasoning capabilities are unverified by this check. Gemini CLI, Claude Code, and Antigravity can be detected, with execution adapters pending. Use environment references or the external CLI credential store.

**Edit model and runtime** can update roles, harnesses, budgets, routing scores, runtime limits and credential references. The advanced JSON registry saves schema version 1 and preserves prior bytes under `backups/registry.json`. Projects and SSH profiles use a separate `workspace.json`.

## Agents and terminals

The **Agent Dashboard** shows persisted node state, execution routes, observed tokens, tool calls, changed files, and results. Use event search for failures, QA and tool activity. Open an Agent from its DAG node or compare two run reports in **Orchestration**. The **Task Runs** screen applies the existing approval flow to a QA-verified candidate SHA.

The integrated terminal uses an operator-controlled PTY for local and SSH shells. It supports tabs, a split view, ANSI output, input and resizing. Reopening a session starts a fresh shell. The Supervisor's non-interactive Agent processes expose structured events, and a completed node can open a separate shell in its Worktree.

## SSH and the Linux Worker

1. Prepare Python 3.11 or newer and Git on the remote server. Place the `orchestra/` directory and `ModelOrchestration.pyw` together in the Worker source directory.
2. As the same server user, run `python3 -m orchestra.remote --register /absolute/path/to/repo` in that directory. This adds the repository to the Worker allowlist. The default Worker data location is the `remote-worker/` subdirectory in the app data path.
3. Add any required and trusted model settings to the Worker's `registry.json` on the server. To permit file changes add `--allow-background-write` to the registration command. Uploads are separately enabled with `--allow-upload`.
4. In **Execution Environments → Add SSH host**, enter the host, account, SSH Agent or key path, and Worker source path. Specify a Python 3.11+ interpreter if the server's default is older.
5. Under **Trusted fingerprint**, enter the key fingerprint confirmed with the server administrator over a separate channel. After **Test connection** succeeds, use **Projects → Add remote repository** to select an allowed repository.
6. Submit a plan in that project. One DAG runs on the selected Linux host. The server Supervisor owns the job if the app or SSH connection closes. Use **Remote runs → Reconnect** to inspect the same execution.

The project browser can list directories and download regular files up to 200 KB. When enabled and explicitly approved, uploads go to a separate Worker staging directory. Unlock encrypted keys in your SSH Agent before non-interactive API calls. Windows SSH hosts have a shell and connection-test path, with native verification pending.

## MCP and troubleshooting

Use **MCP & Tools** to discover existing CLI configurations and create separate Managed server and tool policies. Optional Agent restrictions use the `role/node-id` form. Existing Federated connections change only through user-initiated migration. Existing approval gates continue to control external writes and merges.

- If the model is unavailable, check the model list, the project execution host and the selected role and harness.
- If an SSH host key changes, independently verify the new fingerprint before updating it.
- On a remote disconnect, use **Reconnect** on the original run to retain its submission ID.
- Keep credential values and private key contents outside configuration JSON.

See [ssh-keyscan](https://man.openbsd.org/ssh-keyscan) and [ssh_config](https://man.openbsd.org/ssh_config) for host-key collection and trust behavior.
