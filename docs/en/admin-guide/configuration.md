# Configuration and API

## Registry

**설정 → 고급 JSON** (Settings → Advanced JSON) validates UTF-8 JSON and saves it to `registry.json` in the data directory. Omitted top-level sections use defaults. Importing a section replaces its previous contents when saved. Jobs keep the settings snapshot from submission.

| Section | Main settings |
| --- | --- |
| `providers` | Each ID has `kind` set to `local` or `attached`. The defaults are `local` and `subscription`. |
| `models` | Links `provider`, the real `model` ID, optional `runtime`, `harnesses`, `roles`, scores, and `token_budget`. |
| `runtimes` | One of `llama.cpp`, `ollama`, or `openai-compatible`. Set `url`, `context`, `max_output`, `slots`, reservations, and optional `auth_env`. |
| `harnesses` | `managed` accepts `max_rounds`. `opencode` and `codex` accept an `executable` and trust and execution policies. |
| `mcp` | Specifies `transport`, `url` or `command`, environment references, and `tools` policy. |

## Execution defaults

| Key | Default | Range or meaning |
| --- | --- | --- |
| `background`, `allow_background_write`, `notifications` | All `false` | JSON booleans |
| `parallel_jobs`, `parallel_tasks` | `2`, `3` | 1–16 each |
| `heartbeat_sec`, `lease_sec` | `15`, `90` | 1–120s and 4–3600s, respectively. A lease must be at least three heartbeat intervals. |
| `job_timeout_sec`, `attempts` | `14400`, `2` | 1–86400s and 1–5 attempts, respectively |
| `gpu_budget_mb`, `ram_budget_mb` | `0`, `0` | 0–2097152 each. See [Operations](operations.md) for what zero means. |
| `gateway_port` | `8767` | 1024–65535 |

Runtime defaults are `context: 32768`, `max_output: 2048`, and `slots: 1`. The respective ranges are 1024–2097152, 32–131072, and 1–32. A positive `gpu_layers` requires a positive `gpu_mb` reservation. The effective output cap also accounts for observed Runtime limits and Context.

## Job definition

Set the top-level `title`, the absolute repository root `repo`, the local branch `target`, and 1–100 `tasks`. `background` and integration `qa` are optional, but jobs with write paths require integration `qa`. Each node requires `id`, `role`, `prompt`, and `acceptance`. Optional fields include `depends`, `model`, `harness`, `read_paths`, `paths`, `tools`, `min_context`, and `qa`. QA takes a list of argv arrays, such as `[["git", "--version"]]`.

## API reference

| Entry point | Contract |
| --- | --- |
| `ModelOrchestration.pyw` | Starts the desktop by default. `--supervisor` starts the Supervisor for the same data directory. |
| `core.config_check`, `core.plan_check` | Validate configuration and plans. Invalid inputs raise `Invalid`. |
| `Store.submit`, `Store.request`, `Store.decide` | Internal Python interfaces for submission, state requests, and tool approval. Direct database writes are unsupported. |
| `Store.events`, `Store.report` | Internal event and report interfaces. The event cursor is an increasing `seq`. |
| `POST http://127.0.0.1:<gateway_port>/mcp/<profile>` | Token-protected MCP JSON-RPC. Supports `initialize`, `ping`, `tools/list`, and `tools/call` with the native read policy. |

Job submission, scheduling, and queries have no public REST API. Model HTTP is the Runtime interface called by the app. For the external MCP protocol and server setup, see [MCP Streamable HTTP](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) and [OpenCode MCP configuration](https://opencode.ai/docs/mcp-servers/).
