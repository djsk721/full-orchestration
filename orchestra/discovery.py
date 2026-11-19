from __future__ import annotations

import json
import os
import re
import tomllib
import uuid
from pathlib import Path

from .core import Invalid, atomic_bytes, atomic_json, digest, ident, require, settings
from .mcp import MCPClient, do_call, virtual_name
from .runtime import secret

JSONC = re.compile(r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*[\s\S]*?\*/|,\s*(?=[}\]])')
ACCOUNT_FIELDS = {"headers", "environment", "env", "env_vars", "oauth", "bearer_token_env_var", "http_headers",
                  "env_http_headers", "oauth_resource", "authorization"}


def parse_file(path, raw, client):
    source = raw.decode("utf-8-sig")
    if client in ("codex",):
        return tomllib.loads(source)
    if path.suffix.lower() in (".jsonc", ".json5"):
        source = JSONC.sub(lambda m: m[0] if m[0].startswith('"') else " ", source)
        source = JSONC.sub(lambda m: m[0] if m[0].startswith('"') else " ", source)
    return json.loads(source)


def entries(obj, client):
    if client == "codex":
        return obj.get("mcp_servers", {})
    if client in ("claude", "gemini", "antigravity"):
        return obj.get("mcpServers", {})
    section = obj.get("mcp", {})
    return section.get("servers", section)


def discover(project=None):
    home = Path.home()
    codex = Path(os.environ.get("CODEX_HOME", str(home / ".codex")))
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))
    opencode = xdg / "opencode"
    values = [
        ("opencode", "global", opencode / "opencode.json"),
        ("opencode", "global", opencode / "opencode.jsonc"),
        ("codex", "global", codex / "config.toml"),
        ("claude", "global", home / ".claude.json"),
        ("gemini", "global", home / ".gemini" / "settings.json"),
        ("antigravity", "global", home / ".gemini" / "antigravity" / "mcp_config.json"),
    ]
    if os.name == "nt" and os.environ.get("APPDATA"):
        roaming = Path(os.environ["APPDATA"]) / "opencode"
        values += [("opencode", "global", roaming / name) for name in ("opencode.json", "opencode.jsonc")]
    if os.environ.get("OPENCODE_CONFIG"):
        values.append(("opencode", "override", Path(os.environ["OPENCODE_CONFIG"]).expanduser()))
    if project:
        root = Path(project).resolve()
        values += [
            ("opencode", "project", root / "opencode.json"),
            ("opencode", "project", root / "opencode.jsonc"),
            ("codex", "project", root / ".codex" / "config.toml"),
            ("claude", "project", root / ".mcp.json"),
            ("gemini", "project", root / ".gemini" / "settings.json"),
        ]
    records, failures, seen = [], [], set()
    for client, scope, path in values:
        if not path.is_file() or path in seen:
            continue
        seen.add(path)
        try:
            raw = path.read_bytes()
            obj = parse_file(path, raw, client)
            registered = entries(obj, client)
            if client == "claude" and scope == "global" and project:
                local = obj.get("projects", {}).get(str(Path(project).resolve()), {}).get("mcpServers", {})
                registered = registered | local
            for name, item in registered.items():
                if not isinstance(item, dict) or not ("url" in item or "httpUrl" in item or "command" in item or "serverUrl" in item):
                    continue
                authenticated = bool(any(item.get(key) for key in ACCOUNT_FIELDS)
                                     or client == "opencode" and item.get("url") and item.get("oauth") is not False)
                if client == "codex" and item.get("url"):
                    authenticated = True
                env_names = set()
                for key in ACCOUNT_FIELDS:
                    value = item.get(key)
                    if isinstance(value, dict):
                        env_names.update(value.keys())
                url = item.get("url") or item.get("httpUrl") or item.get("serverUrl")
                command = item.get("command")
                argv = command if isinstance(command, list) else [command, *item.get("args", [])] if command else None
                connection = {"transport": "http" if url else "stdio", "url": url,
                              "command": argv, "cwd": item.get("cwd"), "env_keys": sorted(env_names),
                              "account_scope": f"{client}:{path}:{name}" if authenticated else None}
                records.append({"client": client, "scope": scope, "path": str(path), "name": name,
                                "file_hash": digest(raw.hex()), "transport": connection["transport"],
                                "fingerprint": digest(connection), "authenticated": authenticated,
                                "account_scope": connection["account_scope"],
                                "enabled": item.get("enabled", True) and not item.get("disabled", False),
                                "mode": "Federated"})
        except (ValueError, OSError, TypeError, AttributeError):
            failures.append({"path": str(path), "status": "설정 해석 실패"})
    for row in records:
        same_name = [other for other in records if other["client"] == row["client"] and other["name"] == row["name"]]
        duplicates = [other for other in records if other["client"] == row["client"] and other["fingerprint"] == row["fingerprint"]]
        row["alternatives"] = len(same_name) - 1
        row["duplicates"] = len(duplicates) - 1
        row["precedence"] = ("프로젝트 후보 우선 · CLI 적용 확인 필요"
                             if row["alternatives"] else "별도 바인딩")
    return records, failures


def gateway_probe(config, profile, tool, args):
    spec = config["mcp"][profile]
    token_var = spec.get("gateway_token_env")
    require(isinstance(token_var, str) and len(secret(token_var)) >= 24, "Gateway 토큰 환경 변수가 필요합니다 (24자 이상).")
    alias = virtual_name(profile, tool)
    url = f'http://127.0.0.1:{settings(config)["gateway_port"]}/mcp/{profile}'
    class ProbeClient(MCPClient):
        def headers(self):
            return super().headers() | {"Authorization": "Bearer " + secret(token_var)}

    with ProbeClient({"transport": "http", "url": url}) as client:
        catalog = client.catalog()
        require(alias in catalog, "Gateway 읽기 전용 Probe 도구를 찾을 수 없습니다.")
        do_call(client, alias, catalog[alias], args)
    return url, token_var


def migrate(root, config, record, profile, tool, args, project=None):
    ident(profile)
    require(profile in config["mcp"], "Gateway 프로파일을 찾을 수 없습니다.")
    require(record["client"] in ("opencode", "codex"), "이 CLI는 읽기 전용 탐색을 지원합니다.")
    candidates, _ = discover(project)
    selected = next((row for row in candidates if row == record), None)
    require(selected and selected["enabled"] and not selected["alternatives"] and not selected["duplicates"],
            "기존 바인딩의 수정 또는 중복이 발견되었습니다. 초기 탐색 결과를 새로고침하세요.")
    path = Path(record["path"])
    require(not path.is_symlink(), "심볼릭 링크 설정 파일은 전환할 수 없습니다.")
    require(record["client"] != "opencode" or path.suffix.lower() == ".json",
            "OpenCode JSONC 설정은 읽기 전용 탐색을 지원합니다.")
    original = path.read_bytes()
    require(digest(original.hex()) == record["file_hash"], "원본 설정이 변경되었습니다.")
    document = parse_file(path, original, record["client"])
    servers = entries(document, record["client"])
    entry = servers[record["name"]]
    spec = config["mcp"][profile]
    url = entry.get("url")
    if url:
        require(spec["transport"] == "http" and spec["url"] == url, "발견된 URL과 Gateway 원본 URL이 다릅니다.")
    else:
        command = entry["command"]
        argv = command if isinstance(command, list) else [command, *entry.get("args", [])]
        require(spec["transport"] == "stdio" and spec["command"] == argv and spec.get("cwd") == entry.get("cwd"),
                "발견된 명령/CWD와 Gateway 원본 설정이 다릅니다.")
    if record["authenticated"]:
        require(spec.get("account_scope") == record["account_scope"],
                "인증된 바인딩에는 발견된 account_scope를 명시해야 합니다.")
    key = uuid.uuid4().hex
    journal = root / "migrations" / key
    journal.mkdir(parents=True, mode=0o700)
    backup = journal / "original"
    atomic_bytes(backup, original)
    endpoint, token = gateway_probe(config, profile, tool, args)
    binding = "orchestra_" + profile.replace(".", "_").replace("-", "_")
    require(binding not in servers, "Gateway 이름이 기존 바인딩과 충돌합니다.")
    if record["client"] == "opencode":
        new = {"type": "remote", "url": endpoint, "oauth": False,
               "headers": {"Authorization": "Bearer {env:" + token + "}"}}
        if servers is not document["mcp"]:
            new["codemode"] = False
        del servers[record["name"]]
        servers[binding] = new
        replacement = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode()
    else:
        name = record["name"]
        ident(name)
        require("." not in name, "복합 TOML 키는 자동 전환을 지원하지 않습니다.")
        source = original.decode("utf-8-sig")
        table = re.compile(r"(?m)^\s*\[([^]\r\n]+)\]\s*(?:#[^\n]*)?$")
        headings = list(table.finditer(source))
        changed = source
        ranges = []
        match_base = "mcp_servers." + name
        for i, match in enumerate(headings):
            if match[1] == match_base or match[1].startswith(match_base + "."):
                ranges.append((match.start(), headings[i+1].start() if i+1 < len(headings) else len(source)))
        require(ranges, "이 Codex TOML 테이블 형식은 읽기 전용 탐색을 지원합니다.")
        for start, end in reversed(ranges):
            changed = changed[:start] + "\n" + changed[end:]
        changed += (f"\n[mcp_servers.{binding}]\nurl = {json.dumps(endpoint)}\n"
                    f"bearer_token_env_var = {json.dumps(token)}\n")
        parsed = tomllib.loads(changed)
        expected = entries(document, "codex").copy()
        del expected[name]
        expected[binding] = {"url": endpoint, "bearer_token_env_var": token}
        require(parsed == (document | {"mcp_servers": expected}), "TOML 변경 범위를 검증할 수 없습니다.")
        replacement = changed.encode()
    data = {"path": str(path), "before": record["file_hash"], "after": digest(replacement.hex()),
            "profile": profile, "state": "prepared"}
    metadata = journal / "migration.json"
    atomic_json(metadata, data)
    require(path.read_bytes() == original, "원본 설정이 외부에서 변경되었습니다.")
    atomic_bytes(path, replacement)
    try:
        require(path.read_bytes() == replacement, "전환 후 설정이 외부에서 변경되었습니다.")
        gateway_probe(config, profile, tool, args)
    except Exception as error:
        try:
            rollback(root, key)
        except (ValueError, OSError) as restore_error:
            raise Invalid(f"MCP 전환 후 변경 충돌이 발생했습니다. 롤백 ID {key}") from restore_error
        raise Invalid(f"MCP 전환 검증에 실패해 원본을 복원했습니다. 롤백 ID {key}") from error
    atomic_json(metadata, data | {"state": "applied"})
    return key


def rollback(root, key):
    ident(key)
    journal = root / "migrations" / key
    metadata = journal / "migration.json"
    require(metadata.is_file(), "전환 기록을 찾을 수 없습니다.")
    data = json.loads(metadata.read_text(encoding="utf-8"))
    path = Path(data["path"])
    require(path.is_file() and not path.is_symlink(), "원본 설정 경로가 변경되었습니다.")
    current = digest(path.read_bytes().hex())
    before = (journal / "original").read_bytes()
    require(current in (data["before"], data["after"]) and digest(before.hex()) == data["before"],
            "설정 변경 충돌이 있어 덮어쓰기를 중단했습니다.")
    if current == data["after"]:
        atomic_bytes(path, before)
    atomic_json(metadata, data | {"state": "rolled_back"})
