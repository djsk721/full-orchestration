# Operations

## Host and user account

- Run the desktop, Supervisor, Git, Runtimes, and external CLIs under the intended Windows user account. Git and the required `.exe` files must be accessible to that account.
- For Background Execution at login, finish active GUI work and build the Windows executable. Run the first command below to register an interactive user task with the default data directory. Use the second command by itself to remove the task.

```powershell
.\Register-SupervisorTask.ps1
.\Register-SupervisorTask.ps1 -Unregister
```

- Registration rejects a configured `ORCHESTRA_DATA`. The desktop's **작업 대시보드** (Job dashboard) displays Supervisor status.

## Authentication and security settings

- Model HTTP Runtimes use loopback. For an attached Runtime with bearer authentication, store the value in the variable named by `auth_env`. Managed llama.cpp and OpenCode's local Runtime route require a local address without authentication.
- Subscription CLIs use the current account's existing login. Enable `trusted`, `allow_unverified`, `inherit_environment`, and `allow_write` only as needed for a trusted CLI and Workspace. CLI permissions and Git checks provide limited isolation.
- SSH uses app-managed public host key pins and the existing SSH Agent or a key file reference. Linux Workers run in explicitly registered Git repositories. [Workspace guide](../user-guide/workspace.md)
- QA argv executes with the user's privileges. Approve only trusted job definitions and repositories, and use a dedicated unprivileged account with appropriate OS file and network access controls.

## MCP policy

Use HTTPS for external HTTP MCP connections. Loopback can also use HTTP. Configure environment variable names in `header_env`, `env`, and `gateway_token_env`. Assign roles and `read`/`write` access to each tool. Writes require a Developer and approval per call. The loopback Gateway requires a valid token and exposes read tools marked `native: true`. Restrict access to original configurations and rollback files. [MCP connections](../user-guide/mcp.md)

## CPU, GPU, and memory

Start with low `parallel_jobs`, `parallel_tasks`, and Runtime `slots`. The Supervisor sums declared `gpu_mb` and `ram_mb` reservations. `gpu_budget_mb: 0` prohibits positive GPU reservations. `ram_budget_mb: 0` disables the RAM budget check. Use host tools to measure actual CPU and memory use. The Windows example uses `gpu_layers: 0`. [Configuration and API](configuration.md)

## Logs, reports, and data

| Path | Contents |
| --- | --- |
| `registry.json` | Providers, Models, Runtimes, Harnesses, MCP, and execution settings |
| `state.db` and SQLite WAL | Queue, submitted plans and configuration snapshots, events, approval arguments, call state, and checkpoints |
| `artifacts/` and `worktrees/` | Agent output, individual and integration Git Worktrees |
| `migrations/` | Original MCP settings and migration journals |
| `supervisor.json` | Live Supervisor status and Gateway errors |

The Windows default is `%LOCALAPPDATA%\ModelOrchestration`. Set `ORCHESTRA_DATA` to use a different directory. **JSON 보고서 저장** (Save JSON report) exports spec and config hashes, QA exit codes, events, usage, and result metadata. Calls missing usage totals are counted separately. Review paths, Agent outputs, and events before sharing.

## Backup and recovery

1. Stop submitting jobs and ensure active jobs are in a safe state. Choose **Supervisor 종료** (Stop Supervisor) and close the desktop to stop data writes.
2. Back up the data directory and target repositories together. If SQLite WAL files remain, keep a copy of them from the same snapshot as the database. Record the original paths because Git Worktree metadata points back to its repository and checkout.
3. Stop the desktop and Supervisor before restoring the original paths. Reconcile external writes that may already have started. Review MCP rollback separately with **롤백** (Rollback).
4. Reopen the app and check recent history, approval state, a read-only job, and the target branch. Manage backup access and encryption at the host level.
