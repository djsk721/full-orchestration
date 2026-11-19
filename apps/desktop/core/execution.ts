import type { DagAnalysis } from "./dag";
import type { Harness, Registry, Runtime, Task } from "./configuration";
import { expect, isObject, object } from "./configuration";

export interface Route {
  modelId: string;
  providerId: string;
  runtimeId: string | null;
  harnessId: string;
  score: number;
}

export function harnessEligible(harness: Harness, task: Pick<Task, "tools">): boolean {
  return harness.kind === "managed" || (harness.trusted === true && !task.tools?.length);
}

export function attachedExecutionPolicy(harness: Harness, options: { runtimeVerified: boolean; writes: boolean }):
  { allowed: true; readOnly: boolean } | { allowed: false; reason: string } {
  if (harness.kind === "managed") return { allowed: false, reason: "not an attached harness" };
  if (harness.trusted !== true) return { allowed: false, reason: "executable trust is required" };
  if (harness.kind === "codex" && options.runtimeVerified) return { allowed: false, reason: "Codex uses its existing provider environment" };
  if (options.writes && !(harness.kind === "opencode" && options.runtimeVerified && harness.allow_write === true)) {
    return { allowed: false, reason: "worktree writes require a verified writable OpenCode route" };
  }
  if (!options.runtimeVerified && harness.allow_unverified !== true) {
    return { allowed: false, reason: "unverified runtime is disabled" };
  }
  return { allowed: true, readOnly: !options.writes };
}

export function rankRoutes(registry: Registry, task: Task): Route[] {
  const found: Route[] = [];
  for (const [modelId, model] of Object.entries(registry.models)) {
    if ((task.model !== undefined && task.model !== modelId) || (model.roles && !model.roles.includes(task.role))) continue;
    const runtime = model.runtime ? registry.runtimes[model.runtime] : undefined;
    if (runtime && (runtime.context ?? 32768) < (task.min_context ?? 1024)) continue;
    for (const harnessId of new Set(model.harnesses ?? ["managed"])) {
      const harness = registry.harnesses[harnessId];
      if (!harness || (task.harness !== undefined && task.harness !== harnessId) || !harnessEligible(harness, task)) continue;
      const score = (model.quality ?? 0) * 3 + (model.reliability ?? 0) * 2 +
        (task.paths?.length || task.tools?.length ? (model.tool_score ?? 0) * 2 : 0) - (model.cost ?? 0);
      found.push({ modelId, providerId: model.provider, runtimeId: model.runtime ?? null, harnessId, score });
    }
  }
  const compare = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;
  return found.sort((a, b) => b.score - a.score || compare(a.modelId, b.modelId) || compare(a.harnessId, b.harnessId));
}

export function modelCatalog(payload: unknown): { id: string; reportedContext: number | null }[] {
  const response = object(payload, "provider catalog");
  expect(Array.isArray(response.data), "provider catalog.data", "expected a list of models");
  return response.data.flatMap((entry) => {
    if (!isObject(entry) || typeof entry.id !== "string" || !entry.id) return [];
    const context = entry.context_length ?? entry.max_model_len;
    return [{ id: entry.id, reportedContext: typeof context === "number" && Number.isSafeInteger(context) && context > 0 ? context : null }];
  });
}

export function validatedLimits(runtime: Runtime, requestedModel: string, observed: {
  model: string | null; context: number | null; output: number | null; slots: number | null;
}, minimum = 1024): { context: number; maxOutput: number } {
  expect(observed.model === requestedModel, "runtime.model", "observed model does not match");
  expect(observed.context !== null && Number.isSafeInteger(observed.context) && observed.context >= minimum,
    "runtime.context", "observed context is below the requirement or unknown");
  const slots = typeof runtime.slots === "number" ? runtime.slots : 1;
  expect(observed.slots === null ? slots === 1 : Number.isSafeInteger(observed.slots) && observed.slots >= slots,
    "runtime.slots", "observed slots are insufficient");
  const context = Math.min(observed.context, runtime.context ?? 32768);
  const cap = typeof runtime.max_output === "number" ? runtime.max_output : 2048;
  return { context, maxOutput: Math.min(Math.floor(context / 4), cap,
    observed.output && Number.isSafeInteger(observed.output) && observed.output > 0 ? observed.output : Infinity) };
}

export const runStates = ["QUEUED", "PREPARING", "RUNNING", "VERIFYING", "RETRY_WAIT", "AWAITING_TOOL",
  "AWAITING_APPROVAL", "MERGE_QUEUED", "MERGING", "SUCCEEDED", "MERGED", "FAILED", "CANCELLED"] as const;
export type RunState = typeof runStates[number];

export function isRunState(value: unknown): value is RunState {
  return runStates.some((state) => state === value);
}

export function agentStage(job: string, stage: string): string {
  const stale = ["QUEUED", "PREPARING", "RUNNING", "VERIFYING", "AWAITING_TOOL", "RETRY_WAIT"];
  if (!stale.includes(stage)) return stage;
  if (job === "CANCELLED") return "CANCELLED";
  if (job === "FAILED" || job === "SUCCEEDED" || job === "MERGED") return "NOT_EXECUTED";
  return stage;
}

/** A pure scheduling decision on a snapshot. Claiming and lease transactions remain server duties. */
export function readyTasks(graph: Extract<DagAnalysis, { status: "valid" }>, rows: ReadonlyMap<string, {
  state: RunState; availableAt: number;
}>, inFlight: ReadonlySet<string>, now: number, workers: number): string[] {
  if (Array.from(rows.values()).some(({ state }) => state === "FAILED" || state === "AWAITING_TOOL")) return [];
  const capacity = Math.max(0, workers - inFlight.size);
  return graph.order.filter((key) => {
    const task = rows.get(key);
    return task && !inFlight.has(key) && (task.state === "QUEUED" || task.state === "RETRY_WAIT") &&
      task.availableAt <= now && [...(graph.ancestry.get(key) ?? [])].every((dep) => rows.get(dep)?.state === "SUCCEEDED");
  }).slice(0, capacity);
}
