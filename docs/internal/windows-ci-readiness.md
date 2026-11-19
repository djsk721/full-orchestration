# Windows CI and packaging readiness

| Gate | Status | Evidence |
| --- | --- | --- |
| Native Windows job definition | PASS | Static inspection of the `windows-2025` matrix job, pinned Node 24 and Python 3.11 setup, desktop requirements, and `npm ci`. |
| Strict TypeScript, Python regression and source Electron | NOT VERIFIED | The shared Windows command builds TypeScript and runs the Python, TypeScript and Playwright suites on the Windows runner. The candidate has no run on that runner. |
| Windows adapters, ConPTY and Job Object process cleanup | NOT VERIFIED | Shared native adapter tests include a real command tree whose descendants are terminated on timeout and hard owner exit, Windows-only read-only file and junction cases, and a native PTY. A dedicated Tk test adds Unicode paths, Korean clipboard, both splits, resize, Ctrl+C and owned descendant cleanup. |
| NSIS build, installation, startup, uninstallation and reinstallation | NOT VERIFIED | CI builds NSIS, opens unpacked Electron, then tests silent install → installed Playwright → uninstall → reinstall → installed Playwright → uninstall. |
| Existing SQLite and configuration preserved by NSIS | NOT VERIFIED | The installed data test uses a disposable account and verifies five file hashes before and after both uninstalls. |
| Tk first-run, packaged Supervisor startup/recovery and shutdown | NOT VERIFIED | The Windows job separately builds the PyInstaller workspace, dismisses its native first-run language picker into a fresh Unicode profile, observes a real Supervisor heartbeat, checks replacement after a forced child exit, then closes both and checks layout and SQLite integrity. |
| Full Windows deployment | PARTIAL | The test procedures and release build targets are wired. Native runtime, installation and manual acceptance evidence are outstanding. |

The installer is the read-only Electron monitor. It consumes the existing Python data and is tested independently. The Tk workspace and Supervisor are built as a standalone PyInstaller executable. The shared native Tk first-run smoke configures a temporary Git project, Provider and SSH profile and opens a local terminal. The Windows SSH profile check covers setup of the saved profile. A connection from Windows to a pinned OpenSSH server remains unverified. Linux evidence covers a real loopback OpenSSH server.

The workflow collects shared Windows/NSIS, ConPTY, installed Electron and frozen Tk logs in the `windows-verification-evidence` artifact. Native ConPTY and frozen workspace checks can still run after a shared-suite failure if Python dependencies installed. The installed Electron test requires a successful shared NSIS build. The artifact can contain incomplete results when the job fails. Korean IME and the three display scales require manual evidence from an interactive desktop. See [Windows native acceptance](windows-native-ux-validation.md).

## Actions needed for hosted verification

The implementation remains in the working tree of `feature/orca-workspace`. To use GitHub Actions, first commit the reviewed candidate changes locally with separate authorization, then publish that commit with:

```bash
git push -u origin feature/orca-workspace
```

Dispatch **Cross-platform verification** against that branch or open a pull request touching the workflow's path filters. A checkout copied to a native Windows test host can run the documented procedure without publishing anything. This pass used Linux and made no GitHub changes.
