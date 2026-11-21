# Windows CI and packaging readiness

GitHub Actions executes this candidate on native `windows-2025`. The [CI execution report](windows-ci-execution-report.md) records the run and commit IDs. The [native test results](windows-native-test-results.md) record the Windows environment, test results and independent terminal measurements.

| Gate | Status | Evidence |
| --- | --- | --- |
| Dependency setup | PASS | Node 24.14.1, CPython 3.11.9, Tk 8.6.12 and pywinpty 3.1.2 on Windows Server 2025 x64. |
| TypeScript and Python regression | PASS | All 25 TypeScript checks and 52 Python cases passed. Three Linux-only Python cases skipped. |
| Windows adapters, ConPTY and Job Object cleanup | PASS | Real processes and console sessions. Timeout and forced owner exit reaped tracked child trees. Three native 8,000-line workloads exercised both split directions. |
| NSIS build | PASS | Built an unsigned x64 per-user installer and uploaded it as an Actions artifact. |
| Electron source, unpacked and forced-close cleanup | PASS | Source and unpacked Playwright passed with process-tree termination and the existing independent Supervisor assertions. |
| Installed startup, uninstallation, reinstallation and data preservation | PASS | The runner opened both installed apps after fresh install and reinstall, and checked the fixture hashes through both removals. |
| Korean IME and 100%, 125%, 150% desktop scaling | NOT VERIFIED | A Windows desktop session is required. See [manual native acceptance](windows-native-ux-validation.md). |

## Package composition and diagnostics

NSIS builds both executables from the same checkout. The app executable is the Electron read-only monitor. The installed primary Tk workspace is `resources\workspace\ModelOrchestration.exe`. It bundles Python and Tk and starts the existing Supervisor from the same frozen binary. The installation test opens both apps in separate disposable profiles, validates the installed Windows shell and drives a real Supervisor restart, and compares five data files across both uninstalls.

```powershell
npm run verify -- --ui --package
./scripts/qa/verify-windows-installer.ps1
```

Use a disposable Windows account for silent install and uninstall. The installer test refuses an existing installation or pre-existing default Python profile. CI captures shared Windows regressions, native ConPTY, build and installed test logs in the `windows-verification-evidence` artifact and retains the built installer for seven days. Signing is outside this verification.
