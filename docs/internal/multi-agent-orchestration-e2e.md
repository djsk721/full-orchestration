# Multi-agent orchestration end-to-end verification

**PASS on Linux with deterministic model responses.** The real Supervisor ran the DAG, installed OpenCode 2.2.7 executed the Planner, Managed tools changed a real Git Worktree, the independent Reviewer read the committed implementation, and local QA and an explicit approval integrated the candidate into a temporary repository. The Linux namespace contained only loopback. The fixture received eight model requests. External inference requests were zero.

## Recorded run

| Evidence | Value |
| --- | --- |
| Execution ID | `5ec605e4c95c47ed9aedb7e4febeb2e9` |
| Disposable repository | `/tmp/orchestra-multi-agent-qbmxnhbd/disposable` |
| Target and base | `main` at `fa97447051276786a3ae36e3734579acc9f82507` |
| Worktree parent | `/tmp/orchestra-multi-agent-qbmxnhbd/data/worktrees/5ec605e4c95c47ed9aedb7e4febeb2e9` |
| DAG order | `plan → develop → review → qa`; each node succeeded once. |
| Job state history | `QUEUED → PREPARING → RUNNING → VERIFYING → AWAITING_APPROVAL → MERGING → MERGED` |
| Changed file | `utility.py` implemented `clamp(value, lower, upper)` as `min(max(value, lower), upper)`. |
| Independent review | `REVIEW: PASS` after reading the committed Developer file through a read-only tool in the review Worktree. |
| Local QA | `python -B test_utility.py` exited 0 on `e23dd5d34520f69fa78443228212b9e6b1626f25` in 0.106 s. |
| Integration QA | The same command exited 0 on `df4be0b99202c7913a7821ae7cfbbeb1518fb73f` in 0.101 s. |
| Candidate SHA | `df4be0b99202c7913a7821ae7cfbbeb1518fb73f` |
| Approval revision | `1773562df9f54610b07253cef795693e` |
| Merge result | The target stayed at its base before approval. One concurrent approval succeeded, the other was rejected, and the temporary branch advanced to the exact candidate. Reopening SQLite retained the `MERGED` state and evidence. |

| Worktree | Agent ID | Provider profile | Model supplied to execution | Harness |
| --- | --- | --- | --- | --- |
| `plan` | `planner/plan` | `planning` | `orchestralocal/fixture-planner` | `planner-cli`, installed OpenCode |
| `develop` | `developer/develop` | `implementation` | `fixture-developer` | Managed |
| `review` | `reviewer/review` | `review` | `fixture-reviewer` | Managed |
| `qa` | `qa/qa` | N/A | N/A | Command-only |
| `_integration` | Supervisor | N/A | N/A | Git and final QA |

The plan came from the Workspace's natural-language change template. The test added Planner and QA nodes using the same plan format available in the existing node editor. The fixture refused Developer calls that did not contain the Planner's actual note. It refused a successful review until the read tool returned the new implementation. The Workspace integration smoke separately exercised the native Tk form, persisted DAG, Agent panel, explicit route display, QA command, changed file, and the approval dialog.

The Linux regression set passed 114 checks, including 67 Python, 26 TypeScript, six Tk, and 15 Electron cases. Three Windows-only cases skipped. The OpenSSH loopback Worker, installed OpenCode smoke, and full DAG above passed separately. The Linux terminal benchmark delivered all 8,000 numbered rows in each of nine streams with zero missing or duplicated rows and no leaked processes.

## Reproduce

On Linux with Git, Python, Tk dependencies and OpenCode installed, run the model fixture in a network namespace with only loopback:

```bash
unshare -Urn sh -c '
  ip link set lo up &&
  python tests/smoke_installed_opencode.py &&
  python tests/smoke_multi_agent_orchestration.py --evidence /tmp/orchestra-multi-agent-e2e.json
'
npm run verify -- --ui --package --ssh
```

The smoke creates and removes its own Git repository and captures the evidence JSON when requested. Git operations affect only that fixture. Authenticated headless GPT E2E and native Windows execution on the current source remain **NOT VERIFIED**. The previously authorized interactive GPT request is documented separately. [Authenticated evidence](windows-opencode-gpt-integration.md) · [Routing analysis](gpt-agent-routing-analysis.md) · [Failure and recovery](orchestration-failure-recovery.md)
