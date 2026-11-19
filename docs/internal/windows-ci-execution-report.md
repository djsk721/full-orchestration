# GitHub Actions execution report

The **Cross-platform verification** workflow tests `feature/orca-workspace` on GitHub-hosted Linux and Windows plus a portable TypeScript job. Each run was dispatched explicitly against the feature branch. The checkout uses the SHA of that dispatch. The repository's default branch remains `main`.

| Run | Tested commit | Ubuntu 24.04 | Windows Server 2025 | Portable TypeScript |
| --- | --- | --- | --- | --- |
| [44571098427](https://github.com/djsk721/full-orchestration/actions/runs/44571098427) | `c3ede6bb1b4d09de53bff2abd8a32bb8d15c1cd7` | PASS | FAIL at Python setup | PASS |
| [44571326763](https://github.com/djsk721/full-orchestration/actions/runs/44571326763) | `efa23a9c1bb8c2e3479d9399ae21b83d65612cd8` | PASS | FAIL during regressions and frozen Tk startup | PASS |
| [44572159235](https://github.com/djsk721/full-orchestration/actions/runs/44572159235) | `9f44fc1695b5abb9f2a3f4f5465ce335ce376fd1` | PASS | FAIL in source and unpacked Electron cleanup. Native ConPTY and NSIS build passed. | PASS |
| [44573538314](https://github.com/djsk721/full-orchestration/actions/runs/44573538314) | `e3236583819377e4d8a67609df8b61027f6a5eb0` | PASS | PASS | PASS |

## Verified runner setup

The matrix uses `ubuntu-24.04` and `windows-2025` with Node.js 24.14.1. GitHub identified the Windows image as `windows-2025-vs2026`. Windows resolved CPython 3.11.9 after switching to the available 3.11 series. Ubuntu retains the exact 3.11.14 pin. The workflow installs the pinned or constrained desktop requirements with pip and uses `npm ci` for the TypeScript workspace. The setup steps specify no explicit dependency-cache settings. GitHub's tool cache is used when a matching interpreter is present. Pinned Actions perform checkout, tool setup and artifact upload.

## Passing candidate

Run `44573538314`, attempt 1, finished successfully. The [Linux job](https://github.com/djsk721/full-orchestration/actions/runs/44573538314/job/135734782981) passed 99 checks with two Windows-only Python cases skipped. The [portable TypeScript job](https://github.com/djsk721/full-orchestration/actions/runs/44573538314/job/135734782912) passed without a Python, native or desktop runtime requirement.

The [Windows job](https://github.com/djsk721/full-orchestration/actions/runs/44573538314/job/135734782532) passed 52 Python checks, 25 TypeScript checks, six source Tk smoke scenarios and five source Electron cases. Three Linux-only Python cases were skipped for Linux case semantics, PTY and Worker server. The native ConPTY suite, NSIS build, all five unpacked Electron cases and the dedicated installed-app step passed. Both installation rounds passed the frozen Tk checks and six installed Electron cases, including retained execution history. No Windows gate failed in this run.

## Failed steps and corrections

1. The first Windows runner could not install the exact `3.11.14` x64 build. All subsequent native test and packaging steps were skipped. GitHub produced no Windows verification or installer artifact for that run. [Windows setup log](https://github.com/djsk721/full-orchestration/actions/runs/44571098427/job/135726049031)
2. The second Windows run installed Python and dependencies and built TypeScript. Two Python test assertions compared the canonical Git and MCP paths with the unexpanded Windows short path `RUNNER~1`. Native Tk rejected X11-specific `ISO_Left_Tab` while configuring its keyboard shortcuts. PyInstaller built the executable, then its Tk startup probe timed out after closing the language picker. The installed NSIS step was skipped because the shared suite stopped before packaging. The native Tk key binding and the two fixture comparisons were corrected. [Windows test and build log](https://github.com/djsk721/full-orchestration/actions/runs/44571326763/job/135726869265)
3. The third Windows run passed 52 Python cases, skipped three Linux-only cases and passed all 25 TypeScript cases. Native Tk/ConPTY and three 8,000-line workloads passed. The NSIS build produced an x64 per-user installer with the bundled Tk executable. Source and unpacked Electron both reached the final cleanup of the forced-close test, then Windows rejected removal of the still-locked temporary profile with `EPERM`. The installed-app step was skipped. [Windows regression and build log](https://github.com/djsk721/full-orchestration/actions/runs/44572159235/job/135729896005)
4. Windows now terminates the test-owned Electron subprocess tree and waits for exit before removing the fixture profile. The Supervisor assertions still exercise recovery of a successful QA result. The installer test is triggered by the built NSIS file and blockmap. This allows installation checks after an independent unpacked-test failure. The fourth run passed both paths.

## Retained artifacts

| Run | Windows logs | NSIS |
| --- | --- | --- |
| 44571098427 | None after the Python setup failure | None |
| 44571326763 | [windows-verification-evidence](https://github.com/djsk721/full-orchestration/actions/runs/44571326763/artifacts/14554338794) | None |
| 44572159235 | [windows-verification-evidence](https://github.com/djsk721/full-orchestration/actions/runs/44572159235/artifacts/14554644480) | [windows-nsis-installer](https://github.com/djsk721/full-orchestration/actions/runs/44572159235/artifacts/14554699675), ZIP artifact 133,419,658 bytes |
| 44573538314 | [windows-verification-evidence](https://github.com/djsk721/full-orchestration/actions/runs/44573538314/artifacts/14554914509) | [windows-nsis-installer](https://github.com/djsk721/full-orchestration/actions/runs/44573538314/artifacts/14555204038), ZIP artifact 133,419,729 bytes |

The tested unsigned installer is `Model Orchestration Preview Setup 0.1.0.exe` (133,477,760 bytes). Its SHA-256, reported from the runner before installation, is `4bfebdcd108b65ba63c3ecea31c7235f2c50e1bcbcc68f84f5ff6d8a4c24aa32`. The artifact is retained for seven days.

See [native Windows test results](windows-native-test-results.md) and [release candidate assessment](orca-workspace-release-candidate.md).
