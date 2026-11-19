# 문서 인벤토리

기준 커밋은 `f1bc7bd1d92d9c92b73f9f853ac4614dd59ef86a`입니다. 초기 저장소에는 한국어 README, Python 패키지 `orchestra/`, Windows 실행·빌드·로그인 작업 스크립트, JSON 예제 2개, unittest 모듈 1개가 있었습니다. 초기 README 본문은 [이전 README](legacy-readme.md)에서 볼 수 있습니다. 이동에 따라 예제 링크의 상대 경로만 수정했습니다.

앱은 Python 3.11+, 표준 라이브러리, Tkinter, Git CLI를 사용합니다. 기준 시점에 `package.json`, Electron, 번역 리소스, 사이트 설정, CI, 정식 라이선스 또는 GitHub 릴리스가 없었습니다. 추가한 Node.js 도구는 문서 검사에 사용합니다.

## 상태 기준

`IMPLEMENTED`는 명시한 동작이 소스에 있고 자동 테스트로 재현되는 상태입니다. `PARTIALLY_IMPLEMENTED`는 현재 제공하는 일부 흐름에 제한이 있는 상태입니다. `PLANNED`는 현재 구현이 없는 향후 항목이며 일정을 뜻하지 않습니다. `NOT_VERIFIED`는 실제 대상 환경에서 검증이 남은 상태입니다. GUI 명칭은 현재 화면에서 사용하는 한국어를 기록했습니다.

## 기능별 근거

| 기능 및 상태 | 접근과 설정 | 구현, 오류 및 검증 |
| --- | --- | --- |
| Desktop 및 입력 검증 · IMPLEMENTED | `Launch-Windows.cmd` / `ModelOrchestration.pyw`, **새 작업**, **모델 및 실행 설정** | `Desktop.layout`, `submit`, `save_registry`와 `core.plan_check`, `config_check`. 잘못된 값은 오류 대화 상자에 표시. Linux 가상 디스플레이에서 실제 Tk 시작과 Supervisor 연결을 확인. |
| Provider 및 Model · PARTIALLY_IMPLEMENTED | 앱 내 JSON 편집기. `providers/models/runtimes/harnesses`. 연결 검증은 작업 실행 중 | `runtime.routes`, `RuntimeClient.probe`; Context·경로 오류는 `route.failed`. 모의 Runtime 검증 및 OpenCode 연결 테스트. 직접 모델 HTTP는 loopback, 전용 양식이나 연결 버튼 없음. |
| Attached CLI · PARTIALLY_IMPLEMENTED | `trusted`, `allow_unverified`, `allow_write` 및 CLI 기존 로그인 | `harness.attached`에서 OpenCode 설정 생성과 Codex 읽기 전용 argv 적용. 버전·종료 코드·JSON 결과를 검사. 모의 OpenCode 테스트가 있으며 실제 계정 및 CLI 동작은 미검증. |
| MCP · PARTIALLY_IMPLEMENTED | **MCP 연결**에서 탐색, 전환, 롤백, 감사. 레지스트리와 노드에서 도구 선택 | `discovery.discover/migrate/rollback`, `mcp.MCPClient/Gateway`, `Managed.discover/execute`. HTTP/stdio, 역할 정책, 읽기 전용 Gateway, 지문 보호. 전환·롤백·쓰기 승인 테스트. 모든 CLI 전환, OAuth 자동 이전, GUI 토글은 없음. |
| Managed Harness · IMPLEMENTED | `managed`, Model Runtime, 읽기·쓰기 범위, `max_rounds`, 필요 시 토큰 예산 | `Managed.execute_plan`, `compact`, `RuntimeClient.probe`, `Store.checkpoint`. 도구 스키마·반복·범위 오류 처리, 결과 불명 쓰기 재호출 방지. Runtime Gate, 승인 후 체크포인트, Supervisor 충돌 복구 테스트. |
| Multi-Agent Orchestration · IMPLEMENTED | **새 작업**의 `tasks/depends/role`, **작업 대시보드** | `ordered`, `JobRunner`가 위상 순서, 동시성, 독립 Reviewer, QA-only, 재시도를 처리. DAG 오류, Reviewer 실패, 종료 코드 검증. 병렬 DAG 및 모델 없는 QA 테스트. |
| Git Gate · IMPLEMENTED | 대상 로컬 브랜치, Developer `paths`, QA argv, **병합 승인** | `GitGate`의 기준 SHA, Worktree, 변경 경로와 모드, 통합 QA, 후보 SHA 검증. 대상 이동·더러운 Worktree·비 fast-forward 차단. 통합 병합 및 QA 실패 테스트. |
| Background Execution · IMPLEMENTED | 레지스트리와 작업에 각각 `background: true`, 대시보드 및 로그인 스크립트 | `Supervisor.serve`, `Store.claim/recover`, `processes.Child`. 클라이언트 presence, lease, heartbeat, 취소 및 제한된 재시도. 만료 임대·프로세스 분리·충돌 복구 테스트. Windows Job Object와 Task Scheduler 실기 검증은 별도. |
| 설정·저장소·보고 · IMPLEMENTED | `registry.json`, `state.db`, 결과 폴더, **JSON 보고서 저장** | `core.atomic_json`, `Store`의 WAL·트랜잭션·이벤트와 요약 보고. 로컬 Python 인터페이스 및 토큰 보호 MCP API. 작업 관리용 공개 REST API 없음. |
| SSH/Remote Execution · PLANNED | 연결, 원격 Workspace, 실행/로그 화면 없음 | 로컬 Supervisor와 Worktree만 확인. 외부 MCP와 CLI 자체 네트워크 이용은 Remote Worker가 아님. 해당 테스트 없음. |
| 양식 기반 설정 및 처음 실행 · PLANNED | 앱 내 JSON 편집과 저장소 선택 구현 | Wizard, Git 초기화, Provider 전용 연결 테스트 버튼과 MCP 활성화 토글은 소스에서 확인되지 않음. |
| Desktop i18n 및 도움말 · PLANNED | 문서 사이트만 한·영 언어 전환 제공 | `desktop.py`의 라벨·상태·대화 상자, `core.py` 및 백엔드 예외에 직접 작성한 문자열. 런타임 locale, 저장된 언어 선택, 오류/툴팁 번역, 도움말 URL 연결 없음. |
| 실제 Windows 번들/외부 계정/GPU · NOT_VERIFIED | `Build-Windows.ps1`, 실기 프로세스 수명 주기 및 모델 구성 필요 | 모의 서버와 테스트 CLI에서 검증. Windows 빌드·로그인 작업, 외부 계정·GPU 프로브, Orca 실측 비교는 운영 환경 검증이 남음. |

## Desktop 언어 및 도움말 적용 검토

기존 공용 번역 계층이 없습니다. 후속 구현에서 Desktop의 문자열과 상태 표시를 메시지 ID로 옮기고 `locales/ko.json`, `locales/en.json`을 패키징합니다. 레지스트리는 허용 설정 키를 엄격히 검증하고 실행 시 설정 스냅샷에 포함하므로 UI 언어는 실행 구성과 별도의 사용자 기본 설정에 저장하는 편이 안전합니다. 백엔드 오류는 오류 코드와 표시 인자를 먼저 도입한 후 Desktop에서 번역할 수 있습니다. 기존 Python 오류 문자열은 호환 기간에 fallback으로 유지합니다. 툴팁과 키보드 접근성은 Desktop 프레임워크에서 검증하고, 도움말은 한국어/영어의 대응 경로를 선택하도록 연결합니다. 게시 주소 결정 전에는 정해지지 않은 URL을 앱에 넣을 필요가 없습니다.

## 검증 및 유지보수

테스트 참조와 문서 변경 안내는 [기능 매핑](features.json)에 기록합니다. 검증 상태는 [구현 보고서](documentation-implementation-report.md)를 참고하세요.
