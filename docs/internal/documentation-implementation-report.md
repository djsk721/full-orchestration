# 문서 구현 및 검증 보고서

기준은 `f1bc7bd1d92d9c92b73f9f853ac4614dd59ef86a`입니다. 2026년 11월 19일 작업을 시작했습니다. 기존 한국어 README의 절차와 기능 설명을 검토하고 사용자·관리자·개발자 가이드에 재배치했습니다. [기능 인벤토리](documentation-inventory.md)와 [기능 매핑](features.json)에서 근거 및 미구현 상태를 확인할 수 있습니다.

## 변경 및 신규 파일

| 유형 | 파일 |
| --- | --- |
| 수정 | `README.md`, `.gitignore` |
| 새 루트 자료 | `README.en.md`, `CONTRIBUTING.md`, `CONTRIBUTING.en.md`, `CHANGELOG.md`, `LICENSE` |
| 공개 가이드 | `docs/ko/`, `docs/en/`에 각각 홈, 사용자 가이드 6개, 관리자 가이드 2개, 개발자 가이드 3개, 문제 해결, FAQ 및 로드맵 |
| 디자인과 이미지 | `docs/assets/`의 로고 마크, 실제 앱 스크린샷, Mermaid 원본과 SVG, `docs-theme/`의 언어 전환과 404 |
| 검증 | `mkdocs.yml`, `requirements-docs.txt`, `.markdownlint-cli2.yaml`, `scripts/docs/`의 Python 검사 3개와 npm 잠금 파일 |
| GitHub | `.github/workflows/docs-quality.yml`, `.github/pull_request_template.md` |
| 저장소 내부 자료 | `docs/internal/`의 이전 README, 기능 인벤토리·매핑, 번역 검토 해시, 이 보고서 |

## 구현 확인 및 범위

DAG, Agent/QA 실행, Managed Harness, Git 승인, Supervisor 백그라운드 복구와 SQLite는 자동 테스트로 확인했습니다. Provider와 Model은 GUI의 JSON 등록 방식이고 MCP는 알려진 설정 탐색과 제한된 전환을 지원합니다. SSH 원격 Worker, Desktop 언어 선택·도움말, 자동 OAuth 이관과 GUI 설정 마법사는 로드맵에 기록했습니다.

사이트는 한국어를 루트, 영어를 `/en/`에 게시합니다. `python -m mkdocs build --strict`로 `site/`를 빌드하고, `python scripts/docs/check_doc_structure.py --site site`로 HTML과 검색 인덱스를 검증합니다. 승인된 주소를 사용할 때 `DOCS_SITE_URL`에 정확한 게시 주소를 전달합니다. 사이트 자체는 GitHub Actions 산출물로 보관할 수 있습니다. Pages 또는 외부 호스트의 활성화에는 호스팅 설정이 필요합니다.

## 검증 결과

| 검증 | 결과 | 실행 및 근거 |
| --- | --- | --- |
| 한국어·영어 README 및 언어 링크 | PASS | `check_doc_structure.py`로 양방향 링크와 이미지 경로 확인. GitHub 소스 링크에 HTTP 200 응답. |
| 문서 구조 · 내부 링크 · 스크린샷 | PASS | `python scripts/docs/check_doc_structure.py`. 원본 Markdown 39개, 로컬 에셋 경로와 참조를 검사. 실제 Tkinter를 Linux Xvfb에서 새 데이터 폴더로 띄워 1240×800 PNG 캡처. |
| 번역 대응 및 오래된 번역 | PASS | `python scripts/docs/check_translations.py`. 사이트 15쌍 및 루트 문서 2쌍. 번역 삭제와 미검토 수정이 실패하는 것도 임시 복제에서 확인. |
| 문서 상태와 소스 일치 | PASS | `python scripts/docs/check_feature_consistency.py`. 상태와 소스·테스트 근거 10개 확인. 상태를 과장한 변형을 거절. |
| Markdown lint | PASS | `npm ci --prefix scripts/docs --ignore-scripts` 및 `npm run --prefix scripts/docs lint`. 이전 README는 보관 원문이므로 링크만 확인. |
| 프로덕션 빌드 및 결과 검증 | PASS | MkDocs strict 빌드 및 `check_doc_structure.py --site`. 루트와 테스트용 하위 경로에서 각각 HTML 31개 및 공용 검색 인덱스 확인. |
| 한국어·영어 탐색, 전환과 검색 | PASS | Chromium 브라우저로 하위 경로의 두 홈, 대응 Provider 페이지 양방향 이동, 한국어 `백그라운드`와 영어 `authentication` 검색, 왼쪽 탐색, 페이지 목차와 다음 문서 링크 확인. |
| 모드·모바일·404·코드 복사 | PASS | 실제 PNG 로드 및 크기, 클립보드의 QA 예제, 새로 고침 후 다크 모드, 390px 탐색, HTTP 404 및 영어 홈 이동을 Chromium에서 확인. |
| 코드 예제 및 외부 링크 | PASS | 한·영 JSON과 기존 두 예제를 앱 검증기로 검사. QA smoke의 `git --version` 정상 종료. 문서의 외부 URL 12개 모두 HTTP 200. |
| 기존 앱 회귀 | PASS | Linux에서 `python -m unittest discover -s tests -v` 10개 통과. 기본 샌드박스는 loopback 소켓을 차단하여 허용된 실행 환경에서 재실행. |
| 민감정보 | PASS | 스테이징한 변경을 Gitleaks 8.30.0로 검사. 스크린샷은 작업 이력이 없는 임시 폴더에서 캡처. |
| GitHub Actions | PASS | 문서 브랜치 push와 PR 이벤트 모두 성공. [PR 실행 및 사이트 산출물](https://github.com/djsk721/full-orchestration/actions/runs/44460311660). |
| Pages 게시·Windows 실기·실제 외부 CLI/GPU | NOT_VERIFIED | Pages 호스팅이 설정되어 있지 않습니다. 대상 환경에서 Windows 번들, 로그인 작업 및 실제 CLI·Model 통합 실행이 필요합니다. |

## 남아 있는 항목

GitHub의 라이선스 메타데이터와 저장소에서 프로젝트 라이선스를 확인할 수 없어 `LICENSE`에 현재 상태를 기록했습니다. 라이선스 선택과 호스팅 주소는 저장소 관리 결정입니다. [로드맵](../ko/roadmap.md)에 Desktop 다국어 및 도움말, SSH/Remote Execution, 양식 기반 설정의 현재 범위를 정리했습니다. 장기적으로 Material 유지보수 일정에 맞춰 Zensical의 언어 경로·검색·대응 문서 전환을 다시 검증합니다.
