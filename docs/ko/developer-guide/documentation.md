# 문서 관리

## 문서 편집

한국어가 기준입니다. `docs/ko/`와 `docs/en/`의 상대 경로와 섹션 순서를 맞추세요. 한국어 Desktop 버튼의 원문을 영어 가이드에 함께 표시합니다. Provider, Model, Agent, MCP, Managed Harness, Orchestration, Session, Context, Background Execution, Remote Execution, Workspace와 설정 키는 원래 표기를 유지합니다. 예제에는 실제 자격 증명 대신 환경 변수 이름을 사용하세요.

두 언어를 검토한 뒤 저장소 루트에서 `python scripts/docs/check_translations.py --ack user-guide/providers.md`처럼 검토한 쌍을 기록합니다. README와 기여 가이드는 각각 `README.md`, `CONTRIBUTING.md`를 인수로 사용합니다. 파일의 어느 쪽이든 변경되면 검토 기록이 오래되었는지 검사합니다.

## 기능 변경

사용자에게 보이는 기능, 기본값, GUI 라벨, 오류 복구 절차를 변경하면 `docs/internal/features.json`에서 관련 문서와 테스트를 확인합니다. 기능 상태가 바뀌면 매핑과 양쪽 문서의 상태 표시를 갱신합니다. 맞닿은 소스만 바뀌면 CI에 검토 안내가 표시됩니다. 내부 리팩터링은 PR에 문서 영향이 없음을 적으면 됩니다.

## 로컬 빌드 및 게시

Python 3.11과 Node.js 24 환경에서 아래 명령을 실행합니다.

```bash
python -m pip install -r requirements-docs.txt
npm ci --prefix scripts/docs
npm run --prefix scripts/docs lint
python -m mkdocs serve
python -m mkdocs build --strict
python scripts/docs/check_doc_structure.py --site site
```

빌드의 한국어 경로는 `/`, 영어는 `/en/`입니다. 승인된 정적 호스트에 `site/` 전체를 배치하고 찾을 수 없는 경로에 `404.html`을 연결하세요. 도메인과 경로가 승인되면 빌드 환경의 `DOCS_SITE_URL`에 승인된 전체 주소를 지정하고 실제 하위 경로에서 언어 전환과 에셋을 점검합니다. PR 검증은 읽기 권한으로 수행하며 게시 작업은 해당 호스트에 맞추어 별도로 구성합니다.

## Zensical 호환성

MkDocs 1.6.1, Material 9.8.1, mkdocs-static-i18n 1.3.0의 폴더 모드를 사용합니다. Material의 중요 유지보수는 2027년 5월 5일까지입니다. Zensical은 임의의 MkDocs 플러그인을 실행하지 않으며 다국어 프로젝트 기능은 로드맵에 있습니다. 이동을 검토할 때 Markdown과 언어 트리는 유지하고 언어별 배포 경로, 대응 페이지 전환, 검색 인덱스, 404 및 엄격한 링크 검증을 새 빌드에서 비교합니다. [Material 유지보수 일정](https://zensical.org/upcoming-changes/) · [Zensical 플러그인 호환성](https://zensical.org/docs/compatibility/mkdocs/plugins/) · [다국어 로드맵](https://zensical.org/roadmap/)
