# Windows desktop acceptance

**Manual desktop acceptance NOT VERIFIED.** The Linux execution host has no direct access to the operator's Windows session. The operator shared a Windows startup screenshot. Previous native CI on Windows Server 2025 verified startup, ConPTY, clipboard data and process cleanup. [Startup screenshot and interactive checks](windows-desktop-ui-qa.md) · [Native CI results](windows-native-test-results.md)

| Acceptance gate | Status | Evidence |
| --- | --- | --- |
| Retained NSIS installer SHA-256 | PASS | The 133,477,760-byte executable from artifact 14555204038 was downloaded and hashed on 2026-11-20. The calculated digest matched the expected value. |
| NSIS lifecycle, installed Tk and Electron, Supervisor recovery and local shell startup | PASS | Run 44573538314 ran both installation rounds and checked fixture data preservation. |
| Korean clipboard round-trip, splitting, resizing and passive layout restoration in source Tk | PASS | Native Windows CI console fixtures, at 96 DPI. |
| Interactive desktop acceptance at 100%, 125% and 150% | NOT VERIFIED | Installed app screenshots and logs for all three scales are outstanding. |
| Microsoft Korean IME in task forms and both terminal panes | NOT VERIFIED | Requires live composition and confirmation in the installed app. |
| Installed Windows OpenCode and Codex interaction | NOT VERIFIED | Requires both CLIs available to the isolated Windows account. |
| Installed Workspace first-run through controlled workflow and history recovery | NOT VERIFIED | Previous CI covers source UI and installed lifecycle separately. |
| Live SSH from the installed Windows workspace | NOT VERIFIED | Requires an authorized host and an independently verified host key. |
| GPU | NOT APPLICABLE | Outside this acceptance scope. |
| Authenticated external inference | NOT VERIFIED | Outside this acceptance scope. |

## Install the retained candidate in an isolated account

Download and unzip the [Windows NSIS artifact from run 44573538314](https://github.com/djsk721/full-orchestration/actions/runs/44573538314/artifacts/14555204038). Use a disposable Windows account or VM with no registered Model Orchestration Preview installation. Check **Settings → Apps → Installed apps** before proceeding. Use a feature-branch checkout with the acceptance scripts, Git, Python with Tcl/Tk, and PowerShell 7. Open PowerShell at the checkout root and supply the extracted executable path when prompted.

```powershell
$orcaRoot = Join-Path $env:TEMP ("orchestra-acceptance-" + [guid]::NewGuid().ToString("N"))
$orcaEvidence = Join-Path $orcaRoot "evidence"
New-Item -ItemType Directory -Path $orcaEvidence -Force | Out-Null
$orcaInstaller = (Resolve-Path -LiteralPath (Read-Host "Path to the extracted installer")).Path
$orcaExpected = '4bfebdcd108b65ba63c3ecea31c7235f2c50e1bcbcc68f84f5ff6d8a4c24aa32'
$orcaActual = (Get-FileHash -LiteralPath $orcaInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
"NSIS SHA-256 $orcaActual" | Tee-Object -FilePath (Join-Path $orcaEvidence 'installer-sha256.log')
if ($orcaActual -ne $orcaExpected) { throw 'Installer checksum mismatch' }

$orcaTarget = Join-Path $orcaRoot 'installation'
$orcaInstall = Start-Process -FilePath $orcaInstaller -ArgumentList "/S /D=$orcaTarget" -Wait -PassThru
$orcaWorkspace = Join-Path $orcaTarget 'resources\workspace\ModelOrchestration.exe'
$orcaMonitor = Join-Path $orcaTarget 'model-orchestration-preview.exe'
if ($orcaInstall.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $orcaWorkspace) -or
    -not (Test-Path -LiteralPath $orcaMonitor)) { throw 'Installed executables were not found' }
$env:ORCHESTRA_DATA = Join-Path $orcaRoot 'isolated-profile'
$orcaApp = Start-Process -FilePath $orcaWorkspace -PassThru
```

Launch the installed executables from this PowerShell session so they inherit the isolated profile. Keep the temporary directory while collecting evidence. The commands below use the existing installation and the isolated checkout fixture. When changing display scale, fully exit the installed workspace and launch it again from this session.

## Repeat the GUI checks at each display scale

Install the source smoke test dependencies once with `python -m pip install -r requirements-desktop.txt Pillow`. Use Windows **Settings → System → Display** to select the test monitor and its scale. Use a monitor with enough space to fit the entire application window for captures. Run the following once per scale. Set `$orcaScale` to `100`, `125` and `150` in turn. The source smoke test uses its own temporary profile.

```powershell
$orcaScale = 100
$orcaDpi = (@{100 = 96; 125 = 120; 150 = 144})[$orcaScale]
$orcaScaleEvidence = Join-Path $orcaEvidence "windows-$orcaScale"
New-Item -ItemType Directory -Path $orcaScaleEvidence -Force | Out-Null
pwsh -NoProfile -File ./scripts/qa/verify-windows-workspace.ps1 -WorkspaceOnly `
    -ExpectedDpi $orcaDpi -ScreenshotDirectory $orcaScaleEvidence *>&1 |
    Tee-Object -FilePath (Join-Path $orcaScaleEvidence 'native-smoke.log')
if ($LASTEXITCODE -ne 0) { throw "Native smoke failed at $orcaScale percent" }
```

In the installed app, perform each check at the same scale and save actual screenshots to the corresponding directory.

1. **Startup and layout.** Capture the full workspace, then resize the main window and move the terminal and context dividers. Verify panels align, text and icons render legibly, and controls stay visible. Open the model selector and task/approval dialogs and capture their positions. Switch to another application and return. If available, move the workspace between displays and repeat the resize and focus checks.
2. **IME.** Select Microsoft Korean IME. Type `한글 입력` in the task title or objective. Capture live composition with its underline or candidate UI and capture the committed text separately. Confirm that composing does not submit a task. Clear or dismiss the draft.
3. **Terminals.** Open a local PowerShell terminal and split it. In each pane type `Write-Output '한글 입력'` using the physical keyboard and IME, capture composition, commit the text, and execute the local echo. Confirm each pane displays the exact Korean echo. Copy and paste between panes using `Ctrl+Shift+C` and `Ctrl+Shift+V`. Exercise both split orientations, move their sash, and confirm typing goes to the focused pane only.
4. **Restore.** Leave a split and visibly adjusted panels open, exit normally, and restart the installed workspace with the same isolated profile. Compare the restored panels, sash, selected project and terminal placeholders against the closing screenshot. Confirm no prior command starts merely because it appears in the restored layout.
5. Save the display settings screenshot, Windows build, smoke log with observed DPI, IME images, split/resize images, and before/after layout images. Add actual observations for failed or skipped checks.

| Scale | Expected native DPI | Manual installed-app status |
| --- | ---: | --- |
| 100% | 96 | NOT VERIFIED |
| 125% | 120 | NOT VERIFIED |
| 150% | 144 | NOT VERIFIED |

## Installed CLIs with outbound access disabled

Use the isolated account's CLI profiles. Stage both binaries on the VM, then disable its external networking while retaining loopback. Record the isolation setup. A disconnected VM may show an offline or sign-in screen. Evaluate rendering and responsiveness, and record any screen that prevents reaching the interactive input field.

1. In the PowerShell session used to launch the installed workspace, run `Get-Command opencode,codex` and record their executable paths and `--version` output. Launch the workspace from that session and verify its terminal menu discovers both CLIs.
2. Open OpenCode and Codex in separate terminal tabs. Record their startup screens and test typing and deleting a draft in each input field. Leave draft prompts unsubmitted. Trust only the disposable fixture project if the CLI prompts for project trust.
3. Bring the existing sessions into a horizontal split from the terminal menu, switch to vertical, resize both panes and switch focus. Verify input stays in its intended pane and the existing sessions are reused. Capture both layouts.
4. Record the two owned CLI process trees before closing the sessions. For example, use `Get-CimInstance Win32_Process | Select-Object Name,ProcessId,ParentProcessId` and retain the relevant rows for the installed app and its terminal children. When closing each tab, choose the option that ends the session. Check that the recorded CLI PIDs exit with `Get-Process -Id <recorded-PIDs> -ErrorAction SilentlyContinue`.

Record CLI startup and input as their own result. Hosted inference remains NOT VERIFIED.

## Installed workflow with a controlled local Provider

Have the installed app use the same isolated profile for the full workflow and restart. Keep external networking disabled for this fixture. Run these setup commands from the checkout root in the acceptance PowerShell session.

```powershell
$orcaRepo = Join-Path $orcaRoot '테스트 프로젝트'
git init -b main "$orcaRepo"
Set-Content -LiteralPath (Join-Path $orcaRepo 'README.md') -Value '# Workspace acceptance fixture'
git -C "$orcaRepo" add README.md
git -C "$orcaRepo" -c 'user.name=Acceptance Fixture' -c 'user.email=fixture@example.invalid' commit -m 'Fixture base'
$orcaBase = git -C "$orcaRepo" rev-parse HEAD

$orcaFixtureScript = Join-Path $orcaRoot 'provider-fixture.py'
@'
import sys
import time

sys.path.insert(0, "tests")
from test_orchestra import http_fixture

with http_fixture() as (_, endpoint):
    print(endpoint, flush=True)
    while True:
        time.sleep(1)
'@ | Set-Content -LiteralPath $orcaFixtureScript -Encoding utf8
$orcaEndpointLog = Join-Path $orcaEvidence 'provider-endpoint.log'
$orcaProvider = Start-Process python -ArgumentList '-u', ('"' + $orcaFixtureScript + '"') `
    -WorkingDirectory (Get-Location).Path -RedirectStandardOutput $orcaEndpointLog -PassThru
```

1. Read the loopback URL from `$orcaEndpointLog`. In the installed app's first-run flow, add the Git project and a Provider using **llama.cpp** with that URL. Use profile ID `desktop-fixture`, test the connection, and select `test-model` as the project default. Open the local terminal and confirm the repository is its working directory.
2. If an authorized SSH server is available, test it in a separate network session with only the authorized endpoint reachable. Use a disposable SSH profile and compare the server fingerprint through the pre-established trusted channel before saving it. Test a shell in the installed Workspace. If no authorized endpoint is available, record SSH as NOT VERIFIED.
3. Submit a **Change, review and QA** task with objective `ui workflow: verify the integrated workspace`, model `desktop-fixture`, Harness `managed`, and editable path `ui-result.txt`. Leave **Continue after closing the app** unchecked for this foreground run. Add this integration QA command on one line.

   ```text
   python -c "from pathlib import Path; assert Path('ui-result.txt').read_text(encoding='utf-8').strip() == 'approved change'"
   ```

4. Record the run ID. Inspect `develop` and its dependent `review` in the DAG, Agent attempts and events, the `ui-result.txt` diff in the integration candidate, and QA exit code 0. Open the approval review and record the candidate SHA, target branch, QA revision and eligibility. Leave the approval pending. Check `git -C "$orcaRepo" rev-parse HEAD` still equals `$orcaBase`.
5. Close and reopen the installed Tk app and then open the installed Electron monitor from the same PowerShell session. Verify the run ID, saved project/model, QA evidence and candidate SHA persisted. Record that the pending approval and target SHA stayed unchanged. Stop the test-owned loopback Provider with `Stop-Process -InputObject $orcaProvider` after the last check.

Keep the run ID, app version, screenshots, QA result and observed status in the acceptance evidence. Keep personal settings, tokens and private keys out of the captures.

The documented task and QA were exercised locally on Linux with the loopback fixture. The job reached `AWAITING_APPROVAL`, reopening the Store returned the persisted job and approval revision, and the target Git SHA stayed unchanged. The installed Windows workflow still requires the desktop run above.

## Repeat and profile Windows terminal performance

Run uninstrumented repetitions and a separate instrumented series at the same scale, resolution, window geometry, OS build, Python/Tk/pywinpty versions and machine load. The workload uses 8,000 colored lines per pane and checks retained scrollback, ANSI styling and process cleanup.

```powershell
pwsh -NoProfile -File ./scripts/qa/verify-windows-workspace.ps1 -WorkspaceOnly `
    -ExpectedDpi 96 -Benchmark -BenchmarkRounds 3 *>&1 |
    Tee-Object -FilePath (Join-Path $orcaEvidence 'benchmark-windows.log')
pwsh -NoProfile -File ./scripts/qa/verify-windows-workspace.ps1 -WorkspaceOnly `
    -ExpectedDpi 96 -ProfileBenchmark -BenchmarkRounds 3 *>&1 |
    Tee-Object -FilePath (Join-Path $orcaEvidence 'profile-windows.log')
```

The uninstrumented run measures end-to-end latency, timer delays, CPU, RSS and queue depth. The optional profiler adds per-pane wall times for completed ConPTY reads, queue put and get attempts, ANSI parser calls and Tk draws. Queue samples include blocked puts and empty get attempts. The reader can block on the OS and overlap work on the Tk thread. A read already in progress when profiling attaches and a read still blocked at completion are outside the phase sample. Use the existing Tk timer's P95, P99 and max to measure event scheduling delay. Compare each scenario to its own repeated baseline and keep the integrity assertions enabled. [Existing Windows timings](windows-native-test-results.md)

The two CI runs used the same workload and both reported 96 DPI. Their elapsed times changed from 7.739 to 7.460 seconds for one pane, 5.229 to 4.957 seconds for a horizontal split, and 4.778 to 5.018 seconds for a vertical split. The mixed changes on separate hosted VMs do not establish a regression or identify a bottleneck. New Windows phase results are NOT VERIFIED.
