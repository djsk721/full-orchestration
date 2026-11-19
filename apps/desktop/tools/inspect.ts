import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { dataDirectory, readJson } from "../adapters/filesystem";
import { openSshWorker } from "../adapters/openssh";
import { expect, parseRegistry, validatePlan } from "../core/configuration";
import { rankRoutes } from "../core/execution";
import { WorkerClient } from "../core/worker";

async function main(): Promise<void> {
  const [command, first, second, third] = process.argv.slice(2);
  const root = dataDirectory(process.env, process.platform, homedir());
  if (command === "plan") {
    expect(first && (third === "posix" || third === "windows"), "usage", "inspect plan PLAN REGISTRY|- posix|windows");
    const invocation = process.env.INIT_CWD || process.cwd();
    const registry = parseRegistry(await readJson(second && second !== "-" ? resolve(invocation, second) : join(root, "registry.json")));
    const plan = validatePlan(await readJson(resolve(invocation, first)), registry, third);
    const results = plan.tasks.map((task) => ({
      taskId: task.id, candidates: rankRoutes(registry, task),
    }));
    console.log(JSON.stringify({ structuralValidation: "valid", tasks: results }, null, 2));
    return;
  }
  expect(first && (command === "worker-info" || command === "worker-status"), "usage",
    "inspect worker-info PROFILE or worker-status PROFILE JOB [CURSOR]");
  const worker = new WorkerClient(await openSshWorker(root, first));
  if (command === "worker-info") console.log(JSON.stringify(await worker.info()));
  else {
    expect(second, "job ID", "worker-status requires a job ID");
    console.log(JSON.stringify(await worker.status(second, third === undefined ? 0 : Number(third))));
  }
}

void main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : "inspection failed");
  process.exitCode = 1;
});
