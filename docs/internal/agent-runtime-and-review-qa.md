# Agent runtime and independent review QA

| Area | Status | Evidence |
| --- | --- | --- |
| Explicit OpenCode request and work directory | PASS | The installed CLI received `orchestralocal/fixture-planner` and replied via the loopback API. The unit contract verifies the exact CLI argv, a detached Worktree cwd, and POSIX `PWD` when the parent environment contains a stale directory. |
| Provider and Harness eligibility | PASS | Unsupported writes, untrusted CLI, missing opt-in, unsupported local Codex, local OpenCode with Runtime authentication, and attached MCP requirements are filtered in plan preview and execution. Explicit invalid profiles provide a configuration reason. |
| Hosted provider label | PARTIAL | Workspace events show the requested model and its OpenCode provider prefix. The CLI NDJSON output observed in the installed-binary fixture contained no provider identity for a finished step. Remote identity is available only with separate transport or transcript evidence. |
| Developer output | PASS | The Managed fixture wrote the actual interval utility in a separate Worktree. Files, resulting commit, output artifact and exit code were recorded. |
| Review | PASS | A different model profile used a read-only tool against a distinct Worktree and returned `REVIEW: PASS` after receiving the committed implementation. Explicit rejection and contradictory markers both block QA and keep the Reviewer explanation. |
| Local QA | PASS | `python -B test_utility.py` checked below, inside and above the interval in the QA and candidate Worktrees. Each exit code and tested SHA was persisted. |
| Git approval | PASS | Wrong candidate and stale revision were rejected. Two concurrent approval calls on the valid candidate accepted one request. The disposable target advanced to exactly the approved candidate. |
| Authenticated headless Agent | NOT VERIFIED | No additional hosted model request was authorized for this task. |

The task overview uses the run's persisted route and shows its repository, current stage, requested model and Harness. The Agent view shows recorded activity, observed usage, tool count and execution duration. A rejected review's artifact remains available from the Agent result action. The inline approval identifies Reviewer rejection as a review failure. QA shows configured commands and observed outcomes. A legacy candidate that lacks an approval revision requires fresh validation before an approval can be requested.

A portable test replays the earlier authenticated reply text and its known token counts in the same JSON event shape seen from installed OpenCode. The real installed CLI fixture separately exercises a scoped read, cancellation and provider-error handling with synthetic HTTP responses.

## Proposed separately authorized live test

**NOT VERIFIED and pending separate authorization.** Run on Linux with OpenCode 2.2.7 and a fresh, synthetic Git repository lacking remotes, private files and credentials. Use OpenAI OAuth and exactly `openai/gpt-5.6-luna` for the read-only Planner and independent Reviewer. Use the Managed loopback fixture for the Developer and deterministic local QA for the final candidate.

- Permit at most **two** authenticated inference POSTs, one Planner and one Reviewer, with **zero** automatic retries. Install a process-independent request counter scoped to one test and latch each role before dispatch. Block title generation, background warming, continuation, fallback and refresh attempts in the disposable profile.
- Permit no remote tools or MCP. Provide the model with only the synthetic task brief and, for the Reviewer, the small pre-screened diff. Capture and validate the outgoing body locally with sensitive headers excluded. Require the official certificate-validated OpenAI route and never add a provider override.
- Target no more than **6,500 input tokens and 300 output tokens per role**. Prove that the effective request can enforce these limits in a disconnected rehearsal. Use the operator's approved ChatGPT plan allowance. Stop if model availability, authentication, the limits, or the request count cannot be verified. Stop the run after a failed hosted request.
- Verify model identity and HTTP outcome, role, request count, elapsed time, usage and transcript. Capture Reviewer verdict, candidate SHA, final QA exit code and approval revision. Hold the target branch at its original SHA pending separate explicit approval. The completed deterministic fixture already verifies the positive merge path.
- Keep hosted Developer writes out of this test. Extending to an authenticated Developer would require an approved, verifiably contained write path that preserves the local Runtime and MCP safeguards.

The interactive 2026-11-20 request consumed its authorization. Running the proposal requires a new approval. [Authenticated result](windows-opencode-gpt-integration.md)
