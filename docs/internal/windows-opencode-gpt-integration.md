# OpenCode with authenticated OpenAI GPT

**Windows acceptance NOT VERIFIED.** The operator redirected this pass to Linux. The OpenCode executable, source revision, provider account and catalog on the Windows workstation remain unverified. The earlier Windows screenshot establishes main-window rendering only.

| Test | Result | Evidence |
| --- | --- | --- |
| OpenCode installation | PARTIAL | Linux has a working native OpenCode 2.2.7 binary. The Windows executable path, launcher type and version are unknown. |
| OpenAI Provider discovery | NOT VERIFIED | Windows could not report the existing OpenAI profile or its effective endpoint. |
| GPT model discovery | NOT VERIFIED | No exact Windows `openai/<model-id>` has been observed. |
| Authentication verification | NOT VERIFIED | The Windows account's OpenAI authentication was unavailable for inspection. |
| Actual Windows GPT inference | NOT VERIFIED | Zero Windows hosted requests and no observed response, duration or usage. |
| Workspace GPT model selection | PARTIAL | The UI now selects a registered, trusted OpenCode profile and supplies the complete model ID. Exact argument transfer is covered locally. Linux OpenCode validated the actual GPT selection in the authorized Mini run. The corresponding Windows launch is unverified. |
| Workspace terminal interaction | PARTIAL | Linux tests exercised the real OpenCode startup and the Tk terminal contracts. Windows ConPTY with the installed CLI and selected GPT path remains unverified. |
| Codex concurrent terminal | PARTIAL | The Linux offline installed-CLI smoke exercises simultaneous Codex and regular OpenCode tabs. Codex's configured model and invocation stayed unchanged. Windows interaction remains unverified. |
| Windows UI verification | NOT VERIFIED | Korean IME and the 100%, 125% and 150% scales still need native desktop evidence. |
| Regression tests | PARTIAL | The Windows PATH/PATHEXT case and the native ConPTY startup-model case are ready to run on Windows. The latter substitutes a simulated OpenCode executable and asserts the app-generated arguments, the Unicode working directory, input, session reuse and process exit. |

## Linux OpenAI verification

| Test | Result | Evidence |
| --- | --- | --- |
| Linux environment and application source | PASS | Ubuntu 22.04.5 LTS x86-64, kernel `6.8.0-149-generic`, and `feature/orca-workspace` at `08b1d3d` with the uncommitted OpenCode and terminal changes. |
| OpenCode and Provider metadata | PASS | OpenCode 2.2.7, native x86-64 ELF. The isolated `auth list` recognized the saved OpenAI OAuth connection, and the authenticated catalog included `openai/gpt-5.6-luna`. |
| Real OpenCode Mini in the Workspace | PASS | The application started `mini --standalone --model openai/gpt-5.6-luna` in a disposable Git directory. Mini displayed `GPT-5.6 Luna · OpenAI`, its persisted session recorded the same directory, and reselecting the model reused the existing process. The registry, disposable project files and OpenCode configuration retained their contents. |
| Offline Linux terminal interaction | PASS | Real OpenCode and Codex CLI 0.170.0 ran concurrently in the isolated Workspace. Both splits, focus, OpenCode Korean draft copy/paste, session reuse and process cleanup passed. The harness selected `TERM=xterm-256color` and used Codex `--no-daemon` to avoid the user's shared server. No prompt was submitted in this check. |
| POSIX working-directory regression | PASS | Before the fix, Mini persisted the parent application's repository from inherited `PWD` despite the correct process working directory. The POSIX adapter now sets `PWD` after changing directories. The native PTY contract fails with the old adapter and passes with the fix. |
| Single-request guard | PASS | A local HTTP 429 fixture received one request with zero tool definitions and recorded a retry veto. A separate network-isolated Workspace run reached the same guard for the real model's `https://chatgpt.com/backend-api/codex/responses` route and vetoed the DNS-failure retry. These checks made zero hosted requests. |
| Hosted inference through Linux Workspace | PASS | The explicitly authorized 2026-11-20 run sent one authenticated request from the integrated OpenCode Mini pane. The native `openai` route returned HTTP 200 with zero retries. |
| Successful response reception | PASS | OpenCode persisted one assistant message for `openai/gpt-5.6-luna` with the exact text `ORCHESTRATION_GPT_TEST_OK` and marked the session `succeeded`. The screen scraper did not capture the exact rendered response, so the persisted transcript is the evidence for the response text. |

### Authorized Linux run on 2026-11-20

| Evidence | Observed value |
| --- | --- |
| CLI invocation | OpenCode 2.2.7 via Workspace `mini --standalone --model openai/gpt-5.6-luna` |
| Working directory | `/tmp/orchestra-integrated-workspace-gqvgtd3r/second-project`, an existing isolated Git fixture mounted read-only. The process and OpenCode session database both recorded that directory. |
| Authentication and routing | Saved OpenAI OAuth credential in an isolated test profile with refresh disabled. The native `openai` provider sent the request to `https://chatgpt.com/backend-api/codex/responses` over certificate-validated TLS. HTTP 200 confirmed the provider accepted the authenticated request. |
| Request count | 1 authenticated inference request, 0 retries, 0 tool invocations. The guard verified the fixed test prompt and removed tool definitions. |
| Prompt and response | `Reply with exactly: ORCHESTRATION_GPT_TEST_OK` → `ORCHESTRATION_GPT_TEST_OK` |
| Duration | 1.974 s from submission to completed session; 1.214 s from HTTP dispatch to response headers. |
| Token usage | 29 input, 12 output, 0 reasoning, 0 cache-read, and 0 cache-write tokens, as recorded by OpenCode. |
| Session operation and cleanup | Mini accepted a new draft without submitting it. The pane and its inspected child processes exited. Test project files, CLI configuration, and Workspace model registry retained their contents. |
| Final result | **PASS** for Linux model selection, authenticated OpenAI inference, and persisted response reception. |

### Authorized Linux run on 2026-11-22

| Evidence | Result | Observed value |
| --- | --- | --- |
| CLI and model selection | PASS | Linux Workspace on `feature/orca-workspace` at `43f214e` with local changes started native OpenCode 2.2.7 in `mini --standalone --model openai/gpt-5.6-luna` mode. Mini showed Luna and OpenAI. |
| Working directory | PASS | `/tmp/orchestra-integrated-workspace-gqvgtd3r/second-project`, the existing isolated Git fixture. The OpenCode process and its persisted session both reported this directory. The fixture was mounted read-only and its tracked files retained their hashes. |
| Authentication and routing | PASS | An isolated profile recognized the existing, unexpired OpenAI OAuth entry and exact catalog model. The native OpenAI provider resolved to `https://chatgpt.com/backend-api/codex/responses`. Direct TLS certificate and hostname verification passed. The provider accepted the Bearer-authenticated request with HTTP 200. |
| One-request limit | PASS | The temporary test profile selected the native HTTP transport and installed request and retry hooks. A separate network-isolated run checked the same endpoint and vetoed a DNS-failure retry, with zero hosted requests. The live run recorded **1** hosted request, **0** retries and **0** tool invocations. The guard blocked automatic title generation and limited the outbound body to the specified prompt and a generic instruction. |
| Response reception | PASS | `Reply with exactly: ORCHESTRATION_GPT_TEST_OK` returned `ORCHESTRATION_GPT_TEST_OK`. The OpenCode transcript recorded provider `openai`, model `gpt-5.6-luna`, and session outcome `succeeded`. |
| Duration and usage | PASS | 2.619 s from prompt submission to completed session and 1.126 s from HTTP dispatch to response headers. OpenCode recorded 27 input tokens, 12 output tokens, and zero reasoning, cache-read and cache-write tokens. |
| Session operation and cleanup | PASS | Mini accepted an unsubmitted draft after the response. The Workspace pane and its inspected child processes closed. The existing CLI and model configuration remained intact. |
| Final result | **PASS** | Linux model selection, authenticated hosted inference, and exact response reception each verified under this authorization. |

## Current Agent and Windows compatibility

The new Agent pipeline ran on Linux with the installed OpenCode CLI and a deterministic loopback API. It used an explicit model across a real Supervisor DAG and captured OpenCode JSON output, HTTP 401 handling, cancellation, and a role-specific planning handoff. That check made zero hosted requests. The individually authorized interactive runs above provide the hosted inference evidence. [Agent E2E evidence](multi-agent-orchestration-e2e.md)

| Windows item on the current working tree | Status | Procedure and expected evidence |
| --- | --- | --- |
| Source revision and patch application | NOT VERIFIED | Record the actual Windows checkout or ZIP origin, apply the verified patch in a disposable copy, and keep the original settings and credentials. |
| Native OpenCode and Codex discovery | NOT VERIFIED | Record `Get-Command opencode,codex -All` and execute `test_workspace.py` on Windows. The simulated Linux contract passed. |
| Safe launch, explicit model and cwd | NOT VERIFIED | Run the native ConPTY model-selection fixture and then repeat with the actual Windows OpenCode executable. Verify the exact argv, cwd, selective reuse and process exit. The POSIX `PWD` correction applies on Linux. Windows uses the explicit process working directory. |
| Unicode, Korean IME, GUI state and cleanup | NOT VERIFIED | Run the native smoke at 96, 120 and 144 DPI with an interactive desktop. Collect the screenshots, IME acceptance and cleanup evidence in the existing procedure. |
| Supervisor recovery | NOT VERIFIED | Run the current `test_orchestra.py` and `test_platform_contracts.py` in a disposable profile and capture the recovery and cancellation results. |

```powershell
py -3 -m unittest discover -s tests -p test_workspace.py -v
py -3 -m unittest discover -s tests -p test_orchestra.py -v
py -3 -m unittest discover -s tests -p test_platform_contracts.py -v
pwsh -NoProfile -File .\scripts\qa\verify-windows-workspace.ps1 -WorkspaceOnly -ExpectedDpi 96
```

Repeat the Workspace command with `120` and `144` after setting Windows display scaling to 125% and 150%, respectively. Published CI predates these uncommitted changes. [Native acceptance procedure](windows-native-ux-validation.md)

## Model selection implemented

Register a new profile via **Provider setup → OpenCode → Advanced**. Select the trusted native executable. Enter the complete ID discovered by OpenCode, including the provider prefix. Clear **Use as the default model** before saving. Open the intended disposable project and use **Terminal → AI CLI → OpenCode startup model → profile · provider/model**. The selected OpenCode session uses the profile's executable and passes the exact registered ID. The session footer reports the requested startup model. Existing OpenCode authentication and config storage remain owned by the CLI. The plain **OpenCode** action still launches the CLI's usual full-screen session. Existing selected sessions use the current focus and restart confirmation behavior.

OpenCode 1.x launches its interactive interface with `--model`. The installed 2.2.7 full-screen entry point lacked that flag. Explicit-model 2.x sessions use `mini --standalone --model`, the interactive Mini command with its private server. This uses an explicit CLI selection instead of changing the global model or relying on a default. The real offline Linux test verified 2.2.7 Mini startup. The 1.x launch path was tested at argument level. [OpenCode command options](https://opencode.ai/docs/cli/commands/) · [OpenCode model selection](https://opencode.ai/docs/models/)

## Windows discovery and a separately authorized request

The one-request authorization above applied to Linux only and was consumed by that run. Any Windows inference requires separate authorization.

Record the source revision before synchronizing. The source and QA files covered by the patch had identical baselines at `e3236583819377e4d8a67609df8b61027f6a5eb0` and `08b1d3d`. The accompanying `orchestra-agent-workspace.patch` applied to a fresh source snapshot without `.git`. Its SHA-256 is `09bb5c90235006b4889c9125b3a7af414a6dc9dd83746b3f825b9c5da1aaa924`. Apply it to a disposable copy to preserve the original project and settings. A failed forward check means the patch cannot be applied to that copy as written. Check for already applied hunks or a different baseline before making changes.

```powershell
Set-Location -LiteralPath (Read-Host 'Path to the disposable Windows source copy')
if (Test-Path -LiteralPath .git) {
    git rev-parse HEAD
    git status --short
} else {
    'Source folder has no .git metadata'
}
$orcaPatch = (Resolve-Path -LiteralPath (Read-Host 'Path to orchestra-agent-workspace.patch')).Path
if ((Get-FileHash -LiteralPath $orcaPatch -Algorithm SHA256).Hash -ne '09bb5c90235006b4889c9125b3a7af414a6dc9dd83746b3f825b9c5da1aaa924') {
    throw 'Source patch checksum mismatch'
}
git apply --reverse --check -- $orcaPatch 2>$null
if ($LASTEXITCODE -eq 0) {
    'Patch already present'
} else {
    git apply --check -- $orcaPatch
    if ($LASTEXITCODE -ne 0) { throw 'Source differs from the expected baseline' }
    git apply -- $orcaPatch
    if ($LASTEXITCODE -ne 0) { throw 'Patch failed' }
    git apply --reverse --check -- $orcaPatch
    if ($LASTEXITCODE -ne 0) { throw 'Applied source check failed' }
}
```

1. Record the Windows version, the trusted native launcher and the existing account. Run the following from the disposable working directory chosen for the acceptance check. Keep any account identifiers, authentication file contents and credentials out of the report.

   ```powershell
   Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber
   Get-Command opencode -All | Select-Object Name,CommandType,Source
   Get-Command opencode.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object Source
   opencode --version
   opencode auth list
   opencode models openai
   opencode mini --help
   ```

   If discovery returns an npm `.cmd` shim, use `npm root -g` to locate the installed package and look inside it for a native `.exe`. Select the full executable path in Provider setup and record the version from that same binary. If the model filter is unsupported, use `opencode models | Select-String '^openai/'`. Treat the listing and authentication entry as metadata until inference succeeds. Mini may display a requested ID even when the ID is absent from the catalog. Match the full ID in the acceptance directory and confirm the actual hosted OpenAI route. [OpenCode authentication and catalog commands](https://opencode.ai/docs/cli/commands/)

2. After separate authorization, submit the one allowed message directly from the explicit-model OpenCode pane. Use an empty disposable project and verify the effective test configuration denies tools and file access, loads no MCP servers, plugins or external instructions, and uses the verified hosted provider. Keep the repo and personal files outside the test directory. Stop if those effects or retry behavior cannot be controlled. Select the exact model in the Workspace, confirm the CLI's model display, then submit only `Reply with exactly: ORCHESTRATION_GPT_TEST_OK`. Record the response, request status, CLI/provider/model, elapsed time, and usage if shown. If it fails, capture the sanitized error and stop.
3. If the one request is made using `opencode run --model <exact verified ID> --format json` instead, apply the same isolation and use `--standalone` where supported. Record its evidence as direct CLI inference. Verify the Workspace startup model and terminal interaction separately. Workspace inference stays PARTIAL at most without a response from that path. The direct and Workspace variants share a one-request budget.

## Separate evidence

The Linux real-binary check used an isolated CLI profile, a synthetic model name and a network namespace with no outbound route. It exercised startup and reused the same PTY, checked that config and registry bytes were unchanged, and closed the child. It sent no prompt. Python Supervisor, Git, QA and MCP regressions use their existing disposable repositories and deterministic fixtures. See [Windows CLI terminal QA](windows-cli-terminal-qa.md) and [Windows orchestration QA](windows-orchestration-e2e.md).

After the POSIX change, the previous Linux baseline passed 106 checks. The current Agent validation passed 114 checks across 67 Python, 26 TypeScript, six Tk and 15 Electron cases. Three Windows-only cases skipped. The real loopback SSH Worker passed. The Tk integration exercised the explicit OpenCode model, PTY reuse, configured QA and Git approval. [Current release verification](orca-workspace-release-candidate.md)
