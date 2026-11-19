# 자주 묻는 질문

## 기존 Git 저장소가 필요한가요?

예. 앱에서 Git 저장소 루트와 커밋이 있는 대상 로컬 브랜치를 선택합니다. [시작하기](user-guide/getting-started.md)

## Model 없이 실행할 수 있나요?

명령만 실행하는 `qa` 역할에 `qa` 명령을 설정하고 `model`과 `harness`를 생략하세요. 다른 Agent 역할은 유효한 경로가 필요합니다. [작업 실행](user-guide/orchestration.md)

## 실행이 끝나면 자동으로 병합하나요?

파일 변경의 통합 QA가 통과하면 후보 커밋이 승인 대기에 들어갑니다. 사용자가 해당 SHA에 대해 승인해야 병합이 진행됩니다. [작업 실행](user-guide/orchestration.md)

## 앱을 닫아도 계속 실행되나요?

설정과 제출한 작업 모두에서 Background Execution을 켜면 별도 Supervisor가 작업을 이어갑니다. [Background Execution](user-guide/background.md)

## 영어 문서와 앱의 메뉴가 왜 다른가요?

문서 사이트의 언어는 바꿀 수 있으며 현재 Desktop 메뉴는 한국어입니다. 영어 가이드에서 괄호 안 번역과 원래 버튼 이름을 함께 참고하세요. [로드맵](roadmap.md)
