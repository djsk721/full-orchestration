# Release candidate platform compatibility

**PASS** denotes a result executed in the stated environment. **PARTIAL** identifies a verified subset or a missed target. **FAIL** denotes an executed check with a failing result. **NOT VERIFIED** denotes missing execution evidence. **NOT APPLICABLE** identifies an excluded check or absent release target.

| Feature | Linux | Windows | macOS |
| --- | --- | --- | --- |
| TypeScript Core, Python parity and configuration contracts | PASS | NOT VERIFIED | NOT VERIFIED |
| Tk first-run, project and Provider setup, DAG and Git approval | PASS, real Tk, Git and SQLite with scripted model responses | NOT VERIFIED | NOT VERIFIED |
| Python Supervisor, SQLite, Agent, cancellation and restart | PASS | NOT VERIFIED, source and frozen tests prepared | NOT VERIFIED |
| Provider routing, Managed and installed OpenCode Harness | PASS, local API fixture with actual job and process execution | NOT VERIFIED | NOT VERIFIED |
| Installed OpenCode and Codex interactive CLI | PASS, isolated offline startup, focus, input, resize and exit | NOT VERIFIED, manual acceptance prepared | NOT VERIFIED |
| MCP policies, uncertain writes and durable checkpoints | PASS, controlled tool and loopback fixtures against actual Supervisor and Store | NOT VERIFIED | NOT VERIFIED |
| ANSI, scrollback, interactive input and process containment | PASS, real POSIX PTY, including Unicode clipboard and child cleanup | NOT VERIFIED, ConPTY and Job Object tests prepared | NOT VERIFIED |
| 8,000-line output and multi-session performance | PARTIAL, throughput and integrity passed. Some multi-session event delays exceeded 90 ms. | NOT VERIFIED | NOT VERIFIED |
| Korean IME and Windows scales 100%, 125%, 150% | NOT APPLICABLE | NOT VERIFIED, manual acceptance prepared | NOT APPLICABLE |
| SSH shell and Worker clients | PASS, pinned real loopback OpenSSH, Python and TypeScript | NOT VERIFIED, native SSH profile setup prepared | NOT VERIFIED |
| Headless Worker server | PASS, transport outage, reconnect and Supervisor restart | NOT APPLICABLE, Linux release target | NOT APPLICABLE, Linux release target |
| File and Git Worktree policy, branch movement and merge safety | PASS, real Git, Unicode and long paths | NOT VERIFIED, junction and read-only-file checks prepared | NOT VERIFIED |
| Read-only Electron | PASS, source, unpacked and AppImage extract-and-run | NOT VERIFIED | NOT VERIFIED |
| Native release packaging | PASS, x64 AppImage generated and opened in extract-and-run mode | NOT VERIFIED, NSIS lifecycle and standalone Tk package checks prepared | NOT APPLICABLE, no declared package target |
| Authenticated external inference and GPU | NOT APPLICABLE | NOT APPLICABLE | NOT APPLICABLE |

Linux passed 99 regression checks with two Windows-only skips. Platform-independent checks apply to the Linux execution reported above. Windows readiness requires native CI evidence, followed by manual IME and scale acceptance on a Windows desktop. macOS behavior remains unmeasured.

See [terminal measurements](terminal-performance-qa.md), [Windows CI and packaging](windows-ci-readiness.md) and [native Windows verification](windows-native-ux-validation.md).
