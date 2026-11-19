import { spawn } from "node:child_process";

export interface ProcessRequest {
  command: string;
  argv: readonly string[];
  input?: string;
  timeoutMs: number;
  limitBytes: number;
  environment?: NodeJS.ProcessEnv;
  signal?: AbortSignal;
}

export interface ProcessResult {
  code: number | null;
  stdout: string;
  stderr: string;
}

export interface ProcessPort {
  execute(request: ProcessRequest): Promise<ProcessResult>;
}

/** Short, direct, non-interactive requests. Native orchestration process-tree containment stays in Python. */
export const nodeProcess: ProcessPort = {
  execute({ command, argv, input, timeoutMs, limitBytes, environment, signal }) {
    return new Promise((resolve, reject) => {
      if (signal?.aborted) {
        reject(new Error("process request aborted"));
        return;
      }
      const output: Buffer[] = [];
      const errors: Buffer[] = [];
      let size = 0;
      let failure: Error | undefined;
      const child = spawn(command, [...argv], {
        shell: false, windowsHide: true, env: environment, stdio: ["pipe", "pipe", "pipe"],
      });
      function stop(reason: string) {
        failure ??= new Error(reason);
        child.kill("SIGKILL");
      }
      const timeout = setTimeout(() => stop("process request timed out"), timeoutMs);
      const abort = () => stop("process request aborted");
      signal?.addEventListener("abort", abort, { once: true });
      function append(chunk: Buffer, segments: Buffer[]) {
        if (failure) return;
        size += chunk.length;
        if (size > limitBytes) stop("process output exceeded its limit");
        else segments.push(chunk);
      }
      child.stdout.on("data", (chunk: Buffer) => append(chunk, output));
      child.stderr.on("data", (chunk: Buffer) => append(chunk, errors));
      child.stdin.on("error", () => { /* A failed process can close the request pipe early. */ });
      child.on("error", () => { failure ??= new Error("process request could not start"); });
      child.on("close", (code) => {
        clearTimeout(timeout);
        signal?.removeEventListener("abort", abort);
        if (failure) reject(failure);
        else resolve({ code, stdout: Buffer.concat(output).toString("utf8"), stderr: Buffer.concat(errors).toString("utf8") });
      });
      child.stdin.end(input, "utf8");
    });
  },
};
