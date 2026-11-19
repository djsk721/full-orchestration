# Release candidate platform compatibility

**PASS** denotes an executed passing check in the stated environment. **PARTIAL** identifies a verified subset or a missed target. **FAIL** denotes an executed failing check. **NOT VERIFIED** denotes absent execution evidence. **NOT APPLICABLE** identifies an excluded check or absent target.

| Feature | Linux | Windows | macOS release |
| --- | --- | --- | --- |
| TypeScript Core, Python parity and configuration contracts | PASS | PASS | NOT APPLICABLE |
| Tk startup, first-run, Provider, DAG and Git approval | PASS, real Tk, Git and SQLite with scripted model responses | PASS, shared Tk UI suite and native Windows fixture | NOT APPLICABLE |
| Supervisor, SQLite, Agent, cancellation and restart | PASS | PASS in Python native tests, including durable restart and Job Objects | NOT APPLICABLE |
| Provider routing, Managed and installed OpenCode Harness | PASS, controlled local responses and real execution | PARTIAL, Provider routing and Managed fixture. Windows OpenCode unverified. | NOT APPLICABLE |
| Installed OpenCode and Codex interactive CLI | PASS, isolated offline startup and interaction | NOT VERIFIED | NOT APPLICABLE |
| MCP policies, uncertain writes and durable checkpoints | PASS | PASS with local fixtures on native Windows | NOT APPLICABLE |
| ANSI, native shell, scrollback, Unicode clipboard and child cleanup | PASS, real POSIX PTY | PASS, real ConPTY and tracked process cleanup | NOT APPLICABLE |
| Terminal performance | PARTIAL, throughput and integrity passed with tail latency outliers | PASS for the measured single and two-pane Windows workloads. No native before/after baseline. | NOT APPLICABLE |
| Korean IME and manual scales 100%, 125%, 150% | NOT APPLICABLE | NOT VERIFIED | NOT APPLICABLE |
| SSH shell and Worker clients | PASS, pinned real loopback OpenSSH in Python and TypeScript | PARTIAL, strict host pin contract passed. Live Windows client connection unverified. | NOT APPLICABLE |
| Headless Worker server | PASS, transport outage, reconnect and Supervisor restart | NOT APPLICABLE, Linux release target | NOT APPLICABLE |
| File and Git Worktree policy, branch movement and merge safety | PASS, real Git, Unicode and long paths | PASS, native read-only files, junctions, real Unicode Git Worktrees, candidate SHA and approval checks | NOT APPLICABLE |
| Read-only Electron | PASS, source, unpacked and AppImage extract-and-run | PASS, source, unpacked and installed twice | NOT APPLICABLE |
| Release packaging | PASS, x64 AppImage generated and executed | PASS, unsigned x64 NSIS build, startup, removal, reinstall and fixture data retention | NOT APPLICABLE |
| Authenticated external inference | NOT VERIFIED | NOT VERIFIED | NOT APPLICABLE |
| GPU | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |

Linux has 99 passing regression checks. Both native jobs and the portable TypeScript job passed on `e3236583819377e4d8a67609df8b61027f6a5eb0`. The [release candidate](orca-workspace-release-candidate.md), [native Windows results](windows-native-test-results.md) and [Actions execution report](windows-ci-execution-report.md) identify the tested commits, installer evidence and open release gates.
