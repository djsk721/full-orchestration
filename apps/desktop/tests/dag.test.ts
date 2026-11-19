import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { test } from "node:test";
import { analyzeDag } from "../core/dag";
import { readyTasks, type RunState } from "../core/execution";

const node = (id: string, ...dependencies: string[]) => ({ id, dependencies });

test("reports duplicate, case-insensitive duplicate, missing targets, and cycles", () => {
  for (const [nodes, reason] of [
    [[node("A"), node("A")], "duplicate"],
    [[node("A"), node("a")], "duplicate"],
    [[node("A", "a")], "unknown-dependency"],
    [[node("A", "A")], "cycle"],
    [[node("B", "A"), node("A", "B")], "cycle"],
  ] as const) {
    const actual = analyzeDag(nodes);
    assert.equal(actual.status, "invalid");
    assert.equal(actual.reason, reason);
  }
});

test("matches the legacy scheduler's stable order and transitive dependencies", () => {
  const cases = [
    [node("A"), node("B", "A"), node("C"), node("D", "B", "C")],
    [node("review", "work"), node("qa", "review", "review"), node("work"), node("diag")],
    [node("deploy", "qa"), node("qa", "review"), node("review", "work"), node("work")],
    [node("work"), node("Work")],
    [node("A", "B"), node("B", "A")],
    [node("A", "missing")],
  ];
  const legacy = JSON.parse(execFileSync(process.env.PYTHON || "python",
    ["tests/legacy_fixture.py", "--dag"], { encoding: "utf8", input: JSON.stringify(cases) }));
  const current = cases.map((nodes) => {
    const result = analyzeDag(nodes);
    if (result.status === "invalid") return null;
    return {
      order: result.order,
      ancestry: Object.fromEntries([...result.ancestry].map(([id, entries]) => [id, [...entries].sort()])),
    };
  });
  assert.deepEqual(current, legacy);
});

test("matches authoritative Supervisor admission for capacity, backoff, blocking and transitive prerequisites", () => {
  const nodes = [node("review", "edit"), node("qa", "review"), node("edit"), node("other")];
  const row = (id: string, state: RunState, availableAt = 0): [string, { state: RunState; availableAt: number }] =>
    [id, { state, availableAt }];
  const cases = [
    { rows: [row("edit", "QUEUED"), row("other", "QUEUED")], active: [], workers: 1, expected: ["edit"] },
    { rows: [row("edit", "QUEUED"), row("other", "QUEUED")], active: ["edit"], workers: 2, expected: ["other"] },
    { rows: [row("edit", "SUCCEEDED"), row("review", "RETRY_WAIT", 11), row("other", "QUEUED")],
      active: [], workers: 3, expected: ["other"] },
    { rows: [row("edit", "SUCCEEDED"), row("review", "RETRY_WAIT", 10), row("other", "QUEUED")],
      active: [], workers: 3, expected: ["other", "review"] },
    { rows: [row("edit", "RUNNING"), row("review", "SUCCEEDED"), row("qa", "QUEUED")],
      active: [], workers: 3, expected: [] },
    ...(["FAILED", "AWAITING_TOOL"] as const).map((blocked) => ({
      rows: [row("edit", blocked), row("other", "QUEUED")], active: [], workers: 3, expected: [],
    })),
  ].map((entry) => {
    const recorded = new Map(nodes.map(({ id }) => row(id, "PREPARING")));
    for (const [id, state] of entry.rows) recorded.set(id, state);
    return { ...entry, nodes, now: 10, rows: [...recorded] };
  });
  const python = JSON.parse(execFileSync(process.env.PYTHON || "python",
    ["tests/legacy_fixture.py", "--admission"], { encoding: "utf8", input: JSON.stringify(cases) }));
  const graph = analyzeDag(nodes);
  assert(graph.status === "valid");
  const current = cases.map(({ rows, active, now, workers }) =>
    readyTasks(graph, new Map(rows), new Set(active), now, workers));
  assert.deepEqual(current, cases.map(({ expected }) => expected));
  assert.deepEqual(current, python);
});
