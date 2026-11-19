# Managed Harness

<!-- feature: managed-harness IMPLEMENTED -->

## Concept

The Managed Harness lets the app control task Context, tool policies, repetition limits, and checkpoints. Runtime ownership (`managed` or `attached`) is configured independently. You can pair the Managed Harness with a local server you already run.

## Desktop workflow

1. Under **설정 → 고급 JSON** (Settings → Advanced JSON), include `managed` in the Model's allowed Harnesses and link the Model to its local Runtime.
2. In **새 작업** (New job), set the node's `harness` to `managed`. Use `read_paths` to narrow reads and `paths` to limit Developer writes.
3. In **작업 대시보드** (Job dashboard), inspect `runtime.snapshot`, `context.compaction`, `task.checkpoint`, and `model.usage` as they appear. Use **도구 승인 검토** (Review tool approval) to inspect and approve or deny an external write's arguments.
4. For Git changes, use a separate Reviewer node and integration QA. Git merge and external tool calls have their own approval steps.

## Example

Add `"harness": "managed"` and `"read_paths": ["README.md"]` to the default Explorer node, then ask the Agent to identify the entry point. Check the output to see whether it describes the allowed file. The task can run with no write paths or external tools.

## Troubleshooting

- If the read-only tool-calling probe fails, check whether the Model and server expose the required tool-calling format.
- If a repeated call is rejected or the round limit is reached, narrow the task and select only its required tools. If the tool schema changed after a checkpoint, submit a new job.
- If an approved external write was interrupted, inspect its outcome upstream. A call that began and has an unknown outcome will block automatic replay.

## Advanced settings

`max_rounds` defaults to 30. A Model's `token_budget` checks observed usage and constrains output length. Budget validation requires usage data from the Runtime. Context compaction uses application estimates and conversation excerpts. See [Operations](../admin-guide/operations.md) for handling Session logs and raw checkpoints.
