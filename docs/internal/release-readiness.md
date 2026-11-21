# Release readiness and UI responsibilities

For the latest terminal performance, regression and Windows preparation results, see [Workspace production readiness](workspace-production-readiness.md).

## Release candidate assessment

**Overall verdict: BLOCKED.** The Linux candidate has local regression and end-to-end evidence. Windows remains a required deployment target and lacks native NSIS, ConPTY and Job Object evidence for this checkout. The authorized Codex smoke still needs a dedicated test profile and concrete model ID. macOS is outside the declared release scope.

- Tk remains the primary operator app. The merge review shows the integration diff's file names, current QA results, QA cycle, full SHA, branch and eligibility. For cycle-aware records, Python requires the current cycle and exact SHA in the same transaction. Pre-cycle records can still use their exact SHA with recorded successful QA.
- Electron remains a read-only history companion. History and task searches, status filters and the last successful retrieval time use the existing projection. During a failed read, the visible snapshot carries its original timestamp and a cached label.
- The Windows test script now checks installed startup, uninstall, reinstall and SHA-256 identity of the SQLite database and both configuration files in a clean test account's default Python data directory.

[Platform compatibility](platform-compatibility.md) · [Windows native verification](windows-native-verification.md) · [Provider integration evidence](provider-integration-report.md) · [Final QA report](final-qa-report.md)

## Previous stabilization baseline

This work continues from local commit `6c8bb8d` and its [production verification baseline](production-readiness.md). The execution host was Linux. The release assessment distinguishes native execution, loopback service fixtures, and external-provider evidence.

The complete Linux suite passed 38 Python tests with one Windows-only test skipped, 25 TypeScript tests, four Playwright tests on each of the source, unpacked and AppImage targets, both Tk scenarios, the OpenSSH outage scenario, and the installed OpenCode loopback workflow. The CLI inventory also observed startup for Codex 0.170.0, Gemini CLI 0.66.0 and Antigravity 1.5.12.

## Tk and Electron

**Tk remains the primary operator app.** `ModelOrchestration.pyw` launches the Tk workspace or the detached Supervisor. Project registration, Provider and Model profiles, guided plans, DAG review, local and SSH submission, Agent and terminal control, MCP and SSH configuration, and approval decisions are available through Tk. These entry points use the existing Python validators, Store and Supervisor.

**Electron remains the execution history companion.** Its sandboxed renderer receives typed `jobs:snapshot:v1` replies. The main process reads Python-owned SQLite views from a read-only transaction. Electron can observe the workflow, Agent stages, recent structured events and integration QA while the original execution continues independently. Its UI exposes no submission, shell, configuration, cancellation or approval IPC. The TypeScript core continues to provide portable configuration, route, DAG and Worker contracts. Python owns mutable operation rules, leases, recovery and Git approval. This keeps a single authority when both UIs use one data directory.

An Electron primary release would require a separately versioned mutation API, authority for local and remote operator presence, and parity for project and Provider setup, submission, terminal sessions, cancellation, and approvals. Native workflow evidence and a defined Tk migration path are needed before changing the primary app. A TypeScript Supervisor offers no measured benefit in this work.

The Tk layout smoke visits Home, projects, Agents, terminal, workflow graph, settings, MCP, SSH and run history at two window sizes. The guided workflow verifies a local project, the Provider wizard and Git approval through the UI. MCP, host trust and SSH Worker outage behavior have separate backend and transport evidence.

Linux execution screenshots use temporary test data. [Electron history with filters and QA](../assets/screenshots/electron-release-history.png) · [Tk change and QA summary before approval](../assets/screenshots/tk-release-approval.png)

## Changes and verification

| Area | Implementation and files | Evidence and limits |
| --- | --- | --- |
| Electron history workflow | `apps/desktop/src/main.tsx` and `styles.css` add labeled search by title or ID, state filtering, distinct empty/loading/missing states and a clearly labeled last snapshot when a refresh fails. The existing read contract and renderer authority stay the same. | `desktop.spec.ts` uses a real SQLite version mismatch to check retention and recovery, tests both filters, updates live events and restarts Electron. It exercises the same workflow in source, unpacked and AppImage builds. |
| Tk workspace and approval | `orchestra/desktop.py` summarizes recorded changes, passed integration QA and the candidate branch/SHA. Its event viewer follows the tail while the operator is at the bottom and retains the scroll position while they review older entries. Task stages use the existing Python projection policy. | `smoke_workspace_flow.py` checks the summary during a real job and verifies the resulting Git fast-forward after approval. The model endpoint supplies scripted replies. Declining the confirmation leaves the candidate pending. |
| Windows installer | `scripts/qa/verify-windows-installer.ps1` adds fresh NSIS installation, installed-app Playwright verification and silent removal. `.github/workflows/cross-platform.yml` includes the step after the Windows unpacked build. | NOT VERIFIED. A native runner was unavailable for this checkout and the revised workflow was kept local. Use a disposable Windows runner. Installer signing, enterprise install policies and the Tk PyInstaller bundle need separate evidence. |
| Native terminal and filesystem | `smoke_workspace_ui.py` opens two independent terminals, checks separate output, closes a running second command and confirms that the first remains interactive. `test_platform_contracts.py` adds a real Windows directory junction case. `test_orchestra.py` exercises a real Git Worktree with a Unicode, space-containing path longer than 260 characters and records a skip if the Windows host disables long paths. | Linux terminal and long-path cases executed. Windows junction, ConPTY, ANSI behavior, resize, process cleanup and NTFS behavior need native runner results. The existing Job Object tests remain in the shared suite. |
| SSH transport and Worker reliability | `orchestra/ssh.py` validates returned run identity and increasing event cursors. `remote.py` checks the Supervisor lock and matches the live owner before reporting a job heartbeat. `supervisor.py` clears old startup evidence. `workspace_remote.py` retains the last successful timestamp through an outage and resumes known-job status reads with a delay. Job submission with an unresolved receipt still requires explicit reconnection and reuses its request ID. | `smoke_workspace_ssh.py` shuts down real loopback sshd, observes an unavailable transport, lets the job complete while offline, restarts sshd and resumes from the saved cursor with the same run and task IDs. The test also kills/restarts the Worker Supervisor, checks that a stale heartbeat disappears, verifies deduplication and cancels an in-flight QA command over SSH. Physical machine reboot, permanently unavailable hosts and non-loopback network infrastructure are unverified. SSH shell reconnection creates a new terminal session. |
| Runtime, MCP and QA audit | `orchestra/runtime.py` classifies request timeouts separately from connection failure. `harness.py` records an uncertain MCP write outcome and leaves the existing write journal in charge of replay protection. `gitgate.py` records `qa.interrupted` on timeout or cancellation, with the relevant QA index and measured elapsed time. `observability.py` labels that audit event. | `test_orchestra.py` stalls real HTTP fixture responses. Managed inference resumes from its checkpoint. An MCP write times out after one observed effect and stays blocked from retry. The SSH cancellation verifies the persisted interruption. Already-running Managed HTTP requests still wait on their request timeout before a stop can take effect. |
| Git and concurrent state | The same GitGate SHA, integration worktree and target-branch checks remain authoritative. SQLite keeps the existing transactional queue and cancellation rules. | `test_orchestra.py` now alters the verified integration worktree and checks that the approved merge is rejected with the target unchanged. `test_platform_contracts.py` races cancellation and completion under independent SQLite connections and checks that exactly one terminal state is published. Existing crash rollback, WAL reader, restart, QA retry/approval revision and moved branch cases remain in the full suite. |

## Provider and Harness verification

| Route | Installed CLI startup or credentials | Model selection, inference and tools | Pending evidence |
| --- | --- | --- | --- |
| OpenCode | Installed binary startup observed. External account credentials not verified. | Actual CLI and OpenCode Adapter against a scripted loopback API. The run verifies selected model ID, real worktree read, persistence, cancellation and HTTP rejection. | Authenticated discovery, hosted inference, and real-model write workflow. |
| Codex | Installed binary startup observed. The CLI reports stored credentials. | The shared local profile remains untouched. | Test-only authenticated profile, explicit usage authorization and a smoke run. |
| Gemini CLI | Installed binary startup observed. | Discovery-only in the app. | Execution adapter, dedicated account and behavior verification. Gemini via OpenCode is a separate path. |
| Antigravity | Installed binary startup observed. | Discovery-only in the app. | Execution adapter, dedicated account and behavior verification. |
| Managed | Python Supervisor and real tools executed through the Tk and reliability scenarios. | Model discovery, selection, tool calls and edits use a scripted loopback API. Inference timeout exercises checkpoint recovery. | Independently provisioned approved runtime or hosted test route. |

No chargeable external model calls were made. Use a dedicated authorized test profile and a synthetic repository before recording external inference as verified. Installation/version, credential presence, external inference, tool use and full workflow are separate results.

## Compatibility matrix

PASS denotes observed integration in the stated scope. PARTIAL identifies a verified subset and its unverified portion. FAIL denotes a failing result in that scope. NOT VERIFIED indicates missing execution evidence. NOT SUPPORTED describes product scope.

| Feature | Linux | Windows | macOS |
| --- | --- | --- | --- |
| Electron history, IPC, shutdown and recovery | PASS | NOT VERIFIED | NOT VERIFIED |
| Python Supervisor and SQLite persistence | PASS | NOT VERIFIED | NOT VERIFIED |
| TypeScript core and cross-language contracts | PASS | NOT VERIFIED | NOT VERIFIED |
| Provider routing | PARTIAL — local policies and scripted service tested | NOT VERIFIED | NOT VERIFIED |
| Harness execution | PARTIAL — installed OpenCode and Managed with scripted responses | NOT VERIFIED | NOT VERIFIED |
| Agent management and DAG execution | PASS — live Supervisor, scripted inference | NOT VERIFIED | NOT VERIFIED |
| MCP Gateway and write journal | PARTIAL — loopback protocol, approval and timeout | NOT VERIFIED | NOT VERIFIED |
| Tk operator workflow | PASS — live worktree, QA and approval | NOT VERIFIED | NOT VERIFIED |
| Local terminal | PASS — POSIX PTY, multi-session, resize and cleanup | NOT VERIFIED — ConPTY | NOT VERIFIED |
| SSH terminal | PASS — loopback OpenSSH and a fresh terminal session after reconnect | NOT VERIFIED | NOT VERIFIED |
| Remote Worker server | PASS — loopback outage, restart and deduplication | NOT SUPPORTED | NOT SUPPORTED |
| Remote Worker client | PASS — Python and TypeScript against Linux | NOT VERIFIED | NOT VERIFIED |
| Git Worktree and approval safeguards | PASS — local Git, including Unicode and long paths | NOT VERIFIED | NOT VERIFIED |
| Background recovery | PASS — process and SSH transport failure | NOT VERIFIED | NOT VERIFIED |
| Packaging | PASS — unpacked and AppImage with extract-and-run | NOT VERIFIED — NSIS and unpacked | NOT SUPPORTED — packaging target absent |
| GPU | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |

## Release gates and reproduction

1. Run the native Windows workflow and retain installer, ConPTY, Job Object, filesystem and Supervisor evidence. Use the separately documented Tk PyInstaller acceptance checks before shipping that bundle.
2. Use an explicitly authorized dedicated Provider profile to validate external discovery, inference and tool behavior. OpenCode and Codex are the current execution paths for external accounts.
3. Run an independent host and client over SSH and exercise real host reboot, sustained network failure and cancellation deadlines under external Provider delays.
4. Test detached Git ref updates and checked-out branch contention with competing processes before advertising guarantees beyond the existing SHA checks. Retain the MCP journal and audit requirements. Snapshot storage on a shared filesystem and power-loss behavior remain unverified.

Run `npm run verify -- --ui --ssh --package --harness` on a Linux test host with OpenSSH and a display or Xvfb. The `ORCHESTRA_QA_SCREENSHOT` and `ORCHESTRA_QA_TK_SCREENSHOT` environment variables capture synthetic execution evidence during the Electron and Tk tests. The Windows CI entry point adds the installed-app test and reuses the same software-rendered Playwright cases.
