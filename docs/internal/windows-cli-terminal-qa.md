# Windows OpenCode and Codex terminal QA

**Interactive Windows CLI status NOT VERIFIED.** This pass has no native Windows CLI logs, paths or screenshots. Existing Linux CLI startup evidence and Windows console-fixture CI results describe separate environments. Authenticated inference remains NOT VERIFIED.

The Workspace accepts an explicit OpenCode `provider/model` profile. On Linux, OpenCode 2.2.7 displayed `GPT-5.6 Luna · OpenAI` and persisted the disposable project path after the POSIX PTY adapter corrected an inherited `PWD`. The OpenCode configuration and Workspace registry retained their original contents. Windows OpenAI metadata and actual inference remain unverified. [Dedicated GPT verification report](windows-opencode-gpt-integration.md)

The Linux offline check used the installed OpenCode and Codex binaries, an isolated profile and `--no-daemon` for Codex. Startup, both splits, focus, OpenCode Korean draft copy/paste, session reuse and process cleanup passed. Windows Microsoft IME and installed terminal behavior remain pending.

## Discovery defect

| Item | Status | Evidence |
| --- | --- | --- |
| Shim reported as an available CLI | FAIL before the fix | A reproduced discovery contract with `codex.cmd` ahead of `codex.exe` returned the shim. The Win32 process policy rejects that suffix. |
| Windows CLI path selection | PASS in a local contract test | Discovery selects `.exe` or `.com`, and reports a shim-only package unavailable. POSIX executable scripts still resolve. A native PATH/PATHEXT test is prepared and requires Windows. |
| Native ConPTY startup-model fixture | NOT VERIFIED | The Windows desktop smoke now checks the exact Mini arguments and Unicode project path, sends interactive input, reopens the same session, and checks process exit. It simulates OpenCode and uses native ConPTY. |
| Windows interactive behavior after the fix | NOT VERIFIED | The real OpenCode and Codex consoles must be exercised on Windows. The retained installer predates this change. |

To reproduce with the updated tests, run `py -3 -m unittest discover -s tests -p test_workspace.py -v`. The Windows operator can diagnose mismatches with the [environment inventory](windows-desktop-acceptance.md#record-the-windows-environment). Compare `path_lookup` with `workspace_path`. A shell shim alone still requires a native executable on PATH. The app's launch policy is unchanged.

## Run the live checks

Use the disposable Windows account, a disposable Git repo and CLI test profiles with network egress blocked. Stage the CLIs before disconnecting. Confirm `where.exe opencode` and `where.exe codex`, and run each native executable with `--version`. Attach executable versions and whether the initial screen reached an editable input field. Capture any startup screen that prevents interaction. Prompts stay unsubmitted.

1. Open OpenCode and Codex as separate Workspace tabs. Record their own process PIDs and switch tabs several times. Select each existing CLI again and confirm it focuses the same tab or pane with the same PID.
2. Put the existing tabs into both horizontal and vertical splits. Drag the divider and resize the main window. Verify both displays redraw and the selected pane receives focus.
3. Enter and delete an English and Korean draft in each input field. Copy and paste between panes. Capture ANSI colors and full-screen redraws. Exercise long numbered ANSI output using the offline console fixture separately from the interactive CLI draft. Compare the final marker and scrollback.
4. Choose **View → Separate terminals into tabs** to move the second pane into a separate tab before the close-one check. End one session and confirm the other process and input field remain usable. End the final session and check the recorded PID tree exited. Process identities can be recorded by `Get-CimInstance Win32_Process | Select-Object Name,ProcessId,ParentProcessId` and checked afterward with `Get-Process -Id <recorded-PIDs> -ErrorAction SilentlyContinue`. Save only rows for the processes owned by the test.

Record whether the run used source or NSIS. Save startup, both splits, draft input, ANSI output and cleanup evidence. A login prompt or model refusal is an observed limit of startup or interaction. It carries no inference result.
