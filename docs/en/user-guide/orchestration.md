# Multi-Agent Orchestration

<!-- feature: orchestration IMPLEMENTED -->
<!-- feature: git-gate IMPLEMENTED -->

## Concept

A job's `tasks` form a directed acyclic graph (DAG). The local Supervisor schedules each node as an Agent task or as command-only QA. You define the roles and dependencies. Planner and Diagnostic are task roles. Planner output stays in the result, and you can use it to design later jobs.

## Desktop workflow

1. In **새 작업** (New job), select an existing Git repository and target branch. In `tasks`, set each node's `id`, `role`, `prompt`, `acceptance`, and `depends`.
2. Put writable repository-relative files or directories under the Developer node's `paths`. Overlapping write scopes require a dependency. Include job-level `qa` for any job with write paths.
3. Choose **작업 제출** (Submit job) and monitor each Agent's route, state, attempt, and events in the dashboard. Use **결과 폴더 열기** (Open results folder) for Agent output and **JSON 보고서 저장** (Save JSON report) for the execution summary.
4. For a change that passes integration QA, select **병합 승인** (Approve merge) and inspect the target branch and candidate SHA. Approval queues the fast-forward merge.

## Example

Use **JSON 열기** (Open JSON) to load the [Windows job example](https://github.com/djsk721/full-orchestration/blob/develop/examples/plan.windows.json). The Developer can only write `overview.md`. Its Reviewer has `depends: ["documentation"]` and reviews that commit in a separate Worktree. The final line must be `REVIEW: PASS` to proceed. Integration QA checks the file size. Set the path and branch of an experimental repository before running it.

## Troubleshooting

- If the plan is rejected, look for missing task IDs, dependency cycles, overlapping parallel write scopes, or missing integration QA.
- Transient errors can be retried within the configured limit. For a failed job, fix the cause and choose **재시도** (Retry). Successful nodes are retained. An external write with an unknown outcome blocks resumption.
- For a QA failure, check the command index and exit code. If the branch moved or its Worktree became dirty before merge, submit a job to validate against the new base.

## Advanced settings

The available roles are `planner`, `developer`, `explorer`, `reviewer`, `qa`, and `diagnostic`. A `qa` node with QA commands and no explicit Model or Harness runs without inference. See [Configuration and API](../admin-guide/configuration.md) for `read_paths`, `min_context`, configuration snapshots, and limits.
