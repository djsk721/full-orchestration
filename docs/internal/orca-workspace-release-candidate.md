# Orca Workspace release candidate

**Published candidate CI PASS. Final desktop release NO-GO.** The overall gate remains **PARTIAL** pending Windows manual desktop acceptance and native verification of the local CLI discovery correction.

The verified application and build commit is `e3236583819377e4d8a67609df8b61027f6a5eb0` on `feature/orca-workspace`. A documentation-only follow-up records this evidence. [Cross-platform verification run 44573538314](https://github.com/djsk721/full-orchestration/actions/runs/44573538314)

| Gate | Status | Evidence |
| --- | --- | --- |
| Published feature branch | PASS | `feature/orca-workspace` tracks `origin/feature/orca-workspace`. The remote SHA matched each pushed candidate. |
| Local Linux and GitHub Linux | PASS | The published CI baseline passed 99 checks. The current Linux working tree passed 114 checks across 67 Python, 26 TypeScript, six Tk, and 15 source and packaged Electron cases. Three Windows-only Python tests skipped. |
| Linux terminal output integrity | PASS | A fresh 8,000-line round across one, two horizontal, two vertical, and four concurrent panes verified all nine streams and process cleanup. This round measured the one-pane completion at 766.620 ms. The Windows performance comparison still requires native evidence. |
| Linux SSH and packaging | PASS | Actual OpenSSH transport, unpacked Electron and AppImage retained their regression coverage. |
| Automated Windows | PASS | The Windows job passed 52 Python, 25 TypeScript, six Tk, five source and five unpacked Electron checks, plus the ConPTY and Job Object tests. Three Linux-only Python cases were skipped. |
| Windows NSIS lifecycle | PASS | Fresh installation and reinstallation opened both installed apps. Both Tk runs started PowerShell and recovered the Supervisor, and both installed Electron runs passed all six checks. SQLite and four configuration files retained their hashes after both removals. |
| Retained NSIS installer integrity | PASS | Downloaded and independently hashed on 2026-11-20. The 133,477,760-byte executable matches SHA-256 `4bfebdcd108b65ba63c3ecea31c7235f2c50e1bcbcc68f84f5ff6d8a4c24aa32`. |
| Windows operator startup rendering | PASS | User-supplied startup capture shows the main Korean Workspace and Supervisor running badge. The user reports a source launch through Python. |
| Windows Korean IME, display scaling and desktop usability | NOT VERIFIED | Composition evidence, observed scale and installed-app checks at 100%, 125% and 150% are outstanding. |
| Installed Windows OpenCode and Codex | NOT VERIFIED | Offline interactive startup, input, both splits, resize, focus and process cleanup are outstanding on Windows. |
| Installed Windows Workspace end to end | NOT VERIFIED | Prior CI exercised the source workflow and installed lifecycle separately. The installed workflow and SSH on an authorized endpoint require desktop execution. |
| Windows terminal performance | PARTIAL | Two comparable Windows CI runs measured 7.739 and 7.460 seconds for 8,000 lines in one pane. Horizontal and vertical results moved in opposite directions. Optional phase-level profiling awaits a Windows run. |
| Deterministic multi-agent pipeline | PASS | Actual OpenCode and Supervisor executed Planner, Developer, Reviewer and local QA with loopback model responses. One approval integrated the exact verified candidate in a disposable repository. [Workflow and candidate evidence](multi-agent-orchestration-e2e.md) |
| Authenticated OpenAI GPT in OpenCode Mini on Linux | PASS | The separately authorized historical request received HTTP 200 for `openai/gpt-5.6-luna` and its saved response matched the requested marker in 1.974 seconds. The authorization was consumed. [GPT evidence](windows-opencode-gpt-integration.md) |
| Authenticated GPT via Supervisor Agents | NOT VERIFIED | The current task made zero hosted calls. The bounded read-only Planner and Reviewer test requires separate authorization. [Runtime QA and proposed test](agent-runtime-and-review-qa.md) |
| GPU or macOS release | NOT APPLICABLE | Excluded. |

The working tree aligns Windows CLI discovery with the native executable policy and adds explicit OpenCode model selection. Linux PTY and Attached launches use the intended working directory. Current Agent changes reject ineligible routes, pass advisory planning and verified change context to downstream nodes, preserve failed review output, and bind QA evidence to the candidate and approval revision. The retained NSIS installer remains tied to the earlier CI commit. [Routing analysis](gpt-agent-routing-analysis.md) · [Failure and recovery](orchestration-failure-recovery.md)

See the [desktop acceptance report](windows-desktop-acceptance.md), [manual desktop procedure](windows-native-ux-validation.md), [execution report](windows-ci-execution-report.md), [native Windows results](windows-native-test-results.md), [terminal measurements](terminal-performance-qa.md) and [compatibility matrix](platform-compatibility.md).
