# Release candidate QA report

## Execution scope

- Linux host with disposable data, Git repositories, loopback HTTP/OpenSSH and software-rendered UIs. The candidate builds on local `6c8bb8d` with the current working-tree changes.
- Windows-native evidence and paid external inference are outstanding. GPU validation is excluded. [Platform matrix](platform-compatibility.md)

## Commands and results

| Class | Command or test | Outcome |
| --- | --- | --- |
| Full Linux regression | `npm run verify -- --ui --ssh --package --harness` with desktop dependencies, Xvfb and OpenSSH | Python ran 41 cases, with 39 passes and two native Windows skips. All 25 TypeScript tests, two Tk suites and the live OpenSSH scenario passed. The four Playwright scenarios passed for each of source, unpacked Electron and AppImage. |
| Targeted Electron persistence | `python apps/desktop/tests/legacy_fixture.py TEMP_DIR --installer-persistence`, then `ORCHESTRA_INSTALLER_DATA=TEMP_DIR xvfb-run -a npm run test:e2e` | PASS, 5 tests. The extra case reopens the seeded database and compares its bytes. Installation and removal were outside this Linux check. |
| Tk full workflow | `xvfb-run -a python tests/smoke_workspace_flow.py` | PASS. Registers a project and Provider, selects model and Harness, executes a guided workflow against scripted inference, inspects current approval evidence, declines once, approves, checks Git, then verifies GUI QA failure and cancellation. |
| Codex evidence | Run the dedicated-profile preflight and parse synthetic success and failure JSONL samples | PASS for the redaction parser and rejection of an empty auth object with execution requested. Real authenticated inference unverified. |
| Linux installed OpenCode | `python tests/smoke_installed_opencode.py` within full verification | Real CLI, scripted response API, read tool, cancellation, error and persistence. |
| Windows native | `npm run verify -- --ui --package` and `pwsh -NoProfile -File ./scripts/qa/verify-windows-installer.ps1` | NOT VERIFIED. [Windows procedure](windows-native-verification.md) |

Linux screenshots use synthetic test records. [Tk current-cycle approval](../assets/screenshots/rc-tk-approval.png) · [Electron history and freshness](../assets/screenshots/rc-electron-history.png)

## Changes tied to regression cases

- `store.py`, `execution_state.py`, `gitgate.py` and `test_platform_contracts.py` enforce the exact approval cycle for cycle-aware records, even when a retry shares the same SHA. Missing or stale cycle and failed QA are rejected. The GitGate still rechecks the worktree, target branch and candidate.
- `desktop.py`, `workspace_desktop.py` and the Tk smoke use the actual integration diff and persisted QA evidence in the modal. The UI keeps the candidate pending when the dialog is closed, writes the matching cycle to the audit log when approved, and renders a failure without enabling merge.
- `main.tsx`, `styles.css` and `desktop.spec.ts` cover timestamp stability on an incompatible SQLite read followed by a fresh timestamp after restoration. The renderer retains the existing read-only API and uses isolated browser profiles during testing.
- `verify-windows-installer.ps1` and `legacy_fixture.py` prepare fresh-install, uninstall and reinstall evidence with three default data-file hashes. The Windows-only native tests cover a real junction and atomic writes against a read-only file.

## Failed checks and remaining gates

A targeted Codex preflight discovered that an empty auth object can produce a CLI login success status. An application-side structural check now prevents that case from triggering a request. The GitHub lookup found no matching workflow in the remote Actions catalog, which leaves Windows native verification unresolved.

The combined Linux command printed passing results from all test sets and its wrapper exited 143. Source, UI, SSH and Harness were then rerun with `npm run verify -- --ui --ssh --harness`. The two built packages were rerun independently with the same Playwright cases and their own software-rendered launches. Both rerun commands exited zero.

Use a clean Windows host to run the installer and native suites, then use the approved dedicated Codex profile for one synthetic inference. Release approval remains blocked on these results. Keep external-service tests distinct from local harness and fixture results.
