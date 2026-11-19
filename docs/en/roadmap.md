# Roadmap and support boundaries

## Remote Execution

<!-- feature: remote PLANNED -->

The app has no GUI or execution backend for SSH authentication, host management, remote Workspaces, Remote Workers, remote logs, or connection recovery. The current Workspace, Supervisor, and Git Worktrees are on the same host. External HTTPS MCP servers provide tool calls. Future work on this page has no announced delivery date.

## Desktop language and help

<!-- feature: desktop-localization PLANNED -->

The desktop UI and most user-facing errors are currently Korean. The English guides include the Korean button labels. Potential work includes Korean/English selection, a persisted locale, translated errors and tooltips, and a Help action that opens the matching documentation.

## Setup and operational scope

<!-- feature: setup-ui PLANNED -->
<!-- feature: live-integration NOT_VERIFIED -->

Setup wizards, Git repository creation, form-based Provider editing and connection tests, a GUI toggle for MCP bindings, automatic OAuth migration, hardware telemetry, and distributed scheduling are outside the current scope. The Windows bundle and integrations with real GPUs and external CLI accounts still need validation in their operational environment.
