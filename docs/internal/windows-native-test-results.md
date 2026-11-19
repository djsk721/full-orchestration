# Native Windows test results

The Windows matrix ran under GitHub Actions on Windows Server 2025 x64, image `windows-2025-vs2026`. The first execution stopped at Python setup. Subsequent runs use CPython 3.11.9, Node.js 24.14.1 and a Windows-specific pywinpty dependency. The native runner shows what was executed on Win32. Interactive Korean IME and manual display acceptance remain separate.

| Area | Observed automated result | Evidence |
| --- | --- | --- |
| Python/Node setup, TypeScript build and native test execution | PASS | CPython 3.11.9 and npm dependency setup completed. The Windows TypeScript suite passed all 25 cases. |
| Job Objects and Python process recovery | PASS | The timeout and hard-owner-exit cases launched real descendants and verified cleanup. Supervisor crash recovery and detached reconnect tests passed on Windows. |
| Windows paths, NTFS read-only files and junction protection | PASS | Native read-only and junction cases passed. Canonical short-path comparison failures in separate Git and MCP test fixtures were corrected. |
| QA revision, candidate SHA, MCP write controls and SSH pin policy | PASS | Shared native test process passed stale-approval, candidate-change, concurrent approval and MCP uncertain-write tests. The SSH pin contract checked strict flags and rejected unpinned profiles. Live OpenSSH endpoint verification is covered by Linux evidence. |
| ConPTY adapter input and resize | PASS | The shared Windows adapter test created a real ConPTY and verified dimensions and console response. |
| Source Tk and desktop ConPTY workload | PASS | Tk 8.6.12, pywinpty 3.1.2. Korean paths and clipboard round-trip, shell cancellation, both split directions, ConPTY dimensions, child exit and passive layout restore passed. |
| NSIS generation | PASS | Electron Builder produced the x64 per-user installer containing both the frozen workspace and the read-only monitor. |
| Installed workspace and monitor lifecycle | PASS | Fresh install and reinstall both launched Tk, its bundled Supervisor, a local PowerShell terminal and the Electron monitor. The Supervisor restarted after an owned-child hard termination. Both uninstalls preserved the SQLite, registry, workspace, language/theme and layout fixture hashes. |
| Korean IME and all manual Windows GUI acceptance | NOT VERIFIED | Requires an interactive Windows desktop. See the [manual desktop checklist](windows-native-ux-validation.md). |
| GPU validation | NOT APPLICABLE | Excluded. |

## Native Windows terminal measurements

The [third Windows job](https://github.com/djsk721/full-orchestration/actions/runs/44572159235/job/135729896005) reported native DPI 96. The workload streamed 8,000 colored lines per session and checked the last row's Tk color tag and an ordered suffix of the visible buffer plus 1,500 history rows. The Win32 console can translate the wire stream. These checks establish integrity over the retained rows. Overall Linux raw-stream coverage is reported separately.

| Workload | Elapsed | Tk median / P95 / P99 / max | Desktop CPU | Start → peak RSS | Sampled queue / history |
| --- | ---: | ---: | ---: | ---: | --- |
| One | 7.739 s | 3.6 / 24.8 / 39.0 / 91.9 ms | 7.08 s | 61.0 → 65.7 MiB | 39 chunks / 1,500 rows |
| Two, horizontal | 5.229 s | 10.4 / 20.2 / 29.7 / 34.4 ms | 6.78 s | 65.8 → 74.5 MiB | 41, 45 chunks / 1,500 rows per pane |
| Two, vertical | 4.778 s | 4.2 / 30.4 / 31.4 / 36.0 ms | 5.36 s | 74.8 → 79.0 MiB | 34, 28 chunks / 1,500 rows per pane |

All five workload PTYs and their tracked subprocesses exited. The Windows workload uses the console's normal rendering path and a hosted VM. No before/after Windows speedup or Windows/Linux timing equivalence was derived. See the [execution report](windows-ci-execution-report.md) for all runner results and artifacts.

### Passing candidate repeat

The [successful Windows run](https://github.com/djsk721/full-orchestration/actions/runs/44573538314/job/135734782532) repeated all three Windows workloads independently with the same integrity and cleanup checks.

| Workload | Elapsed | Tk median / P95 / P99 / max | Desktop CPU | Start → peak RSS | Sampled queue / history |
| --- | ---: | ---: | ---: | ---: | --- |
| One | 7.460 s | 3.9 / 25.1 / 31.0 / 55.2 ms | 6.81 s | 60.3 → 65.0 MiB | 43 chunks / 1,500 rows |
| Two, horizontal | 4.957 s | 10.3 / 19.1 / 31.7 / 63.2 ms | 6.64 s | 65.4 → 73.9 MiB | 48, 39 chunks / 1,500 rows per pane |
| Two, vertical | 5.018 s | 4.7 / 29.7 / 31.9 / 38.7 ms | 5.42 s | 73.9 → 78.1 MiB | 29, 35 chunks / 1,500 rows per pane |
