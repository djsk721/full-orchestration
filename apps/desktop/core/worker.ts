import { expect, isObject, object, string } from "./configuration";
import { isRunState } from "./execution";
import type { RunState } from "./execution";

export interface WorkerTransport {
  exchange(request: string): Promise<string>;
}
const version = 1;
const requestBytes = 400_000;
const responseBytes = 2_000_000;
const bytes = new TextEncoder();
export const runIdPattern = /^[a-f0-9]{32}$/;

export function validRunId(value: unknown): value is string {
  return typeof value === "string" && value.length === 32 && runIdPattern.test(value);
}
export interface WorkerEvent {
  seq: number;
  event_type: string;
  timestamp: number;
  task_id: string | null;
}
export interface WorkerObservation {
  id: string;
  state: RunState;
  heartbeat: number | null;
  events: WorkerEvent[];
  nextCursor: number;
}

export class WorkerRemoteError extends Error {}

export class WorkerClient {
  constructor(private readonly transport: WorkerTransport) {}

  private async request(method: "info" | "status", params: Record<string, unknown>): Promise<unknown> {
    const request = JSON.stringify({ version, method, params });
    expect(bytes.encode(request).length <= requestBytes, "worker request", "size limit exceeded");
    const raw = await this.transport.exchange(request);
    expect(bytes.encode(raw).length <= responseBytes, "worker response", "size limit exceeded");
    const response = object(JSON.parse(raw) as unknown, "worker response");
    expect(response.version === version, "worker version", "incompatible protocol");
    if (response.ok === false) {
      const reason = typeof response.error === "string" ? response.error.slice(0, 250) : "worker rejected request";
      throw new WorkerRemoteError(reason);
    }
    expect(response.ok === true, "worker response.ok", "expected boolean success");
    return response.result;
  }

  async info(): Promise<{ os: string; heartbeat: number | null; registeredProjects: number; modelProfiles: number }> {
    const data = object(await this.request("info", {}), "worker info");
    const os = string(data.os, "worker OS");
    const heartbeat = readHeartbeat(data.heartbeat);
    expect(Array.isArray(data.repos) && data.repos.every((entry) => typeof entry === "string"),
      "worker repositories", "invalid inventory");
    expect(isObject(data.models), "worker models", "invalid inventory");
    return { os, heartbeat, registeredProjects: data.repos.length, modelProfiles: Object.keys(data.models).length };
  }

  async status(job: string, after = 0): Promise<WorkerObservation> {
    expect(validRunId(job), "worker job ID", "invalid run ID");
    expect(Number.isSafeInteger(after) && after >= 0, "worker cursor", "invalid cursor");
    const data = object(await this.request("status", { job, after }), "worker status");
    expect(data.id === job && isRunState(data.state), "worker status", "identity or state mismatch");
    expect(Array.isArray(data.events) && data.events.length <= 150, "worker events", "invalid event page");
    let cursor = after;
    const events = data.events.map((value): WorkerEvent => {
      const event = object(value, "worker event");
      expect(event.run_id === job && typeof event.seq === "number" && Number.isSafeInteger(event.seq) && event.seq > cursor,
        "worker event", "event identity or order mismatch");
      expect(typeof event.timestamp === "number" && Number.isFinite(event.timestamp) && event.timestamp >= 0,
        "worker event time", "invalid Unix timestamp");
      expect(event.task_id === null || typeof event.task_id === "string", "worker event task", "invalid task");
      cursor = event.seq;
      return { seq: cursor, event_type: string(event.event_type, "worker event type"),
        timestamp: event.timestamp, task_id: event.task_id };
    });
    return { id: job, state: data.state, heartbeat: readHeartbeat(data.heartbeat), events, nextCursor: cursor };
  }
}

function readHeartbeat(value: unknown): number | null {
  expect(value === null || (typeof value === "number" && Number.isFinite(value) && value >= 0), "worker heartbeat", "invalid timestamp");
  return value;
}
