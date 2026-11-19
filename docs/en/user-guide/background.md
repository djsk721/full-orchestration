# Background Execution

<!-- feature: background IMPLEMENTED -->

## Concept

Foreground jobs are tied to a live desktop session. With Background Execution, a separate Supervisor running as the same user continues after you close the UI. It stores state and checkpoints in local SQLite.

## Desktop workflow

1. Enable execution after closing the app under **Settings → Execution and notifications**.
2. In **새 작업** (New job), add `"background": true` at the plan's top level and submit it.
3. Check the mode and state in the dashboard. Close and reopen the window to see jobs, history, and events from the same data directory.
4. Use **중지** (Stop) for active jobs and **재시도** (Retry) for failed jobs. **Supervisor 종료** (Stop Supervisor) is a separate action that can interrupt background work.

## Example

Submit the command-only QA job from [Getting started](getting-started.md) in background mode to check the history. Inspect the mode and `qa.result`, reopen the app, and select the same job. A longer read-only job can continue in the Supervisor while the window is closed.

## Troubleshooting

- If the job is marked foreground, verify `background` in both the registry and the plan. Submitted jobs keep their configuration snapshot.
- After a crash, wait for the new Supervisor to detect the expired lease. Look for `job.recovered`. An external write with an unknown outcome or an interrupted Attached CLI may require operator review before another run.
- Optional notifications appear while the UI is open. View execution history in the dashboard or use **JSON 보고서 저장** (Save JSON report).

## Advanced settings

Writing Git files in the background also requires `settings.allow_background_write`. For Supervisor startup at login, build the Windows executable and follow the Task Scheduler procedure in [Operations](../admin-guide/operations.md). Plan for process interruptions during sleep, sign-out, and reboot.
