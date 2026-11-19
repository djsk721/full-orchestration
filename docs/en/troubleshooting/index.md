# Troubleshooting

## Installation and startup

| Symptom | What to check |
| --- | --- |
| No window opens | Run `py -3 -m tkinter`. Check Git on PATH and Python 3.11 or later. |
| Supervisor stays in the connecting state | Verify the data directory, choose **Supervisor 시작** (Start Supervisor), and look for updates to `supervisor.json`. |
| Gateway port error | Check for a `gateway_port` conflict and save your settings. Restart the Supervisor to pick up environment changes. |

## Jobs and verification

| Symptom | What to check |
| --- | --- |
| Runtime validation fails | Check `runtime.snapshot` and `route.failed` in the dashboard. [Providers and models](../user-guide/providers.md) |
| Job awaits tool approval | Review the node and arguments under **도구 승인 검토** (Review tool approval). Check the upstream system for external writes with an unknown outcome. [MCP connections](../user-guide/mcp.md) |
| Verification or merge fails | Inspect `qa.result`, the Reviewer's final line, the target SHA, and the Worktree state. [Running jobs](../user-guide/orchestration.md) |
| Job stops after closing the app | Check the foreground session and the background flags at submission time. [Background Execution](../user-guide/background.md) |

## What to include in a report

Record the launch method and OS, steps to reproduce, job state, relevant events, and QA exit codes. Use **JSON 보고서 저장** (Save JSON report), then inspect the report for local paths, configuration, CLI output, and private data before sharing. Keep the full registry and data directory private.
