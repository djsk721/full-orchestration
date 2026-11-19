"""Versioned, read-only SQLite projections owned by the Python writer.

These are additive views. Keep v1 immutable for installed readers and add
a new version if a projection's columns or semantics change.
"""
from __future__ import annotations

from .execution_state import INCOMPLETE, MERGE_EVIDENCE, TERMINAL

VERSION = 1


def _in(states):
    return ", ".join("'" + state + "'" for state in sorted(states))


def installed(conn):
    return conn.execute(
        "SELECT 1 FROM sqlite_schema WHERE name='desktop_contract' AND type='view'"
    ).fetchone() is not None


def install(conn):
    """The caller keeps all view creation, including the version marker, in one transaction."""
    statements = (
        f"""CREATE VIEW IF NOT EXISTS desktop_jobs_v1 AS
        SELECT id, state, updated, foreground IS NULL AS background,
               CASE WHEN json_valid(plan) THEN substr(json_extract(plan, '$.title'), 1, 240) END AS title,
               CASE WHEN state IN ({_in(MERGE_EVIDENCE)}) AND json_valid(result)
                    THEN json_extract(result, '$.candidate') END AS candidate
        FROM jobs""",
        f"""CREATE VIEW IF NOT EXISTS desktop_tasks_v1 AS
        SELECT t.job, t.id, t.rowid AS position, t.attempt,
               CASE WHEN t.state IN ({_in(INCOMPLETE)}) AND j.state IN ({_in(TERMINAL)})
                    THEN CASE WHEN j.state = 'CANCELLED' THEN 'CANCELLED' ELSE 'NOT_EXECUTED' END
                    ELSE t.state END AS state
        FROM tasks t JOIN jobs j ON j.id = t.job""",
        """CREATE VIEW IF NOT EXISTS desktop_edges_v1 AS
        SELECT j.id AS job, json_extract(node.value, '$.id') AS id,
               substr(json_extract(node.value, '$.role'), 1, 24) AS role,
               dependency.value AS dependency
        FROM jobs j
        JOIN json_each(CASE WHEN json_valid(j.plan) THEN j.plan ELSE '{}' END, '$.tasks') AS node
        LEFT JOIN json_each(CASE WHEN node.type = 'object' THEN node.value ELSE '{}' END, '$.depends') AS dependency
        WHERE node.type = 'object'""",
        """CREATE VIEW IF NOT EXISTS desktop_events_v1 AS
        SELECT job, seq, task, type, at FROM events""",
        """CREATE VIEW IF NOT EXISTS desktop_qa_v1 AS
        SELECT e.job, e.seq AS position,
               CASE WHEN json_valid(e.payload) THEN json_extract(e.payload, '$.index') END AS ordinal,
               CASE WHEN json_valid(e.payload) THEN json_extract(e.payload, '$.exit_code') END AS exit_code
        FROM events e
        WHERE e.task IS NULL AND e.type = 'qa.result' AND e.seq > coalesce((
            SELECT max(boundary.seq)
            FROM events boundary
            WHERE boundary.job = e.job AND boundary.task IS NULL
              AND boundary.type IN ('job.state', 'job.request', 'job.recovered')
              AND CASE WHEN json_valid(boundary.payload) THEN json_extract(boundary.payload, '$.state') END
                  IN ('VERIFYING', 'QUEUED')
        ), 0)
        UNION ALL
        SELECT j.id, CAST(checks.key AS INTEGER), json_extract(checks.value, '$.index'),
               json_extract(checks.value, '$.exit_code')
        FROM jobs j JOIN json_each(CASE WHEN json_valid(j.result) THEN j.result ELSE '{}' END, '$.qa') AS checks
        WHERE checks.type = 'object'
          -- Old records may have only the final committed QA result, with an initial QUEUED event.
          AND j.state IN ('SUCCEEDED', 'AWAITING_APPROVAL', 'MERGE_QUEUED', 'MERGING', 'MERGED')
          AND NOT EXISTS (
              SELECT 1 FROM events e WHERE e.job = j.id AND e.task IS NULL AND e.type = 'qa.result'
          )""",
        f"CREATE VIEW IF NOT EXISTS desktop_contract AS SELECT {VERSION} AS version",
    )
    for statement in statements:
        conn.execute(statement)
