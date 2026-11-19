import { analyzeDag } from "./dag";

export const roles = ["planner", "developer", "explorer", "reviewer", "qa", "diagnostic"] as const;
export type Role = typeof roles[number];
export type JsonObject = Record<string, unknown>;
export type PathStyle = "posix" | "windows";
export type HarnessKind = "managed" | "opencode" | "codex";
type Profile<Kind extends string> = JsonObject & { kind: Kind };
export type Harness = Profile<HarnessKind>;
export interface Model extends JsonObject {
  provider: string;
  model: string;
  runtime?: string;
  roles?: Role[];
  harnesses?: string[];
  quality?: number;
  reliability?: number;
  tool_score?: number;
  cost?: number;
}
export type Runtime = Profile<"llama.cpp" | "ollama" | "openai-compatible"> & { context?: number };
export type Provider = Profile<"local" | "attached">;
export interface Registry {
  schema_version: 1;
  settings: typeof defaultSettings;
  models: Record<string, Model>;
  providers: Record<string, Provider>;
  runtimes: Record<string, Runtime>;
  harnesses: Record<string, Harness>;
  mcp: Record<string, JsonObject>;
}
export interface Task extends JsonObject {
  id: string;
  role: Role;
  prompt: string;
  acceptance: string;
  depends?: string[];
  tools?: string[];
  paths?: string[];
  read_paths?: string[];
  qa?: string[][];
  model?: string;
  harness?: string;
  min_context?: number;
}
export interface Plan extends JsonObject {
  title: string;
  target: string;
  repo: string;
  tasks: Task[];
  background?: boolean;
  qa?: string[][];
}

export class ValidationError extends Error {
  constructor(readonly field: string, message: string) {
    super(`${field}: ${message}`);
    this.name = "ValidationError";
  }
}

export function expect(condition: unknown, field: string, message: string): asserts condition {
  if (!condition) throw new ValidationError(field, message);
}

export function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function object(value: unknown, field: string): JsonObject {
  expect(isObject(value), field, "expected an object");
  return value;
}

export function own(object: object, key: string): boolean {
  return Object.hasOwn(object, key);
}

export function string(value: unknown, field: string): string {
  expect(typeof value === "string" && value.length > 0, field, "expected a nonempty string");
  return value;
}

function texts(value: unknown, field: string): string[] {
  expect(Array.isArray(value), field, "expected an array");
  return value.map((item, index) => string(item, `${field}[${index}]`));
}

export function id(value: unknown, field: string): string {
  const result = string(value, field);
  expect(/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$/.test(result) && !result.endsWith("\n") && !result.endsWith("\r"),
    field, "invalid profile or task ID");
  return result;
}

export function isRole(value: unknown): value is Role {
  return roles.some((role) => role === value);
}

function integer(value: unknown, field: string, low: number, high: number): void {
  expect(typeof value === "number" && Number.isSafeInteger(value) && value >= low && value <= high,
    field, `expected an integer from ${low} to ${high}`);
}

function flag(value: unknown, field: string): void {
  expect(typeof value === "boolean", field, "expected a boolean");
}

function optional(source: JsonObject, key: string, fallback: unknown): unknown {
  return own(source, key) ? source[key] : fallback;
}

function member(value: unknown, values: readonly string[], field: string): void {
  expect(values.some((candidate) => candidate === value), field, `expected one of ${values.join(", ")}`);
}

const defaultSettings = {
  background: false, parallel_jobs: 2, parallel_tasks: 3, heartbeat_sec: 15, lease_sec: 90,
  job_timeout_sec: 14400, attempts: 2, allow_background_write: false, notifications: false,
  gpu_budget_mb: 0, ram_budget_mb: 0, gateway_port: 8767,
};
const settingRanges = {
  parallel_jobs: [1, 16], parallel_tasks: [1, 16], heartbeat_sec: [1, 120], lease_sec: [4, 3600],
  job_timeout_sec: [1, 86400], attempts: [1, 5], gpu_budget_mb: [0, 2097152], ram_budget_mb: [0, 2097152],
  gateway_port: [1024, 65535],
} as const;
const runtimeRanges = {
  context: [32768, 1024, 2097152], max_output: [2048, 32, 131072],
  slots: [1, 1, 32], gpu_mb: [0, 0, 2097152], ram_mb: [0, 0, 2097152], gpu_layers: [0, 0, 999],
} as const;
const sections = ["providers", "runtimes", "models", "harnesses", "mcp"] as const;
const envName = /^[A-Z_][A-Z0-9_]*$/i;

function reference(map: object, value: unknown, field: string): string {
  const key = id(value, field);
  expect(own(map, key), field, "referenced profile does not exist");
  return key;
}

function validateMcp(entry: JsonObject, field: string): void {
  member(entry.transport, ["http", "stdio"], `${field}.transport`);
  if (entry.transport === "http") string(entry.url, `${field}.url`);
  else {
    expect(texts(entry.command, `${field}.command`).length > 0, `${field}.command`, "expected argv");
    texts(optional(entry, "env", []), `${field}.env`);
  }
  for (const key of ["headers", "token", "api_key", "secret"]) {
    expect(!own(entry, key), `${field}.${key}`, "use a secret reference instead");
  }
  const fields = object(optional(entry, "header_env", {}), `${field}.header_env`);
  for (const [name, value] of Object.entries(fields)) {
    expect(/^[a-zA-Z0-9_-]+$/.test(name), field, "invalid header name");
    expect(typeof value === "string" && envName.test(value), field, "invalid environment reference");
  }
  if (own(entry, "gateway_token_env")) {
    expect(typeof entry.gateway_token_env === "string" && envName.test(entry.gateway_token_env), field,
      "invalid gateway credential reference");
  }
  for (const [key, value] of Object.entries(object(optional(entry, "tools", {}), `${field}.tools`))) {
    const path = `${field}.tools.${key}`;
    const rule = object(value, path);
    member(rule.access, ["read", "write"], `${path}.access`);
    expect(texts(optional(rule, "roles", []), `${path}.roles`).every(isRole), path, "unknown MCP role");
    for (const agent of texts(optional(rule, "agents", []), `${path}.agents`)) {
      const [role, task, extra] = agent.split("/");
      expect(isRole(role) && extra === undefined, path, "expected role/task ID");
      id(task, path);
    }
    flag(optional(rule, "native", false), `${path}.native`);
  }
}

/** Structural validation. Executable, filesystem, and live provider checks belong to the backend. */
export function parseRegistry(value: unknown): Registry {
  const root = object(value, "registry");
  expect(Object.keys(root).every((key) => key === "schema_version" || key === "settings" || sections.some((s) => s === key)),
    "registry", "unknown top-level field");
  const version = optional(root, "schema_version", 0);
  expect(version === 0 || version === 1, "schema_version", "unsupported registry version");
  const settings = { ...defaultSettings, ...object(optional(root, "settings", {}), "settings") };
  expect(Object.keys(settings).every((key) => own(defaultSettings, key)), "settings", "unknown field");
  for (const key of ["background", "allow_background_write", "notifications"] as const) flag(settings[key], key);
  for (const [key, [low, high]] of Object.entries(settingRanges)) integer(settings[key as keyof typeof settings], key, low, high);
  expect(settings.lease_sec >= settings.heartbeat_sec * 3, "settings.lease_sec", "must be at least three heartbeat intervals");

  const defaults: Record<typeof sections[number], JsonObject> = {
    providers: { local: { kind: "local" }, subscription: { kind: "attached" } },
    harnesses: { managed: { kind: "managed", max_rounds: 30 } }, runtimes: {}, models: {}, mcp: {},
  };
  const records = Object.fromEntries(sections.map((section) => [
    section, Object.fromEntries(Object.entries(object(optional(root, section, defaults[section]), section))
      .map(([key, entry]) => [id(key, section), object(entry, `${section}.${key}`)])),
  ])) as Record<typeof sections[number], Record<string, JsonObject>>;

  for (const [key, entry] of Object.entries(records.providers)) member(entry.kind, ["local", "attached"], `providers.${key}.kind`);
  for (const [key, entry] of Object.entries(records.runtimes)) {
    const field = `runtimes.${key}`;
    member(entry.kind, ["llama.cpp", "ollama", "openai-compatible"], `${field}.kind`);
    member(optional(entry, "ownership", "attached"), ["attached", "managed"], `${field}.ownership`);
    for (const [name, [initial, low, high]] of Object.entries(runtimeRanges)) {
      integer(optional(entry, name, initial), `${field}.${name}`, low, high);
    }
    expect(!entry.gpu_layers || entry.gpu_mb, field, "offload requires a memory reservation");
    if (entry.ownership === "managed") {
      expect(entry.kind === "llama.cpp", field, "only llama.cpp has a managed executable");
      string(entry.executable, `${field}.executable`);
      string(entry.model_path, `${field}.model_path`);
    }
  }
  for (const [key, entry] of Object.entries(records.harnesses)) {
    const field = `harnesses.${key}`;
    member(entry.kind, ["managed", "opencode", "codex"], `${field}.kind`);
    if (entry.kind === "managed") integer(optional(entry, "max_rounds", 30), `${field}.max_rounds`, 1, 100);
    else {
      string(entry.executable, `${field}.executable`);
      for (const name of ["trusted", "allow_write", "allow_unverified", "inherit_environment"]) {
        flag(optional(entry, name, false), `${field}.${name}`);
      }
    }
  }
  for (const [key, model] of Object.entries(records.models)) {
    const field = `models.${key}`;
    const providerName = reference(records.providers, model.provider, `${field}.provider`);
    string(model.model, `${field}.model`);
    if (own(model, "runtime")) reference(records.runtimes, model.runtime, `${field}.runtime`);
    const harnesses = texts(optional(model, "harnesses", ["managed"]), `${field}.harnesses`);
    expect(harnesses.length, field, "a harness is required");
    for (const name of harnesses) reference(records.harnesses, name, `${field}.harnesses`);
    expect(model.runtime || (records.providers[providerName]?.kind !== "local" &&
      harnesses.every((name) => records.harnesses[name]?.kind !== "managed")), field, "runtime is required");
    expect(texts(optional(model, "roles", roles), `${field}.roles`).every(isRole), field, "unknown model role");
    for (const name of ["quality", "tool_score", "reliability", "cost"]) integer(optional(model, name, 0), `${field}.${name}`, 0, 100);
    integer(optional(model, "token_budget", 0), `${field}.token_budget`, 0, 1000000000);
  }
  for (const [key, entry] of Object.entries(records.mcp)) validateMcp(entry, `mcp.${key}`);
  // Preserve extension fields in individual profiles. Callers never receive a write authority.
  return { ...records, settings, schema_version: 1 } as Registry;
}

const reserved = /^(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\..*)?$/i;
const invalidPathCharacters = /[<>:"|?*\x00-\x1f\\]/;

export function scopePath(path: string, field: string): void {
  expect(path.split("/").every((part) => part !== "" && part !== "." && part !== ".." &&
    part.toLowerCase() !== ".git" && !/[. ]$/.test(part) && !reserved.test(part) && !invalidPathCharacters.test(part)),
  field, "expected a portable, repository-relative path");
}

function includesScope(path: string, scopes: readonly string[], style: PathStyle): boolean {
  const key = (part: string) => style === "windows" ? part.toLowerCase() : part;
  return scopes.some((scope) => key(path) === key(scope) || key(path).startsWith(key(scope) + "/"));
}

function commands(value: unknown, field: string): void {
  expect(Array.isArray(value), field, "expected an argv array per command");
  value.forEach((row, index) => expect(texts(row, `${field}[${index}]`).length > 0, field, "empty command"));
}

export function validatePlan(value: unknown, registry: Registry, style: PathStyle): Plan {
  const plan = object(value, "plan");
  expect(string(plan.title, "title").trim(), "title", "cannot be whitespace");
  const repo = string(plan.repo, "repo");
  const absolute = style === "windows"
    ? /^(?:[a-z]:[\\/]|[\\/]{2}[^\\/]+[\\/][^\\/]+)/i.test(repo)
    : repo.startsWith("/");
  expect(absolute && !repo.includes("\0"), "repo", "expected an absolute repository location on the execution host");
  expect(!string(plan.target, "target").startsWith("-"), "target", "invalid target branch");
  flag(optional(plan, "background", false), "background");
  expect(!plan.background || registry.settings.background, "background", "background execution is disabled");
  expect(Array.isArray(plan.tasks) && plan.tasks.length > 0 && plan.tasks.length <= 100, "tasks", "expected 1 to 100 tasks");

  const tasks = plan.tasks.map((entry, index) => {
    const field = `tasks[${index}]`;
    const task = object(entry, field);
    const taskId = id(task.id, `${field}.id`);
    expect(!reserved.test(taskId) && !taskId.endsWith("."), field, "reserved task ID");
    expect(isRole(task.role), `${field}.role`, "unknown role");
    expect(string(task.prompt, `${field}.prompt`).trim(), `${field}.prompt`, "cannot be whitespace");
    expect(string(task.acceptance, `${field}.acceptance`).trim(), `${field}.acceptance`, "cannot be whitespace");
    const writes = texts(optional(task, "paths", []), `${field}.paths`);
    for (const path of [...writes, ...texts(optional(task, "read_paths", []), `${field}.read_paths`)]) scopePath(path, field);
    expect(!writes.length || task.role === "developer", `${field}.paths`, "writes require a developer");
    expect(!writes.length || !plan.background || registry.settings.allow_background_write, field, "background writes disabled");
    if (own(task, "model")) reference(registry.models, task.model, `${field}.model`);
    if (own(task, "harness")) reference(registry.harnesses, task.harness, `${field}.harness`);
    expect(texts(optional(task, "tools", []), `${field}.tools`).every((tool) => /^[a-zA-Z0-9_-]{1,64}$/.test(tool)),
      `${field}.tools`, "invalid tool alias");
    integer(optional(task, "min_context", 1024), `${field}.min_context`, 1024, 2097152);
    commands(optional(task, "qa", []), `${field}.qa`);
    return { id: taskId, dependencies: texts(optional(task, "depends", []), `${field}.depends`), writes };
  });

  const analysis = analyzeDag(tasks);
  expect(analysis.status === "valid", "tasks", analysis.status === "invalid" ? `${analysis.node}: ${analysis.reason}` : "");
  for (const [index, first] of tasks.entries()) {
    for (const second of tasks.slice(index + 1)) {
      if (analysis.ancestry.get(first.id)?.has(second.id) || analysis.ancestry.get(second.id)?.has(first.id)) continue;
      expect(!first.writes.some((path) => includesScope(path, second.writes, style)) &&
        !second.writes.some((path) => includesScope(path, first.writes, style)), "tasks", "independent tasks have overlapping write scopes");
    }
  }
  const qa = optional(plan, "qa", []);
  commands(qa, "qa");
  expect(!tasks.some((task) => task.writes.length) || (qa as unknown[]).length, "qa", "file changes require integration QA");
  return plan as Plan;
}
