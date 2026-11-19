# Documentation maintenance

## Editing documentation

Korean is the source language. Match relative paths and section order under `docs/ko/` and `docs/en/`. Include the Korean desktop labels alongside their English translations. Keep Provider, Model, Agent, MCP, Managed Harness, Orchestration, Session, Context, Background Execution, Remote Execution, Workspace, and configuration keys in their established forms. Use environment variable names in examples that require credentials.

After reviewing both languages, record the pair from the repository root, for example with `python scripts/docs/check_translations.py --ack user-guide/providers.md`. Use `README.md` or `CONTRIBUTING.md` for the root pairs. Changing either file makes the acknowledgment stale.

## Feature changes

For user-facing behavior, defaults, desktop labels, or recovery changes, check `docs/internal/features.json` for affected documentation and tests. If a feature's status changes, update the mapping and corresponding markers in both languages. CI prints a review notice when mapped source changes without its docs. For internal refactoring, explain the lack of documentation impact in the PR.

## Local build and publishing

Run the commands below with Python 3.11 and Node.js 24.

```bash
python -m pip install -r requirements-docs.txt
npm ci --prefix scripts/docs
npm run --prefix scripts/docs lint
python -m mkdocs serve
python -m mkdocs build --strict
python scripts/docs/check_doc_structure.py --site site
```

The build serves Korean at `/` and English at `/en/`. Deploy the full `site/` directory to the approved static host and configure its missing-page response to serve `404.html`. Once the domain and base path are approved, set `DOCS_SITE_URL` to the full approved site URL when building and check language switching and assets at the actual subpath. PR validation runs with read access. Configure deployment separately for the chosen host.

## Zensical compatibility

The site uses folder mode with MkDocs 1.6.1, Material 9.8.1, and mkdocs-static-i18n 1.3.0. Material receives critical maintenance through May 5, 2027. Zensical does not run arbitrary MkDocs plugins and lists multilingual project support on its roadmap. Preserve the Markdown and language trees for a migration trial, then compare locale routes, equivalent-page switching, search indexes, 404 behavior, and strict link checks with the new builder. [Material maintenance schedule](https://zensical.org/upcoming-changes/) · [Zensical plugin compatibility](https://zensical.org/docs/compatibility/mkdocs/plugins/) · [Multilingual roadmap](https://zensical.org/roadmap/)
