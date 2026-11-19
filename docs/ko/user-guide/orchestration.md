# Multi-Agent Orchestration

<!-- feature: orchestration IMPLEMENTED -->
<!-- feature: git-gate IMPLEMENTED -->

## 개념

작업의 `tasks`는 방향성 비순환 그래프(DAG)를 이룹니다. 로컬 Supervisor가 스케줄러이며 각 노드가 하나의 Agent 작업 또는 QA 명령을 나타냅니다. 사용자가 역할과 의존성을 지정합니다. Planner와 Diagnostic도 작업 역할이며 Planner의 출력이 자동으로 새 노드를 등록하지는 않습니다.

## GUI 사용 방법

1. **새 작업**에서 기존 Git 저장소와 대상 브랜치를 고릅니다. `tasks`에 각 노드의 `id`, `role`, `prompt`, `acceptance`와 `depends`를 입력하세요.
2. 쓸 파일이나 디렉터리는 Developer 노드의 `paths`에 저장소 상대 경로로 지정합니다. 겹치는 쓰기 범위에는 의존성이 필요합니다. 쓰기 작업에는 작업 전체의 `qa`도 입력합니다.
3. **작업 제출** 후 대시보드에서 Agent별 실행 경로, 상태, 시도 번호, 이벤트를 확인합니다. **결과 폴더 열기**는 저장된 Agent 응답을, **JSON 보고서 저장**은 실행 요약을 엽니다.
4. 변경이 있고 통합 QA가 통과하면 **병합 승인**에서 대상 브랜치와 후보 SHA를 확인합니다. 사용자 승인 후 fast-forward가 실행됩니다.

## 실제 예제

**JSON 열기**에서 [Windows 작업 예제](https://github.com/djsk721/full-orchestration/blob/develop/examples/plan.windows.json)를 가져옵니다. 첫 Developer 노드는 `overview.md`만 쓸 수 있고, Reviewer는 `depends: ["documentation"]`으로 그 커밋을 독립 Worktree에서 검토합니다. Reviewer 응답 마지막 줄이 `REVIEW: PASS`여야 다음 단계로 진행합니다. 통합 QA는 파일 크기를 검사합니다. 실험용 저장소의 경로와 브랜치를 지정한 후 실행하세요.

## 오류 해결

- 제출이 거절되면 누락된 노드 ID, 순환 의존성, 겹치는 병렬 쓰기 범위, QA 누락 여부를 확인합니다.
- 일시적 오류는 한도 안에서 자동 재시도될 수 있습니다. 실패한 작업은 원인을 수정하고 **재시도**할 수 있습니다. 완료된 노드는 재실행하지 않으며 결과를 알 수 없는 외부 쓰기는 재개가 차단됩니다.
- QA 실패 시 명령 위치와 종료 코드를 확인하세요. 병합 직전에 브랜치가 이동했거나 Worktree가 수정되면 새 기준으로 검증할 작업을 제출하세요.

## 고급 설정

`planner`, `developer`, `explorer`, `reviewer`, `qa`, `diagnostic` 역할을 사용할 수 있습니다. 별도 Model/Harness 지정 없이 `qa` 역할에 QA 명령만 넣으면 Model 호출을 생략합니다. `read_paths`, `min_context`, 설정 스냅샷 및 실행 한도는 [설정 및 API](../admin-guide/configuration.md)를 참고하세요.
