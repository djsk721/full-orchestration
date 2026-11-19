# Model Orchestration

<div align="center">
  <img src="docs/assets/images/mark.svg" width="64" height="64" alt="Model Orchestration logo">
</div>

[한국어](README.md) · **English**

A Windows desktop app that turns work in a local Git repository into a task DAG, with Agent runs, independent review, integration QA, and merge approval in one place.

![Windows 10/11](https://img.shields.io/badge/Windows-10%20%2F%2011-2563eb)
![Python 3.11+ and Tkinter](https://img.shields.io/badge/Python%203.11%2B-Tkinter-356b98)
![Git Worktree](https://img.shields.io/badge/Git-Worktree-d14836)
![MCP](https://img.shields.io/badge/MCP-HTTP%20%2F%20stdio-28766c)

[Getting started](docs/en/user-guide/getting-started.md) · [Documentation](docs/en/index.md) · [Troubleshooting](docs/en/troubleshooting/index.md)

## Screenshot

![Model Orchestration job dashboard](docs/assets/screenshots/dashboard.png)

This is the running Tkinter dashboard with a fresh data directory. The capture uses a Linux virtual display, so fonts and window borders can differ on Windows.

## Key features

| Feature | What you can do |
| --- | --- |
| Providers and models | Register local Runtimes and trusted CLI routes in the desktop JSON editor. Select a Model and Harness in each task. |
| MCP | Discover CLI configurations and allow tools for Managed jobs. Migrate supported OpenCode JSON and Codex TOML bindings to the Gateway and roll them back. |
| Multi-Agent Orchestration | Define DAG nodes by role. The Supervisor runs eligible tasks in individual Git Worktrees. |
| Managed Harness | Probe effective Context and tool calling, then enforce file scopes, repetition limits, checkpoints, and approval for external writes. |
| Background Execution | Let opted-in jobs continue under the Supervisor after you close the app. Expired job leases can be recovered on restart. |
| Git verification | Review the candidate SHA after integration QA and approve a fast-forward into the local target branch. |

## Architecture

The Tkinter desktop and a separate Python Supervisor share a local SQLite database for jobs, states, and events. The Supervisor selects a Model and Harness and runs tasks in Git Worktrees. The dashboard and exported JSON report show the outcome. [Architecture and execution flow](docs/en/developer-guide/architecture.md)

## Installation and quick start

1. Install Git for Windows and Python 3.11 or later on Windows 10/11, including Tcl/Tk and the Python Launcher. Confirm that `git --version` works in a terminal.
2. Obtain the repository source and run [Launch-Windows.cmd](Launch-Windows.cmd). Without the launcher, open [ModelOrchestration.pyw](ModelOrchestration.pyw) with `pythonw.exe`.
3. Under **모델 및 실행 설정** (Model and execution settings), choose **JSON 가져오기** (Import JSON). Load the [Windows registry example](examples/registry.windows.json), enter the installed Runtime and Model paths, and choose **설정 저장** (Save settings).
4. Open **새 작업** (New job), pick the Git repository and target branch, and submit. [Getting started](docs/en/user-guide/getting-started.md) includes a read-only Agent run and a smoke test that needs no Model.

Install Model files, external Runtimes, and CLIs separately. For a Windows executable built from source, see [Testing and builds](docs/en/developer-guide/testing.md).

## Documentation

| Guide | Topics |
| --- | --- |
| User | [Providers and models](docs/en/user-guide/providers.md), [MCP](docs/en/user-guide/mcp.md), [Running jobs](docs/en/user-guide/orchestration.md), [Managed Harness](docs/en/user-guide/managed-harness.md), [Background Execution](docs/en/user-guide/background.md) |
| Administrator | [Operations, credentials, resources, and backups](docs/en/admin-guide/operations.md), [Configuration and API](docs/en/admin-guide/configuration.md) |
| Developer | [Architecture](docs/en/developer-guide/architecture.md), [Testing and builds](docs/en/developer-guide/testing.md), [Documentation maintenance](docs/en/developer-guide/documentation.md) |
| Support | [Troubleshooting](docs/en/troubleshooting/index.md), [FAQ](docs/en/faq.md), [Roadmap](docs/en/roadmap.md) |

## Development and contributions

```bash
python -m unittest discover -s tests -v
```

The suite uses temporary Git repositories and loopback fixtures. See the [contribution guide](CONTRIBUTING.en.md) for site preview and validation commands and [CHANGELOG.md](CHANGELOG.md) for the change history.

## Roadmap

See the [Roadmap](docs/en/roadmap.md) for SSH/Remote Execution, desktop language selection and help links, and form-based Provider setup.

## License

The maintainers have not published a project license. [License status](LICENSE)
