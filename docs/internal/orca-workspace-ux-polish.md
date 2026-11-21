# Workspace UX polish

## Working in one window

- Choose a project in the sidebar or project selector. The project overview opens the terminal launcher directly. The right panel remembers its Files, Git, Agent, or Activity tab per project.
- Use **Focus** to temporarily give the terminal both side panels' space. **Show panels** restores the previous visibility choices. The existing splitter can compare two live sessions in either direction.
- Use **View → Open tabs** to reach any open regular tab, including tabs displaced by a narrow strip. The same menu contains Provider settings, panel toggles and language preferences.
- Create the task with **New task**, review the plan and permission evidence, then use the task tab for Agent activity, changes and QA. **Review merge** opens the existing authoritative approval interface.

## Remote Git

Pinned OpenSSH invokes the Worker using the existing JSON protocol. The new read-only methods accept an approved repository and, for a diff, one canonical project-relative path. The Worker checks the active Git status before previewing a changed path. Secret paths, out-of-scope repositories and traversal requests are rejected server-side. Diffs use Git blob content and bounded filesystem reads. They exclude external diff commands, binary previews, and unbounded output.

**Git → Reload** starts a new observation. A failed SSH connection shows a reconnect/reload message. A Worker built before the new methods reports that it needs an update. Existing remote job state, approval handling, and SSH host authentication operate through their original paths.

## Layout and language

Language choice is persisted in the UI preferences. Choose Korean or English from **View → Language** and reopen the app to apply it. This leaves foreground terminals running until the user decides to close the app. For launch-time overrides, use `ORCHESTRA_LANG=ko` or `ORCHESTRA_LANG=en`. Existing administrative subpages retain their existing localization coverage.

Layout preferences contain project associations, tab order, focused tab, split direction, ratios, context choice and panel visibility. Focus mode is temporary. A saved terminal restores as a placeholder and requires **Open session** to start a new process.

## Verification boundary

Real installed OpenCode and Codex ran together in disposable Linux user, network and PID namespaces with isolated configuration and loopback only. The test entered text without submitting a prompt, used the app's clipboard, switched focus, resized the panes and confirmed process cleanup. Separate fixtures exercise the entire task-to-approval workflow and detached execution. Full native Windows, authenticated inference, and GPU behavior remain unverified. [Results and screenshots](orca-workspace-qa.md)
