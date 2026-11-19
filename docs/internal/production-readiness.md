# Cross-platform integration and production readiness

See the [release readiness follow-up](release-readiness.md) for the primary desktop decision, expanded outage tests and native installer verification plan.

Verification date: 2026-11-19. The test host was Linux 6.8.0 with Node 24.14.1, Python 3.11.5 and OpenSSH 8.9p1. Windows and macOS results require native execution on those platforms. The runs use temporary data directories, repositories and loopback services. GPU checks, inference and acceleration are outside this run.

The Linux suite passed 33 Python regression tests and 25 TypeScript tests. Each of the three Electron targets ran four Playwright scenarios. The two native Tk scenarios and the live OpenSSH Worker test also passed.

## Architecture and cross-language contracts

The TypeScript core validates and migrates registry/plan inputs, ranks Provider/Harness routes, computes DAG order and readiness on a supplied snapshot, describes Agent states and validates Worker v1 messages. Those helpers are usable without Python or Electron. The Electron application provides a read-only run history. Python continues to execute Provider and Harness calls, acquire leases, persist checkpoints, enforce MCP approvals, manage Git worktrees and own job recovery. The Tk workspace remains the operator interface for submission and approvals. The Python SSH Worker calls the same Store and Supervisor.

| Boundary | Owner and contract |
| --- | --- |
| Job, task, lease, checkpoint, approval and tool-call writes | Python `Store` owns the transaction rules. Tk, the SSH Worker and the Supervisor use that Store from separate connections. SQLite serializes write transactions using `BEGIN IMMEDIATE`. The Supervisor process lock prevents two schedulers from owning the same data directory. |
| DAG and routing preview | TypeScript has pure calculations for consumers. Python revalidates and admits work, uses its own clock and capacity, and owns leases. Cross-language parity checks compare config validation, route ranking, stable DAG/ancestry and admission decisions. |
| Python → Electron main | Python installs additive views `desktop_jobs_v1`, `desktop_tasks_v1`, `desktop_edges_v1`, `desktop_events_v1` and `desktop_qa_v1` in one transaction with marker `desktop_contract.version = 1`. Base `PRAGMA user_version` stays at zero for older clients. Electron opens the database read-only and reads a single SQLite transaction. Views and IPC select explicit fields and omit raw prompts, event payloads, credential fields and checkpoints. |
| Electron main → sandboxed preload | `jobs:snapshot:v1` carries `SnapshotRequest { version, jobId }` and `SnapshotEnvelope { version, projection }`. The handler validates the top frame, channel payload and job ID. The preload checks the response version. Unsupported SQLite projection versions are reported as unavailable. Pre-contract stores can still show raw historical states and QA without exposing an inferred approval candidate. |
| Desktop SSH → headless Worker | Existing request/response protocol v1 runs over OpenSSH stdio. Python and TypeScript use pinned host keys and validate message identities and event cursors. Status reads the run, tasks and event page in one committed snapshot. Approval responses include an additive QA revision. A matching SHA is still accepted for older clients; updated operators submit both the SHA and QA revision. |
| OS integration | Tk and the Supervisor call the native terminal and process adapters. Linux uses a POSIX PTY, process groups and a controller-lifetime pipe. Windows has separate ConPTY and Job Object implementations. Node process/SSH adapters and Electron packaging remain at platform boundaries. |

The QA projection ignores results from earlier attempts once the Supervisor starts verification again, recovers to queued, or accepts a retry. The Agent projection derives terminal task presentation from Python execution policy. Electron renders the projected fields directly.

The IPC implementation touches `electron/main.ts`, `electron/preload.ts`, `electron/legacy-store.ts`, `src/contracts.ts` and `packaging/electron-builder.json`. The schema-upgrade and IPC-shape tests in `legacy-store.test.ts` cover migration and validation. The Playwright suite also probes renderer isolation and runs against the packaged IPC bundle.

## State consistency and fault injection

| Scenario and result | Changed implementation and evidence |
| --- | --- |
| Supervisor hard exit and restart | A POSIX guard starts commands in a payload process group and closes that group on controller exit, cancellation or command completion. Windows uses Job Object kill-on-close. `orchestra/platform/processes_posix.py`, `orchestra/platform/guard_posix.py` and the application entry point implement POSIX cleanup. `test_controller_hard_exit_terminates_a_real_descendant` and `test_timeout_terminates_a_real_descendant` use real subprocesses. `test_supervisor_crash_resumes_durable_checkpoint` kills and restarts the real Supervisor against fixture inference. |
| Electron hard exit | A real QA subprocess waits on a release marker while Electron is killed. The same Supervisor PID finishes attempt one. Source and packaged Playwright runs reopen Electron and read the success and QA check. See `desktop.spec.ts` and `legacy_fixture.py`. |
| SSH disconnect and Worker hard restart | The loopback test opens an actual interactive SSH channel, submits a detached job, closes SSH and reconnects. It kills the Worker Supervisor, observes lease recovery and attempt two, and checks that the first command never writes its scheduled marker. Submitting the same request ID again returns the same run, including after completion. Both Python and TypeScript read the result through OpenSSH. See `smoke_workspace_ssh.py`, `remote.py` and `store.py`. |
| Duplicate submits and cancellation | `test_concurrent_remote_submissions_and_claims_have_one_identity` races independent SQLite connections. `test_cancel_persists_when_completion_is_already_in_flight` injects cancellation between claim and completion and verifies one authoritative terminal result and no published candidate. |
| SQLite interrupted write and migration | The writer process is killed with job and event writes still uncommitted. A parallel reader sees the previous snapshot. Reopen, WAL integrity check and a new transaction succeed. The additive migration rollback/concurrent-open test preserves the original request ID and checkpoint. Node tests exercise old, supported and unsupported projections and committed reads. See `desktop_contract.py`, `store.py`, `test_platform_contracts.py` and `legacy-store.test.ts`. |
| Mixed Worker snapshots during concurrent commits | One WAL snapshot now spans state, tasks and events. A regression injects a real concurrent SQLite commit after the first read and checks that the response stays on the original snapshot. See `Store.status_snapshot` and `test_worker_snapshot_is_one_transaction_during_concurrent_commit`. |
| Uncertain external writes | The MCP fixture records an effect and closes the HTTP connection before replying. Recovery keeps its `started` journal row and the Store refuses automatic retry. Concurrent approval uses one transaction and one decision. See `test_lost_mcp_response_after_effect_blocks_automatic_retry` and `test_concurrent_tool_approval_is_consumed_once`. |
| Failed integration QA and approval staleness | Python captures exit 7, keeps the job failed and refuses approval. The state and exact candidate SHA must match. Updated clients also compare the QA revision in the same transaction. A test rejects the right SHA with an old QA revision, advances the target branch in Git, attempts approval with the current revision and verifies the branch and working tree are intact. See `supervisor.py`, `store.py`, `desktop.py`, `remote.py`, `workspace_remote.py`, `test_orchestra.py` and `desktop.spec.ts`. |

The fault tests cover process interruption and transaction rollback. A power loss, a shared network filesystem, separately detached descendant sessions and arbitrary external effects from QA commands require separate verification. The MCP call journal specifically guards ambiguous MCP writes. A QA command is an operator-approved program and may run again during recovery. Git's checked-out branch still has a small window for an external writer between the final branch checks and fast-forward.

## User workflow and Harness evidence

`smoke_workspace_flow.py` drives the real Tk workspace from a blank data directory. It registers a local Git project, checks the local environment without GPU access, uses the Provider Wizard to fetch and save a model, selects the Managed Harness and reviews the dependent Developer/Reviewer DAG. It submits through the UI, observes a live running Agent, inspects events and changed files, executes real integration QA, declines once, then approves the exact candidate and verifies the Git fast-forward and terminal output. The model and API replies are scripted. The native widgets, subprocesses, SQLite state, tools, QA and Git are real. The test supplies answers to the native directory picker and confirmation dialogs. In guided local plans, the UI now filters Harness options to the selected model, and the Wizard identifies which integrations are currently discovery-only. See `workspace_forms.py`.

| Harness | Local evidence | External authenticated inference |
| --- | --- | --- |
| OpenCode 2.2.7 | Installed binary starts. The Supervisor selects the expected model, observes an actual worktree read, persists the result, cancels an in-flight request and records a failed API call. The Harness now accepts the installed CLI's v-prefixed version and passes XDG paths through the process adapter. See `harness.py`, `processes.py`, `harness_inventory.py` and `smoke_installed_opencode.py`. | NOT VERIFIED. The API fixture does not check a hosted account or real model. |
| Codex 0.170.0 | Installed binary starts. The CLI reports stored credentials through its status command, which checks credential presence. The app has an attached adapter. [Official CLI reference](https://learn.chatgpt.com/docs/cli/reference#codex-login) | NOT VERIFIED. The host's shared CLI profile has user-level instructions. A dedicated smoke account and profile are needed to exercise the complete production route with only synthetic input. |
| Gemini CLI 0.66.0 | Installed binary starts during the native run. The restricted sandbox probe could not start Snap. The app offers discovery. | NOT VERIFIED. Execution adapter and end-to-end testing are pending. |
| Antigravity 1.5.12 | Installed binary starts. The app offers discovery. | NOT VERIFIED. Execution adapter and end-to-end testing are pending. |
| Managed | Live Python engine against scripted HTTP inference and MCP endpoints, with real tools, Git, cancellation and failure recovery. | NOT VERIFIED. A provisioned CPU-compatible or hosted test endpoint is needed. |

The optional Harness probes print statuses and versions only. They do not dump provider output, credentials or session data.

## Compatibility matrix

**PASS** means executed successfully on the stated host. **FAIL** means a probe executed and failed in that environment. **NOT VERIFIED** means the relevant environment or capability was not exercised. The fixture and integration columns identify what actually ran.

| Feature | Linux | Windows | macOS | Fixture evidence | Real integration evidence and remaining blocker |
| --- | --- | --- | --- | --- | --- |
| Provider/Harness/MCP/DAG/Agent/config and Worker core | PASS | NOT VERIFIED | NOT VERIFIED | Pure policies, cross-language golden cases and scripted protocols | Native OS dependencies are unnecessary for the TypeScript-only suite. Hosted providers need their own integration runs. |
| SQLite projection/IPC, migration, crash and concurrent readers | PASS | NOT VERIFIED | NOT VERIFIED | Fixture runs, forced shutdown and injected ordering | Real Node SQLite, Python SQLite, WAL and local files. Native test runs still needed for Windows and macOS. |
| POSIX PTY, process group, foreground and background recovery | PASS | N/A | NOT VERIFIED | Scripted workloads and abrupt termination | Linux subprocess, PTY and Supervisor exercised. macOS PTY/process check pending. |
| ConPTY, Job Object, file paths and Python Supervisor | N/A for Win32 APIs | NOT VERIFIED | N/A for Win32 APIs | Win32 path policy and simulated reparse-point check run on Linux. The same tests include native PTY/Job Object paths when run on Windows. | Windows run needed, including access control and reparse-point behavior on NTFS. |
| OpenSSH Worker, detached job and reconnect after Supervisor loss | PASS | NOT VERIFIED as client | NOT VERIFIED as client | Temporary keys, QA markers and local server | Actual Linux OpenSSH client/server, Python Worker and TypeScript client. Windows/macOS SSH clients to an independent Linux Worker are pending. |
| Tk full operator workflow and terminal | PASS | NOT VERIFIED | NOT VERIFIED | Scripted model API and operator dialogs | Native UI, real job, worktree, terminal, QA and approval on Linux. |
| Electron history and restart | PASS | NOT VERIFIED | NOT VERIFIED | QA marker and fixture plan | Actual Electron processes, TypeScript/Python contract and independent Python execution. |
| Native packaging | PASS | NOT VERIFIED | NOT VERIFIED | Same Playwright tests per available build | Linux AppImage extract-and-run and unpacked preview pass. Windows unpacked/NSIS and PyInstaller need native verification. macOS packaging is not configured. |
| OpenCode subprocess and version | PASS | NOT VERIFIED | NOT VERIFIED | Scripted API | Installed CLI, worktree read, cancellation, HTTP error and persisted history. Hosted authenticated execution pending. |
| Codex startup and credential presence | PASS | NOT VERIFIED | NOT VERIFIED | None for startup | Installed CLI. Dedicated test account needed for inference and tool behavior. |
| Gemini CLI startup | PASS in native run | NOT VERIFIED | NOT VERIFIED | None | Installed CLI version observed. App has no execution adapter. |
| Antigravity startup | PASS | NOT VERIFIED | NOT VERIFIED | None for startup | Installed CLI version observed. App has no execution adapter. |
| GPU | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED | None | Excluded for this run at the user's request. |

## Packaging and architecture recommendation

| Concern | A. Electron/TypeScript with Python Supervisor | B. Electron/TypeScript with native TypeScript Supervisor |
| --- | --- | --- |
| Portability and dependencies | Portable TS core plus mature Python execution path. Electron preview runs independently for read-only history. Full execution needs Python, Git, plus platform terminal dependencies for Tk. | One implementation language and potentially one packaged runtime. Still needs Git, SSH and native process/PTY support. A detached headless executable or Node runtime is still required when Electron is absent. |
| Packaging | Versioned SQLite boundary allows independent distribution and rollback. Windows legacy desktop packaging, Windows Electron installation and macOS require native evidence. | Bundling looks simpler after parity, but platform tooling, native modules and Worker delivery remain separate concerns. Validate Node SQLite distribution and runtime versions before replacement. |
| Recovery and operations | Existing persisted leases, scopes, approvals, checkpoints, MCP journal and Git recovery were exercised on Linux. | Reimplement and demonstrate crash-consistent delivery, write guards, existing checkpoint decoding, lease takeover and Git recovery before enabling writes. |
| Maintenance and testability | Keep parity tests on portable previews and execute the critical side effects once in Python. Keep one writer policy. | Removes cross-language policy drift after retirement. During migration, dual mutable implementations carry an ownership and recovery risk. |

**Keep A for production execution.** The TypeScript core and projection are already independently testable, and the current Python recovery path has execution evidence. Revisit B after an independent Worker builds on every target and a rollback exercise proves that existing records, in-flight work, approvals and tool journals survive migration. Never enable two scheduler implementations against the same live queue.

## Reproduction and remaining work

`npm run verify -- --core-only` runs the TypeScript core without Python. `npm run verify -- --ui --ssh --package --harness` adds the native UI and packaging, local Linux OpenSSH fixture, and optional installed CLI checks. Install `requirements-desktop.txt` first and provide a display or Xvfb. The Windows workflow runs the shared suite and Windows packaging without the Linux sshd fixture. The commands use software rendering and do not query GPU metrics.

1. Run the Windows workflow and verify the native installer, ConPTY, Job Object, path/permission behavior and recovery. Add native macOS runs before claiming support.
2. Run Windows and macOS OpenSSH clients against a Linux Worker, and exercise actual network interruptions outside loopback.
3. Provision dedicated synthetic credentials and endpoints to verify authenticated model selection, prompt execution, tools, cancellation, errors and history on supported providers.
4. Decide whether to add Gemini CLI and Antigravity execution adapters based on their supported noninteractive contracts. Preserve clear discovery-only status until then.
5. Verify Git race behavior under competing processes, arbitrary QA replay policies, long-running WAL/backups and recovery from power or storage loss. Consider adding a stricter protocol revision with mandatory approval generation after older clients are retired.
