# 시작하기

## 개념

Model Orchestration은 기존 Git 저장소를 Workspace로 사용합니다. 앱의 작업은 대상 로컬 브랜치, 하나 이상의 DAG 노드, 선택적인 QA 명령으로 구성됩니다. 최초 설정은 앱 화면에서 진행하며 현재 별도 마법사나 Git 저장소 생성 기능은 제공하지 않습니다.

## GUI 사용 방법

1. Windows 10/11, Git for Windows, Python 3.11 이상(Tcl/Tk 및 Python Launcher 포함)을 준비합니다. `git --version`과 `py -3 -m tkinter`로 확인합니다.
2. 저장소의 `Launch-Windows.cmd`를 실행합니다. Launcher가 없다면 Python 설치 폴더의 `pythonw.exe`로 `ModelOrchestration.pyw`를 열 수 있습니다. Windows 빌드가 필요하면 [테스트와 빌드](../developer-guide/testing.md)를 참고하세요.
3. **모델 및 실행 설정 → JSON 가져오기**에서 [Windows 레지스트리 예제](https://github.com/djsk721/full-orchestration/blob/develop/examples/registry.windows.json)를 엽니다. 설치한 `llama-server.exe`와 GGUF Model의 절대 경로를 넣고 **설정 저장**을 누릅니다. 예제는 CPU용입니다.
4. **새 작업 → 기본 작업 불러오기 → 저장소 선택**으로 커밋과 로컬 브랜치가 있는 Git 저장소의 루트를 선택합니다. JSON 편집기에서 `target`을 실제 브랜치로 바꾸고 첫 노드에 `"model": "local-model"`과 `"harness": "managed"`를 지정합니다.
5. **작업 제출**을 누르고 **작업 대시보드**에서 해당 작업을 선택합니다. `runtime.snapshot`과 최종 상태를 확인하고 **결과 폴더 열기**로 읽기 전용 Agent의 결과를 읽습니다.

## 실제 예제

Model 없이 실행 흐름을 먼저 확인하려면 기본 작업의 `tasks`를 아래 배열로 교체하세요. 저장소와 대상 브랜치는 그대로 사용합니다. 제출할 때 표시되는 QA 실행 확인을 검토하고 승인한 뒤 대시보드에서 `qa.result`와 종료 코드 0을 확인하세요.

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

## 오류 해결

- 실행 창이 열리지 않으면 Python Launcher와 Tkinter를 확인하세요. 앱 요구사항은 Python 3.11 이상입니다.
- 저장소 오류가 나면 Git 저장소 루트를 선택했는지, 대상 로컬 브랜치와 커밋이 있는지 확인하세요.
- Agent용 경로 검증이 실패하면 [Provider 및 Model](providers.md)의 Runtime 점검 절차를 따르세요.

## 고급 설정

[Windows 작업 예제](https://github.com/djsk721/full-orchestration/blob/develop/examples/plan.windows.json)를 **새 작업 → JSON 열기**로 가져오면 Developer, Reviewer, 통합 QA 흐름을 구성할 수 있습니다. 사용할 저장소와 브랜치, 문서 파일 경로, `python.exe` 명령을 확인한 후 실험용 브랜치에서 실행하세요.
