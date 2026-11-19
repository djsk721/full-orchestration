# Windows native verification

**Candidate status: NOT VERIFIED.** The execution host is Linux and no native Windows runner was available. A read-only GitHub Actions lookup for `cross-platform.yml` returned “could not find any workflows named cross-platform.yml”. The GitHub commit lookup returned no pull-request workflow runs for local commit `6c8bb8d`. The workflow and release-candidate updates are local, so neither query establishes a successful Windows run. No remote workflow was dispatched.

## Reproduce on native Windows

Use a disposable native Windows account with Git, Node 24, Python 3.11 or later and Tcl/Tk. Use a checkout containing this working tree. The script checks for an existing preview install and an existing default Python data directory before proceeding.

```powershell
python -m pip install -r requirements-desktop.txt
npm ci
npm run verify -- --ui --package
pwsh -NoProfile -File ./scripts/qa/verify-windows-installer.ps1
```

| Check | Prepared evidence | This checkout |
| --- | --- | --- |
| Electron generation, unpacked startup, read IPC, window close and SQLite recovery | Shared workflow and Playwright suite | NOT VERIFIED |
| NSIS install, launch, shutdown, uninstall and reinstall | `verify-windows-installer.ps1` runs the Playwright suite on both installs and checks removal of the executable | NOT VERIFIED |
| Default data location, configuration and history creation and retention | Python fixture creates `state.db`, `registry.json` and `workspace.json` under the clean account's default `%LOCALAPPDATA%\ModelOrchestration` location. The installed Electron reopens the data without an explicit data-path override. The script hashes the files after each launch and uninstall. | Linux fixture and Electron retained-data check passed with a temporary override. Windows default path and NSIS persistence remain NOT VERIFIED. |
| Job Object, child process tree, Supervisor and detached execution | Python process adapter and crash/restart regression tests | NOT VERIFIED |
| ConPTY input/output, color, resize, multiple sessions and cleanup | Native PTY regression and interactive Tk smoke tests | NOT VERIFIED |
| Windows file handling and Git safeguards | Real junction and read-only-file tests, Unicode/long-path Worktree checks, SHA and branch checks. Long-path case reports a skip when the native host disallows it. | NOT VERIFIED |
| Tk and Supervisor | Native Tk guided workflow drives actual Python writes and execution with scripted model responses. Electron reads the same persisted schema. | NOT VERIFIED on Windows |

Retain the Windows job log and its commit or checkout identity. Record skipped cases separately. Windows installer signing and the standalone Tk PyInstaller distribution require their own release evidence.
