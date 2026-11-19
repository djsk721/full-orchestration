# Workspace and administration localization

Korean remains the initial language. **View → Language** saves the selection for the next launch to keep active terminals running until the user closes the app. `ORCHESTRA_LANG` can override the launch preference. Theme changes preserve the saved language.

The English and Korean labels cover workspace navigation, setup and task wizards, project and job details, Provider and Advanced settings, SSH/Worker administration, Managed MCP catalog and policy forms, and integrated Git and tool approvals. Provider connection types and task strategies map display choices back to canonical values before validation or saving. Wrapped toolbars and captions protect action placement when texts have different widths.

Native checks used 940×650 for the English workspace and administrative navigation. They opened the task, Provider, SSH and MCP forms, inspected labels and available choices, and verified a translated tooltip and a protected-path error. Korean integration exercises the task execution and approval dialogs. [Provider](../assets/screenshots/orca-workspace/onboarding/admin-provider-en.png) · [SSH](../assets/screenshots/orca-workspace/onboarding/admin-ssh-en.png) · [MCP](../assets/screenshots/orca-workspace/onboarding/admin-mcp-en.png)

The Electron monitor keeps its existing English UI and read-only contract. Shared terminology includes Provider, Worker, Integration QA and merge approval. User-authored titles, upstream CLI text, external tool output, recorded event identifiers and raw advanced JSON keep their original content. Unknown upstream errors can use a localized summary in the workspace.
