# Providers and models

Start with the [Provider setup wizard](workspace.md) for guided registration. The JSON steps below use **Settings → Advanced JSON**.
<!-- feature: providers PARTIALLY_IMPLEMENTED -->

## Concept

A Provider identifies whether a Model uses a `local` Runtime or is reached through an `attached` CLI. A Model entry links its registry ID to the Runtime's actual Model name, eligible roles, and Harnesses. The app runs OpenCode as an Attached Harness. Direct Model HTTP calls are limited to loopback.

## Desktop workflow

1. In **설정 → 고급 JSON** (Model and execution settings), choose **JSON 가져오기** (Import JSON) for an example or **저장된 설정 열기** (Open saved settings).
2. In `providers`, add an entry with `kind: "local"` or `kind: "attached"`. For a Model with a Runtime, connect the entries in `runtimes` and `models`. **설정 저장** (Save settings) checks the schema.
3. In **새 작업** (New job), set a task's `model` and `harness` to their registry IDs, or omit them for automatic route selection.
4. Run a read-only Agent job and check `runtime.snapshot` and `route.failed` in the dashboard. Runtime connectivity and capability checks run as part of the job.

## Example

This registry uses an OpenAI-compatible loopback server that already runs and returns `my-local-model` with `context_length` or `max_model_len` from `/v1/models`. The server must also support chat and tool calling for Managed execution. Substitute your server URL and Model ID.

```json
{
  "providers": {"local": {"kind": "local"}},
  "runtimes": {
    "local-http": {
      "kind": "openai-compatible",
      "ownership": "attached",
      "url": "http://127.0.0.1:8080",
      "context": 8192
    }
  },
  "models": {
    "local-model": {
      "provider": "local",
      "model": "my-local-model",
      "runtime": "local-http",
      "harnesses": ["managed"]
    }
  }
}
```

## Troubleshooting

- For a Context validation error, check the Model ID and the Context the server actually exposes. The probe reads llama.cpp's `/props`, Ollama's `/api/ps` for a running Model, or an OpenAI-compatible server's `/v1/models`.
- For a connection failure, verify the loopback address, port, and Model availability in the API. If you set `auth_env`, the Supervisor must be able to read that environment variable.
- If no route is eligible, check the Model's `roles` and `harnesses`, the task's `min_context`, and the Attached Harness's `trusted` setting.

## Advanced settings

- To let the app start llama.cpp, set `ownership: "managed"` and provide `executable` and `model_path`. Start Ollama and other OpenAI-compatible servers separately.
- To connect OpenCode to the same local Model, configure a `kind: "opencode"` Harness and a Runtime. The app passes validated local limits to OpenCode. Actual application of those settings can only be confirmed where the CLI exposes evidence.
- To use Codex in read-only mode with its existing login, set `kind: "codex"`, `trusted: true`, and `allow_unverified: true` for a CLI you trust. Register the Model under the default `subscription` Provider and omit `runtime`. Use `cli_model` if the CLI expects a different alias.
- Automatic routing filters by role, minimum Context, and Harness/tool compatibility. It ranks eligible routes by `quality`, `reliability`, `tool_score`, and `cost`, with IDs breaking ties. See [Configuration and API](../admin-guide/configuration.md) for defaults and constraints.
