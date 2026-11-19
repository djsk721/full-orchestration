import { existsSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { validRunId } from "../core/worker";
import type { Activity, DashboardResponse, JobDetail, JobSummary, QaResult, TaskSummary } from "../src/contracts";

type Row = Record<string, unknown>;
const taskIdPattern = /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$/;
const eventPattern = /^[a-zA-Z0-9_.-]{1,64}$/;
const shaPattern = /^(?:[a-f0-9]{40}|[a-f0-9]{64})$/;

export function isJobId(value: unknown): value is string {
  return validRunId(value);
}

function isTaskId(value: unknown): value is string {
  return typeof value === "string" && taskIdPattern.test(value);
}

function number(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function timestamp(value: unknown): number {
  const seconds = number(value);
  return Math.abs(seconds) < 8.64e12 ? seconds : 0;
}

function state(value: unknown): string {
  return typeof value === "string" && /^[A-Z_]{1,32}$/.test(value) ? value : "UNKNOWN";
}

function summary(row: Row): JobSummary | null {
  if (!isJobId(row.id)) return null;
  return {
    id: row.id,
    title: typeof row.title === "string" && row.title ? row.title : "Untitled job",
    state: state(row.state),
    background: row.background === 1,
    updatedAt: timestamp(row.updated),
  };
}

const summaryQuery = `
  SELECT id, state, updated, foreground IS NULL AS background,
      CASE WHEN json_valid(plan) THEN substr(json_extract(plan, '$.title'), 1, 240) END AS title
  FROM jobs
`;

function readDetail(db: DatabaseSync, job: JobSummary, contract: boolean): JobDetail {
  // Project only the primitive fields consumed by the renderer. Never transfer the raw plan or events.
  const edges = db.prepare(contract ?
    "SELECT DISTINCT id, role, dependency FROM desktop_edges_v1 WHERE job = ? LIMIT 10000" : `
    SELECT DISTINCT json_extract(node.value, '$.id') AS id,
        substr(json_extract(node.value, '$.role'), 1, 24) AS role,
        dependency.value AS dependency
    FROM jobs
    JOIN json_each(CASE WHEN json_valid(plan) THEN plan ELSE '{}' END, '$.tasks') AS node
    LEFT JOIN json_each(node.value, '$.depends') AS dependency
    WHERE jobs.id = ? AND node.type = 'object'
    LIMIT 10000
  `).all(job.id);
  const graph = new Map<string, { role: string; dependencies: string[] }>();
  for (const edge of edges) {
    if (!isTaskId(edge.id)) continue;
    const node = graph.get(edge.id) ?? { role: typeof edge.role === "string" ? edge.role : "", dependencies: [] };
    if (isTaskId(edge.dependency)) node.dependencies.push(edge.dependency);
    graph.set(edge.id, node);
  }

  const tasks = db.prepare(contract ?
    "SELECT id, state, attempt FROM desktop_tasks_v1 WHERE job = ? ORDER BY position LIMIT 100" :
    "SELECT id, state, attempt FROM tasks WHERE job = ? ORDER BY rowid LIMIT 100")
    .all(job.id).flatMap((row): TaskSummary[] => {
      if (!isTaskId(row.id)) return [];
      const node = graph.get(row.id);
      return [{
        id: row.id,
        state: state(row.state),
        attempt: number(row.attempt),
        role: node?.role || "Unknown role",
        dependencies: node?.dependencies ?? [],
      }];
    });
  const events = db.prepare(contract ?
    "SELECT seq, task, type, at FROM desktop_events_v1 WHERE job = ? ORDER BY seq DESC LIMIT 120" :
    "SELECT seq, task, type, at FROM events WHERE job = ? ORDER BY seq DESC LIMIT 120")
    .all(job.id).flatMap((row): Activity[] => {
      if (typeof row.type !== "string" || !eventPattern.test(row.type)) return [];
      return [{
        sequence: number(row.seq),
        taskId: isTaskId(row.task) ? row.task : null,
        type: row.type,
        at: timestamp(row.at),
      }];
    });

  const candidate = committedCandidate(db, job, contract);
  const checks = contract ? db.prepare(
    "SELECT ordinal, exit_code FROM desktop_qa_v1 WHERE job = ? ORDER BY position LIMIT 100",
  ).all(job.id) : legacyChecks(db, job.id);
  const qa = checks.flatMap((row): QaResult[] => (
    typeof row.ordinal === "number" && Number.isSafeInteger(row.ordinal) && row.ordinal > 0 &&
    typeof row.exit_code === "number" && Number.isSafeInteger(row.exit_code)
      ? [{ index: row.ordinal, exitCode: row.exit_code }] : []
  ));
  return { job, tasks, events, candidate, qa };
}

function committedCandidate(db: DatabaseSync, job: JobSummary, contract: boolean): string | null {
  // A pre-contract database has historical evidence, but no authoritative approval projection.
  if (!contract) return null;
  const value = db.prepare("SELECT candidate FROM desktop_jobs_v1 WHERE id = ?").get(job.id)?.candidate;
  return typeof value === "string" && shaPattern.test(value) ? value : null;
}

function legacyChecks(db: DatabaseSync, jobId: string): Row[] {
  // Compatibility for installed stores that have not yet been opened by Python.
  const boundary = db.prepare(`
    SELECT max(seq) AS seq
    FROM events
    WHERE job = ? AND task IS NULL AND type IN ('job.state', 'job.request', 'job.recovered')
      AND CASE WHEN json_valid(payload) THEN json_extract(payload, '$.state') END IN ('VERIFYING', 'QUEUED')
  `).get(jobId)?.seq;
  const recentChecks = db.prepare(`
    SELECT
      CASE WHEN json_valid(payload) THEN json_extract(payload, '$.index') END AS ordinal,
      CASE WHEN json_valid(payload) THEN json_extract(payload, '$.exit_code') END AS exit_code
    FROM events
    WHERE job = ? AND task IS NULL AND type = 'qa.result' AND seq > ?
    ORDER BY seq
    LIMIT 100
  `).all(jobId, typeof boundary === "number" ? boundary : 0);
  return recentChecks.length ? recentChecks : db.prepare(`
    SELECT json_extract(checks.value, '$.index') AS ordinal,
        json_extract(checks.value, '$.exit_code') AS exit_code
    FROM jobs JOIN json_each(CASE WHEN json_valid(result) THEN result ELSE '{}' END, '$.qa') AS checks
    WHERE jobs.id = ? AND checks.type = 'object'
      AND jobs.state IN ('SUCCEEDED', 'AWAITING_APPROVAL', 'MERGE_QUEUED', 'MERGING', 'MERGED')
      AND NOT EXISTS (
        SELECT 1 FROM events WHERE job = jobs.id AND task IS NULL AND type = 'qa.result'
      )
    ORDER BY checks.key
    LIMIT 100
  `).all(jobId);
}

export function readDashboard(databasePath: string, jobId: string | null): DashboardResponse {
  if (!existsSync(databasePath)) return { status: "empty" };
  const db = new DatabaseSync(databasePath, {
    readOnly: true,
    allowExtension: false,
    timeout: 250,
  });
  try {
    db.exec("PRAGMA query_only = ON; PRAGMA trusted_schema = OFF; BEGIN;");
    const version = db.prepare("PRAGMA user_version").get()?.user_version;
    const tables = db.prepare(`
      SELECT name FROM sqlite_schema WHERE type = 'table' AND name IN ('jobs', 'tasks', 'events')
    `).all();
    if (version !== 0 || tables.length !== 3) return { status: "unavailable" };
    const marker = db.prepare("SELECT type FROM sqlite_schema WHERE name='desktop_contract'").get();
    const contract = marker !== undefined;
    if (contract && (marker.type !== "view" || db.prepare("SELECT version FROM desktop_contract").get()?.version !== 1)) {
      return { status: "unavailable" };
    }
    const query = contract ? "SELECT id, state, updated, background, title FROM desktop_jobs_v1" : summaryQuery;
    const jobs = db.prepare(query + " ORDER BY updated DESC, id LIMIT 100")
      .all().flatMap((row) => {
        const job = summary(row);
        return job ? [job] : [];
      });
    const picked = jobId ? db.prepare(query + " WHERE id = ?").get(jobId) : null;
    const job = picked ? summary(picked) : null;
    return { status: "ready", dashboard: { jobs, detail: job ? readDetail(db, job, contract) : null } };
  } finally {
    db.close();
  }
}
