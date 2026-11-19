# Testing and builds

## Development environment

The app uses Python 3.11 or later, the standard library, and Tcl/Tk. External dependencies are Git and any Model Runtimes or CLIs you configure. Node.js 24 runs the TypeScript dashboard and test tooling. The Tk desktop and Supervisor do not need Node.js.

## Testing and QA

```bash
python -m unittest discover -s tests -v
```

`tests/test_orchestra.py` uses temporary Git repositories, loopback HTTP, a fake CLI, and a separate Supervisor process. It covers DAG execution and merge approval, QA failure, Runtime validation, MCP migration, rollback, external write approval, and background recovery. Allow temporary loopback sockets in the test environment.

On the target host, verify that the desktop opens, the external CLI version and login work, the Runtime passes Model, Context, and tool checks, and approvals and Background Execution behave as expected. To compare Harnesses, keep the base commit, Model, task specification, QA, and time limit fixed and export each run's JSON report. Compare missing usage counts alongside reported model usage.

## Windows build and distribution

Run this command on Windows. The `-InstallBuildDependency` switch installs PyInstaller 6.x. Omit it when the build dependency is already installed.

```powershell
.\Build-Windows.ps1 -InstallBuildDependency
```

The executable is `dist\ModelOrchestration\ModelOrchestration.exe`. This is an `--onedir` build. Distribute the entire `dist\ModelOrchestration` bundle. On a clean Windows host, check launch, Git on PATH, a QA-only job, and Supervisor startup and shutdown before distributing the bundle.

## Unified and native verification

```bash
npm ci
python -m pip install -r requirements-desktop.txt
npm run verify -- --ui --package
```

The same command runs the TypeScript and Python suites, both desktop smoke tests and native adapter contracts on Linux and Windows. Use `npm run verify -- --core-only` for tests without Python or a desktop. On Linux, add `--ssh` to exercise a disposable OpenSSH server and Worker. Native Windows evidence is required for ConPTY, Job Objects, and the installer.

The Tk workflow runs a real Supervisor from project registration through approved Git integration against a scripted model API. Electron's tests also terminate the app during a real QA command and check the result after reopening. Add `--harness` for installed CLI checks. Observe startup and credential presence separately from authenticated model execution.

On a disposable native Windows host, run `./scripts/qa/verify-windows-installer.ps1` after `npm run verify -- --ui --package` to test the installed NSIS build. The script uses a temporary installation directory and runs the same Playwright tests before uninstalling it. The Windows CI job includes this step.
