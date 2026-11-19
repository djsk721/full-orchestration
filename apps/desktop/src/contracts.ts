import { validRunId } from "../core/worker";

export const snapshotChannel = "jobs:snapshot:v1";

export interface SnapshotRequest {
  version: 1;
  jobId: string | null;
}

export interface SnapshotEnvelope {
  version: 1;
  projection: DashboardResponse;
}

export function isSnapshotRequest(value: unknown): value is SnapshotRequest {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const candidate = value as Record<string, unknown>;
  return Object.keys(candidate).length === 2 && Object.hasOwn(candidate, "version") &&
    Object.hasOwn(candidate, "jobId") && candidate.version === 1 &&
    (candidate.jobId === null || validRunId(candidate.jobId));
}

export interface JobSummary {
  id: string;
  title: string;
  state: string;
  background: boolean;
  updatedAt: number;
}

export interface TaskSummary {
  id: string;
  role: string;
  state: string;
  attempt: number;
  dependencies: string[];
}

export interface Activity {
  sequence: number;
  taskId: string | null;
  type: string;
  at: number;
}

export interface QaResult {
  index: number;
  exitCode: number;
}

export interface JobDetail {
  job: JobSummary;
  tasks: TaskSummary[];
  events: Activity[];
  candidate: string | null;
  qa: QaResult[];
}

export interface Dashboard {
  jobs: JobSummary[];
  detail: JobDetail | null;
}

export type DashboardResponse =
  | { status: "ready"; dashboard: Dashboard }
  | { status: "empty" | "unavailable" };

export interface DesktopApi {
  snapshot(jobId: string | null): Promise<DashboardResponse>;
}
