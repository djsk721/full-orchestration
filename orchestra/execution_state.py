"""Supervisor-owned execution decisions and presentation states."""
from __future__ import annotations

import re

LIVE = frozenset({"PREPARING", "RUNNING", "VERIFYING", "AWAITING_TOOL", "RETRY_WAIT"})
INCOMPLETE = LIVE | {"QUEUED"}
TERMINAL = frozenset({"FAILED", "CANCELLED", "SUCCEEDED", "MERGED"})
BLOCKED = frozenset({"AWAITING_TOOL", "FAILED"})
MERGE_EVIDENCE = ("AWAITING_APPROVAL", "MERGE_QUEUED", "MERGING", "MERGED")
RUNNABLE = frozenset({"QUEUED", "RETRY_WAIT"})


def integration_qa_passed(checks):
    return isinstance(checks, list) and bool(checks) and all(
        isinstance(check, dict) and type(check.get("exit_code")) is int and check["exit_code"] == 0
        for check in checks)


def merge_candidate_ready(job):
    result = job.get("result") or {}
    candidate = result.get("candidate")
    return (job["state"] == "AWAITING_APPROVAL" and isinstance(candidate, str)
            and re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", candidate) is not None
            and integration_qa_passed(result.get("qa")))


def task_stage(job_state, state):
    if state not in INCOMPLETE or job_state not in TERMINAL:
        return state
    return "CANCELLED" if job_state == "CANCELLED" else "NOT_EXECUTED"


def ready_tasks(sequence, ancestry, rows, active, now, limit):
    if any(row["state"] in BLOCKED for row in rows.values()):
        return []
    capacity = max(0, limit - len(active))
    result = []
    for key in sequence:
        if len(result) == capacity:
            break
        row = rows[key]
        if (key not in active and row["state"] in RUNNABLE and row["available"] <= now
                and all(rows[dep]["state"] == "SUCCEEDED" for dep in ancestry[key])):
            result.append(key)
    return result
