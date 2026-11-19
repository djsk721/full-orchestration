from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .core import Invalid, digest, encode, require
from . import desktop_contract


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "state.db"
        with self.connect() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS clients (token TEXT PRIMARY KEY, heartbeat REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, run_key TEXT NOT NULL, plan TEXT NOT NULL,
                    config TEXT NOT NULL, foreground TEXT, state TEXT NOT NULL,
                    created REAL NOT NULL, updated REAL NOT NULL, owner TEXT,
                    heartbeat REAL, action TEXT, result TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_pending ON jobs(state,created);
                CREATE TABLE IF NOT EXISTS tasks (
                    job TEXT NOT NULL, id TEXT NOT NULL, state TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 0,
                    available REAL NOT NULL DEFAULT 0, checkpoint TEXT, result TEXT,
                    PRIMARY KEY(job,id), FOREIGN KEY(job) REFERENCES jobs(id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT NOT NULL, task TEXT,
                    type TEXT NOT NULL, at REAL NOT NULL, route TEXT, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_job ON events(job,seq);
                CREATE TABLE IF NOT EXISTS approvals (
                    job TEXT NOT NULL, task TEXT NOT NULL, key TEXT NOT NULL, state TEXT NOT NULL,
                    tool TEXT NOT NULL, args TEXT NOT NULL, PRIMARY KEY(job,task,key)
                );
                CREATE TABLE IF NOT EXISTS remote_requests (
                    request_id TEXT PRIMARY KEY, plan_hash TEXT NOT NULL, job TEXT NOT NULL REFERENCES jobs(id)
                );
                CREATE TABLE IF NOT EXISTS remote_runs (
                    id TEXT PRIMARY KEY, host TEXT NOT NULL, plan TEXT NOT NULL, remote_job TEXT, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS calls (
                    job TEXT NOT NULL, task TEXT NOT NULL, key TEXT NOT NULL, state TEXT NOT NULL,
                    result TEXT, PRIMARY KEY(job,task,key)
                );
            """)
            needs_contract = not desktop_contract.installed(conn)
        if needs_contract:
            with self.connect(write=True) as conn:
                desktop_contract.install(conn)

    @contextmanager
    def connect(self, write=False):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.commit()
        except BaseException:
            if write:
                conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def event_tx(conn, job, task, kind, payload, route=None):
        conn.execute("INSERT INTO events(job,task,type,at,route,payload) VALUES (?,?,?,?,?,?)",
                     (job, task, kind, time.time(), encode(route) if route else None, encode(payload)))

    def event(self, job, task, kind, payload, route=None):
        with self.connect(write=True) as conn:
            self.event_tx(conn, job, task, kind, payload, route)

    def submit(self, plan, config, foreground, *, request_id=None):
        key = digest([plan, config])
        now = time.time()
        with self.connect(write=True) as conn:
            plan_hash = digest(plan)
            if request_id is not None:
                receipt = conn.execute("SELECT plan_hash,job FROM remote_requests WHERE request_id=?", (request_id,)).fetchone()
                if receipt:
                    require(receipt["plan_hash"] == plan_hash, "기존 원격 요청 ID의 계획이 일치하지 않습니다.")
                    return receipt["job"]
            existing = conn.execute(
                "SELECT id FROM jobs WHERE run_key=? AND state NOT IN ('SUCCEEDED','MERGED','FAILED','CANCELLED')", (key,)
            ).fetchone()
            if existing:
                if request_id is not None:
                    conn.execute("INSERT INTO remote_requests VALUES (?,?,?)", (request_id, plan_hash, existing["id"]))
                return existing["id"]
            job = uuid.uuid4().hex
            conn.execute("INSERT INTO jobs(id,run_key,plan,config,foreground,state,created,updated) VALUES (?,?,?,?,?,'QUEUED',?,?)",
                         (job, key, encode(plan), encode(config), foreground, now, now))
            conn.executemany("INSERT INTO tasks(job,id,state) VALUES (?,?,'QUEUED')",
                             ((job, task["id"]) for task in plan["tasks"]))
            self.event_tx(conn, job, None, "job.state", {"state": "QUEUED"})
            if request_id is not None:
                conn.execute("INSERT INTO remote_requests VALUES (?,?,?)", (request_id, plan_hash, job))
            return job

    def remote_receipt(self, request_id):
        with self.connect() as conn:
            return conn.execute("SELECT job FROM remote_requests WHERE request_id=?", (request_id,)).fetchone()

    def queue_remote(self, host, plan):
        key = uuid.uuid4().hex
        with self.connect(write=True) as conn:
            conn.execute("INSERT INTO remote_runs VALUES (?,?,?,NULL,?)", (key, host, encode(plan), time.time()))
        return key

    def remote_runs(self):
        with self.connect() as conn:
            return [self.decode(row) for row in conn.execute("SELECT * FROM remote_runs ORDER BY created DESC LIMIT 200")]

    def remember_remote(self, key, job):
        with self.connect(write=True) as conn:
            row = conn.execute("SELECT remote_job FROM remote_runs WHERE id=?", (key,)).fetchone()
            require(row and row["remote_job"] in (None, job), "원격 실행의 ID가 변경되었습니다.")
            conn.execute("UPDATE remote_runs SET remote_job=? WHERE id=?", (job, key))

    @staticmethod
    def decode(row):
        if row is None:
            return None
        item = dict(row)
        for key in ("plan", "config", "result", "checkpoint"):
            if item.get(key) is not None:
                item[key] = json.loads(item[key])
        return item

    def list_jobs(self):
        with self.connect() as conn:
            return [self.decode(row) for row in conn.execute(
                "SELECT id,plan,state,created,updated,heartbeat,result FROM jobs ORDER BY created DESC LIMIT 200")]

    def job(self, job):
        with self.connect() as conn:
            return self.decode(conn.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone())

    def tasks(self, job):
        with self.connect() as conn:
            return {row["id"]: self.decode(row) for row in conn.execute("SELECT * FROM tasks WHERE job=?", (job,))}

    @staticmethod
    def event_record(row):
        route = json.loads(row["route"]) if row["route"] else {}
        return {
            "run_id": row["job"], "task_id": row["task"], "agent_id": route.get("agent_id"),
            "model_id": route.get("model_id"), "runtime_id": route.get("runtime_id"),
            "harness_id": route.get("harness_id"), "worktree_id": route.get("worktree_id"),
            "seq": row["seq"], "event_type": row["type"], "timestamp": row["at"],
            "payload_ref": f"sqlite:events:{row['seq']}", "payload": json.loads(row["payload"]),
        }

    def events(self, job, after=0, limit=500):
        with self.connect() as conn:
            return self.events_tx(conn, job, after, limit)

    def events_tx(self, conn, job, after, limit):
        rows = conn.execute("SELECT * FROM events WHERE job=? AND seq>? ORDER BY seq LIMIT ?", (job, after, limit))
        return [self.event_record(row) for row in rows]

    def status_snapshot(self, job, after, limit):
        with self.connect() as conn:
            conn.execute("BEGIN")
            item = self.decode(conn.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone())
            require(item, "원격 실행을 찾을 수 없습니다.")
            events = self.events_tx(conn, job, after, limit)
            tasks = {row["id"]: self.decode(row) for row in conn.execute("SELECT * FROM tasks WHERE job=?", (job,))}
            return item, tasks, events

    def recent_events(self, job=None, limit=200):
        with self.connect() as conn:
            if job is None:
                rows = conn.execute("""SELECT seq,job,task,type,at,route,payload
                    FROM events WHERE job IN (SELECT id FROM jobs) ORDER BY seq DESC LIMIT ?""", (limit,))
            else:
                rows = conn.execute("SELECT * FROM events WHERE job=? ORDER BY seq DESC LIMIT ?", (job, limit))
            return [self.event_record(row) for row in rows]

    def report(self, job):
        item = self.job(job)
        require(item, "작업을 찾을 수 없습니다.")
        events = []
        while page := self.events(job, events[-1]["seq"] if events else 0):
            events.extend(page)
        tokens = []
        for event in events:
            if event["event_type"] != "model.usage":
                continue
            tokens.append({"agent_id": event["agent_id"], "task_id": event["task_id"], **event["payload"]})
        base = next((event["payload"]["base"] for event in events if "base" in event["payload"]), None)
        verified = next((event["timestamp"] for event in reversed(events) if event["event_type"] == "job.state"
                         and event["payload"].get("state") in ("SUCCEEDED", "AWAITING_APPROVAL")), None)
        total = [row["total_tokens"] for row in tokens if row["total_tokens"] is not None]
        return {
            "run_id": job, "state": item["state"], "elapsed_sec": item["updated"] - item["created"],
            "base": base, "seconds_to_verified": verified - item["created"] if verified else None,
            "tokens_observed": sum(total) if total else None, "usage_events_missing_total": len(tokens) - len(total),
            "spec_hash": digest(item["plan"]), "config_hash": digest(item["config"]), "result": item["result"],
            "tasks": {key: {k: row[k] for k in ("state", "attempt", "result")} for key, row in self.tasks(job).items()},
            "tokens": tokens, "events": events,
        }

    def presence(self, token, active=True):
        with self.connect(write=True) as conn:
            if active:
                conn.execute("INSERT INTO clients VALUES (?,?) ON CONFLICT(token) DO UPDATE SET heartbeat=excluded.heartbeat",
                             (token, time.time()))
            else:
                conn.execute("DELETE FROM clients WHERE token=?", (token,))

    def live_clients(self):
        with self.connect() as conn:
            return {row["token"] for row in conn.execute("SELECT token FROM clients WHERE heartbeat>?", (time.time() - 10,))}

    def pending(self):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT id,foreground FROM jobs WHERE state IN ('QUEUED','RETRY_WAIT','MERGE_QUEUED') ORDER BY created")]

    def expire_foreground(self):
        with self.connect(write=True) as conn:
            rows = conn.execute("""SELECT id FROM jobs WHERE foreground IS NOT NULL AND owner IS NULL
                    AND state IN ('QUEUED','RETRY_WAIT','MERGE_QUEUED')
                    AND foreground NOT IN (SELECT token FROM clients WHERE heartbeat>?)""", (time.time() - 10,)).fetchall()
            for row in rows:
                conn.execute("UPDATE jobs SET state='CANCELLED',updated=? WHERE id=?", (time.time(), row["id"]))
                self.event_tx(conn, row["id"], None, "job.state", {"state": "CANCELLED", "reason": "foreground_disconnected"})

    def claim(self, job, owner):
        with self.connect(write=True) as conn:
            row = conn.execute("SELECT state,owner FROM jobs WHERE id=?", (job,)).fetchone()
            if not row or row["owner"] is not None or row["state"] not in ("QUEUED", "RETRY_WAIT", "MERGE_QUEUED"):
                return False
            state = "MERGING" if row["state"] == "MERGE_QUEUED" else "PREPARING"
            now = time.time()
            conn.execute("UPDATE jobs SET state=?,owner=?,heartbeat=?,updated=?,action=NULL WHERE id=?",
                         (state, owner, now, now, job))
            self.event_tx(conn, job, None, "job.state", {"state": state})
            return True

    def heartbeat(self, job, owner):
        with self.connect(write=True) as conn:
            conn.execute("UPDATE jobs SET heartbeat=? WHERE id=? AND owner=?", (time.time(), job, owner))

    def set_job(self, job, state, details=None, release=True, result=None):
        with self.connect(write=True) as conn:
            row = conn.execute("SELECT action FROM jobs WHERE id=?", (job,)).fetchone()
            require(row, "작업을 찾을 수 없습니다.")
            if row["action"] == "cancel":
                if not release:
                    return False
                if state != "CANCELLED":
                    state, details, result = "CANCELLED", {"reason": "cancel_requested"}, None
            conn.execute("""UPDATE jobs SET state=?,updated=?,
                action=CASE WHEN ? THEN NULL ELSE action END,owner=CASE WHEN ? THEN NULL ELSE owner END,
                result=COALESCE(?,result) WHERE id=?""",
                         (state, time.time(), release, release, encode(result) if result is not None else None, job))
            self.event_tx(conn, job, None, "job.state", {**(details or {}), "state": state})
            return True

    def set_task(self, job, task, state, *, attempt=None, retry_after=0, result=None, route=None):
        with self.connect(write=True) as conn:
            conn.execute("""UPDATE tasks SET state=?,attempt=COALESCE(?,attempt),available=?,
                        result=COALESCE(?,result) WHERE job=? AND id=?""",
                         (state, attempt, time.time() + retry_after, encode(result) if result is not None else None, job, task))
            self.event_tx(conn, job, task, "task.state", {**(result or {}), "state": state, "attempt": attempt}, route)

    def checkpoint(self, job, task, data, route):
        with self.connect(write=True) as conn:
            conn.execute("UPDATE tasks SET checkpoint=? WHERE job=? AND id=?", (encode(data), job, task))
            self.event_tx(conn, job, task, "task.checkpoint", {"step": data["step"]}, route)

    def call_start(self, job, task, key):
        with self.connect(write=True) as conn:
            row = conn.execute("SELECT state,result FROM calls WHERE job=? AND task=? AND key=?", (job, task, key)).fetchone()
            if row:
                if row["state"] != "done":
                    raise Invalid("이전 도구 호출의 결과가 불명확합니다. 다시 실행하기 전에 상태를 확인하세요.")
                return json.loads(row["result"])
            conn.execute("INSERT INTO calls(job,task,key,state) VALUES (?,?,?,'started')", (job, task, key))
            return None

    def call_end(self, job, task, key, result):
        with self.connect(write=True) as conn:
            conn.execute("UPDATE calls SET state='done',result=? WHERE job=? AND task=? AND key=?",
                         (encode(result), job, task, key))

    def approvals(self, job):
        with self.connect() as conn:
            return [{**dict(row), "args": json.loads(row["args"])} for row in conn.execute(
                "SELECT * FROM approvals WHERE job=? AND state='pending' ORDER BY task", (job,))]

    def approval(self, job, task, key, tool, args):
        with self.connect(write=True) as conn:
            row = conn.execute("SELECT state FROM approvals WHERE job=? AND task=? AND key=?", (job,task,key)).fetchone()
            if row:
                return row["state"]
            conn.execute("INSERT INTO approvals VALUES (?,?,?,'pending',?,?)", (job,task,key,tool,encode(args)))
            self.event_tx(conn,job,task,"tool.approval",{"tool": tool, "key": key})
            return "pending"

    def decide(self, job, task, key, accept):
        with self.connect(write=True) as conn:
            row = conn.execute("SELECT state FROM jobs WHERE id=?", (job,)).fetchone()
            require(row and row["state"] == "AWAITING_TOOL", "작업의 승인 대기 상태가 변경되었습니다.")
            changed = conn.execute("UPDATE approvals SET state=? WHERE job=? AND task=? AND key=? AND state='pending'",
                                   ("approved" if accept else "denied",job,task,key)).rowcount
            require(changed, "도구 요청이 이미 처리되었습니다.")
            self.event_tx(conn,job,task,"tool.decision",{"approved": accept, "key": key})
            if not conn.execute("SELECT 1 FROM approvals WHERE job=? AND state='pending'", (job,)).fetchone():
                conn.execute("UPDATE tasks SET state='QUEUED' WHERE job=? AND state='AWAITING_TOOL'", (job,))
                conn.execute("UPDATE jobs SET state='QUEUED',updated=? WHERE id=?", (time.time(),job))

    def request(self, job, action, candidate=None, *, approval_revision=None):
        with self.connect(write=True) as conn:
            row = self.decode(conn.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone())
            require(row, "작업을 찾을 수 없습니다.")
            state = row["state"]
            if action == "merge":
                result = row["result"] or {}
                require(state == "AWAITING_APPROVAL" and candidate and result.get("candidate") == candidate,
                        "현재 QA 후보에 대한 승인이 필요합니다.")
                if approval_revision is not None:
                    require(result.get("approval_revision") == approval_revision,
                            "QA 검증이 갱신되었습니다. 현재 후보를 다시 검토하세요.")
                state = "MERGE_QUEUED"
            elif action == "retry":
                require(state == "FAILED", "실패한 작업만 재시도할 수 있습니다.")
                require(not conn.execute("SELECT 1 FROM calls WHERE job=? AND state='started'", (job,)).fetchone(),
                        "완료 여부가 불명확한 외부 쓰기 호출이 있어 자동 재개할 수 없습니다.")
                state = "QUEUED"
                conn.execute("UPDATE tasks SET state='QUEUED',attempt=0,available=0,result=NULL WHERE job=? AND state!='SUCCEEDED'", (job,))
            else:
                require(action == "cancel" and state not in ("SUCCEEDED", "MERGED", "FAILED", "CANCELLED", "MERGING"),
                        "현재 상태에서는 중지할 수 없습니다.")
                if row["owner"] is None:
                    state = "CANCELLED"
            conn.execute("UPDATE jobs SET state=?,action=?,updated=? WHERE id=?", (state, action, time.time(), job))
            self.event_tx(conn, job, None, "job.request", {"action": action, "state": state, "candidate": candidate})

    def attach_foreground(self, job, token):
        with self.connect(write=True) as conn:
            conn.execute("""UPDATE jobs SET foreground=? WHERE id=? AND foreground IS NOT NULL AND owner IS NULL
                         AND state IN ('QUEUED','MERGE_QUEUED','AWAITING_TOOL')""", (token, job))

    def recover(self, background, owner):
        with self.connect(write=True) as conn:
            rows = conn.execute(
                """SELECT id,state,config,foreground,action FROM jobs WHERE owner IS NOT NULL AND owner<>?
                   AND (foreground IS NULL)=?""", (owner, background)).fetchall()
            for row in rows:
                live = conn.execute("SELECT heartbeat FROM jobs WHERE id=?", (row["id"],)).fetchone()[0]
                lease = json.loads(row["config"])["settings"].get("lease_sec", 90)
                if live is not None and time.time() - live < lease:
                    continue
                job = row["id"]
                state = ("MERGE_QUEUED" if row["state"] == "MERGING" else "QUEUED") if background else "CANCELLED"
                if row["action"] == "cancel":
                    state = "CANCELLED"
                conn.execute("UPDATE jobs SET owner=NULL,state=?,updated=? WHERE id=?", (state, time.time(), job))
                conn.execute("UPDATE tasks SET state=? WHERE job=? AND state IN ('PREPARING','RUNNING','VERIFYING','RETRY_WAIT')",
                             ("QUEUED" if state != "CANCELLED" else "CANCELLED", job))
                self.event_tx(conn, job, None, "job.recovered", {"state": state})
