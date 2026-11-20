from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from .core import (SECRET_FILE, Invalid, Stopped, Temporary, atomic_bytes, atomic_json, config_check,
                   defaults, digest, opencode_model_provider, path_in, plan_check, require, settings)
from .execution_state import BLOCKED, ready_tasks
from .gitgate import GitGate
from .platform.filesystem import repository_identity
from .platform.process_control import process_backend, process_lock as process_lock
from .harness import AwaitApproval, Managed, attached
from .mcp import Gateway
from .runtime import RuntimePool, routes
from .store import Store


def read_config(root):
    path = root / "registry.json"
    return config_check(json.loads(path.read_text(encoding="utf-8"))) if path.is_file() else defaults()


def ordered(tasks):
    remaining = {task["id"]: task for task in tasks}
    sequence = []
    ancestry = {}
    while remaining:
        pending = len(remaining)
        for key, task in list(remaining.items()):
            deps = set(task.get("depends", []))
            if deps <= ancestry.keys():
                sequence.append(key)
                ancestry[key] = deps.union(*(ancestry[dep] for dep in deps))
                del remaining[key]
        require(len(remaining) < pending, "작업 그래프에 잘못된 선행 노드 또는 순환 관계가 있습니다.")
    return sequence, ancestry


def dependency_context(spec, ancestors, specs, rows):
    if spec["role"] == "developer":
        notes = []
        for key in spec.get("depends", []):
            if specs[key]["role"] == "planner" and len(notes) < 6:
                answer = (rows[key]["checkpoint"] or {}).get("answer")
                if isinstance(answer, str) and answer.strip():
                    notes.append({"task": key, "notes": answer[:1000]})
        return {"planning_notes": notes} if notes else {}
    if spec["role"] == "reviewer" and ancestors:
        scopes = spec.get("read_paths")
        files = sorted({name for key in ancestors for name in rows[key]["result"].get("changed", [])
                        if not SECRET_FILE.search(name) and (scopes is None or path_in(name, scopes))})
        return {"changed_paths": files[:40], "more_changed_paths": len(files) > 40}
    return {}


def review_verdict(answer):
    lines = answer.strip().splitlines()
    markers = {line.strip() for line in lines} & {"REVIEW: PASS", "REVIEW: FAIL"}
    if lines and markers == {lines[-1].strip()}:
        return "passed" if "REVIEW: PASS" in markers else "failed"
    return "invalid"


class JobRunner:
    def __init__(self, store, pool, job, closed, client_alive, merge_lock):
        self.store, self.pool, self.job = store, pool, job
        self.closed, self.client_alive, self.merge_lock = closed, client_alive, merge_lock
        self.conf = settings(job["config"])
        self.id = job["id"]
        self.seen_action = threading.Event()
        self.deadline = time.monotonic() + self.conf["job_timeout_sec"]
        self.git = GitGate(store, job, self.stop)
        self.roles = {task["id"]: task for task in job["plan"]["tasks"]}

    def stop(self):
        return (self.seen_action.is_set() or self.closed.is_set()
                or time.monotonic() >= self.deadline
                or self.job["foreground"] and not self.client_alive(self.job["foreground"]))

    def event(self, kind, payload):
        self.store.event(self.id, None, kind, payload)

    def answer_artifact(self, task_id, answer):
        artifact = self.store.root / "artifacts" / self.id / (task_id + ".txt")
        atomic_bytes(artifact, answer.encode())
        return {"answer_hash": digest(answer), "artifact": str(artifact)}

    def task(self, spec, base, deps, row, context):
        task_id = spec["id"]
        attempt = row["attempt"] + 1
        checkpoint = row["checkpoint"]
        self.store.set_task(self.id, task_id, "PREPARING", attempt=attempt)
        if spec["role"] == "qa" and spec.get("qa") and not {"model", "harness"} & spec.keys():
            event_route = {"agent_id": "qa/" + task_id, "worktree_id": task_id}
            try:
                path = self.git.worktree(task_id, base, deps)
                self.store.set_task(self.id, task_id, "VERIFYING", route=event_route)
                qa = self.git.qa(path, spec["qa"], task_id, event_route)
                self.store.set_task(self.id, task_id, "SUCCEEDED", route=event_route,
                                    result={"commit": None, "changed": [], "qa": qa})
            except Stopped:
                self.store.set_task(self.id, task_id, "QUEUED", route=event_route)
            except (Invalid, OSError, TimeoutError) as exc:
                self.store.set_task(self.id, task_id, "FAILED", route=event_route,
                                    result={"reason": str(exc) if isinstance(exc, Invalid) else type(exc).__name__})
            return
        rejected = []
        candidates = routes(self.job["config"], spec, rejected=rejected)
        if checkpoint:
            candidates = [route for route in candidates if route.event(spec) == checkpoint.get("route")]
        last = Invalid(rejected[0] if rejected else "작업 조건과 일치하는 모델 실행 경로가 없습니다.")
        output = {}
        for route in candidates:
            event_route = route.event(spec)

            def emit(kind, payload):
                self.store.event(self.id, task_id, kind, payload, event_route)

            try:
                if self.stop():
                    raise Stopped("실행 준비 중 중지되었습니다.")
                with self.pool.reserve(route, self.job["config"], self.stop) as client:
                    validated = client.probe(route, spec, emit) if client else None
                    model_requested = route.requested_model()
                    provider_requested = opencode_model_provider(model_requested) if route.harness["kind"] == "opencode" else None
                    emit("route.selected", {"provider": route.model["provider"], "model_requested": model_requested,
                                            "provider_requested": provider_requested, "manual_model": bool(spec.get("model")),
                                            "manual_harness": bool(spec.get("harness")),
                                            "quality": route.model.get("quality", 0), "reliability": route.model.get("reliability", 0),
                                            "tool_score": route.model.get("tool_score", 0), "cost": route.model.get("cost", 0)})
                    if checkpoint:
                        path = self.git.root / task_id
                        require(path.is_dir(), "체크포인트 Worktree를 찾을 수 없습니다.")
                    else:
                        path = self.git.worktree(task_id, base, deps)
                    self.store.set_task(self.id, task_id, "RUNNING", route=event_route)
                    if route.harness["kind"] == "managed":
                        answer = Managed(self.store, self.job, spec, route, self.git, path, client,
                                         validated, emit, self.stop).execute_plan(checkpoint, context=context)
                    elif checkpoint:
                        require(checkpoint["step"] in ("agent_done", "commit_started", "committed"),
                                "중단된 Attached CLI는 외부 실행을 다시 호출하기 전에 확인이 필요합니다.")
                        answer = checkpoint["answer"]
                    else:
                        checkpoint = {"step": "attached_started", "route": event_route, "initial_head": self.git.head(path)}
                        answer = attached(route, spec, path, client, validated, emit, self.stop, context=context,
                                          on_start=lambda: self.store.checkpoint(self.id, task_id, checkpoint, event_route))
                        require(self.git.head(path) == checkpoint["initial_head"],
                                "Attached CLI가 Git HEAD를 변경했습니다.")
                        checkpoint.update(step="agent_done", answer=answer)
                        self.store.checkpoint(self.id, task_id, checkpoint, event_route)
                if spec["role"] == "reviewer":
                    verdict = review_verdict(answer)
                    output = self.answer_artifact(task_id, answer) | {"review": verdict}
                    emit("review.result", {"status": verdict})
                    require(verdict != "invalid", "Reviewer의 최종 REVIEW: PASS 또는 REVIEW: FAIL 판정이 필요합니다.")
                    require(verdict == "passed", "독립 Reviewer가 변경을 통과시키지 않았습니다.")
                checkpoint = self.store.tasks(self.id)[task_id]["checkpoint"]
                if checkpoint["step"] == "committed":
                    require(self.git.head(path) == (checkpoint["commit"] or checkpoint["initial_head"])
                            and not self.git.changed(path), "작업 체크포인트 이후 Worktree가 변경되었습니다.")
                    commit, changed = checkpoint["commit"], checkpoint["changed"]
                else:
                    head = self.git.head(path)
                    if head != checkpoint["initial_head"]:
                        require(checkpoint["step"] == "commit_started", "Agent가 Git HEAD를 변경했습니다.")
                        parent = self.git.git(path, "rev-parse", "HEAD^").decode().strip()
                        message = self.git.git(path, "log", "-1", "--format=%s").decode().strip()
                        require(parent == checkpoint["initial_head"] and message == f"Orchestration task {task_id}"
                                and not self.git.changed(path), "복구 중 예상하지 못한 Git 커밋이 발견되었습니다.")
                        changed = self.git.git(path, "diff", "--no-renames", "--name-only", "-z", parent, head).decode().strip("\0").split("\0")
                        require(all(path_in(name, spec.get("paths", [])) for name in changed), "복구된 커밋이 파일 범위를 벗어났습니다.")
                        commit = head
                    else:
                        checkpoint["step"] = "commit_started"
                        self.store.checkpoint(self.id, task_id, checkpoint, event_route)
                        commit, changed = self.git.commit(path, task_id, checkpoint["initial_head"], spec.get("paths", []))
                    checkpoint.update(step="committed", commit=commit, changed=changed)
                    self.store.checkpoint(self.id, task_id, checkpoint, event_route)
                if commit:
                    emit("git.commit", {"commit": commit, "changed": changed})
                self.store.set_task(self.id, task_id, "VERIFYING", route=event_route)
                qa = self.git.qa(path, spec.get("qa", []), task_id, event_route)
                output = output or self.answer_artifact(task_id, answer)
                self.store.set_task(self.id, task_id, "SUCCEEDED", result={
                    "commit": commit, "changed": changed, "qa": qa, **output,
                }, route=event_route)
                return
            except AwaitApproval:
                self.store.set_task(self.id, task_id, "AWAITING_TOOL", route=event_route)
                return
            except Stopped:
                self.store.set_task(self.id, task_id, "QUEUED")
                return
            except (Invalid, Temporary, OSError, TimeoutError, KeyError, TypeError) as exc:
                last = exc
                reason = str(exc) if isinstance(exc, (Invalid, Temporary)) else type(exc).__name__
                emit("route.failed", {"reason": reason})
                checkpoint = self.store.tasks(self.id)[task_id]["checkpoint"]
                if checkpoint:
                    break
        if isinstance(last, Temporary) and attempt < self.conf["attempts"] and not self.stop():
            self.store.set_task(self.id, task_id, "RETRY_WAIT", retry_after=2 ** attempt,
                                result={"reason": str(last)})
        else:
            reason = str(last) if isinstance(last, (Invalid, Temporary)) else type(last).__name__
            self.store.set_task(self.id, task_id, "FAILED", result={**output, "reason": reason})

    def execute(self):
        if self.job["state"] == "MERGING":
            with self.merge_lock:
                self.git.apply(self.job["result"])
            self.store.set_job(self.id, "MERGED")
            return
        plan_check(self.job["plan"], self.job["config"])
        sequence, ancestry = ordered(self.job["plan"]["tasks"])
        root = self.git.root
        base_file = root / "base.json"
        if base_file.exists():
            base = json.loads(base_file.read_text(encoding="utf-8"))["base"]
        else:
            base = self.git.base()
            atomic_json(base_file, {"base": base})
        if not self.store.set_job(self.id, "RUNNING", {"base": base}, release=False):
            raise Stopped("실행 전에 중지되었습니다.")
        active = {}
        with ThreadPoolExecutor(max_workers=self.conf["parallel_tasks"], thread_name_prefix="task") as workers:
            while not self.stop():
                job = self.store.job(self.id)
                if job["action"] == "cancel":
                    self.seen_action.set()
                    break
                rows = self.store.tasks(self.id)
                blocked = {key for key, row in rows.items() if row["state"] in BLOCKED}
                for key in ready_tasks(sequence, ancestry, rows, active, time.time(), self.conf["parallel_tasks"]):
                    deps = ancestry[key]
                    commits = [rows[dep]["result"]["commit"] for dep in sequence if dep in deps and rows[dep]["result"]["commit"]]
                    spec = self.roles[key]
                    context = dependency_context(spec, deps, self.roles, rows)
                    active[key] = workers.submit(self.task, spec, base, commits, rows[key], context)
                if active:
                    wait(active.values(), timeout=.2, return_when=FIRST_COMPLETED)
                    for key, future in list(active.items()):
                        if future.done():
                            del active[key]
                            future.result()
                    continue
                if blocked:
                    state = "FAILED" if any(rows[key]["state"] == "FAILED" for key in blocked) else "AWAITING_TOOL"
                    self.store.set_job(self.id, state)
                    return
                if all(row["state"] == "SUCCEEDED" for row in rows.values()):
                    break
                time.sleep(.15)
        current = self.store.job(self.id)
        if current["action"] == "cancel" or self.job["foreground"] and not self.client_alive(self.job["foreground"]):
            self.store.set_job(self.id, "CANCELLED")
            return
        if self.closed.is_set():
            self.store.set_job(self.id, "QUEUED" if not self.job["foreground"] else "CANCELLED", {"reason": "supervisor_stop"})
            return
        require(time.monotonic() < self.deadline, "작업 실행 시간이 초과되었습니다.")
        rows = self.store.tasks(self.id)
        if not self.store.set_job(self.id, "VERIFYING", release=False):
            raise Stopped("통합 QA 전에 중지되었습니다.")
        commits = [rows[key]["result"]["commit"] for key in sequence if rows[key]["result"]["commit"]]
        result = self.git.integrate(base, commits)
        if self.stop() or self.store.job(self.id)["action"] == "cancel":
            raise Stopped("통합 검증 후 중지되었습니다.")
        if commits:
            result["approval_revision"] = uuid.uuid4().hex
        self.store.set_job(self.id, "AWAITING_APPROVAL" if commits else "SUCCEEDED", result=result)

    def work(self):
        try:
            self.execute()
        except Stopped:
            current = self.store.job(self.id)
            resume = self.closed.is_set() and not self.job["foreground"] and current["action"] != "cancel"
            state = ("MERGE_QUEUED" if self.job["state"] == "MERGING" else "QUEUED") if resume else "CANCELLED"
            self.store.set_job(self.id, state)
        except Exception as err:
            reason = str(err) if isinstance(err, (Invalid, Temporary)) else type(err).__name__
            self.store.set_job(self.id, "FAILED", {"reason": reason})


class Supervisor:
    def __init__(self, root):
        self.root = root
        self.store = Store(root)
        self.pool = RuntimePool()
        self.owner = uuid.uuid4().hex
        self.closed = threading.Event()
        self.clients = set()
        self.merge_locks = {}
        self.gateway = None
        self.gateway_hash = None
        self.gateway_error = None

    def setup_gateway(self, cfg):
        port = settings(cfg)["gateway_port"]
        profiles = {name: item for name, item in cfg["mcp"].items() if item.get("gateway_token_env")}
        fingerprint = digest([port, profiles])
        if fingerprint == self.gateway_hash:
            return
        if self.gateway:
            self.gateway.close()
            self.gateway = None
        self.gateway_hash = fingerprint
        self.gateway_error = None
        if profiles:
            try:
                self.gateway = Gateway(port, profiles, lambda profile, kind, payload:
                                       self.store.event("gateway:" + profile, None, kind, payload))
                self.gateway.start()
            except OSError:
                self.gateway_error = "Gateway 포트를 열 수 없습니다."

    def serve(self):
        status = self.root / "supervisor.json"
        stop_file = self.root / "supervisor.stop"
        with process_lock(self.root / "supervisor.lock") as acquired:
            if not acquired:
                return
            status.unlink(missing_ok=True)
            stop_file.unlink(missing_ok=True)
            active = {}
            idle_since = time.monotonic()
            next_heartbeat = 0
            try:
                with ThreadPoolExecutor(max_workers=16, thread_name_prefix="job") as workers:
                    while not self.closed.is_set():
                        if stop_file.exists():
                            self.closed.set()
                            break
                        try:
                            cfg = read_config(self.root)
                        except (OSError, ValueError, TypeError):
                            cfg = defaults()
                        self.setup_gateway(cfg)
                        self.clients = self.store.live_clients()
                        now = time.monotonic()
                        if now >= next_heartbeat:
                            next_heartbeat = now + 1
                            for key, (_, row, previous) in list(active.items()):
                                if now - previous >= settings(row["config"])["heartbeat_sec"]:
                                    self.store.heartbeat(key, self.owner)
                                    active[key] = (active[key][0], row, now)
                            self.store.recover(True, self.owner)
                            self.store.recover(False, self.owner)
                            self.store.expire_foreground()
                            atomic_json(status, {"pid": os.getpid(), "at": time.time(), "owner": self.owner,
                                                 "gateway": bool(self.gateway), "gateway_error": self.gateway_error})
                        for key, (future, row, stamp) in list(active.items()):
                            if future.done():
                                future.result()
                                del active[key]
                        for pending in self.store.pending():
                            key = pending["id"]
                            if key in active or (pending["foreground"] and pending["foreground"] not in self.clients):
                                continue
                            if len(active) >= settings(cfg)["parallel_jobs"]:
                                break
                            if self.store.claim(key, self.owner):
                                row = self.store.job(key)
                                repo = repository_identity(row["plan"]["repo"])
                                lock = self.merge_locks.setdefault(repo, threading.Lock())
                                runner = JobRunner(self.store, self.pool, row, self.closed, lambda token: token in self.clients, lock)
                                active[key] = (workers.submit(runner.work), row, now)
                        if active or self.clients or self.gateway or settings(cfg)["background"]:
                            idle_since = now
                        elif now - idle_since > 12:
                            break
                        self.closed.wait(.25)
            finally:
                self.closed.set()
                if self.gateway:
                    self.gateway.close()
                status.unlink(missing_ok=True)
                stop_file.unlink(missing_ok=True)


def start_supervisor(root):
    if getattr(sys, "frozen", False):
        argv = [sys.executable, "--supervisor"]
    else:
        launcher = Path(__file__).resolve().parent.parent / "ModelOrchestration.pyw"
        argv = [sys.executable, str(launcher), "--supervisor"]
    child = subprocess.Popen(argv, cwd=root, env=os.environ | {"ORCHESTRA_DATA": str(root)}, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **process_backend().detached_options())
    threading.Thread(target=child.wait, name="supervisor-reaper", daemon=True).start()


def run_supervisor(root):
    supervisor = Supervisor(root)
    signal.signal(signal.SIGTERM, lambda *_: supervisor.closed.set())
    supervisor.serve()
