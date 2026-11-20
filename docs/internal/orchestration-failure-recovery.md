# Orchestration failure and recovery

The checks below use disposable repositories, local process fixtures and loopback servers. External model authentication was deliberately kept out of this test batch.

| Scenario | Status | Observed behavior |
| --- | --- | --- |
| Invalid Provider | PASS | Registry validation rejected a model whose Provider was absent. |
| Invalid or unavailable model | PASS | A malformed OpenCode selector was rejected before launch. Managed Runtime tests reject an unobserved or mismatched model. Explicit routes do not switch to another model. |
| Invalid executable | PASS | A missing attached executable failed with an actionable filename and recorded no uncertain Agent-start checkpoint. |
| Authentication error handling | PASS | Actual OpenCode received a loopback HTTP 401. The Supervisor classified it as an authentication or model entitlement problem and excluded the raw error body. Actual hosted headless authentication remains NOT VERIFIED. |
| Agent process exits or is terminated | PASS | The installed CLI error/cancel smoke and native process contracts covered child cleanup, errors, cancellation and unexpected controller exit. The parser gives failures precedence over any earlier success-looking text. |
| Developer fails | PASS | Deterministic execution failure left the Reviewer at attempt zero, with no target branch change. |
| Reviewer rejects or gives an ambiguous verdict | PASS | The persisted explanation remained available and the verdict was failed or invalid. QA did not start and Git approval was rejected. |
| QA fails | PASS | Real nonzero commands produced exit-code evidence and no eligible candidate. |
| Explicit retry after failed integration QA | PASS | An operator retry reran QA after the fixture dependency recovered. Successful Developer and Reviewer checkpoints were preserved and their attempts stayed at one. The new evidence bound QA to the new candidate. |
| Supervisor crashes and restarts | PASS | The existing process test kills the supervisor, expires its lease, and resumes a Managed checkpoint from the same SQLite state. The interrupted Attached process retains the conservative no-replay checkpoint. |
| SSH interruption on Linux loopback | PASS | The real pinned OpenSSH Worker test reconnects, rereads the existing cursor, and verifies job completion and receipt deduplication. |
| Candidate or Worktree changes | PASS | Dirty candidate Worktrees and QA records for a different commit block approval. |
| Target branch moves | PASS | Integration fails and leaves the moved checkout and its files intact. |
| Stale or absent approval revision | PASS | Stale and absent revisions are rejected, including snapshots without an assigned revision. Concurrent approval of a single valid revision consumes it once. |
| Cancellation | PASS | Native CLI cancellation, local and SSH Worker cancellation, and the concurrent cancellation contract preserve a single final state. |
| MCP write recovery | PASS | Authorized writes retain effect receipts. A dropped response or timeout leaves the effect uncertain and blocks automatic retry. |
| Native Windows behavior on the current tree | NOT VERIFIED | Windows PATH/PATHEXT, ConPTY, Unicode input and process cleanup require a Windows host. |

A missing or rejected review token is an execution failure, even when the CLI exits successfully. The test keeps failed review output as an artifact and the Workspace distinguishes that failure from QA failure. For a detached Attached CLI that may have reached the provider, the recorded checkpoint requires an operator decision before any possible replay. A failure observed before launch can be retried without running a previously started model request.

To repeat the failure contracts and Linux SSH scenario:

```bash
python -m unittest discover -s tests -p 'test_orchestra.py' -v
python -m unittest discover -s tests -p 'test_platform_contracts.py' -v
npm run verify -- --ui --ssh
```

See [the workflow evidence](multi-agent-orchestration-e2e.md) and [the Windows procedure](windows-opencode-gpt-integration.md).
