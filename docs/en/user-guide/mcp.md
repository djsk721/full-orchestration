# MCP connections

<!-- feature: mcp PARTIALLY_IMPLEMENTED -->

## Concept

Model Context Protocol (MCP) connects Agents to external tools. MCP profiles live in the global registry's `mcp` section, independently of Providers. Discovered CLI bindings are shown as **Federated** and remain in use by their original CLI. For a Managed Harness job, you explicitly register a profile and allow specific tools in each task.

## Desktop workflow

1. In **MCP 연결** (MCP connections), choose **사용자 설정 탐색** (Scan user settings) or **프로젝트 탐색** (Scan project). The scan checks known paths for Codex, OpenCode, Claude Code, Gemini CLI, and Antigravity.
2. Select a server to see its path, scope, fingerprint, enabled state, and possible conflicts. The enabled state reflects the source file.
3. For a Managed job, save each allowed tool and role under `mcp.<profile>.tools` in **설정 → 고급 JSON** (Settings → Advanced JSON). Add the virtual name to the node's `tools` list in **새 작업** (New job). Omit it to keep it from the node.
4. Submit a read-only job and inspect `route.failed`, `tool.call`, and the result. Migration to the Gateway has a separate read-only probe in the UI.

## Example

Add this profile under `mcp` in the registry. Replace the sample URL with the address of your MCP server. If the server exposes `search`, add `"documentation__search"` to an Explorer node's `tools`. Omit `header_env` if the server needs no authentication.

```json
{
  "documentation": {
    "transport": "http",
    "url": "https://mcp.example.com/mcp",
    "header_env": {"Authorization": "DOCS_MCP_AUTH"},
    "gateway_token_env": "ORCHESTRA_DOCS_GATEWAY_TOKEN",
    "tools": {
      "search": {"access": "read", "roles": ["explorer", "reviewer"], "native": true}
    }
  }
}
```

## Troubleshooting

- A conflict can mean multiple definitions with the same name or duplicate fingerprints. Inspect the detail pane and confirm precedence and account identity in the original CLI. Resolve duplicates before migration.
- For a missing tool, check the task's role, the virtual name, and the server catalog. The usual form is `profile__tool`. Unsupported characters become underscores, and names longer than 64 characters are shortened with a hash.
- When an external write pauses, inspect the arguments under **도구 승인 검토** (Review tool approval). If a call began and its outcome is unknown, inspect the remote system's records.

## Advanced settings

- For `stdio`, use an argv array in `command` and environment variable names in `env`. For HTTP, reference environment variable names in `header_env`.
- **Gateway 전환** (Migrate to Gateway) supports OpenCode JSON and compatible Codex TOML tables. Register the same upstream first and copy the discovered `account_scope` for any authenticated binding. Select the profile, a read tool, and JSON arguments to approve the byte-for-byte backup, read probe, replacement, and verification.
- The Gateway uses a token of at least 24 characters from the configured environment variable and exposes read tools marked `native: true`. To pick up new environment values, stop the Supervisor and restart it with those values set. Reload the external CLI session after migration.
- Use **Gateway 감사** (Gateway audit) for profile events and **롤백** (Rollback) with the ID from the completion dialog. It stops when it detects an intervening source change. Discovery of OpenCode JSONC and other CLI formats is read-only.
