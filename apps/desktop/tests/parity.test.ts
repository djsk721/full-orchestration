import assert from "node:assert/strict";
import { test } from "node:test";
import { execFileSync } from "node:child_process";
import { parseRegistry, validatePlan } from "../core/configuration";
import { rankRoutes } from "../core/execution";

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

test("real Python configuration/plan validation and candidate ranking agree across the common contract", () => {
  const repo = process.cwd();
  const style = process.platform === "win32" ? "windows" : "posix";
  const cases = [
    { config, plan: request(repo, [node("read")]) },
    { config, plan: request(repo, [node("read", { tools: ["files__read"] })]) },
    { config, plan: request(repo, [node("review", { role: "reviewer", min_context: 4096 })]) },
    { config, plan: request(repo, [node("read", { depends: ["unknown"] })]) },
    { config, plan: request(repo, [node("a", { depends: ["b"] }), node("b", { depends: ["a"] })]) },
    { config, plan: request(repo, [node("review", { role: "reviewer", paths: ["src"] })]) },
    { config: { schema_version: 9 }, plan: request(repo, [node("read")]) },
  ];
  const legacy = JSON.parse(execFileSync(process.env.PYTHON || "python", ["tests/legacy_fixture.py", "--policies"],
    { encoding: "utf8", input: JSON.stringify(cases) }));
  const projected = cases.map(({ config, plan }) => {
    try {
      const registry = parseRegistry(config);
      return validatePlan(plan, registry, style).tasks.map((task) => rankRoutes(registry, task).map(({ modelId, harnessId }) => [modelId, harnessId]));
    } catch {
      return null;
    }
  });
  assert.deepEqual(projected, legacy);
  assert.equal(projected.filter((value) => value !== null).length, 3);
});

