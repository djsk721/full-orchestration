# 설정 및 API

## 레지스트리

**모델 및 실행 설정**은 UTF-8 JSON을 검증해 데이터 폴더의 `registry.json`에 저장합니다. 생략한 최상위 섹션에 기본값을 채우며, 이미 등록한 섹션을 가져올 때는 이전 섹션과 자동 합치지 않습니다. 새 작업은 제출 당시 설정을 저장합니다.

| 섹션 | 주요 설정 |
| --- | --- |
| `providers` | ID별 `kind`는 `local` 또는 `attached`입니다. 기본 항목은 `local`과 `subscription`입니다. |
| `models` | `provider`, 실제 `model` ID, 선택적 `runtime`, `harnesses`, `roles`, 점수와 `token_budget`을 연결합니다. |
| `runtimes` | `llama.cpp`, `ollama`, `openai-compatible` 중 하나입니다. `url`, `context`, `max_output`, `slots`, 예약값, 선택적 `auth_env`를 설정합니다. |
| `harnesses` | `managed`는 `max_rounds`를 받습니다. `opencode` 및 `codex`는 `executable`과 신뢰·실행 정책을 받습니다. |
| `mcp` | `transport`, `url` 또는 `command`, 환경 변수 참조, `tools` 정책을 지정합니다. |

## 실행 기본값

| 키 | 기본값 | 허용 범위 또는 의미 |
| --- | --- | --- |
| `background`, `allow_background_write`, `notifications` | 모두 `false` | JSON 불리언 |
| `parallel_jobs`, `parallel_tasks` | `2`, `3` | 각각 1–16 |
| `heartbeat_sec`, `lease_sec` | `15`, `90` | 각각 1–120초와 4–3600초. 임대는 하트비트의 최소 3배 |
| `job_timeout_sec`, `attempts` | `14400`, `2` | 각각 1–86400초와 1–5회 |
| `gpu_budget_mb`, `ram_budget_mb` | `0`, `0` | 각각 0–2097152. 0의 의미는 [운영 환경](operations.md) 참조 |
| `gateway_port` | `8767` | 1024–65535 |

Runtime은 기본 `context: 32768`, `max_output: 2048`, `slots: 1`을 사용합니다. 허용 범위는 각각 1024–2097152, 32–131072, 1–32입니다. `gpu_layers`가 양수이면 `gpu_mb`를 양수로 예약해야 합니다. 실제 요청의 출력 상한은 관측 Runtime 한도 및 Context와 함께 계산됩니다.

## 작업 정의

최상위 `title`, 저장소 루트의 절대 경로인 `repo`, 로컬 브랜치 `target`, `tasks` 1–100개를 입력합니다. `background`와 통합 `qa`는 선택 값이지만 쓰기 노드에는 통합 `qa`가 필요합니다. 노드의 필수 필드는 `id`, `role`, `prompt`, `acceptance`입니다. 선택 필드에는 `depends`, `model`, `harness`, `read_paths`, `paths`, `tools`, `min_context`, `qa`가 있습니다. QA는 예를 들어 `[["git", "--version"]]`처럼 argv 배열의 목록으로 입력합니다.

## API 참조

| 진입점 | 계약 |
| --- | --- |
| `ModelOrchestration.pyw` | 기본값은 Desktop, `--supervisor`로 동일한 데이터 폴더의 Supervisor 실행 |
| `core.config_check`, `core.plan_check` | 구성을 검증하고 유효하지 않으면 `Invalid` 발생 |
| `Store.submit`, `Store.request`, `Store.decide` | 내부 Python 인터페이스. 작업 제출, 상태 요청, 도구 승인. 직접 DB 변경은 지원하지 않습니다. |
| `Store.events`, `Store.report` | 내부 이벤트 조회와 실행 보고서. 이벤트 커서는 증가하는 `seq`입니다. |
| `POST http://127.0.0.1:<gateway_port>/mcp/<profile>` | 토큰을 검증하는 MCP JSON-RPC. `initialize`, `ping`, `tools/list`, `tools/call` 지원. Native 읽기 정책 적용. |

작업 제출·스케줄링·조회에 공개 REST API는 없습니다. 모델 HTTP는 앱이 호출하는 Runtime 인터페이스입니다. MCP 외부 규약과 서버 설정은 [MCP Streamable HTTP](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)와 [OpenCode MCP 설정](https://opencode.ai/docs/mcp-servers/)을 참고하세요.
