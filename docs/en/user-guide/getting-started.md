# Getting started

## Concept

Model Orchestration uses an existing Git repository as the Workspace. A job specifies a local target branch, one or more DAG nodes, and optional QA commands. Setup takes place in the desktop editor. Create or clone the repository in Git before opening it in the app.

## Desktop workflow

1. Prepare Windows 10/11, Git for Windows, and Python 3.11 or later with Tcl/Tk and the Python Launcher. Check your installation with `git --version` and `py -3 -m tkinter`.
2. Run `Launch-Windows.cmd` from the repository. If the launcher is unavailable, open `ModelOrchestration.pyw` with `pythonw.exe` from the Python installation. For a Windows executable, see [Testing and builds](../developer-guide/testing.md).
3. Open **모델 및 실행 설정 → JSON 가져오기** (Model and execution settings → Import JSON). Load the [Windows registry example](https://github.com/djsk721/full-orchestration/blob/develop/examples/registry.windows.json), set the absolute paths to your installed `llama-server.exe` and GGUF Model, and select **설정 저장** (Save settings). The example uses the CPU.
4. In **새 작업** (New job), choose **기본 작업 불러오기** (Load default job), then **저장소 선택** (Choose repository). Choose the root of a Git repository with a committed local branch. In the JSON editor, set `target` to that branch and add `"model": "local-model"` and `"harness": "managed"` to the first node.
5. Choose **작업 제출** (Submit job) and select the job in **작업 대시보드** (Job dashboard). Look for `runtime.snapshot` and the final state. Choose **결과 폴더 열기** (Open results folder) to read the Agent output.

## Example

To check the execution flow before installing a Model, replace the default job's `tasks` array with the one below. Keep the repository and branch you selected. Review and approve the QA execution dialog when submitting, then check the dashboard for `qa.result` with exit code 0.

```json
[
  {
    "id": "smoke",
    "role": "qa",
    "prompt": "Check Git availability",
    "acceptance": "Git exits with status zero",
    "qa": [["git", "--version"]]
  }
]
```

## Troubleshooting

- If the window fails to open, verify the Python Launcher and Tkinter. The app requires Python 3.11 or later.
- For a repository error, select the Git root and verify the local target branch has a commit.
- For a failed Agent route, follow the Runtime checks in [Providers and models](providers.md).

## Advanced settings

Use **새 작업 → JSON 열기** (New job → Open JSON) to load the [Windows job example](https://github.com/djsk721/full-orchestration/blob/develop/examples/plan.windows.json) with Developer, Reviewer, and integration QA stages. Check the repository, branch, output file path, and `python.exe` command, then try it on a test branch.
