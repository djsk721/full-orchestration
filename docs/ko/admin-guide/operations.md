# 운영 환경

## 호스트 및 서비스 계정

- 앱, Supervisor, Git, Runtime, 외부 CLI는 같은 Windows 사용자 환경에서 운용합니다. Git과 실행하려는 `.exe`를 해당 계정에서 사용할 수 있어야 합니다.
- Background Execution에서 로그인 시작이 필요하면 GUI 작업을 정리하고 Windows 실행 파일을 빌드한 뒤 아래 명령을 실행합니다. 기본 데이터 폴더를 쓰는 대화형 사용자 작업입니다. 제거 시 두 번째 명령만 실행하세요.

```powershell
.\Register-SupervisorTask.ps1
.\Register-SupervisorTask.ps1 -Unregister
```

- Scheduler 등록 시 `ORCHESTRA_DATA`가 설정되어 있으면 스크립트가 거절합니다. Supervisor 상태는 **작업 대시보드**에서 확인합니다.

## 인증 및 보안 설정

- Model HTTP Runtime은 loopback입니다. Attached Runtime의 Bearer 값은 `auth_env`가 가리키는 환경 변수에 둡니다. Managed llama.cpp 및 OpenCode 로컬 연결에는 인증 없는 로컬 주소가 필요합니다.
- 구독형 CLI는 해당 계정의 기존 로그인을 사용합니다. `trusted`, `allow_unverified`, `inherit_environment`, `allow_write`는 신뢰한 CLI와 Workspace에서 필요한 경우에만 켭니다. CLI 권한과 Git 변경 검사는 완전한 OS 격리를 제공하지 않습니다.
- 앱에는 SSH 호스트, 키, 패스프레이즈, `known_hosts` 또는 원격 Workspace 등록 화면이 없습니다. [Remote Execution 로드맵](../roadmap.md)을 참고하세요.
- QA argv는 사용자의 권한으로 실행됩니다. 신뢰하는 작업 정의와 저장소에서만 승인하고, 전용 비특권 계정과 OS의 파일 및 네트워크 접근 제어를 적용하세요.

## MCP 정책

HTTP 업스트림에는 HTTPS를 사용하세요. loopback은 HTTP도 허용됩니다. `header_env`, `env`, `gateway_token_env`에는 변수 이름만 기록하세요. 도구마다 역할과 `read`/`write` 유형을 지정하고, 쓰기는 승인된 Developer 호출에만 허용합니다. loopback Gateway는 유효한 토큰을 요구하고 `native: true`인 읽기 도구만 게시합니다. 원본 설정 백업과 롤백 파일은 민감한 데이터로 취급하세요. [MCP 연결](../user-guide/mcp.md)

## CPU, GPU 및 메모리

`parallel_jobs`, `parallel_tasks`와 Runtime의 `slots`를 낮게 시작합니다. Supervisor는 운영자가 입력한 `gpu_mb` 및 `ram_mb`를 예약값으로 합산합니다. `gpu_budget_mb: 0`은 양수 GPU 예약을 허용하지 않으며 `ram_budget_mb: 0`은 RAM 예산 검사를 비활성화합니다. CPU 코어 및 메모리 실측은 OS 도구로 확인하세요. Windows 예제는 `gpu_layers: 0`입니다. [설정 및 API](configuration.md)

## 로그, 보고서 및 데이터

| 위치 | 내용 |
| --- | --- |
| `registry.json` | Provider, Model, Runtime, Harness, MCP 및 운영 설정 |
| `state.db` 및 SQLite WAL | 큐, 제출한 작업과 설정 스냅샷, 이벤트, 승인 인자, 호출 상태와 체크포인트 |
| `artifacts/` 및 `worktrees/` | Agent 출력, 노드별 및 통합 Git Worktree |
| `migrations/` | MCP 원본 설정 백업과 전환 저널 |
| `supervisor.json` | 실행 중인 Supervisor의 상태 및 Gateway 오류 |

기본 Windows 데이터 경로는 `%LOCALAPPDATA%\ModelOrchestration`입니다. `ORCHESTRA_DATA`로 별도 폴더를 사용할 수 있습니다. **JSON 보고서 저장**은 스펙·설정 해시, QA 종료 코드, 이벤트, 사용량과 결과 정보를 내보냅니다. 사용량이 누락된 호출은 별도로 집계합니다. 공유하기 전에 경로, 응답 및 이벤트를 검토하세요.

## 백업 및 복구

1. 새 작업 제출을 중단하고 진행 중인 작업이 안전한 상태인지 확인합니다. **Supervisor 종료** 후 앱을 닫아 데이터 쓰기를 중지합니다.
2. 데이터 폴더 전체와 대상 Git 저장소를 함께 백업합니다. SQLite WAL 파일이 남아 있으면 DB와 같은 시점의 사본을 보관합니다. Worktree 메타데이터가 원본 저장소와 경로를 참조하므로 원래 위치도 기록합니다.
3. Supervisor와 앱을 종료한 상태에서 같은 위치에 복원합니다. 이미 실행이 시작된 외부 쓰기가 있으면 외부 시스템의 상태를 먼저 대조하세요. MCP 롤백은 앱의 **롤백** 버튼으로 별도 확인합니다.
4. 앱을 다시 열고 최근 이력, 승인 상태, 조회 전용 작업, Git 대상 브랜치를 확인합니다. 백업의 권한과 암호화는 운영 환경에서 관리합니다.
