# MCP 연결

<!-- feature: mcp PARTIALLY_IMPLEMENTED -->

## 개념

MCP(Model Context Protocol)는 Agent가 외부 도구를 호출하는 연결 규약입니다. 이 앱의 MCP 프로파일은 전역 레지스트리의 `mcp`에 있고 Provider와 별도로 관리합니다. 탐색으로 찾은 기존 CLI 연결은 기본적으로 **Federated**로 표시되며 기존 CLI가 계속 사용합니다. Managed Harness에서 사용하려면 프로파일과 작업의 도구 허용 목록을 명시합니다.

## GUI 사용 방법

1. **MCP 연결 → 사용자 설정 탐색** 또는 **프로젝트 탐색**을 누릅니다. 대상은 알려진 Codex, OpenCode, Claude Code, Gemini CLI, Antigravity 설정 경로입니다.
2. 서버를 선택해 경로, 범위, 지문, 활성 상태와 충돌 후보를 확인합니다. 이 화면에 있는 활성 상태는 원본 파일에서 읽은 값입니다.
3. Managed 작업에서는 **모델 및 실행 설정**에서 `mcp.<profile>.tools`에 허용 도구와 역할을 저장하고, **새 작업**에서 노드의 `tools`에 가상 이름을 추가합니다. 작업에서 빼면 해당 노드에 노출하지 않습니다.
4. 읽기 작업을 제출하고 `route.failed`, `tool.call`과 결과를 확인하세요. Gateway로 전환하는 경우 UI가 별도의 읽기 Probe를 요청합니다.

## 실제 예제

레지스트리의 `mcp`에 아래 프로파일을 추가하세요. 예제 주소는 실제 MCP 서버 주소로 바꿉니다. 서버가 `search`를 제공하면 Explorer 노드의 `tools`에 `"documentation__search"`를 추가할 수 있습니다. 서버에 인증이 필요 없는 경우 `header_env`를 생략하세요.

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

## 오류 해결

- `충돌 후보`가 있으면 동일 이름의 다중 설정이나 동일 지문의 중복이 있는지 상세 화면에서 확인하세요. 실제 우선순위와 인증 계정은 대상 CLI에서 확인합니다. 중복 상태에서는 전환을 진행할 수 없습니다.
- Managed 작업에서 도구가 보이지 않으면 역할, 가상 이름, 서버 카탈로그를 확인합니다. 가상 이름은 보통 `profile__tool`입니다. 지원하지 않는 문자는 밑줄로 바뀌며 64자가 넘으면 해시가 붙습니다.
- 외부 쓰기가 멈추면 **도구 승인 검토**에서 인자를 확인합니다. 시작된 호출의 결과가 불명확하면 서버의 기록을 확인하세요.

## 고급 설정

- `stdio`는 `command`에 argv 배열을, `env`에 전달할 환경 변수 이름을 사용합니다. HTTP에서는 `header_env`에 환경 변수 이름을 둡니다.
- **Gateway 전환**은 OpenCode JSON과 지원되는 Codex TOML 형식에 적용됩니다. 동일한 업스트림을 먼저 등록하고 인증된 연결은 탐색 상세의 `account_scope`를 지정하세요. 선택한 프로파일과 읽기 도구, JSON 인자를 입력해 승인하면 원본 바이트를 백업하고 읽기 Probe, 파일 교체, 재검증을 수행합니다.
- Gateway는 설정한 환경 변수에 담긴 24자 이상 토큰과 `native: true`인 읽기 도구를 사용합니다. 새 환경을 읽어야 하면 Supervisor를 종료하고 해당 변수가 설정된 환경에서 재시작하세요. 전환 후 외부 CLI 세션도 설정을 다시 로드합니다.
- **Gateway 감사**로 프로파일 이벤트를 확인하고 **롤백**에 완료 대화 상자의 ID를 입력합니다. 원본과 다른 외부 변경이 발견되면 새 설정을 덮어쓰지 않도록 중단합니다. OpenCode JSONC와 다른 CLI는 읽기 전용 탐색입니다.
