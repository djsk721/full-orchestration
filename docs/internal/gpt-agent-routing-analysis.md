# GPT agent routing analysis

This assessment covers `feature/orca-workspace` at source commit `08b1d3d` plus the local working-tree changes. The Python Supervisor remains the execution and approval authority. The TypeScript desktop reads execution data, validates portable plan structure, and previews eligible routes.

## Execution path

| Stage | Implementation | Evidence and boundary |
| --- | --- | --- |
| Task intake and planning | The Tk wizard calls `draft_plan`; its existing node editor controls role, predecessors, model, Harness, QA and scopes. `plan_routes` validates each route before submission. | The guided change template creates Developer and Reviewer nodes. An operator can add Planner and command-only QA nodes in the existing editor. Natural language fills node prompts; the operator-reviewed plan fixes topology and permissions. |
| Submission | The Workspace calls `Store.submit` with the plan and registry snapshot. SQLite atomically creates the run, task rows and first event. | An identical in-flight submission reuses the existing run ID. Remote submission also records a request receipt. |
| Scheduling | `Supervisor` owns the lease and heartbeats. `JobRunner` evaluates topological ancestry and `ready_tasks` under the configured concurrency limit. | A successor runs only after its ancestors succeed. Results and checkpoints live in SQLite. |
| Planning handoff | `JobRunner` reads successful direct Planner checkpoint answers for a Developer. | OpenCode's CLI output reaches the actual Developer prompt as bounded advisory text. Scope and settings stay with the approved plan. |
| Agent routes | `runtime.routes` matches role, explicit model and Harness, Runtime context and permissions. The runner resolves the executable, probes a local Runtime and persists the request metadata. | A pinned profile cannot fall through to a different profile. Compatible automatic routes retain the existing ranking. Python and TypeScript apply the same Attached eligibility constraints. |
| Tool execution | `Managed` executes scoped file operations and publishes authorized MCP tools. `attached` starts a trusted CLI with an explicit model and isolated OpenCode permission config. | Managed validates the model in Runtime responses. MCP writes require approval and persist their effect checkpoints. Attached CLI logs provide a requested model and observed activity. Native hosted identity still requires a provider transcript or transport observation. |
| Worktrees and review | `GitGate.worktree` builds a private detached node Worktree and applies ancestor commits. A Reviewer receives the bounded, scoped changed-path list and can read the inherited versions. | The Reviewer's decision must end with a valid, unambiguous verdict. Rejected or malformed decisions keep their original explanation as an artifact. |
| QA and integration | Command-only QA nodes run native commands. Integration creates a distinct Worktree from the base and verified node commits, runs final QA and stores its exact commit and exit code. | Integration runs even after a command-only QA node passed. The integration candidate receives a new approval revision only after final QA passes. |
| Git approval | `Store.request` gates the submitted candidate and revision against current evidence. The Supervisor serializes same-repository integration and `GitGate.apply` rechecks the candidate, Worktree, target base, and QA. | Concurrent approvals for one candidate consumed one revision in the fixture. A missing revision and mismatched QA commit are rejected. |
| Desktop representation | The Workspace reads persisted task and event snapshots for its DAG, overview, terminal-related logs, QA and approval views. | A detached Agent log describes recorded events. Its Worktree terminal opens a separate interactive shell after the run. |

## Agent routing matrix

| Agent or route | Model source | Effective request | Worktree permissions and platform control |
| --- | --- | --- | --- |
| Planner or Reviewer with hosted OpenCode | Attached registry profile and saved CLI credentials | Exact provider-qualified request such as `openai/gpt-5.6-luna` | Trusted executable and an explicit unverified-Runtime opt-in. Read-only with CLI permissions. This execution path has no authenticated Supervisor E2E result. |
| Planner using local OpenCode in the E2E | Profile `planning`, OpenCode Harness `planner-cli`, loopback Runtime | CLI flag `orchestralocal/fixture-planner`; HTTP body model `fixture-planner` | Read-only Planner. Actual installed OpenCode started and returned a plan through its normal JSON event format. |
| Developer using Managed | Profile `implementation`, OpenAI-compatible loopback Runtime | `fixture-developer` checked in the Runtime response | Scoped `write_file` to `utility.py`. Git rejects changes outside declared paths. |
| Independent Reviewer using Managed | Profile `review`, same fixture endpoint with a distinct model ID | `fixture-reviewer` checked in the Runtime response | Read-only. Actual observed tool output contains the Developer's committed implementation. |
| Developer using verified local OpenCode | Runtime-backed OpenCode profile with `allow_write` | CLI flag `orchestralocal/<model>` and an explicitly configured local endpoint | Existing trusted local OpenCode contract. A hosted profile, Codex, and routes that require Managed MCP cannot take this write path. |
| QA | No model | Exact approved argv in the node and integration Worktrees | Exit code and tested commit persisted. |
| Integration | No model | Git and the configured final QA commands | Explicit approval required to update the target branch. |

The prior startup-model picker already supported an explicit OpenCode model in interactive Mini. Supervisor Agents use `opencode run --standalone --format json --model …` on OpenCode 2.x. The Linux terminal transcript verifies the actual OpenAI account and model once. The loopback test verifies the Agent route, independent review and Git workflow. A hosted model that accepts and responds to the same headless Agent invocation remains **NOT VERIFIED**.

A local-only regression replays the saved GPT response text and token counts in the installed CLI's observed JSON event shape. This verifies parser compatibility with the response content. It does not treat the interactive session database as a headless CLI trace. [Prior authenticated evidence](windows-opencode-gpt-integration.md) · [Workflow evidence](multi-agent-orchestration-e2e.md) · [Agent runtime and review](agent-runtime-and-review-qa.md)
