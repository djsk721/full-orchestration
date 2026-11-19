# Testing and builds

## Development environment

The app uses Python 3.11 or later, the standard library, and Tcl/Tk. External dependencies are Git and any Model Runtimes or CLIs you configure. Node.js is used for documentation linting. Running the desktop requires neither Node.js nor Docker.

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
