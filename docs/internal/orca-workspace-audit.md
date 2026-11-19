# Integrated workspace baseline audit

## Repository and migration history

Before editing, the working tree was clean. Local `main`, `origin/main`, and the live remote default branch all resolved to `e76e876ec65c61caaeda2a92fe431ce26df3f610`. The remote advertised only `main`. The implementation starts from that commit on `feature/orca-workspace`.

Local history retained the earlier TypeScript preview commit `c89be4b` and the report-only commit `28086eb`. Comparing `apps/desktop` at the old tip to `main` found the preview on `main` with subsequent portable contracts, platform adapters, and read-only safeguards. The old branch's unique report commit updated five migration reports. No execution or workspace code was recovered from the old branch.

## Existing components and gaps

| Component | Baseline behavior | Workspace integration |
| --- | --- | --- |
| Tk control plane | Grouped navigation, project detail, standalone terminal and operator pages | Place work tabs, project/session tree and local context in a common shell |
| Terminal | Python PTY on Linux, ConPTY adapter on Windows, Tk/pyte surface | Make project-associated sessions independently focusable, resizable and restorable, and improve full-screen terminal behavior |
| Provider and Harness | Configuration wizard, executable discovery, connectivity checks, task routing | Surface configured models and expose only verified interactive startup options |
| Agent, DAG and approvals | Supervisor events and task data, graph, QA and exact candidate approval | Compose existing evidence in workspace task tabs and Agent context |
| SSH | Pinned OpenSSH, saved hosts, file operations and detached Linux Worker | Use the same connection/profile controls from the workspace tabs |
| Explorer | Project Git metadata, task diff and remote Worker file operations in individual views | Add a persistent read-only Files/Git context next to the terminal |
| Electron and TypeScript | Read-only preview with portable event and orchestration contracts | Align the monitor visually and launch it from Tk with the same data root |

`ttk.Notebook`, `ttk.Panedwindow`, `Treeview`, and the existing native PTY adapters support the required fixed dock positions, independent tabs, panel resizing and terminal interaction. Geometry-managed split widgets can be replaced without moving or restarting their underlying process. A free-floating dock manager would require a different UI implementation and is outside the workspace interaction selected here.

The supplied Orca reference organizes registered projects and sessions at left, uses the center primarily for terminal work, and shows file context at right. The implemented shell uses these positions, keeps its existing theme system, and adds Agent and execution context within the same window. Native screenshots and verification boundaries are in the [QA report](orca-workspace-qa.md).
