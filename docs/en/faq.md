# Frequently asked questions

## Do I need an existing Git repository?

Yes. Select its root and a local target branch with an existing commit. [Getting started](user-guide/getting-started.md)

## Can I run a job without a Model?

Use a `qa` role with `qa` commands and omit `model` and `harness`. Other Agent roles need a usable route. [Running jobs](user-guide/orchestration.md)

## Does a successful run merge automatically?

After integration QA passes for a change, the candidate commit awaits approval. The user must approve that SHA before a merge runs. [Running jobs](user-guide/orchestration.md)

## Do jobs continue after I close the app?

When Background Execution is enabled in both the registry and the submitted plan, a separate Supervisor continues the job. [Background Execution](user-guide/background.md)

## Why are the desktop menus in Korean?

The documentation site has a language selector. Desktop menus currently use Korean, so the English guides show both the label and its translation. [Roadmap](roadmap.md)
