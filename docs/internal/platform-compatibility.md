# Release candidate platform compatibility

**PASS** denotes a result executed in the stated environment. **PARTIAL** identifies the verified subset. **FAIL** denotes an executed check with a failing result. **NOT VERIFIED** denotes missing execution evidence. **NOT SUPPORTED** describes an unavailable product target.

| Feature | Linux | Windows | macOS |
| --- | --- | --- | --- |
| Electron history, task search, filters, IPC and recovery | PASS, source and native packages | NOT VERIFIED | NOT VERIFIED |
| Tk registration, Provider profiles, DAG and Git approval | PASS, scripted inference and real execution | NOT VERIFIED | NOT VERIFIED |
| Python Supervisor, SQLite, cancellation and restart | PASS | NOT VERIFIED | NOT VERIFIED |
| TypeScript policies and Python/TypeScript contract parity | PASS | NOT VERIFIED | NOT VERIFIED |
| Provider selection and Harness execution | PARTIAL, installed OpenCode and Managed via loopback API | NOT VERIFIED | NOT VERIFIED |
| Authenticated hosted inference | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |
| MCP Gateway and uncertain external writes | PARTIAL, HTTP loopback and actual local state journal | NOT VERIFIED | NOT VERIFIED |
| Native terminal and process containment | PASS, POSIX PTY and process groups | NOT VERIFIED, ConPTY and Job Objects | NOT VERIFIED |
| SSH shell and Worker client | PASS, real local OpenSSH server | NOT VERIFIED | NOT VERIFIED |
| Worker server | PASS, transport outage and Supervisor restart | NOT SUPPORTED | NOT SUPPORTED |
| Git Worktrees, branch movement and merge safety | PASS, real Git, Unicode and long paths | NOT VERIFIED | NOT VERIFIED |
| Unpacked and packaged app | PASS, AppImage extract-and-run and unpacked preview | NOT VERIFIED, unpacked, NSIS, installed startup and data retention | NOT SUPPORTED, no declared packaging target |
| GPU | NOT VERIFIED, excluded from candidate scope | NOT VERIFIED | NOT VERIFIED |

**Linux:** local candidate regression passes. The separate hosted-provider acceptance gate remains open.

**Windows:** blocked pending an actual Windows run. The [native verification procedure](windows-native-verification.md) reuses the shared suite and checks the installed application.

**macOS:** outside this release. The declared packaging targets are Linux AppImage and Windows NSIS, and the verification workflow has Linux and Windows jobs. No macOS release blocker is inferred from these results.

**Overall:** blocked on Windows native evidence and authenticated external inference.
