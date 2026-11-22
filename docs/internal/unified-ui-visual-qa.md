# Model Orchestration — Unified UI Visual QA Report

## 1. Visual Inspection Scope & Method

Real screenshots of the consolidated Tk application (`WorkspaceDesktop`) were captured under Xvfb using `tests/smoke_unified_ui.py --screenshots docs/assets/screenshots/unified-ui` across **12 screens** at **3 resolutions**:

- `1280×770` (`docs/assets/screenshots/unified-ui/1280x770/`)
- `1664×900` (`docs/assets/screenshots/unified-ui/1664x900/`)
- `1920×1080` (`docs/assets/screenshots/unified-ui/1920x1080/`)

In addition, compact responsiveness (`940×650`) and header/status-bar non-overlap were asserted programmatically in `tests/smoke_unified_ui.py`, `tests/smoke_integrated_workspace.py`, and `tests/smoke_workspace_localization.py`.

---

## 2. Before vs. After Architecture Comparison

| Aspect | Before Consolidation | After Consolidation | Evidence |
| --- | --- | --- | --- |
| **Shell Switching** | Legacy dark/light admin shell (`docs/assets/screenshots/ui-ux-redesign/01-tk-home-dashboard.png`, `07-tk-provider-settings.png`) replaced the workspace sidebar (`nav_scroll_canvas` ↔ `workspace_sidebar`) and reshaped the header bar. | Single unified Orca-style shell stays intact across Workspace, Terminals, File Explorer, Tasks, Agents, Providers, SSH, MCP, History, and Settings. | [Provider Settings (`1280x770`)](../assets/screenshots/unified-ui/1280x770/07-provider-settings.png), [SSH Management (`1280x770`)](../assets/screenshots/unified-ui/1280x770/08-ssh-management.png) |
| **Default Visual Theme** | Dark theme default with mismatched sidebar/toolbar density vs. workspace view. | Minimal Orca-inspired light default (`#ffffff` center workspace, `#f6f7f9` sidebar, `#fafafa` header, 1px `#e5e7eb` dividers) with full dark theme parity. | [Empty Workspace (`1280x770`)](../assets/screenshots/unified-ui/1280x770/01-empty-workspace.png), [Dark Theme (`1920x1080`)](../assets/screenshots/unified-ui/1920x1080/12-dark-theme.png) |
| **Global Controls** | Duplicate `"새 작업"` button, duplicate footer (`sidebar_footer` + `workspace_status`), dual sidebar search/nav chrome. | One `48px` header, one project selector (`sidebar_picker`), one `"새 작업"` CTA, one terminal menu, one model picker, one status bar. | [Registered Project (`1280x770`)](../assets/screenshots/unified-ui/1280x770/02-registered-project.png) |

---

## 3. Issues Found & Fixed During Visual Inspection

1. **Non-Xft Hangul Font Fallback & Glyph Tofu (`01-empty-workspace.png` initial capture)**:
   - *Observation*: Removing `"gothic"` from `resolve_fonts()` left Anaconda Tk without Xft falling back to literal `"TkDefaultFont"` tuples, causing Korean characters and `"⚙"`/`"☰"` glyphs to render as tofu boxes.
   - *Fix*: Restored `"gothic"`/`"courier 10 pitch"` at the end of the non-Windows fallback list in `orchestra/ui/theme.py` (after scalable fonts), resolved actual family names when `"TkDefaultFont"` is returned, and updated `PRIMARY_NAV` / toggle glyphs to `"◎"` / `"≡"`.
2. **Sidebar Utility Strip Clipping at `236px` (`01-empty-workspace.png` initial capture)**:
   - *Observation*: Packing 4 buttons (`Provider`, `SSH`, `MCP`, `기록`) horizontally inside `236px` pushed `MCP` and `기록` past the sidebar border.
   - *Fix*: Changed `sidebar_utility` in `orchestra/workspace_shell.py` to a uniform 2×2 grid so all 4 buttons fit cleanly with zero clipping.
3. **`Provider` Table Column Width & `jobs_page` Search Entry Squeezing (`07-provider-settings.png`, `10-task-and-dag.png`)**:
   - *Observation*: `Provider` column (`85px`) slightly clipped `"subscription"` at `1280×770`; `jobs_page` inline search `Entry` competed with toolbar buttons, hiding the `"검색"` label at `1280×770`; `detail_evidence` wraplength (`540`) caused tight bottom spacing at `1664×900`.
   - *Fix*: Adjusted `provider_models_list` widths (`140, 105, 175, 130, 100`), moved `jobs_page` search filter onto a dedicated `filter_bar` row with compact table column widths (`130, 84, 62, 72`), and bound `detail_evidence` wraplength dynamically to `header_card.body` width. Re-captured and visually verified clean in `1280×770` and `1664×900`.

---

## 4. Captured 12-Screen Verification Inventory (`1280×770`, `1664×900`, `1920×1080`)

| # | Screen | `1280×770` | `1664×900` | `1920×1080` | Visual Check |
| --- | --- | --- | --- | --- | --- |
| 1 | Empty workspace | [1280x770](../assets/screenshots/unified-ui/1280x770/01-empty-workspace.png) | [1664x900](../assets/screenshots/unified-ui/1664x900/01-empty-workspace.png) | [1920x1080](../assets/screenshots/unified-ui/1920x1080/01-empty-workspace.png) | Clean light shell, onboarding CTA visible, 2×2 utility buttons aligned |
| 2 | Registered project | [1280x770](../assets/screenshots/unified-ui/1280x770/02-registered-project.png) | [1664x900](../assets/screenshots/unified-ui/1664x900/02-registered-project.png) | [1920x1080](../assets/screenshots/unified-ui/1920x1080/02-registered-project.png) | Project selected in header & tree, file explorer active, status bar accurate |
| 3 | OpenCode terminal | [1280x770](../assets/screenshots/unified-ui/1280x770/03-opencode-terminal.png) | [1664x900](../assets/screenshots/unified-ui/1664x900/03-opencode-terminal.png) | [1920x1080](../assets/screenshots/unified-ui/1920x1080/03-opencode-terminal.png) | PTY ANSI colors, startup model shown in terminal & status bar |
| 4 | OpenCode + Codex split | [1280x770](../assets/screenshots/unified-ui/1280x770/04-split-terminals.png) | [1664x900](../assets/screenshots/unified-ui/1664x900/04-split-terminals.png) | [1920x1080](../assets/screenshots/unified-ui/1920x1080/04-split-terminals.png) | Both live PTY panes, focus outline, sidebar live session indicators |
| 5 | Project File Explorer | [1280x770](../assets/screenshots/unified-ui/1280x770/05-project-file-explorer.png) | [1664x900](../assets/screenshots/unified-ui/1664x900/05-project-file-explorer.png) | [1920x1080](../assets/screenshots/unified-ui/1920x1080/05-project-file-explorer.png) | Directory expansion, Git `M` marker, read-only preview |
| 6 | Agent Dashboard | [1280x770](../assets/screenshots/unified-ui/1280x770/06-agent-dashboard.png) | [1664x900](../assets/screenshots/unified-ui/1664x900/06-agent-dashboard.png) | [1920x1080](../assets/screenshots/unified-ui/1920x1080/06-agent-dashboard.png) | Unified shell preserved, `Agent 대시보드` active, tokens & events intact |
| 7 | Provider settings | [1280x770](../assets/screenshots/unified-ui/1280x770/07-provider-settings.png) | [1664x900](../assets/screenshots/unified-ui/1664x900/07-provider-settings.png) | [1920x1080](../assets/screenshots/unified-ui/1920x1080/07-provider-settings.png) | Settings nav highlighted, KPI cards & model table aligned without clipping |
| 8 | SSH management | [1280x770](../assets/screenshots/unified-ui/1280x770/08-ssh-management.png) | [1664x900](../assets/screenshots/unified-ui/1664x900/08-ssh-management.png) | [1920x1080](../assets/screenshots/unified-ui/1920x1080/08-ssh-management.png) | Unified shell preserved, host table & fingerprint details clean |
| 9 | MCP management | [1280x770](../assets/screenshots/unified-ui/1280x770/09-mcp-management.png) | [1664x900](../assets/screenshots/unified-ui/1664x900/09-mcp-management.png) | [1920x1080](../assets/screenshots/unified-ui/1920x1080/09-mcp-management.png) | Unified shell preserved, wrapped toolbar & binding detail clean |
| 10 | Task & DAG | [1280x770](../assets/screenshots/unified-ui/1280x770/10-task-and-dag.png) | [1664x900](../assets/screenshots/unified-ui/1664x900/10-task-and-dag.png) | [1920x1080](../assets/screenshots/unified-ui/1920x1080/10-task-and-dag.png) | Task list, filter bar, status badge, and embedded DAG canvas clean |
| 11 | QA & Git approval | [1280x770](../assets/screenshots/unified-ui/1280x770/11-qa-and-git-approval.png) | [1664x900](../assets/screenshots/unified-ui/1664x900/11-qa-and-git-approval.png) | [1920x1080](../assets/screenshots/unified-ui/1920x1080/11-qa-and-git-approval.png) | Approval modal KPI cards, candidate SHA, QA revision, and buttons aligned |
| 12 | Dark theme | [1280x770](../assets/screenshots/unified-ui/1280x770/12-dark-theme.png) | [1664x900](../assets/screenshots/unified-ui/1664x900/12-dark-theme.png) | [1920x1080](../assets/screenshots/unified-ui/1920x1080/12-dark-theme.png) | Consistent dark re-theming across header, sidebar, tabs, terminals, explorer, and status bar |
