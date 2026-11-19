import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, posix, win32 } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { test } from "node:test";
import { dataDirectory } from "../electron/config";
import { isJobId, readDashboard } from "../electron/legacy-store";
import { isSnapshotRequest } from "../src/contracts";

test("resolves platform data paths and explicit overrides", () => {
  assert.equal(dataDirectory({ LOCALAPPDATA: "C:\\Users\\Operator\\AppData\\Local" }, "win32", "ignored"),
    win32.join("C:\\Users\\Operator\\AppData\\Local", "ModelOrchestration"));
  assert.equal(dataDirectory({ XDG_DATA_HOME: "xdg" }, "linux", "ignored"), posix.join("xdg", "ModelOrchestration"));
  assert.equal(dataDirectory({}, "linux", "home"), posix.join("home", ".local", "share", "ModelOrchestration"));
  assert.equal(dataDirectory({ ORCHESTRA_DATA: "~/isolated" }, "linux", "/home/operator"), "/home/operator/isolated");
});

test("validates scalar job IDs", () => {
  assert(isJobId("0".repeat(32)));
  for (const input of [{}, 123, "", "../state.db", "a".repeat(33), "A".repeat(32)]) {
    assert(!isJobId(input));
  }
});

test("accepts only the supported dashboard IPC message shape", () => {
  assert(isSnapshotRequest({ version: 1, jobId: null }));
  assert(isSnapshotRequest({ version: 1, jobId: "1".repeat(32) }));
  for (const value of [null, [], {}, { version: 2, jobId: null }, { version: 1, jobId: "../state.db" },
    { version: 1, jobId: null, file: "state.db" }]) assert(!isSnapshotRequest(value));
});

test("a missing Python database does not create a directory or database", (t) => {
  const directory = mkdtempSync(join(tmpdir(), "orchestra-missing-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const database = join(directory, "missing", "state.db");
  assert.deepEqual(readDashboard(database, null), { status: "empty" });
  assert(!existsSync(database));
});

test("reads real Python Store rows without exporting private fields or modifying the database", (t) => {
  const directory = mkdtempSync(join(tmpdir(), "orchestra-compatibility-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const result = execFileSync(process.env.PYTHON || "python", ["tests/legacy_fixture.py", directory], { encoding: "utf8" });
  const { id } = JSON.parse(result) as { id: string };
  const path = join(directory, "state.db");
  const before = readFileSync(path);

  const jobs = readDashboard(path, null);
  assert.equal(jobs.status, "ready");
  assert.deepEqual(jobs.dashboard.jobs.map(({ id: key, title, background }) => [key, title, background]),
    [[id, "문서 verification", true]]);
  assert.equal(jobs.dashboard.detail, null);

  const reading = readDashboard(path, id);
  assert.equal(reading.status, "ready");
  const { detail } = reading.dashboard;
  assert(detail);
  assert.equal(detail.job.state, "AWAITING_APPROVAL");
  assert.deepEqual(detail.tasks.find((task) => task.id === "qa")?.dependencies, ["review"]);
  assert.equal(detail.events.find((event) => event.type === "qa.result")?.taskId, "qa");
  assert.equal(detail.candidate, "a".repeat(40));
  assert.deepEqual(detail.qa, [{ index: 1, exitCode: 0 }]);
  assert(!JSON.stringify(reading).includes("PRIVATE_"));
  assert.deepEqual(readFileSync(path), before);
});

test("rejects an unknown legacy schema version", (t) => {
  const directory = mkdtempSync(join(tmpdir(), "orchestra-schema-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const database = join(directory, "state.db");
  const conn = new DatabaseSync(database);
  conn.exec("PRAGMA user_version = 9");
  conn.close();
  assert.deepEqual(readDashboard(database, null), { status: "unavailable" });
});

test("loads old rows conservatively, then uses only Python's supported projection version", (t) => {
  const directory = mkdtempSync(join(tmpdir(), "orchestra-schema-upgrade-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const python = process.env.PYTHON || "python";
  const fixture = "tests/legacy_fixture.py";
  const { id } = JSON.parse(execFileSync(python, [fixture, directory], { encoding: "utf8" })) as { id: string };
  const database = join(directory, "state.db");
  const writer = new DatabaseSync(database);
  try {
    writer.exec("DROP VIEW desktop_contract; UPDATE tasks SET state='RUNNING'; UPDATE jobs SET state='FAILED'");
    const past = readDashboard(database, id);
    assert.equal(past.status, "ready");
    assert(past.dashboard.detail?.tasks.every((task) => task.state === "RUNNING"));
    assert.equal(past.dashboard.detail?.candidate, null);

    execFileSync(python, [fixture, directory, "--reopen"]);
    const migrated = readDashboard(database, id);
    assert.equal(migrated.status, "ready");
    assert(migrated.dashboard.detail?.tasks.every((task) => task.state === "NOT_EXECUTED"));
    assert.equal(migrated.dashboard.detail?.candidate, null);
    writer.exec("DROP VIEW desktop_contract; CREATE VIEW desktop_contract AS SELECT 2 AS version");
    assert.deepEqual(readDashboard(database, id), { status: "unavailable" });
  } finally {
    writer.close();
  }
});

test("an invalid SQLite file remains untouched", (t) => {
  const directory = mkdtempSync(join(tmpdir(), "orchestra-invalid-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const database = join(directory, "state.db");
  writeFileSync(database, "not sqlite");
  assert.throws(() => readDashboard(database, null));
  assert.equal(readFileSync(database, "utf8"), "not sqlite");
});

test("live read-only snapshots exclude uncommitted writes and stale QA from prior attempts", (t) => {
  const directory = mkdtempSync(join(tmpdir(), "orchestra-read-consistency-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const { id } = JSON.parse(execFileSync(process.env.PYTHON || "python", ["tests/legacy_fixture.py", directory],
    { encoding: "utf8" })) as { id: string };
  const database = join(directory, "state.db");
  const writer = new DatabaseSync(database);
  try {
    writer.exec("BEGIN IMMEDIATE");
    writer.prepare("UPDATE jobs SET state='VERIFYING' WHERE id=?").run(id);
    writer.prepare("INSERT INTO events(job,task,type,at,payload) VALUES (?,NULL,'job.state',1,?)")
      .run(id, JSON.stringify({ state: "VERIFYING" }));
    const snapshot = readDashboard(database, id);
    assert.equal(snapshot.status, "ready");
    assert.equal(snapshot.dashboard.detail?.candidate, "a".repeat(40));
    assert.deepEqual(snapshot.dashboard.detail?.qa, [{ index: 1, exitCode: 0 }]);
    writer.exec("COMMIT");
    const next = readDashboard(database, id);
    assert.equal(next.status, "ready");
    assert.equal(next.dashboard.detail?.job.state, "VERIFYING");
    assert.equal(next.dashboard.detail?.candidate, null);
    assert.deepEqual(next.dashboard.detail?.qa, []);
  } finally {
    writer.close();
  }
});
