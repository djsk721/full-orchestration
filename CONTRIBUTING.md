# Model Orchestration 기여 가이드

**한국어** · [English](CONTRIBUTING.en.md)

## 작업 시작

기능 브랜치에서 작업합니다. 동작이 바뀌면 기존 또는 신규 회귀 테스트로 확인합니다. API 토큰, 실제 사용자 레지스트리, 데이터 폴더, 작업 결과물과 CLI 설정을 커밋하지 마세요.

```bash
python -m unittest discover -s tests -v
```

## 문서와 번역

[문서 관리 가이드](docs/ko/developer-guide/documentation.md)를 따르세요. 두 언어의 경로와 섹션을 맞추고, 영어 문서에는 앱의 실제 한국어 버튼을 함께 표기합니다. 검토가 끝난 문서 쌍만 번역 매니페스트에 기록합니다.

```bash
python -m pip install -r requirements-docs.txt
npm ci --prefix scripts/docs
python scripts/docs/check_translations.py --ack user-guide/providers.md
```

## 검사와 미리 보기

```bash
npm run --prefix scripts/docs lint
python scripts/docs/check_translations.py
python scripts/docs/check_doc_structure.py
python scripts/docs/check_feature_consistency.py
python -m mkdocs build --strict
python scripts/docs/check_doc_structure.py --site site
python -m mkdocs serve
```

PR에는 재현할 수 있는 검증 결과와 관련 문서를 연결합니다. 사용자 동작이나 설정 기본값을 바꾸면 [기능 매핑](docs/internal/features.json)에서 관련 문서를 확인하세요.
