# Windows workspace projects and orchestration E2E

**Operator desktop status NOT VERIFIED.** The previous Windows CI source workflow used a deterministic loopback model and real Supervisor, SQLite and Git. Its installed lifecycle independently verified first-run startup and data preservation. No manual task, merge, live SSH or recovery evidence was supplied from the operator's Windows app.

The deterministic Supervisor and Git workflow and the single hosted OpenAI GPT probe have different objectives. The hosted probe was not executed. Keep it out of repository-modifying QA and use the [separate GPT evidence report](windows-opencode-gpt-integration.md).

| Acceptance row | Status | Evidence |
| --- | --- | --- |
| Local project, nested Unicode paths, file and Git UI | NOT VERIFIED | Run the disposable fixture on the operator desktop. |
| Controlled workflow through QA and isolated merge | NOT VERIFIED | Windows CI source baseline passed. The operator desktop is outstanding. |
| Supervisor interruption, stale QA and wrong candidate rejection | NOT VERIFIED | Automated contract evidence exists. A new Windows run after the discovery correction is outstanding. |
| Windows live SSH / Remote Worker | NOT VERIFIED | An authorized Windows-accessible endpoint and independently verified host fingerprint are required. |

## Project and file fixture

Use the disposable Git repository and loopback Provider procedure from [Windows native validation](windows-native-ux-validation.md#installed-workflow-with-a-controlled-local-provider). Register the repository by selecting a nested folder such as `자료 폴더\nested dir`. Confirm the app detects the repository root and current branch. Register a second disposable repo and switch between them.

Add and commit a harmless text file in the nested folder. Modify it and add a second untracked text file. In the context panel, expand directories, preview and search by filename, inspect modified indicators, Git status and the actual Git diff. Open a project terminal and run `git rev-parse --show-toplevel` and `git branch --show-current`. Confirm a fixture-only `.env` and out-of-root targets remain unavailable through file preview. Use fabricated marker text for denied-path checks. Reopen the app and compare selected project, tabs and session placeholders.

## Task, QA and isolated merge

1. Open the `desktop-fixture` Provider and select `test-model`. Submit the **Change, review and QA** plan for `ui-result.txt` described in the linked fixture procedure. Examine the generated plan and confirm the `review` node depends on `develop`.
2. Inspect live Agent state, model and Harness, execution logs, changed-file report and successful QA. Open the Git approval and record candidate SHA, target branch, QA verification cycle and eligibility.
3. In the fixture repository only, approve the eligible candidate and confirm the repository SHA advances to the approved SHA. Capture the job ID and final state. Restart and verify the job ID, QA evidence and merge result in the same isolated profile.
4. In separate fixtures, submit a task with a deliberate nonzero QA exit and confirm no eligible merge. Use the desktop stop action on a separate live task and confirm cancellation. Exercise stale QA revision, candidate mismatch and Supervisor interruption/recovery with the existing isolated contract suite rather than editing the state database or production repository.

```powershell
py -3 -m unittest discover -s tests -p test_orchestra.py -v
py -3 -m unittest discover -s tests -p test_platform_contracts.py -v
```

Record explicit states, revision and SHA comparisons, approved/unavailable button states and screenshots. The disposable repository is the only target for the test merge.

## Live authorized SSH

Register a dedicated SSH profile, verify the fingerprint against the trusted test-server channel and test the connection. Open the remote shell using a disposable repository. Record Worker version and negotiated capabilities. Reconnect, then confirm remote Git status and diff against a known fixture edit. Preserve the installed Worker. Store only diagnostic output and redact credentials or private host details. Keep this check NOT VERIFIED when no authorized endpoint is available.
