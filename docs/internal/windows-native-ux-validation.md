# Windows native workspace validation

**Manual result NOT VERIFIED.** A GitHub-hosted Windows runner has executed the automated ConPTY suite. See [native Windows test results](windows-native-test-results.md) for automated evidence.

## Reproduce on a native Windows desktop

Use a disposable Windows account, an interactive desktop session and a checkout containing the candidate changes. The prerequisites are Git, Node 24, Python with Tcl/Tk, PowerShell 7 and the repository dependencies. Install Pillow if capturing screenshots.

```powershell
python -m pip install -r requirements-desktop.txt
npm ci
pwsh -NoProfile -File ./scripts/qa/verify-windows-workspace.ps1
```

This runs the native ConPTY fixture, shared unit/UI suite and NSIS installer lifecycle for both installed executables. The NSIS lifecycle verifies the registry, workspace, SQLite history, theme/language preferences and layout hashes using a disposable account without an existing installation or default data folder. The primary Tk app is the installed `resources\workspace\ModelOrchestration.exe`. Electron opens the read-only preview.

Run the following after setting the Windows display scale to 125% on the target desktop. Use `96` at 100% and `144` at 150%. Open a new process for each scale.

```powershell
pwsh -NoProfile -File ./scripts/qa/verify-windows-workspace.ps1 -WorkspaceOnly -ExpectedDpi 120 -ScreenshotDirectory ./qa-evidence/windows-125
```

| Required behavior | Prepared procedure | Candidate status |
| --- | --- | --- |
| Tk launch, Unicode paths, ConPTY initialization and two simultaneous sessions | Native Tk smoke starts two Windows console fixtures in a repository whose path contains spaces and Korean text | PASS in CI |
| Both splits, terminal resizing, keyboard cancellation and child process cleanup | Native smoke compares console-reported geometry, sends input and Ctrl+C through ConPTY, and checks its own subprocess tree after closing | PASS in CI |
| Unicode clipboard and passive restoration | Native smoke round-trips Korean clipboard text and reopens the same profile with terminal placeholders | PASS in CI |
| Korean IME composition, fonts and 100%/125%/150% | Run the scale commands. Activate Korean Microsoft IME, compose and commit Korean in a task field and both terminal panes, then inspect ligatures, focus, text clipping and candidate-window placement | NOT VERIFIED |
| Installed OpenCode and Codex | In a disposable Windows account with outbound network blocked, discover both installed binaries, open both interactively, type without submitting an inference prompt and exercise split, focus, resize and close | NOT VERIFIED |
| Windows Supervisor integration and path safeguards | Shared Tk first-run and Python suites, including expired leases, process recovery, Job Object cleanup, directory junctions and read-only files | PASS in CI |
| Electron unpacked startup and NSIS lifecycle | Shared packaging runner and installer persistence script in the disposable account | PASS in CI |
| Installed frozen Tk and Supervisor | The installed executable exercises first-run language selection, heartbeat, Supervisor replacement, shutdown and SQLite integrity | PASS in CI |
| Packaged local terminal | The installer lifecycle checks actual PowerShell launch and exit from the installed Tk workspace | PASS in CI |
| Live SSH from the packaged workspace | Create a test SSH profile with a pinned fingerprint and connect to an authorized disposable SSH server | NOT VERIFIED |
| GPU and authenticated external inference | Excluded from this pass | NOT APPLICABLE |

## Manual desktop checklist

1. Repeat the native verification at 100%, 125% and 150% display scale using reported DPI 96, 120 and 144. For each scale retain the run log, Windows display settings and one image of the complete window. Check readable text, unclipped controls, both split directions and pane resizing.
2. Select Microsoft Korean IME. Compose and commit `한글 입력` in a task title and each terminal pane while the composition candidate or underline is visible. Repeat after switching pane and project. Capture composition and the committed text. For terminals, use an echo fixture and retain the rendered response.
3. With temporary CLI profiles and outbound networking disabled, launch installed OpenCode and Codex inside the workspace. Record executable versions, capture both rendered startup screens, type text without submitting a prompt, resize both panes and close them. Record whether each CLI process exited.
4. In the standalone workspace, register a new disposable Git project, open its local terminal and test a pinned SSH profile against an authorized fixture server. Record the first-run screen, local command response and successful remote shell. Retain fixture fingerprints and omit private keys or credential details.
5. At each scale open the model selector and first-run and approval dialogs, resize the sidebar and file panels, change the split direction, and switch away from and back to the app. Verify focus, font rendering and dialog positioning. With two monitors, move the app between them and repeat a resize and IME composition at their respective scales. Record whether a second monitor was available.

Record Windows build, display scale, Tk and pywinpty versions, screenshot dimensions, log hashes, and any failed or skipped cases next to the corresponding evidence.
