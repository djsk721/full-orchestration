# Orca Workspace release candidate

**Automated release candidate PASS. Final desktop release NO-GO.** The overall gate remains **PARTIAL** pending Windows manual desktop acceptance.

The verified application and build commit is `e3236583819377e4d8a67609df8b61027f6a5eb0` on `feature/orca-workspace`. A documentation-only follow-up records this evidence. [Cross-platform verification run 44573538314](https://github.com/djsk721/full-orchestration/actions/runs/44573538314)

| Gate | Status | Evidence |
| --- | --- | --- |
| Published feature branch | PASS | `feature/orca-workspace` tracks `origin/feature/orca-workspace`. The remote SHA matched each pushed candidate. |
| Local Linux and GitHub Linux | PASS | The 99-check baseline was reproduced locally and in GitHub Actions with 53 Python, 25 TypeScript, six Tk and 15 Electron passes. Two Windows-only Python cases were skipped. |
| Linux terminal performance and output integrity | PARTIAL | Three repeated runs preserve the throughput gains and verify zero missing or duplicate output. Tail latency still varies on the shared desktop. |
| Linux SSH and packaging | PASS | Actual OpenSSH transport, unpacked Electron and AppImage retained their regression coverage. |
| Automated Windows | PASS | The Windows job passed 52 Python, 25 TypeScript, six Tk, five source and five unpacked Electron checks, plus the ConPTY and Job Object tests. Three Linux-only Python cases were skipped. |
| Windows NSIS lifecycle | PASS | Fresh installation and reinstallation opened both installed apps. Both Tk runs started PowerShell and recovered the Supervisor, and both installed Electron runs passed all six checks. SQLite and four configuration files retained their hashes after both removals. |
| Windows Korean IME, display scaling and desktop usability | NOT VERIFIED | Manual release gate. |
| Authenticated external inference | NOT VERIFIED | Outside this task's validation. |
| GPU or macOS release | NOT APPLICABLE | Excluded. |

See the [execution report](windows-ci-execution-report.md), [native Windows results](windows-native-test-results.md), [terminal measurements](terminal-performance-qa.md) and [compatibility matrix](platform-compatibility.md).
