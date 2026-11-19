"""SSH-invoked Worker API. The detached Supervisor owns jobs independently of SSH."""
from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

from .core import Invalid, SECRET_FILE, atomic_json, data_directory, encode, require
from .execution_state import MERGE_EVIDENCE, TERMINAL, task_stage
from .harness import workspace_path
from .platform.process_control import process_lock
from .processes import env_for_process, run
from .ssh import MAX_REQUEST, PROTOCOL, remote_path
from .store import Store
from .supervisor import read_config, start_supervisor
from .workspace import inspect_project, plan_routes, protect_and_save, save_registry, scan_clis

ALLOWED_METHODS = {"info", "project", "validate", "submit", "status", "action", "approvals", "decide", "browse", "download", "upload"}
TERMINAL_STATES = {"FAILED", "CANCELLED", "SUCCEEDED", "MERGED"}
MAX_FILE = 200_000


def metrics(*, gpu=False):
    result = {"os": platform.system(), "release": platform.release(), "cpu_cores": os.cpu_count(), "cpu_percent": None,
              "ram_total": None, "ram_used": None, "gpu": None}
    try:
        import psutil
        ram = psutil.virtual_memory()
        result.update(cpu_percent=psutil.cpu_percent(interval=.12), ram_total=ram.total, ram_used=ram.used)
    except (ImportError, OSError, RuntimeError):
        pass
    if gpu and shutil.which("nvidia-smi"):
        code, raw = run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                         "--format=csv,noheader,nounits"], env=env_for_process(), timeout=6, limit=12000)
        if code == 0:
            rows = []
            for row in raw.decode("utf-8", "replace").splitlines():
                parts = [part.strip() for part in row.split(",")]
                if len(parts) == 5 and all(value.isdecimal() for value in parts[1:]):
                    rows.append({"name": parts[0], **dict(zip(("utilization", "used_mib", "total_mib", "temp_c"),
                                                              map(int, parts[1:])))})
            result["gpu"] = rows or None
    return result


def worker_root():
    override = os.environ.get("ORCHESTRA_REMOTE_DATA")
    return Path(override).expanduser().resolve() if override else data_directory() / "remote-worker"


def worker_settings(root):
    path = root / "worker.json"
    require(path.is_file(), "서버에서 Worker의 허용 저장소를 먼저 등록하세요.")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict) and value.get("schema_version") == 1 and isinstance(value.get("repos"), list),
            "Worker 설정 형식이 올바르지 않습니다.")
    return value


def register_project(root, repo, allow_write=False):
    project = inspect_project(repo)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    value = worker_settings(root) if (root / "worker.json").exists() else {"schema_version": 1, "repos": []}
    value["repos"] = sorted({*value["repos"], project["path"]})
    protect_and_save(root, "worker.json", value)
    config = read_config(root)
    config["settings"]["background"] = True
    if allow_write:
        config["settings"]["allow_background_write"] = True
    save_registry(root, config)
    return project


def job_id(value):
    require(isinstance(value, str) and re.fullmatch("[a-f0-9]{32}", value), "원격 실행 ID를 확인하세요.")
    return value


def _approved(root, repo):
    path = Path(remote_path(repo)).resolve()
    policy = worker_settings(root)
    require(str(path) in policy["repos"], "서버 Worker에 등록된 저장소를 선택하세요.")
    return path


def _status(root):
    path = root / "supervisor.json"
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
        if not 0 <= time.time() - status["at"] < 8:
            return None
        with process_lock(root / "supervisor.lock") as available:
            return None if available else status
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _ensure_running(root, job=None):
    if not _status(root) and (job is None or job["state"] in
                              ("QUEUED", "PREPARING", "RUNNING", "VERIFYING", "RETRY_WAIT", "MERGE_QUEUED", "MERGING")):
        start_supervisor(root)


def _validate(root, plan, config):
    require(isinstance(plan, dict) and plan.get("background") is True, "원격 Worker는 백그라운드 계획을 실행합니다.")
    path = _approved(root, plan.get("repo"))
    require(str(path) == plan["repo"], "계획에 정규화된 원격 저장소 경로를 사용하세요.")
    branch = plan.get("target")
    require(isinstance(branch, str) and branch in inspect_project(path)["branches"], "원격 대상 브랜치를 찾을 수 없습니다.")
    return plan_routes(plan, config)


def _files(root, method, args):
    repo = _approved(root, args["repo"])
    relative = args.get("path", ".")
    path = repo if relative == "." else workspace_path(repo, relative)
    if method == "browse":
        require(path.is_dir(), "원격 디렉터리를 찾을 수 없습니다.")
        entries = []
        for child in path.iterdir():
            if child.name == ".git" or child.is_symlink() or SECRET_FILE.search(child.relative_to(repo).as_posix()):
                continue
            entries.append({"name": child.name, "directory": child.is_dir()})
            if len(entries) == 300:
                break
        return sorted(entries, key=lambda item: (not item["directory"], item["name"].casefold()))
    if method == "download":
        require(path.is_file() and path.stat().st_size <= MAX_FILE, "일반 파일을 선택하세요 (최대 200 KB).")
        with path.open("rb") as source:
            raw = source.read(MAX_FILE + 1)
        require(len(raw) <= MAX_FILE, "파일이 다운로드 한도를 초과합니다.")
        return {"name": path.name, "content": base64.b64encode(raw).decode()}
    require(worker_settings(root).get("allow_upload", False), "Worker 관리자가 업로드를 활성화하지 않았습니다.")
    name = args["name"]
    require(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,121}", name)
            and not SECRET_FILE.search(name), "업로드 파일 이름을 확인하세요.")
    raw = base64.b64decode(args["content"], validate=True)
    require(len(raw) <= MAX_FILE, "파일이 업로드 한도를 초과합니다.")
    target = root / "uploads" / job_id(args["upload_id"]) / name
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(dir=target.parent) as staged:
        staged.write(raw)
        staged.flush()
        os.fsync(staged.fileno())
        try:
            os.link(staged.name, target)
        except FileExistsError:
            require(target.is_file() and not target.is_symlink() and target.read_bytes() == raw,
                    "같은 업로드 ID가 다른 파일로 이미 사용됐습니다.")
    return {"name": name, "path": str(target)}


def dispatch(root, message, *, restart=True):
    require(isinstance(message, dict) and message.get("version") == PROTOCOL, "지원하는 Worker 프로토콜 버전이 아닙니다.")
    method, args = message.get("method"), message.get("params", {})
    require(isinstance(method, str) and method in ALLOWED_METHODS and isinstance(args, dict), "지원하지 않는 Worker 요청입니다.")
    policy = worker_settings(root)
    config = read_config(root)
    if method == "info":
        info = metrics(gpu=args.get("gpu") is True)
        store = Store(root) if (root / "state.db").is_file() else None
        history = store.list_jobs() if store else []
        active_jobs = [job for job in history if job["state"] not in TERMINAL_STATES]
        active_agents = sum(task["state"] in ("PREPARING", "RUNNING", "VERIFYING", "AWAITING_TOOL")
                            for job in active_jobs for task in store.tasks(job["id"]).values())
        worker = _status(root) or {}
        info.update(repos=policy["repos"], heartbeat=worker.get("at"), git=bool(shutil.which("git")),
                    active_jobs=len(active_jobs), active_agents=active_agents,
                    recent_failed_jobs=[job["id"] for job in history if job["state"] == "FAILED"][:10],
                    python=platform.python_version(), clis={name: bool(path) for name, path in scan_clis().items()},
                    models={name: {"provider": value["provider"], "model": value["model"]}
                            for name, value in config["models"].items()},
                    harnesses={name: value["kind"] for name, value in config["harnesses"].items()},
                    allow_upload=bool(policy.get("allow_upload")))
        return info
    if method == "project":
        return inspect_project(_approved(root, args["repo"]))
    if method in ("browse", "download", "upload"):
        return _files(root, method, args)
    if method == "validate":
        return _validate(root, args["plan"], config)
    store = Store(root)
    if method == "submit":
        request_id = job_id(args["request_id"])
        plan = args["plan"]
        # An existing receipt is authoritative even if the operator has since changed
        # runtime configuration or branches. Store compares the immutable plan hash.
        if not store.remote_receipt(request_id):
            _validate(root, plan, config)
        job = store.submit(plan, config, None, request_id=request_id)
        if restart:
            _ensure_running(root, store.job(job))
        return {"id": job}
    key = job_id(args["job"])
    if method == "status":
        job, tasks, events = store.status_snapshot(key, max(0, int(args.get("after", 0))), 150)
        worker = _status(root) or {}
        if restart:
            _ensure_running(root, job)
        for event in events:
            payload = event["payload"]
            event["payload"] = {name: payload[name] for name in (
                "state", "attempt", "reason", "index", "exit_code", "phase", "prompt_tokens",
                "completion_tokens", "total_tokens", "name", "status", "changed", "elapsed_sec", "step",
                "validated", "file", "commit", "provider", "manual_model", "manual_harness",
            ) if name in payload}
        evidence = (job["result"] or {}) if job["state"] in MERGE_EVIDENCE else {}
        heartbeat = job["heartbeat"] if job["owner"] and job["owner"] == worker.get("owner") and job["state"] not in TERMINAL else None
        return {"id": key, "state": job["state"], "heartbeat": heartbeat, "worker_heartbeat": worker.get("at"),
                "candidate": evidence.get("candidate"), "approval_revision": evidence.get("approval_revision"),
                "tasks": [{"id": task_id, "state": task_stage(job["state"], row["state"]), "attempt": row["attempt"],
                           "changed": (row["result"] or {}).get("changed", [])}
                          for task_id, row in tasks.items()],
                "events": events}
    require(store.job(key), "원격 실행을 찾을 수 없습니다.")
    if method == "approvals":
        return store.approvals(key)
    if method == "decide":
        require(type(args.get("accept")) is bool, "도구 승인 여부를 지정하세요.")
        store.decide(key, args["task"], args["key"], args["accept"])
        if restart:
            _ensure_running(root, store.job(key))
        return {"state": store.job(key)["state"]}
    action = args.get("action")
    require(action in ("cancel", "retry", "merge"), "지원하지 않는 작업 제어입니다.")
    store.request(key, action, args.get("candidate"), approval_revision=args.get("approval_revision"))
    if restart:
        _ensure_running(root, store.job(key))
    return {"state": store.job(key)["state"]}


def main():
    parser = argparse.ArgumentParser(description="Model Orchestration Linux Worker")
    parser.add_argument("--register", metavar="REPOSITORY", help="Allow a Git repository for SSH jobs")
    parser.add_argument("--allow-background-write", action="store_true")
    parser.add_argument("--allow-upload", action="store_true", help="Enable staging uploads outside Git worktrees")
    args = parser.parse_args()
    root = worker_root()
    if args.register:
        project = register_project(root, args.register, args.allow_background_write)
        if args.allow_upload:
            atomic_json(root / "worker.json", worker_settings(root) | {"allow_upload": True})
        print(project["path"])
        print(f"Worker data directory: {root}")
        return
    try:
        request = sys.stdin.buffer.read(MAX_REQUEST + 1)
        require(len(request) <= MAX_REQUEST, "원격 작업 요청이 허용 크기를 초과했습니다.")
        result = dispatch(root, json.loads(request))
        print(encode({"version": PROTOCOL, "ok": True, "result": result}))
    except (ValueError, KeyError, OSError, RuntimeError, TypeError) as exc:
        reason = str(exc) if isinstance(exc, Invalid) else "Worker가 요청을 처리하지 못했습니다."
        print(encode({"version": PROTOCOL, "ok": False, "error": reason}))


if __name__ == "__main__":
    main()
