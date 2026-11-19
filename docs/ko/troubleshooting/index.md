# 문제 해결

## 설치 및 실행

| 증상 | 확인할 사항 |
| --- | --- |
| 실행 창이 뜨지 않음 | `py -3 -m tkinter`, Git PATH, Python 3.11 이상을 확인합니다. |
| Supervisor 연결 중에서 반복 | 같은 데이터 폴더인지 확인하고 **Supervisor 시작**을 누릅니다. `supervisor.json`이 갱신되는지 확인합니다. |
| Gateway 포트 오류 | `gateway_port` 충돌을 확인하고 설정을 저장합니다. 환경 변수 변경은 Supervisor 재시작 후 적용합니다. |

## 작업 및 검증

| 증상 | 확인할 사항 |
| --- | --- |
| Runtime 검사 실패 | 대시보드의 `runtime.snapshot` 및 `route.failed`를 확인합니다. [Provider 및 Model](../user-guide/providers.md) |
| 도구 승인 대기 | **도구 승인 검토**에서 선택한 노드와 인자를 확인합니다. 결과 불명의 외부 쓰기는 외부 시스템에서 확인합니다. [MCP 연결](../user-guide/mcp.md) |
| 검증 실패 또는 병합 불가 | `qa.result`, Reviewer의 마지막 줄, 대상 브랜치 SHA와 Worktree 상태를 확인합니다. [작업 실행](../user-guide/orchestration.md) |
| 작업을 닫은 뒤 중지됨 | 포그라운드 세션의 연결 여부와 제출 시점의 백그라운드 설정을 확인합니다. [Background Execution](../user-guide/background.md) |

## 보고할 정보

앱의 실행 방식과 운영체제, 재현 순서, 작업 상태, 관련 이벤트 및 QA 종료 코드를 기록하세요. **JSON 보고서 저장**으로 보고서를 만들고 사용자 경로, 설정, CLI 출력과 데이터가 포함되어 있는지 검토한 뒤 공유하세요. 레지스트리와 원본 데이터 폴더 전체는 지원 요청에 첨부하지 마세요.
