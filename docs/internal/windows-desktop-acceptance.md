# Windows desktop acceptance

**Final decision PARTIAL.** The operator reported launching the source app with Python and shared an actual Windows screenshot. The window shows the Korean Workspace, the empty project list, the Files/Git/Agent/Activity context panel, and the green Supervisor status badge. The execution host for this review is Linux. The Windows checkout and desktop are available through operator evidence.

| Scope | Status | Evidence |
| --- | --- | --- |
| Windows main window rendering | PASS | The operator supplied a 1357 × 885 screenshot of the Korean Workspace before registering a project. |
| Windows source startup and Supervisor | PARTIAL | Operator-reported Python launch and visible running status. Exact checkout, heartbeat, local shell and SQLite activity are outstanding. |
| Windows runtime and checkout inventory | NOT VERIFIED | Collect the read-only inventory below. A downloaded ZIP may have no Git metadata. Keep it as-is. |
| Windows automated candidate baseline | PASS | Run 44573538314 passed native regression and packaged lifecycle for application commit `e3236583819377e4d8a67609df8b61027f6a5eb0`. |
| Retained NSIS integrity | PASS | The installer downloaded in the preceding acceptance pass matched SHA-256 `4bfebdcd108b65ba63c3ecea31c7235f2c50e1bcbcc68f84f5ff6d8a4c24aa32`. Installation on the operator's desktop is NOT VERIFIED. |
| Desktop GUI, IME and 100%, 125%, 150% | NOT VERIFIED | The startup capture does not include an observed scale or an input interaction. |
| OpenCode and Codex | NOT VERIFIED | Actual Windows paths, versions and both interactive sessions are outstanding. The discovery correction has a locally passing contract test. |
| Hosted OpenAI GPT through OpenCode | NOT VERIFIED | The operator redirected GPT validation to Linux. The Linux Workspace displayed `openai/gpt-5.6-luna` and its retry controls passed isolated checks. Windows source, CLI, authentication and inference still need native evidence. [GPT verification report](windows-opencode-gpt-integration.md) |
| Disposable project and orchestration E2E | NOT VERIFIED | This review exercises the Linux fixture independently. The operator's Windows source and Windows installed UI are separate acceptance surfaces. |
| Windows SSH and Remote Worker | NOT VERIFIED | No authorized Windows-accessible test endpoint was provided. |
| Desktop performance phase timings | NOT VERIFIED | Prior native CI aggregate measurements exist. The test profiler now also records queue processing. |
| GPU testing | NOT APPLICABLE | Outside scope. |

See the [CI execution report](windows-ci-execution-report.md), [GUI checks](windows-desktop-ui-qa.md), [CLI checks](windows-cli-terminal-qa.md), [GPT verification report](windows-opencode-gpt-integration.md), and [orchestration checks](windows-orchestration-e2e.md).

## Record the Windows environment

Use the PowerShell session that launched the source app so it sees the same PATH and profile selection. If this QA inventory file is absent from the Windows copy, record the Windows build, `py -3 --version`, `node --version`, `git --version`, and `where.exe opencode` / `where.exe codex` separately. Check for `.git` before running Git status or revision commands.

```powershell
Set-Location -LiteralPath (Read-Host 'Path to the Windows project folder')
$orcaEvidence = Join-Path $env:TEMP ('orchestra-desktop-qa-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $orcaEvidence | Out-Null
py -3 .\scripts\qa\windows_desktop_inventory.py |
    Tee-Object -FilePath (Join-Path $orcaEvidence 'inventory.json')
```

The inventory reports OS, Python, Tk, dependencies, Git revision and change count, Node and Git versions, raw CLI lookup and Workspace-selected paths, counts for existing projects and Provider configuration, SQLite header readability and Supervisor heartbeat age. Profile contents, endpoints, project names, keys and tokens stay out of the output. A valid SQLite header establishes file readability. Use the running app's History and project sidebar to verify actual access and rendering. Capture a screenshot with private project names masked if it will be shared.

For the known source checkout, use `py -3 .\ModelOrchestration.pyw` for a diagnostic launch. Launch a second instance only from an isolated profile using `ORCHESTRA_DATA` in a separate test PowerShell. Follow the [retained installer procedure](windows-native-ux-validation.md) when testing the verified NSIS executable.

## Regression and performance commands

Set `$env:PYTHON = (py -3 -c 'import sys; print(sys.executable)')` in the test shell if `python.exe` on PATH does not match the launcher. The source verification uses temporary test profiles. The full Windows suite also exercises NSIS installation and requires a disposable account with no existing installation or default profile.

```powershell
pwsh -NoProfile -File .\scripts\qa\verify-windows-workspace.ps1 -WorkspaceOnly -ExpectedDpi 96
pwsh -NoProfile -File .\scripts\qa\verify-windows-workspace.ps1
```

Use the [repeat and profile commands](windows-native-ux-validation.md#repeat-and-profile-windows-terminal-performance) for three uninstrumented runs and three profiled runs. Record completed ConPTY read wall time, queue put and get attempts, ANSI feed, Tk draw, event-loop percentile delay, CPU, RSS, output integrity and cleanup. ConPTY read and queue wait can overlap the Tk thread. Compare the same Windows scenario, scale, resolution and machine load across repeats. Native CI measured 7.460 seconds for one pane, 4.957 seconds for a horizontal split and 5.018 seconds for a vertical split in the passing run. A second hosted run changed the three scenarios in mixed directions. There is no reproducible desktop bottleneck on record. [Native timing evidence](windows-native-test-results.md)

## Current Linux regression

`npm run verify -- --ui --package --ssh` passed 106 checks on this working tree, up from the 101-check baseline. It ran 60 passing Python tests, 25 TypeScript tests, six Tk checks and 15 Electron checks across source, unpacked and AppImage. Three Windows-only tests were skipped for native read-only attributes, junction behavior and real PATH/PATHEXT discovery. The separate real loopback OpenSSH Worker check and both offline installed Linux CLI sessions passed. A Linux PTY run confirmed the test profiler recorded all five phases, restored the original methods and reaped the child process. An isolated inventory check confirmed unchanged files and that fixture profile values stayed out of the JSON output.

A single Linux PTY benchmark round exercised one pane, both two-pane orientations and four simultaneous panes. All nine sessions delivered the expected 8,000 rows with zero omissions and duplicates, and all tracked children exited. This is a Linux regression check. Windows performance remains classified separately.
