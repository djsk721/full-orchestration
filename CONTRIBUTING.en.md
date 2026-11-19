# Contributing to Model Orchestration

[한국어](CONTRIBUTING.md) · **English**

## Start a change

Use a feature branch. Verify behavior changes with an existing or new regression test. Keep API tokens, real user registries, data directories, job artifacts, and CLI settings out of commits.

```bash
python -m unittest discover -s tests -v
```

## Documentation and translations

Follow the [documentation maintenance guide](docs/en/developer-guide/documentation.md). Match paths and sections in both languages. Include original Korean desktop labels in English instructions. Update the translation manifest after reviewing the pair.

```bash
python -m pip install -r requirements-docs.txt
npm ci --prefix scripts/docs
python scripts/docs/check_translations.py --ack user-guide/providers.md
```

## Checks and preview

```bash
npm run --prefix scripts/docs lint
python scripts/docs/check_translations.py
python scripts/docs/check_doc_structure.py
python scripts/docs/check_feature_consistency.py
python -m mkdocs build --strict
python scripts/docs/check_doc_structure.py --site site
python -m mkdocs serve
```

Include reproducible test results and links to affected guides in the PR. Check the [feature mapping](docs/internal/features.json) when changing user-visible behavior or defaults.
