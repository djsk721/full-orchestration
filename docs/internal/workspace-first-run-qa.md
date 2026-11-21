# Workspace first-run QA

The prior flow opened the workspace before the language choice, hid the local runtime URL behind Advanced, and used one ambiguous connection-test button for both model and SSH checks. A clean launch now asks for language before constructing workspace widgets. The Provider wizard shows runtime URL in Simple mode. Setup presents independent **Test local connection** and **Test SSH connection** actions with separate feedback.

| Case | Actual evidence | Status |
| --- | --- | --- |
| Clean launch, language and Git folder | Linux native Tk selected English in a clean profile and discovered a Git root from a nested folder in a Korean path | PASS |
| CLI discovery and first terminal | The clean flow detected a controlled Codex executable and opened a real PTY. The independent installed-binary smoke covers actual OpenCode and Codex. | PASS |
| New Provider, model and optional SSH | The same clean profile registered a loopback llama.cpp-compatible Provider and selected its discovered model in Simple mode. It registered a disposable SSH profile and kept the local task on its local route. | PASS |
| Natural-language task, DAG, Agent and changed files | One continuous Tk workflow used the real Supervisor, SQLite and Git with scripted model output | PASS |
| QA and exact candidate approval | QA passed, the merge review showed candidate SHA and revision, and the approved SHA became Git HEAD | PASS |
| Live external Provider authentication or inference | The scenario uses a loopback fixture | NOT VERIFIED |
| Native Windows first launch and Korean IME | Prepared separately in the Windows validation report | NOT VERIFIED |

```bash
xvfb-run -a -s '-screen 0 1920x1080x24' python tests/smoke_workspace_first_run.py --screenshots qa-evidence/first-run
```

[Language choice](../assets/screenshots/orca-workspace/production/language-picker.png) · [940×650 clean workspace](../assets/screenshots/orca-workspace/production/clean-workspace-940x650.png) · [Configured setup](../assets/screenshots/orca-workspace/production/configured-setup.png) · [1440×900 task](../assets/screenshots/orca-workspace/production/task-execution-1440x900.png) · [Git approval](../assets/screenshots/orca-workspace/production/git-qa-approval.png)
