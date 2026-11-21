from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .platform import filesystem
from .platform.filesystem import case_sensitive_paths
from .platform.filesystem import path_in as scope_matches


atomic_bytes = filesystem.atomic_bytes
data_directory = filesystem.data_directory


class Invalid(ValueError):
    pass


class Temporary(RuntimeError):
    pass


class Stopped(RuntimeError):
    pass


ROLES = ("planner", "developer", "explorer", "reviewer", "qa", "diagnostic")
IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\Z")
WINDOWS_DEVICE = re.compile(r"(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\..*)?", re.IGNORECASE)
SECRET_FILE = re.compile(
    r'(^|/)(\.env(?:\.[^/]+)?|\.netrc|\.npmrc|credentials(?:\.[^/]+)?|id_(?:rsa|ed25519)|[^/]+\.(?:pem|pfx|key))$',
    re.IGNORECASE,
)


def opencode_model_provider(value):
    if isinstance(value, str) and len(value) <= 200:
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)/[A-Za-z0-9][A-Za-z0-9_.:/-]*", value)
        if match:
            return match[1]
    return None


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, sort_keys=False, indent=2) + "\n").encode("utf-8"))


def defaults() -> dict:
    return {
        "schema_version": 1,
        "settings": {
            "background": False, "parallel_jobs": 2, "parallel_tasks": 3,
            "heartbeat_sec": 15, "lease_sec": 90, "job_timeout_sec": 14400,
            "attempts": 2, "allow_background_write": False, "notifications": False,
            "gpu_budget_mb": 0, "ram_budget_mb": 0, "gateway_port": 8767,
        },
        "providers": {"local": {"kind": "local"}, "subscription": {"kind": "attached"}},
        "models": {},
        "runtimes": {},
        "harnesses": {"managed": {"kind": "managed", "max_rounds": 30}},
        "mcp": {},
    }


def require(condition: Any, message: str) -> None:
    if not condition:
        raise Invalid(message)


def number(value: Any, minimum: int, maximum: int, name: str) -> int:
    require(type(value) is int and minimum <= value <= maximum,
            f"{name}: {minimum}~{maximum} 사이 정수가 필요합니다.")
    return value


def flag(value: Any, name: str) -> None:
    require(type(value) is bool, f"{name}: true 또는 false가 필요합니다.")


def ident(value: Any) -> str:
    require(isinstance(value, str) and IDENTIFIER.fullmatch(value), "잘못된 등록 ID입니다.")
    return value


def string_list(value: Any, label: str) -> list[str]:
    require(isinstance(value, list) and all(isinstance(item, str) and item for item in value),
            f"{label}: 비어 있지 않은 문자열의 배열이 필요합니다.")
    return value


def commands(value: Any) -> list[list[str]]:
    require(isinstance(value, list), "QA 명령은 argv 배열의 목록이어야 합니다.")
    for row in value:
        require(string_list(row, "QA 명령"), "빈 QA 명령입니다.")
    return value


def settings(config: dict) -> dict:
    return defaults()["settings"] | config.get("settings", {})


def config_check(config: Any) -> dict:
    require(isinstance(config, dict), "설정은 JSON 객체여야 합니다.")
    require(set(config) <= set(defaults()), "알 수 없는 최상위 설정이 있습니다.")
    version = config.get("schema_version", 0)
    require(type(version) is int and version in (0, 1), "지원하지 않는 레지스트리 설정 버전입니다.")
    result = defaults() | config | {"schema_version": 1}
    require(isinstance(result["settings"], dict), "settings는 객체여야 합니다.")
    cfg = settings(result)
    require(set(cfg) <= set(defaults()["settings"]), "알 수 없는 실행 설정이 있습니다.")
    for key in ("background", "allow_background_write", "notifications"):
        flag(cfg[key], key)
    for key, lo, hi in (
        ("parallel_jobs", 1, 16), ("parallel_tasks", 1, 16), ("heartbeat_sec", 1, 120),
        ("lease_sec", 4, 3600), ("job_timeout_sec", 1, 86400), ("attempts", 1, 5),
        ("gpu_budget_mb", 0, 2097152), ("ram_budget_mb", 0, 2097152),
        ("gateway_port", 1024, 65535),
    ):
        number(cfg[key], lo, hi, key)
    require(cfg["lease_sec"] >= cfg["heartbeat_sec"] * 3, "리스는 하트비트 간격의 3배 이상이어야 합니다.")
    for section in ("providers", "models", "runtimes", "harnesses", "mcp"):
        require(isinstance(result[section], dict), f"{section}: JSON 객체가 필요합니다.")
        for key, item in result[section].items():
            ident(key)
            require(isinstance(item, dict), f"{section}/{key}: JSON 객체가 필요합니다.")
    for provider in result["providers"].values():
        require(provider.get("kind") in ("local", "attached"), "Provider kind는 local 또는 attached입니다.")
    for value in result["runtimes"].values():
        require(value.get("kind") in ("llama.cpp", "ollama", "openai-compatible"), "지원하지 않는 Runtime입니다.")
        require(value.get("ownership", "attached") in ("attached", "managed"), "Runtime ownership이 잘못되었습니다.")
        number(value.get("context", 32768), 1024, 2097152, "context")
        number(value.get("max_output", 2048), 32, 131072, "max_output")
        number(value.get("slots", 1), 1, 32, "slots")
        number(value.get("gpu_mb", 0), 0, 2097152, "gpu_mb")
        number(value.get("ram_mb", 0), 0, 2097152, "ram_mb")
        layers = number(value.get("gpu_layers", 0), 0, 999, "gpu_layers")
        require(not layers or value.get("gpu_mb", 0), "GPU 레이어에는 GPU 메모리 예약값이 필요합니다.")
        if value.get("ownership") == "managed":
            require(value["kind"] == "llama.cpp" and value.get("executable") and value.get("model_path"),
                    "Managed Runtime에는 llama.cpp 실행 파일과 모델 파일이 필요합니다.")
    for value in result["harnesses"].values():
        require(value.get("kind") in ("managed", "opencode", "codex"), "지원하지 않는 Harness입니다.")
        if value["kind"] == "managed":
            number(value.get("max_rounds", 30), 1, 100, "max_rounds")
        else:
            require(isinstance(value.get("executable"), str) and value["executable"], "CLI 실행 파일을 설정하세요.")
            for key in ("trusted", "allow_write", "allow_unverified", "inherit_environment"):
                flag(value.get(key, False), key)
    for tag, value in result["models"].items():
        require(ident(value.get("provider")) in result["providers"], f"{tag}: Provider를 찾을 수 없습니다.")
        require(isinstance(value.get("model"), str) and value["model"], f"{tag}: 실제 모델 ID가 필요합니다.")
        if "runtime" in value:
            require(ident(value["runtime"]) in result["runtimes"], f"{tag}: Runtime을 찾을 수 없습니다.")
        h = string_list(value.get("harnesses", ["managed"]), "harnesses")
        require(h and set(h) <= set(result["harnesses"]), f"{tag}: Harness를 찾을 수 없습니다.")
        if "runtime" not in value:
            require(all(result["harnesses"][name]["kind"] != "managed" for name in h),
                    f"{tag}: Managed Harness에는 Runtime이 필요합니다.")
        require(not (result["providers"][value["provider"]]["kind"] == "local" and "runtime" not in value),
                f"{tag}: 로컬 Provider에는 Runtime이 필요합니다.")
        require(set(string_list(value.get("roles", list(ROLES)), "roles")) <= set(ROLES), "잘못된 모델 역할입니다.")
        for key in ("quality", "tool_score", "reliability", "cost"):
            number(value.get(key, 0), 0, 100, key)
        number(value.get("token_budget", 0), 0, 1000000000, "token_budget")
    for value in result["mcp"].values():
        transport = value.get("transport")
        require(transport in ("http", "stdio"), "MCP Transport는 http 또는 stdio입니다.")
        if transport == "http":
            require(isinstance(value.get("url"), str) and value["url"], "MCP URL이 필요합니다.")
        else:
            require(string_list(value.get("command"), "MCP command"), "MCP 실행 명령이 필요합니다.")
            string_list(value.get("env", []), "MCP env")
        headers = value.get("header_env", {})
        require(isinstance(headers, dict), "MCP header_env는 객체여야 합니다.")
        for key, ref in headers.items():
            require(isinstance(key, str) and re.fullmatch(r"[\w-]+", key, re.ASCII), "잘못된 HTTP 헤더입니다.")
            require(isinstance(ref, str) and re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", ref), "환경 변수 참조가 필요합니다.")
        require(not (set(value) & {"headers", "token", "api_key", "secret"}), "MCP 비밀값에는 환경 변수 참조를 사용하세요.")
        tool_rules = value.get("tools", {})
        require(isinstance(tool_rules, dict), "MCP tools는 객체여야 합니다.")
        if "gateway_token_env" in value:
            ref = value["gateway_token_env"]
            require(isinstance(ref, str) and re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", ref), "Gateway 환경 변수 참조가 필요합니다.")
        for rule in tool_rules.values():
            require(isinstance(rule, dict) and rule.get("access") in ("read", "write"), "MCP 도구 접근 유형이 필요합니다.")
            require(set(string_list(rule.get("roles", []), "MCP roles")) <= set(ROLES), "잘못된 MCP 역할입니다.")
            for agent in string_list(rule.get("agents", []), "MCP agents"):
                role, separator, task_id = agent.partition("/")
                require(separator and role in ROLES and IDENTIFIER.fullmatch(task_id), "MCP Agent ID는 역할/노드ID 형식입니다.")
            flag(rule.get("native", False), "MCP native")
    return result


def scope_path(value: Any) -> str:
    require(isinstance(value, str) and value and "\\" not in value and "\x00" not in value,
            "파일 범위는 슬래시로 구분된 상대 경로여야 합니다.")
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value and value != "."
            and not ({".", "..", ".git"} & {p.casefold() for p in path.parts})
            and not any(re.search(r'[<>:"|?*\x00-\x1f]', p) or p.endswith((".", " "))
                        or WINDOWS_DEVICE.fullmatch(p) for p in path.parts),
            f"허용되지 않는 경로입니다. {value}")
    return value


def path_in(path: str, scopes: list[str]) -> bool:
    return scope_matches(path, scopes, case_sensitive=case_sensitive_paths())


def plan_check(plan: Any, cfg: dict) -> dict:
    require(isinstance(plan, dict), "작업 정의는 객체여야 합니다.")
    require(isinstance(plan.get("title"), str) and plan["title"].strip(), "작업 제목을 입력하세요.")
    repo = plan.get("repo")
    require(isinstance(repo, str) and Path(repo).is_absolute() and Path(repo).is_dir(), "Git 저장소의 절대 경로가 필요합니다.")
    require(isinstance(plan.get("target"), str) and plan["target"] and not plan["target"].startswith("-"), "대상 브랜치가 필요합니다.")
    flag(plan.get("background", False), "background")
    require(not plan.get("background") or settings(cfg)["background"], "레지스트리에서 백그라운드 모드를 먼저 활성화하세요.")
    tasks = plan.get("tasks")
    require(isinstance(tasks, list) and 0 < len(tasks) <= 100, "작업 노드를 1~100개 입력하세요.")
    known = {}
    for task in tasks:
        require(isinstance(task, dict), "모든 작업 노드는 객체여야 합니다.")
        key = ident(task.get("id"))
        require(not WINDOWS_DEVICE.fullmatch(key) and not key.endswith("."), "Windows에서 사용할 수 없는 작업 ID입니다.")
        require(key.casefold() not in {item.casefold() for item in known}, f"중복 작업 ID입니다. {key}")
        require(task.get("role") in ROLES, f"{key}: 작업 역할을 확인하세요.")
        for k in ("prompt", "acceptance"):
            require(isinstance(task.get(k), str) and task[k].strip(), f"{key}: {k}가 필요합니다.")
        paths = string_list(task.get("paths", []), "paths")
        for path in paths:
            scope_path(path)
        require(not paths or task["role"] == "developer", f"{key}: 쓰기는 Developer에만 부여할 수 있습니다.")
        require(not paths or not plan.get("background") or settings(cfg)["allow_background_write"],
                "백그라운드 쓰기가 비활성화되어 있습니다.")
        if "model" in task:
            require(ident(task["model"]) in cfg["models"], f"{key}: 모델을 찾을 수 없습니다.")
        if "harness" in task:
            require(ident(task["harness"]) in cfg["harnesses"], f"{key}: Harness를 찾을 수 없습니다.")
        for tool in string_list(task.get("tools", []), "tools"):
            require(len(tool) <= 64 and re.fullmatch(r"[a-zA-Z0-9_-]+", tool), f"잘못된 도구 이름입니다. {tool}")
        if "read_paths" in task:
            for path in string_list(task["read_paths"], "read_paths"):
                scope_path(path)
        number(task.get("min_context", 1024), 1024, 2097152, "min_context")
        commands(task.get("qa", []))
        known[key] = task
    parents = {key: set(string_list(task.get("depends", []), "depends")) for key, task in known.items()}
    require(all(all(dep in known for dep in deps) for deps in parents.values()), "존재하지 않는 선행 작업입니다.")
    remaining = dict(parents)
    ancestors: dict[str, set[str]] = {}
    while remaining:
        ready = [key for key, deps in remaining.items() if deps <= ancestors.keys()]
        require(ready, "DAG에서 순환 의존성을 발견했습니다.")
        for key in ready:
            direct = remaining.pop(key)
            ancestors[key] = direct.union(*(ancestors[dep] for dep in direct))
    for key, task in known.items():
        for other in known.keys() - {key} - ancestors[key]:
            if key in ancestors[other]:
                continue
            left, right = task.get("paths", []), known[other].get("paths", [])
            require(not any(path_in(path, right) for path in left) and not any(path_in(path, left) for path in right),
                    f"병렬 작업의 변경 범위가 겹칩니다. {key} / {other}")
    merge = commands(plan.get("qa", []))
    require(not any(task.get("paths") for task in tasks) or merge, "코드 변경 작업에는 통합 QA 명령이 필요합니다.")
    return plan
