# Provider 및 Model

<!-- feature: providers PARTIALLY_IMPLEMENTED -->

## 개념

Provider는 Model이 `local` Runtime을 쓰는지 또는 `attached` CLI를 통해 접근하는지 나타냅니다. Model은 레지스트리 ID, Runtime에 전달하는 실제 Model 이름, 허용 역할과 Harness를 연결합니다. OpenCode는 이 앱에서 Provider가 아닌 Attached Harness입니다. 앱의 직접 Model HTTP 호출은 loopback에서만 지원됩니다.

## GUI 사용 방법

1. **모델 및 실행 설정**에서 **JSON 가져오기**로 예제를 열거나 **저장된 설정 열기**를 누릅니다.
2. `providers`에 `kind: "local"` 또는 `kind: "attached"`인 항목을 지정합니다. Runtime을 쓰는 Model은 `runtimes`와 `models`를 연결합니다. **설정 저장**은 스키마 검증을 수행합니다.
3. **새 작업**에서 노드의 `model`과 `harness`에 각각 레지스트리 ID를 지정하거나 생략해 자동 선택을 사용합니다.
4. 읽기 전용 Agent 작업을 제출하고 대시보드의 `runtime.snapshot`과 `route.failed`를 확인합니다. 연결 검증은 실행 중에 진행됩니다.

## 실제 예제

이미 실행 중인 OpenAI 호환 loopback 서버가 `/v1/models`에 `my-local-model`과 `context_length` 또는 `max_model_len`을 반환하는 경우의 레지스트리입니다. 서버가 채팅과 Managed 도구 호출도 지원해야 합니다. 실제 서버의 URL과 Model ID로 바꾸세요.

```json
{
  "providers": {"local": {"kind": "local"}},
  "runtimes": {
    "local-http": {
      "kind": "openai-compatible",
      "ownership": "attached",
      "url": "http://127.0.0.1:8080",
      "context": 8192
    }
  },
  "models": {
    "local-model": {
      "provider": "local",
      "model": "my-local-model",
      "runtime": "local-http",
      "harnesses": ["managed"]
    }
  }
}
```

## 오류 해결

- `Runtime 실제 Context` 오류에는 Model ID와 서버가 반환하는 Context를 확인하세요. llama.cpp는 `/props`, Ollama는 실행 중인 Model의 `/api/ps`, 기타 OpenAI 호환 Runtime은 `/v1/models`로 검사합니다.
- 연결 실패 시 loopback 주소, 포트, 해당 Model이 API에서 실제로 보이는지 확인합니다. `auth_env`를 쓴 경우 Supervisor가 해당 환경 변수를 읽을 수 있어야 합니다.
- 후보가 없으면 Model의 `roles`, `harnesses`, 작업의 `min_context`와 Attached Harness의 `trusted`를 확인하세요.

## 고급 설정

- 앱에서 llama.cpp를 시작하려면 `ownership: "managed"`와 `executable`, `model_path`를 지정합니다. Ollama와 기타 OpenAI 호환 서버는 실행 중인 프로세스에 연결합니다.
- OpenCode에 같은 로컬 Model을 전달하려면 `kind: "opencode"`인 Harness와 Runtime을 등록합니다. 앱은 검증한 로컬 한도를 OpenCode 설정에 전달합니다. 실제 적용은 CLI 출력에서 관측되는 범위로 제한됩니다.
- 기존 CLI 로그인으로 Codex를 읽기 전용으로 사용하려면 `kind: "codex"`, `trusted: true`, `allow_unverified: true`인 Harness를 신뢰하는 실행 파일에 한해 사용합니다. 기본 `subscription` Provider에 Model을 등록하고 `runtime`을 생략합니다. CLI가 쓰는 별칭이 다르면 `cli_model`을 지정합니다.
- 자동 경로는 역할, 최소 Context, Harness/도구 지원을 필터링하고 `quality`, `reliability`, `tool_score`, `cost`와 ID 순으로 결정합니다. 키의 기본값과 제약은 [설정 및 API](../admin-guide/configuration.md)를 참고하세요.
