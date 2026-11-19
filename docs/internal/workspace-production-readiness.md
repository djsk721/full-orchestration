# Workspace production readiness

**Overall PARTIAL.** Linux regressions and release package execution passed. The original 8,000-line workload returned to approximately 1.6 seconds. Native Windows ConPTY, Job Objects, installation, IME and display scaling remain **NOT VERIFIED**.

| Release gate | Status | Candidate evidence |
| --- | --- | --- |
| Full Linux regression | PASS | 53 Python, 25 TypeScript, six Tk and 15 Electron checks. Two Windows-only Python cases skipped on Linux. |
| Linux release packaging | PASS | Native x64 unpacked build and AppImage generated locally. Five Playwright checks each passed from source, the unpacked build and AppImage extract-and-run. |
| Original 8,000-line Linux burst | PASS | 1.58–1.70 s across three runs. Three matched pre-change runs took 2.37–2.63 s. |
| Linux Tk tail latency | PARTIAL | 79–93 ms maximum across the three optimized soak rounds. Multi-session benchmark maxima exceeded 90 ms in some runs. |
| Simultaneous output, input isolation and process cleanup | PASS | One, two and four active terminals, both splits, repeated project/tab selection, isolated input during peer output, and 360 PTYs reaped by the candidate soak. |
| Supervisor, SQLite, Provider, MCP, Agent, DAG, QA, Git | PASS | Actual Supervisor, process, SQLite and Git execution with controlled API responses or tool fixtures. |
| SSH shell, Worker and remote Git | PASS | Actual pinned loopback OpenSSH with disposable Linux Worker and repos. The current client read earlier and current Worker data. The TypeScript client read the same run and cursor as Python. |
| Installed interactive CLIs and OpenCode Harness | PASS | Real binaries with isolated profiles. CLI terminal sessions started offline. The OpenCode job used a scripted loopback API for tool reads, cancellation and error propagation. |
| Windows native CI, standalone Tk and NSIS lifecycle | NOT VERIFIED | Windows workflow definition and isolated test procedures prepared. Native job and manual acceptance await a Windows host. |
| All-day terminal memory and production deployment | PARTIAL | Repeated workload and recovery passed. Longer operating sessions remain unmeasured. |
| GPU and authenticated inference | NOT APPLICABLE | Excluded from this phase. |

The 98-pass baseline was 52 Python, 25 TypeScript, six Tk and 15 Electron. This run adds one Python regression for cached pyte handlers. The integrated Tk scenario also checks real keyboard delivery to one pane while another writes sustained output. No Linux regression failed. The two skipped cases require real Windows directory junctions and the read-only file attribute.

```bash
npm run verify -- --ui --package
npm run verify -- --core-only
python tests/smoke_workspace_ssh.py --typescript --legacy-ref e76e876
ORCHESTRA_LANG=ko xvfb-run -a python tests/smoke_integrated_workspace.py --ssh
```

The [platform matrix](platform-compatibility.md) shows execution coverage. See [terminal performance and multi-session QA](terminal-performance-qa.md), [Windows CI and packaging readiness](windows-ci-readiness.md) and [Windows native acceptance](windows-native-ux-validation.md) for the matching release evidence.
