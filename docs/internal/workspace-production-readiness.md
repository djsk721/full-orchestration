# Workspace production readiness

**Overall PARTIAL.** The feature branch is published and both Linux and Windows automated release checks passed in GitHub Actions. The [release decision](orca-workspace-release-candidate.md) tracks the manual desktop gates.

| Release gate | Status | Candidate evidence |
| --- | --- | --- |
| Linux regression | PASS | 53 Python, 25 TypeScript, six Tk and 15 Electron checks. Two Windows-only Python cases skipped. |
| Linux packaging | PASS | Native x64 unpacked build and AppImage. Five Electron tests each from source, unpacked output and AppImage extract-and-run. |
| Linux 8,000-line throughput | PASS | The comparable soak median was 1.704 s, versus 2.535 s before optimization. |
| Linux input integrity, resource stability and tail latency | PARTIAL | Zero missing or duplicated numbered rows. Every candidate soak reaped 360 PTYs. The soak maxima were 77–80 ms, and the multi-session benchmark documented higher tail delays. |
| Supervisor, SQLite, Provider, MCP, Agent, DAG, QA and Git | PASS | Local and hosted process, store and Git execution with controlled local API and tool fixtures. |
| SSH shell, Worker and remote Git | PASS | Actual pinned loopback OpenSSH with a disposable Linux Worker and repos. Earlier and current Worker formats and both clients were rechecked. |
| Linux installed offline CLIs | PASS | Both installed binaries start in disposable offline terminals, with focus, resize, clipboard and cleanup. |
| Windows installation, reinstallation and persistence | PASS | Native x64 NSIS build. Installed Tk, PowerShell, Supervisor replacement and installed Electron passed twice, with unchanged SQLite and configuration hashes through both removals. |
| Windows manual desktop release | NOT VERIFIED | Korean IME, 100%, 125%, 150% display scales and manual GUI acceptance remain open. |
| All-day terminal memory and production deployment | PARTIAL | Repeated workloads and recovery passed. Longer operating sessions remain unmeasured. |
| Authenticated inference | NOT VERIFIED | Outside this task's validation. |
| GPU and macOS | NOT APPLICABLE | Excluded. |

The [platform matrix](platform-compatibility.md) shows execution coverage. See [terminal performance](terminal-performance-qa.md), [CI execution](windows-ci-execution-report.md), [Windows packaging](windows-ci-readiness.md) and [manual Windows acceptance](windows-native-ux-validation.md).
