import assert from "node:assert/strict";
import { test } from "node:test";
import { analyzeDag } from "../core/dag";
import { parseRegistry, validatePlan } from "../core/configuration";
import { agentStage, attachedExecutionPolicy, modelCatalog, rankRoutes, readyTasks, validatedLimits } from "../core/execution";
import { toolDecision, writeDisposition } from "../core/mcp";
import { WorkerClient, WorkerRemoteError } from "../core/worker";
import type { RunState } from "../core/execution";

function node(id: string, additions: Record<string, unknown> = {}): Record<string, unknown> {
  return { id, role: "explorer", prompt: "Inspect the project", acceptance: "Summarize findings", ...additions };
}

const config = {
  runtimes: { fixture: { kind: "openai-compatible", context: 8192 } },
  harnesses: { managed: { kind: "managed" }, cli: { kind: "codex", executable: "codex", trusted: true, allow_unverified: true } },
  models: {
    local: { provider: "local", model: "model-a", runtime: "fixture", harnesses: ["managed"], quality: 7 },
    subscribed: { provider: "subscription", model: "model-b", harnesses: ["cli"], quality: 9, roles: ["explorer"] },
  },
};
const request = (repo: string, tasks: ReturnType<typeof node>[]) => ({ title: "Fixture", target: "main", repo, tasks });

test("registry migration preserves extension fields and rejects invalid references, timeouts, and schema versions", () => {
  const registry = parseRegistry({ ...config, runtimes: { fixture: { ...config.runtimes.fixture, extension: true } } });
  assert.equal(registry.schema_version, 1);
  assert.equal(registry.runtimes.fixture?.extension, true);
  assert.throws(() => parseRegistry({ schema_version: 99 }), /version/);
  assert.throws(() => parseRegistry({ settings: { heartbeat_sec: 60, lease_sec: 90 } }), /lease_sec/);
  assert.throws(() => parseRegistry({ models: { a: { provider: "missing", model: "model" } } }), /provider/);
  assert.throws(() => parseRegistry({ mcp: { a: { transport: "http", url: "https://example.invalid", token: "inline" } } }), /reference/);
});

test("execution-host filesystem semantics, scope boundaries and cross-host path shapes are explicit", () => {
  const cfg = parseRegistry(config);
  const first = node("a", { role: "developer", paths: ["Src"] });
  const second = node("b", { role: "developer", paths: ["src/file.py"] });
  const qa = [["git", "--version"]];
  assert.doesNotThrow(() => validatePlan({ ...request("/repo", [first, second]), qa }, cfg, "posix"));
  assert.throws(() => validatePlan({ ...request("C:\\repo", [first, second]), qa }, cfg, "windows"), /overlapping/);
  assert.doesNotThrow(() => validatePlan({ ...request("\\\\host\\share\\repo", [first, {...second, depends: ["a"]}]), qa }, cfg, "windows"));
  assert.throws(() => validatePlan(request("/repo", [node("nul.txt")]), cfg, "posix"), /reserved/);
  assert.throws(() => validatePlan(request("/repo", [node("a", { read_paths: ["src/../secret"] })]), cfg, "posix"), /relative/);
  assert.throws(() => validatePlan({ ...request("/repo", [first]), qa: [] }, cfg, "posix"), /integration QA/);
});

test("route ranking respects provider roles, context, manual override, and tool policy", () => {
  const registry = parseRegistry(config);
  const make = (additions: Record<string, unknown> = {}) => validatePlan(request("/repo", [node("a", additions)]), registry, "posix").tasks[0]!;
  assert.deepEqual(rankRoutes(registry, make()).map(({ modelId }) => modelId), ["subscribed", "local"]);
  assert.deepEqual(rankRoutes(registry, make({ tools: ["files__read"] })).map(({ modelId }) => modelId), ["local"]);
  assert.deepEqual(rankRoutes(registry, make({ harness: "managed", min_context: 16384 })), []);
  assert.deepEqual(rankRoutes(registry, make({ model: "local" })).map(({ harnessId }) => harnessId), ["managed"]);
});

test("an explicit OpenCode profile must be executable for the requested operation", () => {
  const registry = parseRegistry({
    harnesses: { cli: { kind: "opencode", executable: "opencode", trusted: true, allow_unverified: true } },
    models: { attached: { provider: "subscription", model: "openai/gpt-5.6-luna", harnesses: ["cli"] } },
  });
  const task = validatePlan(request("/repo", [node("a", { model: "attached", harness: "cli" })]), registry, "posix").tasks[0]!;
  assert.equal(rankRoutes(registry, task)[0]?.providerId, "subscription");
  assert.deepEqual(rankRoutes(registry, { ...task, role: "developer", paths: ["a.txt"] }), []);
  registry.models.attached!.cli_model = "--prompt";
  assert.deepEqual(rankRoutes(registry, task), []);
});

test("model limits use observed identity, context and slots; capabilities are not invented", () => {
  const runtime = parseRegistry(config).runtimes.fixture!;
  const valid = { model: "model-a", context: 4096, slots: 1, output: 800 };
  assert.deepEqual(modelCatalog({ data: [{ id: "model-a", max_model_len: 4096 }, { id: "unknown" }, false] }),
    [{ id: "model-a", reportedContext: 4096 }, { id: "unknown", reportedContext: null }]);
  assert.deepEqual(validatedLimits(runtime, "model-a", valid), { context: 4096, maxOutput: 800 });
  assert.throws(() => validatedLimits(runtime, "another", valid), /match/);
  assert.throws(() => validatedLimits(runtime, "model-a", { ...valid, context: null }), /context/);
  assert.throws(() => validatedLimits({ ...runtime, slots: 2 }, "model-a", valid), /slots/);
});

test("attached harness refuses untrusted, unverified or unsupported write profiles", () => {
  const cli = parseRegistry(config).harnesses.cli!;
  assert.deepEqual(attachedExecutionPolicy(cli, { writes: false, runtimeVerified: false }), { allowed: true, readOnly: true });
  assert.equal(attachedExecutionPolicy(cli, { writes: true, runtimeVerified: false }).allowed, false);
  assert.equal(attachedExecutionPolicy({ ...cli, trusted: false }, { writes: false, runtimeVerified: false }).allowed, false);
  assert.deepEqual(attachedExecutionPolicy({ ...cli, kind: "opencode", allow_write: true },
    { writes: true, runtimeVerified: true }), { allowed: true, readOnly: false });
});

test("MCP denies wrong agents, unselected tools and native writes; uncertain writes cannot be replayed", () => {
  const write = { access: "write", roles: ["developer", "reviewer"], agents: ["developer/build"], native: true } as const;
  assert.equal(toolDecision(write, { role: "developer", agent: "developer/build" }), "approval-required");
  assert.equal(toolDecision(write, { role: "developer", agent: "developer/other" }), "deny");
  assert.equal(toolDecision(write, { role: "reviewer", agent: "developer/build" }), "deny");
  assert.equal(toolDecision(write, { native: true, agent: "developer/build" }), "deny");
  assert.equal(toolDecision({ access: "read", native: true }, { native: true, selected: false }), "deny");
  assert.equal(writeDisposition("approved", "started"), "stop-uncertain");
  assert.equal(writeDisposition("approved", "done"), "reuse-result");
  assert.equal(writeDisposition("missing", "missing"), "await-approval");
});

test("DAG admission honors dependencies, capacity, backoff and approval state", () => {
  const graph = analyzeDag([{ id: "a", dependencies: [] }, { id: "b", dependencies: [] }, { id: "c", dependencies: ["a", "b"] }]);
  assert.equal(graph.status, "valid");
  const state = (state: RunState, availableAt = 0) => ({ state, availableAt });
  const rows = new Map([["a", state("RUNNING")], ["b", state("RETRY_WAIT", 20)], ["c", state("QUEUED")]]);
  assert.deepEqual(readyTasks(graph, rows, new Set(["a"]), 19, 2), []);
  assert.deepEqual(readyTasks(graph, rows, new Set(["a"]), 20, 1), []);
  assert.deepEqual(readyTasks(graph, rows, new Set(["a"]), 20, 2), ["b"]);
  rows.set("a", state("SUCCEEDED"));
  rows.set("b", state("AWAITING_TOOL"));
  assert.deepEqual(readyTasks(graph, rows, new Set(), 20, 2), []);
  rows.set("b", state("SUCCEEDED"));
  assert.deepEqual(readyTasks(graph, rows, new Set(), 20, 2), ["c"]);
  assert.equal(agentStage("CANCELLED", "RUNNING"), "CANCELLED");
  assert.equal(agentStage("FAILED", "QUEUED"), "NOT_EXECUTED");
  assert.equal(agentStage("FAILED", "SUCCEEDED"), "SUCCEEDED");
});

test("Worker status can reconnect from the last cursor without resubmission on a lost reply", async () => {
  const id = "a".repeat(32);
  let calls = 0;
  const client = new WorkerClient({
    async exchange(text) {
      const request = JSON.parse(text);
      assert.equal(request.method, "status");
      assert.equal(request.version, 1);
      ++calls;
      if (calls === 2) throw new Error("transport disconnected");
      const after = request.params.after;
      return JSON.stringify({ ok: true, version: 1, result: {
        id, state: "RUNNING", heartbeat: 20, events: [{ run_id: id, seq: after + 2, event_type: "task.state", timestamp: 20, task_id: "a" }],
      } });
    },
  });
  const first = await client.status(id);
  assert.equal(first.nextCursor, 2);
  await assert.rejects(client.status(id, first.nextCursor), /disconnected/);
  const recovered = await client.status(id, first.nextCursor);
  assert.equal(recovered.nextCursor, 4);
  assert.equal(calls, 3);
});

test("Worker protocol rejects foreign and out-of-order events, version drift and remote failures", async () => {
  const id = "a".repeat(32);
  const envelope = (result: unknown) => JSON.stringify({ version: 1, ok: true, result });
  const corrupt = new WorkerClient({ exchange: async () => envelope({ id, state: "RUNNING", heartbeat: null, events: [
    { run_id: id, event_type: "state", timestamp: 5, seq: 8, task_id: null },
    { run_id: id, event_type: "state", timestamp: 6, seq: 7, task_id: null },
  ] }) });
  await assert.rejects(corrupt.status(id), /order/);
  await assert.rejects(new WorkerClient({ exchange: async () => envelope({ id: "b".repeat(32), state: "RUNNING" }) }).status(id), /identity/);
  await assert.rejects(new WorkerClient({ exchange: async () => '{"version":9}' }).info(), /incompatible/);
  await assert.rejects(new WorkerClient({ exchange: async () => '{"version":1,"ok":false,"error":"unavailable"}' }).info(), WorkerRemoteError);
});
