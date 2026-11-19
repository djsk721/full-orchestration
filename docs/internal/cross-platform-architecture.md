# Cross-platform migration and compatibility

See the [production readiness report](production-readiness.md) for the later contract, failure-injection and native workflow results.

## Source audit

The active worktree had the expanded Python/Tk desktop, SSH Worker, and 18 tests as local changes over `49e5062`. The separate TypeScript worktree at `28086eb` contained Electron main and preload, the React dashboard, the read-only SQLite projection, and the DAG analyzer. The Python/Tk launcher, Supervisor, Git gate, MCP transports, runtime process ownership, Worktree policy, PTY/ConPTY and SSH Worker were still Python. The TypeScript workspace was brought into the active checkout as additive files so it can be verified against the expanded Python backend. The separate worktree and existing data were retained.

The separation follows the existing data-ownership model. TypeScript parses configuration, evaluates portable execution policies and projects live evidence. Node adapters perform read-only SQLite access, OpenSSH and subprocess I/O. Python remains the job writer, lease holder, approval authority, and Worker execution backend. Native process containment, terminal and filesystem operations belong to the platform adapter layer.

## Component ownership

| Component | TypeScript | Python and operating-system dependencies |
| --- | --- | --- |
| Desktop | Electron main/preload and React read-only dashboard. The Node SQLite adapter reads a consistent snapshot and exposes only a typed projection. | The Tk desktop still edits configuration, submits work, manages terminals and approves execution. |
| Provider and Harness | Versioned registry parsing, candidate scoring and filtering, reported model and limit validation, attached-harness policy. | Live Runtime startup and probes, managed agent loops, OpenCode/Codex subprocesses and external credentials. |
| MCP | Role, selection, native and Agent policy plus uncertain-write decisions. | HTTP/stdio clients, Gateway, real tool catalog, approval and persistent call journal. |
| DAG and Agent | Structural plans, dependency analysis, pure candidate admission and derived Agent stage. | Authoritative queue, Worktree execution, dispatch, QA evidence, retries and lease recovery. |
| SSH and Worker | OS-neutral read protocol with a cursor, plus the Node OpenSSH adapter and a headless inspection CLI. | The Worker runs on Linux over SSH. Host registration, submission, jobs, cancellation, approvals and remote file UI stay in the existing backend. |
| Native execution and packaging | Host path selection, direct bounded Node subprocess adapter and standalone Electron packaging config. | Python's platform package holds Win32 Job Objects/ConPTY, POSIX process groups/PTY, filesystem guards, platform locks, argument quoting, and desktop OS hooks. The Windows Python package script is retained. |

The TypeScript execution policies can be tested without a model server or a desktop. Their candidate and scheduling projections have no job-write or process authority. The TypeScript inspect CLI can validate plans against an explicit execution-host path style and read a registered SSH Worker's inventory or run state. It never creates a host trust record or submits work.

## Python Supervisor compatibility decision

The Supervisor is still required to run and recover jobs. An Electron installation can read an existing SQLite database without a running Python process. Receiving new job events, operating the queue, or controlling a Worker still requires the Python backend. The TypeScript policy modules have no equivalent of the Python store's transaction ownership for leases, wait states, approvals, side-effect receipts, and candidate merges.

Replacing the writer would require a versioned repository and migration tool, lossless recovery of active checkpoints, worktree and candidate identity checks, lease coordination during transition, and a verified way to reconcile uncertain external writes without replay. A parallel writer would invalidate the current ownership guarantees. The live database remains on the existing schema with one writer and read-only Electron access. A persisted cancellation now wins a race with a late completion. The viewer also reads the latest integration QA attempt from events, including failure exit codes, and hides stale approval candidates.

## Unified verification

Use Node 24.14 or newer in the Node 24 line, Python 3.11 or newer, Git and a native display for graphical tests. Install `requirements-desktop.txt` for the Tk and native terminal checks. The same runner selects the OS adapter in both Linux and Windows jobs.

```bash
npm ci
python -m pip install -r requirements-desktop.txt
npm run verify
npm run verify -- --ui --package
```

- `npm run verify -- --core-only` runs strict builds and pure TypeScript domain tests without invoking Python, a desktop, SSH, or a provider. `npm ci --ignore-scripts` is sufficient on this path.
- `npm run verify -- --ui` adds Electron Playwright scenarios and the real Tk/PTY smoke on both hosts. Linux uses `xvfb-run` if a display is unavailable. Electron tests disable GPU acceleration.
- On Linux, `npm run verify -- --ui --ssh` adds a disposable OpenSSH server, ephemeral keys, remote interactive terminal, server-side detached work and observation from both CLI implementations.
- `--package` builds and launches the target's Electron artifact. Linux covers both the unpacked app and AppImage extract-and-run. Windows checks the unpacked NSIS payload in the workflow. Running the installer and the optional Windows Python package or scheduled task require separate native evidence.
- The [local CI workflow](../../.github/workflows/cross-platform.yml) defines the same command for Linux and Windows. The workflow was not pushed or run remotely.

Examples after a build:

```bash
npm run inspect -- plan examples/plan.windows.json examples/registry.windows.json windows
npm run inspect -- worker-info registered-host-id
npm run inspect -- worker-status registered-host-id 00000000000000000000000000000000 0
```

Use an existing registered SSH host and a real run ID for the last two commands. The application folder used for the saved pin and profiles follows `ORCHESTRA_DATA` or the native data directory.

## Compatibility matrix

| Function | Linux x64 observed | Windows | macOS and other POSIX |
| --- | --- | --- | --- |
| TypeScript registry, Provider, Harness, MCP, DAG and Agent policies | Verified with pure inputs. Both POSIX and Windows path rules exercised | Same test logic configured. Native Windows run pending | Portable code. Platform run not verified |
| TypeScript/Python schema and routing parity, SQLite viewer, consistency | Verified with real Python Store and SQLite, including a WAL writer and selected-plan parity fixtures | Same suite configured. Pending | Not verified |
| Git Worktrees, QA, approvals, job cancellation, concurrent claims, leases, recovery | Verified with temporary repositories, actual processes and SQLite | Same regression suite and process contract tests configured. Pending | POSIX adapter available. Not verified |
| Live model and MCP integrations | Mock HTTP and attached CLI fixtures. MCP socket and test transitions exercised locally. External provider login and live models not verified | Native and external checks pending | Not verified |
| SSH Worker protocol and client | Simulated fault/cursor tests and real loopback OpenSSH from a headless client | Same simulated protocol/argv tests configured. Real Windows OpenSSH client pending | Client source present. Not verified |
| SSH Worker host, remote PTY, reconnect and deduplication | Real isolated Linux Worker and SSH PTY. External server and GPU workload pending | Linux Worker required. Windows Worker host not implemented | Linux Worker required |
| Terminal and process control | Real POSIX PTY input, ANSI and resize. Actual descendant killed on timeout. Reparse-point condition simulated | ConPTY and Job Object adapters with native contract tests. Not verified | POSIX adapters present. Not verified |
| Electron and Tk UI | Real windows under Linux Xvfb, including a failing integration QA run with a real child command | Same UI scenarios configured. Not verified | Not verified |
| Electron packaging | Linux AppImage and unpacked application built and passed Playwright | NSIS configuration. Build and native executable pending | Packaging not configured |
| Python Windows packaging and scheduled task | Not applicable | Windows scripts retained. Not verified | Not applicable |
| Remote and local GPU | Verification excluded | Verification excluded | Verification excluded |

## Test evidence

The final Linux run of `npm run verify -- --ui --ssh --package` passed 26 Python tests and 22 TypeScript tests. All three Electron scenarios passed from source, the unpacked package, and the AppImage using extract-and-run. Tk/PTY and real loopback SSH smoke tests also passed. The independent TypeScript core run passed nine tests. The Windows path rules in the portable tests are simulated inputs, with the native Windows jobs still pending.

The unchanged starting Python suite passed all 18 tests. The expanded suite covers concurrent idempotent submissions and claims, simultaneous approval decisions, cancellation during completion, preservation of checkpoints after lease expiry, denial of uncertain-write replay, filesystem policy, and actual native PTY and descendant processes.

Pure and simulated tests use explicit registry inputs, OS path styles, fake Worker failures, mock inference, and CLI fixtures. Real local integration tests invoke Git, Python, Node and OpenSSH processes and use SQLite and actual desktop windows. The SSH endpoint runs on loopback with disposable keys. It exercises real SSH transport and recovery while keeping production accounts and external servers outside the test. No GPU validation was performed.
