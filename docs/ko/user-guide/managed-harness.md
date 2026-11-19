# Managed Harness

<!-- feature: managed-harness IMPLEMENTED -->

## 개념

Managed Harness는 앱이 작업의 Context, 도구 정책, 반복 제한, 체크포인트를 직접 관리하는 실행 방식입니다. Runtime의 소유권(`managed` 또는 `attached`)은 별도 설정입니다. 이미 실행 중인 로컬 서버와 Managed Harness를 함께 쓸 수 있습니다.

## GUI 사용 방법

1. **설정 → 고급 JSON**에서 Model이 허용하는 Harness 목록에 `managed`를 포함합니다. Model에 로컬 Runtime을 연결합니다.
2. **새 작업**에서 노드의 `harness`를 `managed`로 설정합니다. 필요에 따라 `read_paths`로 읽기를 좁히고, Developer 노드에서는 `paths`로 쓰기 범위를 좁힙니다.
3. **작업 대시보드**의 `runtime.snapshot`, `context.compaction`, `task.checkpoint`, `model.usage`를 확인합니다. 외부 도구 쓰기는 **도구 승인 검토**에서 호출 인자를 검토해 승인하거나 거절합니다.
4. Git 파일 변경은 별도의 Reviewer 노드와 통합 QA로 확인할 수 있습니다. 병합 승인은 도구 쓰기 승인과 각각 적용됩니다.

## 실제 예제

기본 Explorer 노드에 `"harness": "managed"`와 `"read_paths": ["README.md"]`를 넣고 진입점을 찾아 달라는 읽기 전용 작업을 제출하세요. 허용한 문서에서 개요가 작성되는지 결과를 확인합니다. 노드에 쓰기 경로나 외부 도구를 추가할 필요가 없습니다.

## 오류 해결

- 읽기 전용 도구 호출 Probe가 실패하면 해당 Model과 서버의 도구 호출 형식을 확인합니다.
- 반복 호출이 거절되거나 라운드 한도에 도달하면 명세를 작게 나누고 필요한 도구만 선택합니다. 체크포인트 이후 도구 스키마가 바뀌면 새 작업을 제출합니다.
- 승인 후 중단된 외부 쓰기는 대상 시스템의 결과를 확인합니다. 실행을 시작한 호출은 완료 여부가 불명확할 때 자동 재호출하지 않습니다.

## 고급 설정

`max_rounds`는 기본 30입니다. Model의 `token_budget`을 설정하면 관측된 사용량을 검증하고 출력 상한을 줄입니다. 사용량 관측값을 제공하지 않는 Runtime에서는 이 예산 검증이 실패할 수 있습니다. Context 압축은 앱의 추정치와 대화 발췌를 사용합니다. 세션 로그와 원본 체크포인트의 보관 방법은 [운영 환경](../admin-guide/operations.md)을 참고하세요.
