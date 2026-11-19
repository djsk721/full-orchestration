# Windows native workspace validation

**Current result: NOT VERIFIED.** The available host was native Linux. Native Windows CI and desktop procedures are prepared locally. See [Windows CI and packaging readiness](windows-ci-readiness.md).

## Reproduce on a native Windows desktop

Use a disposable Windows account, an interactive desktop session and a checkout containing the candidate changes. The prerequisites are Git, Node 24, Python with Tcl/Tk, PowerShell 7 and the repository dependencies. Install Pillow if capturing screenshots.

```powershell
python -m pip install -r requirements-desktop.txt
npm ci
pwsh -NoProfile -File ./scripts/qa/verify-windows-workspace.ps1
```

This runs the native ConPTY fixture, shared unit/UI suite, NSIS installer lifecycle and standalone frozen Tk workspace check. The NSIS lifecycle verifies the registry, workspace, SQLite history, theme/language preferences and layout hashes using a disposable account without an existing installation or default data folder.

Run the following after setting the Windows display scale to 125% on the target desktop. Use `96` at 100% and `144` at 150%. Open a new process for each scale.

```powershell
pwsh -NoProfile -File ./scripts/qa/verify-windows-workspace.ps1 -WorkspaceOnly -ExpectedDpi 120 -ScreenshotDirectory ./qa-evidence/windows-125
```

| Required behavior | Prepared procedure | Candidate status |
| --- | --- | --- |
| Tk launch, Unicode paths, ConPTY initialization and two simultaneous sessions | Native Tk smoke starts two Windows console fixtures in a repository whose path contains spaces and Korean text | NOT VERIFIED |
| Both splits, terminal resizing, keyboard cancellation and child process cleanup | Native smoke compares console-reported geometry, sends input and Ctrl+C through ConPTY, and checks its own subprocess tree after closing | NOT VERIFIED |
| Unicode clipboard and passive restoration | Native smoke round-trips Korean clipboard text and reopens the same profile with terminal placeholders | NOT VERIFIED |
| Korean IME composition, fonts and 100%/125%/150% | Run the scale commands. Activate Korean Microsoft IME, compose and commit Korean in a task field and both terminal panes, then inspect ligatures, focus, text clipping and candidate-window placement | NOT VERIFIED |
| Installed OpenCode and Codex | In a disposable Windows account with outbound network blocked, discover both installed binaries, open both interactively, type without submitting an inference prompt and exercise split, focus, resize and close | NOT VERIFIED |
| Windows Supervisor integration and path safeguards | Shared Tk first-run and Python suites, including expired leases, process recovery, Job Object cleanup, directory junctions and read-only files | NOT VERIFIED |
| Electron unpacked startup and NSIS lifecycle | Shared packaging runner plus installer persistence script in the disposable account | NOT VERIFIED |
| Standalone Tk executable and frozen Supervisor | `./Build-Windows.ps1 -Python python -InstallBuildDependency -VerifyWorkspace` executes first-run language selection, heartbeat, Supervisor replacement, shutdown and SQLite integrity from the frozen app | NOT VERIFIED |
| Packaged local terminal and SSH | Open a local console from the packaged workspace, execute a harmless echo, then add a test SSH profile with a pinned fingerprint and connect to an authorized disposable SSH server | NOT VERIFIED |
| GPU and authenticated external inference | Excluded from this pass | NOT APPLICABLE |

## Manual desktop checklist

1. Repeat the native verification at 100%, 125% and 150% display scale using reported DPI 96, 120 and 144. For each scale retain the run log, Windows display settings and one image of the complete window. Check readable text, unclipped controls, both split directions and pane resizing.
2. Select Microsoft Korean IME. Compose and commit `한글 입력` in a task title and each terminal pane while the composition candidate or underline is visible. Repeat after switching pane and project. Capture composition and the committed text. For terminals, use an echo fixture and retain the rendered response.
3. With temporary CLI profiles and outbound networking disabled, launch installed OpenCode and Codex inside the workspace. Record executable versions, capture both rendered startup screens, type text without submitting a prompt, resize both panes and close them. Record whether each CLI process exited.
4. In the standalone workspace, register a new disposable Git project, open its local terminal and test a pinned SSH profile against an authorized fixture server. Record the first-run screen, local command response and successful remote shell. Retain fixture fingerprints and omit private keys or credential details.

Record Windows build, display scale, Tk and pywinpty versions, screenshot dimensions, log hashes, and any failed or skipped cases next to the corresponding evidence.
