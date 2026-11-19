# Model Orchestration

Windows용 데스크톱 앱입니다. Git 저장소의 작업을 DAG로 실행하고, 모델과 Harness 경로를 기록하며, 통합 QA를 통과한 커밋만 사용자 승인 후 대상 브랜치에 반영합니다.

## Windows에서 실행

1. Windows 10/11에 Python 3.11 이상(Tcl/Tk와 Python Launcher 포함)과 Git for Windows를 설치하고, 터미널에서 `git`을 실행할 수 있게 설정합니다.
2. **Launch-Windows.cmd**를 더블클릭합니다. Python Launcher 없이 실행하려면 Python 설치 폴더의 `pythonw.exe`로 `ModelOrchestration.pyw`를 엽니다.
3. **모델 및 실행 설정 → JSON 가져오기**에서 [Windows 레지스트리 예제](../../examples/registry.windows.json)를 열고 실제 `.exe`와 모델 파일의 절대 경로를 지정한 뒤 저장합니다. 예제의 llama.cpp 설정은 CPU 경로입니다. 모델과 외부 CLI는 별도로 설치합니다.
4. **새 작업 → JSON 열기**에서 [Windows 작업 예제](../../examples/plan.windows.json)를 가져옵니다. 저장소 최상위 경로와 대상 브랜치, 작업 명세, 검증 명령을 맞춘 뒤 제출합니다. 결과와 이벤트는 **작업 대시보드**에서 확인합니다.

PowerShell에서 `.\Build-Windows.ps1 -InstallBuildDependency`를 실행하면 `dist\ModelOrchestration\ModelOrchestration.exe`를 빌드합니다. 실행 파일을 배포할 때는 같은 폴더의 번들 파일도 함께 배포합니다. 빌드는 Windows에서 수행합니다.

## 모델, 작업 및 QA

- **Managed**는 앱이 Context, 도구 호출 반복, 체크포인트를 관리합니다. Managed llama.cpp를 직접 시작하거나, 이미 실행 중인 loopback llama.cpp/Ollama/OpenAI 호환 Runtime에 연결할 수 있습니다. Attached Runtime은 실제 Context를 노출해야 합니다. 예를 들어 OpenAI 호환 Runtime은 `/v1/models`에 `context_length` 또는 `max_model_len`을 제공해야 합니다. Ollama는 `/api/ps`에 등록 모델의 `context_length`가 관측되는 경우에 사용합니다.
- **OpenCode**에 같은 로컬 모델을 연결하려면 레지스트리 예제의 `opencode-local` 경로를 확인하고, CLI·저장소를 신뢰하는 경우에만 `trusted`를 켭니다. 작업의 `harness`에 `opencode-local`을 지정합니다. 로컬 Runtime 한도는 검증 후 OpenCode 설정에 주입합니다. 외부 설정의 실제 적용 여부는 관측 가능한 범위로 표시됩니다. Attached CLI에는 Git Worktree와 CLI 자체 권한을 적용합니다.
- **Codex**의 비대화형 읽기 경로는 `kind: "codex"`로 등록합니다. Runtime 설정을 관측할 수 없는 구독형 CLI는 `trusted: true` 및 `allow_unverified: true`가 필요합니다. `models` 레지스트리에서 해당 모델의 `provider`는 `subscription`으로 지정하고 `runtime`은 생략합니다. 자격증명은 기존 CLI의 로그인 환경에서 관리합니다. 모델 ID와 CLI의 별칭이 다르면 `cli_model`을 지정합니다.
- **DAG**의 `depends`에는 선행 작업 ID를 적습니다. Developer만 `paths`에 쓰기 범위를 설정할 수 있습니다. 겹치는 범위의 작업은 의존관계가 필요합니다. Reviewer는 독립 Worktree에서 선행 커밋을 검토하고 `REVIEW: PASS`를 반환해야 통과합니다. 모델/Harness를 지정하지 않은 QA 역할은 작업의 `qa` 명령만 실행합니다. 다른 역할도 QA 명령을 추가할 수 있습니다.
- **병합**은 변경 검증과 통합 QA를 통과한 후보의 SHA를 승인한 뒤 fast-forward로 처리합니다. QA는 argv 배열로 지정하며 앱이 이를 실행할 수 있는 신뢰된 작업 정의를 사용합니다. 검증 뒤 대상 브랜치가 움직였거나 대상 Worktree가 수정된 경우 병합을 중단합니다.
- 보고서에는 기준 커밋, 설정 지문과 Runtime 스냅샷, QA 종료 코드, 작업·도구 이벤트, 검증까지 걸린 시간과 토큰 관측값이 포함됩니다. Harness를 A/B 평가할 때는 기준 커밋·모델·명세·QA·시간 상한을 고정한 뒤 각 실행의 JSON 보고서를 저장합니다. 사용량이 제공되지 않은 호출은 보고서에서 별도로 집계합니다.

## MCP

**MCP 연결** 화면은 Codex, OpenCode, Claude Code, Gemini CLI, Antigravity의 알려진 파일 경로를 읽고, 경로·범위·지문·충돌 후보를 표시합니다. 기존 연결을 기본 Federated 상태로 유지합니다. 실행기 내부 우선순위나 OAuth 계정은 파일만으로 확정할 수 없으므로 후보를 별도로 표시합니다.

Managed 작업에서 도구를 사용하려면 레지스트리의 `mcp`에 서버와 개별 도구 정책을 등록하고, 작업의 `tools`에 가상 이름을 적습니다. 이름은 기본적으로 `프로파일ID__도구이름`입니다. 이름에 지원하지 않는 문자가 있으면 밑줄로 바꾸고, 64자를 넘으면 해시를 붙여 줄입니다.

```json
{
  "documentation": {
    "transport": "http",
    "url": "https://mcp.example.com/mcp",
    "header_env": {"Authorization": "DOCS_MCP_AUTH"},
    "gateway_token_env": "ORCHESTRA_DOCS_GATEWAY_TOKEN",
    "tools": {
      "search": {"access": "read", "roles": ["explorer", "reviewer"], "native": true}
    }
  }
}
```

- `header_env`는 업스트림 HTTP 헤더 값의 환경 변수 이름을 가리킵니다. `stdio` 서버는 `command`에 argv 배열을, 필요한 환경 변수 이름을 `env`에 적습니다. 토큰 값을 JSON에 입력하지 않습니다.
- 외부 쓰기에는 Developer 역할과 호출 인자 단위의 승인이 필요합니다. 호출이 시작된 뒤 결과가 불명확하면 해당 쓰기를 자동으로 재호출하지 않습니다.
- Native Gateway는 `gateway_token_env`가 등록된 프로파일에서 명시적으로 `native: true`를 부여한 읽기 도구만 제공합니다. 최소 24자 임의 토큰을 환경에 전달한 상태로 Supervisor와 대상 CLI를 실행합니다. 기존 Supervisor가 이미 실행 중이면 재시작해 새 환경을 로드합니다.
- **Gateway 전환**은 OpenCode JSON 및 일반적인 Codex TOML 테이블에서 지원합니다. 발견된 연결과 동일한 업스트림을 등록하고, 인증된 연결은 탐색 상세의 `account_scope`를 지정합니다. 사용자 승인, 원본 바이트 백업, Gateway 읽기 Probe, 파일 교체와 재검증 순으로 진행합니다. 외부 파일 변경을 감지하면 중단합니다. 앱이 표시한 기록 ID로 롤백할 수 있습니다. OpenCode JSONC와 다른 CLI는 읽기 전용 탐색을 제공합니다. 실행 중인 외부 세션은 직접 새 설정을 로드해야 합니다.

관련 형식은 [OpenCode MCP 문서](https://opencode.ai/docs/mcp-servers/), [MCP Streamable HTTP 명세](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [llama.cpp 서버 문서](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)를 참고합니다.

## 백그라운드와 데이터

- 기본 포그라운드 작업은 앱과 연결이 끊어지면 중지합니다. 레지스트리에서 `settings.background`를 켜고 작업에서도 `background: true`를 선택하면 별도 Supervisor가 UI를 닫은 뒤에도 작업을 유지합니다. 백그라운드 파일 쓰기는 `allow_background_write`를 별도로 켭니다.
- Supervisor는 SQLite에서 큐, 임대, 하트비트, 도구 호출과 체크포인트를 관리합니다. 다음 시작에서 임대가 만료된 백그라운드 작업을 복구합니다. Windows에서는 Supervisor가 시작한 실행 파일의 프로세스 트리를 Job Object로 관리합니다.
- 로그인 시 실행이 필요한 경우 빌드 후 `.\Register-SupervisorTask.ps1`로 사용자 로그인 트리거를 등록할 수 있습니다. 제거는 `.\Register-SupervisorTask.ps1 -Unregister`로 실행합니다. Windows 서비스 대신 사용자 세션에서 실행되는 작업 스케줄러 방식입니다.
- `settings.notifications`는 UI가 열려 있을 때 내용 없는 상태 알림을 표시하는 선택 사항입니다.
- 기본 데이터 폴더는 `%LOCALAPPDATA%\ModelOrchestration`입니다. 작업 정의, 비공개 체크포인트, 작업 결과, Worktree, 설정 백업을 보관합니다. JSON 보고서는 원문 프롬프트나 토큰 값을 포함하지 않습니다.

## 검증 범위

`python -m unittest discover -s tests -v`는 임시 Git 저장소와 loopback 모의 서버를 사용합니다. GPU가 연결된 모델이나 실제 공급자 계정에 접속하지 않습니다. 운영 Windows 호스트에서 실행 파일을 빌드하고 외부 CLI 및 실제 모델과의 조합을 확인하는 단계는 별도로 남아 있습니다.

현재 구현 범위는 로컬 데스크톱과 사용자 수준 Supervisor입니다. 외부 CLI의 완전한 OS 보안 격리, 자동 OAuth 이관, 모든 CLI의 설정 전환, 원격 Worker, 하드웨어 텔레메트리, Orca 실측 벤치마크는 구현 또는 실측 범위에 포함되지 않습니다. GPU·RAM 예약값은 운영자가 구성합니다. Context 압축은 자체 추정치와 대화 발췌를 사용합니다.
