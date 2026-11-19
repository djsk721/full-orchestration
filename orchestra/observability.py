"""Display projections based on persisted task state and observed execution events."""
from __future__ import annotations

import time
from collections import defaultdict

from .execution_state import LIVE, task_stage

EVENT_LABELS = {
    "job.state": "실행 상태", "job.request": "작업 요청", "job.recovered": "실행 복구",
    "task.state": "Agent 단계", "task.checkpoint": "체크포인트", "model.usage": "모델 사용량",
    "runtime.snapshot": "Runtime 검증", "harness.snapshot": "Harness 관측", "tool.call": "도구 호출",
    "tool.approval": "도구 승인 요청", "tool.decision": "도구 승인 처리", "qa.result": "QA 결과",
    "qa.interrupted": "QA 중단",
    "git.commit": "Git 커밋", "review.result": "독립 검토 결과", "route.selected": "실행 경로", "route.failed": "경로 오류",
    "file.changed": "파일 변경", "process.activity": "CLI 활동",
}


def task_roles(plan):
    return {task["id"]: task for task in plan.get("tasks", [])}


def agent_rows(job, tasks, events, *, now=None, config=None):
    now = now if now is not None else time.time()
    configured = task_roles(job["plan"])
    models = (config or job.get("config") or {}).get("models", {})
    groups = defaultdict(list)
    for event in events:
        if event.get("task_id"):
            groups[event["task_id"]].append(event)
    result = []
    for key, task in tasks.items():
        history = sorted(groups[key], key=lambda event: event["seq"])
        role = configured.get(key, {}).get("role")
        current_attempt = task["attempt"]
        begin = next((index for index in reversed(range(len(history)))
                      if history[index]["event_type"] == "task.state"
                      and history[index]["payload"].get("state") == "PREPARING"), 0)
        current = history[begin:]
        active = next((event for event in reversed(current) if any(event.get(name) for name in (
            "agent_id", "model_id", "harness_id"))), {})
        state_events = [event for event in current if event["event_type"] == "task.state"]
        started = next((event["timestamp"] for event in state_events
                        if event["payload"].get("state") in ("RUNNING", "VERIFYING")), None)
        stage = task_stage(job["state"], task["state"])
        ended = state_events[-1]["timestamp"] if state_events else None
        duration = (now if stage in LIVE else ended) - started if started is not None and ended is not None else None
        usage = [event["payload"] for event in history if event["event_type"] == "model.usage"]
        observations = [event["payload"] for event in current if event["event_type"] == "runtime.snapshot"
                        and isinstance(event["payload"].get("validated"), dict)]
        last_tokens = next((row.get("prompt_tokens") for row in reversed(usage) if type(row.get("prompt_tokens")) is int), None)
        failures = [event["payload"].get("reason") for event in current if event["event_type"] == "route.failed"]
        output = task.get("result") or task
        model = active.get("model_id")
        result.append({
            "id": key, "agent": active.get("agent_id"), "role": role, "provider": models.get(model, {}).get("provider"),
            "model": model, "harness": active.get("harness_id"), "runtime": active.get("runtime_id"),
            "state": stage, "started": started, "elapsed": max(0, duration) if duration is not None else None,
            "retry_count": max(0, current_attempt - 1),
            "input": token_sum(usage, "prompt_tokens"), "output": token_sum(usage, "completion_tokens"),
            "last_prompt": last_tokens, "context": observations[-1]["validated"].get("context") if observations else None,
            "tools": sum(event["event_type"] == "tool.call" for event in history),
            "last_error": output.get("reason") or (failures[-1] if failures and stage in ("FAILED", "RETRY_WAIT") else None),
            "changed": output.get("changed", []), "artifact": output.get("artifact"),
            "last_event": current[-1]["event_type"] if current else None,
        })
    return result


def token_sum(usage, key):
    values = [row[key] for row in usage if type(row.get(key)) is int]
    return sum(values) if values else None
