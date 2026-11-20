"""Project, setup and plan services shared by desktop screens."""
from __future__ import annotations

import json
import re
import shutil
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .core import atomic_bytes, atomic_json, config_check, digest, ident, opencode_model_provider, plan_check, require
from .platform import command_line
from .platform.process_control import WINDOWS_EXECUTABLE_SUFFIXES, process_lock
from .processes import env_for_process, run
from .runtime import RuntimeClient, routes
from .ssh import validate_profile

format_commands = command_line.format_commands
parse_commands = command_line.parse_commands

STRATEGIES = ("읽기 전용 분석", "변경 · 검토 · QA", "검증 명령만")
CLI_NAMES = {
    "OpenCode": ("opencode",), "Codex": ("codex",), "Antigravity": ("antigravity", "agy"),
    "Claude Code": ("claude",), "Gemini CLI": ("gemini",),
    "Ollama": ("ollama",), "llama.cpp": ("llama-server",),
}
RUNTIME_KINDS = {"Ollama": "ollama", "llama.cpp": "llama.cpp", "OpenAI 호환": "openai-compatible"}


def read_workspace(root):
    path = root / "workspace.json"
    value = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    require(isinstance(value, dict) and type(value.get("schema_version", 1)) is int
            and value.get("schema_version", 1) == 1, "지원하지 않는 Workspace 설정 버전입니다.")
    value = {"schema_version": 1, "projects": {}, "hosts": {}, "default_model": "", **value}
    require(isinstance(value["projects"], dict) and isinstance(value["hosts"], dict), "Workspace 프로젝트와 호스트 형식을 확인하세요.")
    return value


def protect_and_save(root, name, value, expected=None):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / name
    with process_lock(root / (name + ".lock")) as acquired:
        require(acquired, "다른 창이 설정을 저장하고 있습니다.")
        current = path.read_bytes() if path.is_file() else None
        if expected is not None:
            require(digest(current.hex() if current is not None else None) == expected,
                    "다른 창에서 설정을 변경했습니다. 다시 불러온 뒤 저장하세요.")
        try:
            old_value = json.loads(current) if current else None
        except (ValueError, UnicodeError):
            old_value = None
        if value == old_value:
            return
        if current is not None:
            backup = root / "backups" / name / (digest(current.hex())[:20] + ".json")
            if not backup.exists():
                atomic_bytes(backup, current)
        atomic_json(path, value)


def registry_revision(root, name="registry.json"):
    path = root / name
    return digest(path.read_bytes().hex() if path.is_file() else None)


def save_registry(root, config, expected=None):
    config = config_check(config)
    protect_and_save(root, "registry.json", config, expected)
    return config


def _git(repo, *args):
    code, out = run(["git", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
                    env=env_for_process(), timeout=8, limit=300000)
    return out.decode("utf-8", errors="replace").strip() if code == 0 else ""


def scrub_origin(value):
    if "://" not in value:
        return value.split("?", 1)[0]
    try:
        parsed = urlsplit(value)
        host = parsed.netloc.rsplit("@", 1)[-1]
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except ValueError:
        return ""


def inspect_project(folder):
    path = Path(folder).expanduser().resolve()
    require(path.is_dir(), "프로젝트 폴더를 찾을 수 없습니다.")
    top = _git(path, "rev-parse", "--show-toplevel")
    require(top, "Git 저장소 안의 폴더를 선택하세요.")
    path = Path(top).resolve()
    markers = {
        "Python": ("pyproject.toml", "requirements.txt", "setup.py"),
        "JavaScript / TypeScript": ("package.json", "tsconfig.json"),
        "Rust": ("Cargo.toml",), "Go": ("go.mod",), ".NET": ("global.json",),
    }
    stack = [name for name, files in markers.items() if any((path / item).is_file() for item in files)]
    files = [item for item in ("AGENTS.md", ".mcp.json", "opencode.json", "opencode.jsonc", ".codex/config.toml")
             if (path / item).is_file()]
    package = path / "package.json"
    scripts, frameworks = {}, []
    if package.is_file() and package.stat().st_size <= 256000:
        try:
            data = json.loads(package.read_text(encoding="utf-8-sig"))
            scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
            libraries = set((data.get("dependencies") or {})) | set((data.get("devDependencies") or {}))
            frameworks = sorted(libraries & {"react", "vite", "next", "vue", "electron", "svelte", "@angular/core"})
        except (ValueError, OSError, TypeError, AttributeError):
            pass
    hints = []
    if (path / "tests").is_dir() and "Python" in stack:
        hints.append(["python", "-m", "unittest", "discover", "-s", "tests", "-v"])
    if isinstance(scripts, dict) and "test" in scripts:
        hints.append(["npm", "test"])
    branches = _git(path, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()
    return {"path": str(path), "branch": _git(path, "symbolic-ref", "--quiet", "--short", "HEAD"),
            "branches": branches, "origin": scrub_origin(_git(path, "config", "--get", "remote.origin.url")),
            "stack": stack, "frameworks": frameworks, "config_files": files, "qa_hints": hints,
            "build_hints": [["npm", "run", "build"]] if isinstance(scripts, dict) and "build" in scripts else []}


def put_project(root, profile, key=None):
    revision = registry_revision(root, "workspace.json")
    data = read_workspace(root)
    key = key or uuid.uuid4().hex
    require(isinstance(profile.get("name"), str) and profile["name"].strip(), "프로젝트 이름을 입력하세요.")
    require(profile.get("host", "") == "" or profile["host"] in data["hosts"], "실행 호스트를 선택하세요.")
    require(profile.get("path") and profile.get("branch"), "저장소와 대상 브랜치를 선택하세요.")
    for existing, other in data["projects"].items():
        require(existing == key or (other["path"], other.get("host", "")) != (profile["path"], profile.get("host", "")),
                "이미 추가한 저장소입니다.")
    data["projects"][key] = data["projects"].get(key, {}) | profile
    protect_and_save(root, "workspace.json", data, revision)
    return key


def put_host(root, profile, key=None, *, referenced=False):
    revision = registry_revision(root, "workspace.json")
    data = read_workspace(root)
    key = key or uuid.uuid4().hex
    value = validate_profile(data["hosts"].get(key, {}) | profile)
    if key in data["hosts"] and (referenced or any(project.get("host") == key for project in data["projects"].values())):
        old = data["hosts"][key]
        identity = ("host", "port", "user", "worker_dir")
        require(not any(old.get(k) != value.get(k) for k in identity),
                "기존 원격 실행과의 연결을 유지하려면 호스트 주소·계정·Worker 경로 변경을 새 프로필로 등록하세요.")
    data["hosts"][key] = value
    protect_and_save(root, "workspace.json", data, revision)
    return key


def remove_profile(root, section, key):
    require(section in ("projects", "hosts"), "지원하지 않는 프로필입니다.")
    revision = registry_revision(root, "workspace.json")
    data = read_workspace(root)
    require(key in data[section], "프로필을 찾을 수 없습니다.")
    if section == "hosts":
        require(not any(profile.get("host") == key for profile in data["projects"].values()), "이 호스트를 쓰는 프로젝트를 먼저 해제하세요.")
    del data[section][key]
    protect_and_save(root, "workspace.json", data, revision)


def draft_plan(project, description, strategy, *, model="", harness="", paths=(), qa=None, tools=(), background=False):
    description = description.strip()
    require(description and len(description) <= 24000, "작업 설명을 1~24,000자로 입력하세요.")
    require(strategy in STRATEGIES, "실행 전략을 선택하세요.")
    qa = qa if qa is not None else project.get("qa", [])
    plan = {"title": description.splitlines()[0][:96], "repo": project["path"], "target": project["branch"],
            "background": bool(background or project.get("host")), "qa": [], "tasks": []}
    overrides = {key: value for key, value in (("model", model), ("harness", harness)) if value}
    if strategy == STRATEGIES[0]:
        plan["tasks"] = [{"id": "explore", "role": "explorer", "prompt": description,
                          "acceptance": "요청한 분석 결과와 근거를 정리합니다.", "tools": list(tools), **overrides}]
    elif strategy == STRATEGIES[1]:
        require(paths and qa, "변경 범위와 통합 QA 명령을 입력하세요.")
        plan["tasks"] = [
            {"id": "develop", "role": "developer", "prompt": description, "paths": list(paths),
             "acceptance": "설명에 맞춰 허용 경로 안에서만 변경합니다.", "tools": list(tools), **overrides},
            {"id": "review", "role": "reviewer", "prompt": description,
             "acceptance": "요구사항과 선행 변경을 독립적으로 확인합니다.", "depends": ["develop"]},
        ]
        plan["qa"] = qa
    else:
        require(qa, "실행할 검증 명령을 입력하세요.")
        plan["tasks"] = [{"id": "qa", "role": "qa", "prompt": description,
                          "acceptance": "모든 검증 명령이 정상 종료합니다.", "qa": qa}]
    if project.get("read_paths"):
        for task in plan["tasks"]:
            if task["role"] != "qa":
                task["read_paths"] = list(project["read_paths"])
    return plan


def plan_routes(plan, config):
    plan_check(plan, config)
    result = {}
    for task in plan["tasks"]:
        if task["role"] == "qa" and task.get("qa") and not ({"model", "harness"} & task.keys()):
            result[task["id"]] = []
        else:
            rejected = []
            candidates = routes(config, task, rejected=rejected)
            reason = rejected[0] if rejected else "가능한 모델·Harness 실행 경로를 찾을 수 없습니다."
            require(candidates, f'{task["id"]}: {reason}')
            result[task["id"]] = [f"{route.model_id} / {route.harness_id}" for route in candidates]
    return result


def scan_clis():
    windows = sys.platform == "win32"
    extensions = WINDOWS_EXECUTABLE_SUFFIXES if windows else ("",)
    result = {}
    for name, candidates in CLI_NAMES.items():
        paths = (shutil.which(candidate + extension) for candidate in candidates for extension in extensions)
        result[name] = next((path for path in paths if path and
                             (not windows or Path(path).suffix.lower() in extensions)), None)
    return result


def discover_models(kind, endpoint, auth_ref=""):
    import time
    require(kind in RUNTIME_KINDS, "모델 목록을 조회할 Runtime을 선택하세요.")
    if auth_ref:
        require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", auth_ref), "자격 증명 환경 변수 이름을 입력하세요.")
    setting = {"kind": RUNTIME_KINDS[kind], "url": endpoint}
    if auth_ref:
        setting["auth_env"] = auth_ref
    before = time.monotonic()
    client = RuntimeClient(setting)
    result = client.request("/v1/models", timeout=8)
    models = result.get("data") if isinstance(result, dict) else None
    require(isinstance(models, list), "Runtime에서 모델 목록을 확인할 수 없습니다.")
    rows = []
    for model in models[:200]:
        if not isinstance(model, dict) or not isinstance(model.get("id"), str):
            continue
        context = model.get("context_length") or model.get("max_model_len")
        rows.append({"id": model["id"], "context": context if type(context) is int and context > 0 else None})
    return {"ms": round((time.monotonic() - before) * 1000), "models": rows}


def add_setup_profile(config, form, model=None):
    key = ident(form["id"])
    config = json.loads(json.dumps(config))
    require(key not in config["models"], "이미 사용 중인 모델 프로필 ID입니다.")
    kind = form["kind"]
    selected = model if model is not None else form["model"]
    if kind == "OpenCode":
        require(opencode_model_provider(selected), "OpenCode의 모델 ID를 provider/model 형식으로 입력하세요.")
    provider_key = "local" if kind in RUNTIME_KINDS else "subscription"
    config["providers"].setdefault(provider_key, {"kind": "local" if provider_key == "local" else "attached"})
    if kind in RUNTIME_KINDS:
        require(key not in config["runtimes"], "동일 ID의 Runtime이 있습니다.")
        require(form["endpoint"], "Runtime 주소를 입력하세요.")
        from .runtime import checked_url
        checked_url(form["endpoint"], local_only=True)
        runtime = {"kind": RUNTIME_KINDS[kind], "ownership": "attached", "url": form["endpoint"],
                   "context": int(form.get("context") or 32768)}
        if form.get("auth_env"):
            require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", form["auth_env"]), "자격 증명 환경 변수 이름을 입력하세요.")
            runtime["auth_env"] = form["auth_env"]
        require("managed" not in config["harnesses"] or config["harnesses"]["managed"]["kind"] == "managed",
                "managed ID가 다른 Harness에 할당되어 있습니다.")
        config["harnesses"].setdefault("managed", {"kind": "managed"})
        config["runtimes"][key] = runtime
        route = {"runtime": key, "harnesses": ["managed"]}
    else:
        require(kind in ("OpenCode", "Codex") and form.get("trusted"), "사용할 CLI 및 승인된 실행 파일을 선택하세요.")
        require(key not in config["harnesses"], "동일 ID의 Harness가 있습니다.")
        from .processes import executable
        path = executable(form["executable"])
        config["harnesses"][key] = {"kind": kind.lower(), "executable": path,
                                     "trusted": True, "allow_unverified": True}
        route = {"harnesses": [key], "roles": ["explorer", "reviewer", "planner", "diagnostic"]}
    config["models"][key] = {"provider": provider_key, "model": selected, **route}
    return config_check(config)
