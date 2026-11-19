import { expect, test, _electron as electron } from "@playwright/test";
import { execFileSync, spawn } from "node:child_process";
import { once } from "node:events";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function launch(directory: string) {
  const executablePath = process.env.ORCHESTRA_PREVIEW_EXECUTABLE;
  const software = ["--disable-gpu", "--disable-gpu-compositing"];
  const options = executablePath ? { args: software, executablePath } : { args: [...software, "."] };
  return electron.launch({ ...options, env: { ...process.env, ORCHESTRA_DATA: directory } });
}

test("shows legacy history, workflow, QA evidence and updates without exposing mutation IPC", async () => {
  const directory = mkdtempSync(join(tmpdir(), "orchestra-electron-"));
  const python = process.env.PYTHON || "python";
  const fixture = join("tests", "legacy_fixture.py");
  let app;
  try {
    const { id } = JSON.parse(execFileSync(python, [fixture, directory], { encoding: "utf8" }));
    const database = join(directory, "state.db");
    const before = readFileSync(database);
    app = await launch(directory);
    const window = await app.firstWindow();
    await expect(window.getByRole("heading", { name: "Model Orchestration" })).toBeVisible();
    const job = window.getByRole("button", { name: /문서 verification/ });
    await expect(job).toBeVisible();
    await job.focus();
    await window.keyboard.press("Enter");
    await expect(window.getByRole("heading", { name: "Workflow dependencies" })).toBeVisible();
    await expect(window.getByText("Depends on review")).toBeVisible();
    await expect(window.getByText("Check 1 · exit code 0")).toBeVisible();
    await expect(window.getByText("qa.result")).toBeVisible();
    await expect(window.getByText("a".repeat(40))).toBeVisible();
    const exposure = await window.evaluate(async () => {
      const globals = window as unknown as { orchestration: { snapshot: (id: string) => Promise<unknown> } };
      let invalidRejected = false;
      try {
        await globals.orchestration.snapshot("../state.db");
      } catch {
        invalidRejected = true;
      }
      return {
        api: Object.keys(globals.orchestration),
        nodeRequire: typeof (window as unknown as { require?: unknown }).require,
        deniedWindow: window.open("about:blank") === null,
        invalidRejected,
      };
    });
    expect(exposure).toEqual({ api: ["snapshot"], nodeRequire: "undefined", deniedWindow: true, invalidRejected: true });
    expect(readFileSync(database)).toEqual(before);

    execFileSync(python, [fixture, directory, id]);
    await expect(window.getByText("qa.followup")).toBeVisible();
    await app.close();
    app = await launch(directory);
    const reopened = await app.firstWindow();
    await reopened.getByRole("button", { name: /문서 verification/ }).click();
    await expect(reopened.getByText("qa.followup")).toBeVisible();
  } finally {
    await app?.close();
    rmSync(directory, { recursive: true, force: true });
  }
});

test("shows first-run instructions without creating a legacy store", async () => {
  const directory = mkdtempSync(join(tmpdir(), "orchestra-electron-empty-"));
  const missingPath = join(directory, "not-created");
  try {
    const app = await launch(missingPath);
    try {
      const window = await app.firstWindow();
      await expect(window.getByRole("status")).toHaveText(/No legacy data found/);
      expect(existsSync(missingPath)).toBe(false);
    } finally {
      await app.close();
    }
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("shows failure evidence from a real Python QA exit without an approval candidate", async () => {
  const directory = mkdtempSync(join(tmpdir(), "orchestra-electron-qa-"));
  try {
    execFileSync(process.env.PYTHON || "python", ["tests/legacy_fixture.py", directory, "--qa-failure"]);
    const app = await launch(directory);
    try {
      const window = await app.firstWindow();
      await window.getByRole("button", { name: /Integration failure fixture/ }).click();
      await expect(window.getByText("Check 1 · exit code 7")).toBeVisible();
      await expect(window.getByText("No integration QA results.")).toHaveCount(0);
      await expect(window.getByText(/^Candidate/)).toHaveCount(0);
    } finally {
      await app.close();
    }
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("a forcibly closed Electron cannot interrupt a running Python Supervisor", async () => {
  const directory = mkdtempSync(join(tmpdir(), "orchestra-electron-detach-"));
  const python = process.env.PYTHON || "python";
  const title = "Independent Supervisor run";
  let app;
  let supervisor;
  try {
    execFileSync(python, ["tests/legacy_fixture.py", directory, "--running"]);
    app = await launch(directory);
    const window = await app.firstWindow();
    await window.getByRole("button", { name: new RegExp(title) }).click();
    supervisor = spawn(python, [join("..", "..", "ModelOrchestration.pyw"), "--supervisor"], {
      env: { ...process.env, ORCHESTRA_DATA: directory }, stdio: "ignore", windowsHide: true,
    });
    await once(supervisor, "spawn");
    await expect(window.getByRole("article").getByText("verifying", { exact: true })).toBeVisible();
    await expect.poll(() => existsSync(join(directory, "started"))).toBe(true);

    const electronProcess = app.process();
    const exit = once(electronProcess, "exit");
    expect(electronProcess.kill("SIGKILL")).toBe(true);
    await exit;
    app = undefined;
    writeFileSync(join(directory, "release"), "");
    await expect.poll(() => {
      const status = join(directory, "supervisor.json");
      return existsSync(status) ? JSON.parse(readFileSync(status, "utf8")).pid : null;
    }).toBe(supervisor.pid);

    app = await launch(directory);
    const reopened = await app.firstWindow();
    await reopened.getByRole("button", { name: new RegExp(title) }).click();
    await expect(reopened.getByRole("article").getByText("succeeded", { exact: true })).toBeVisible();
    await expect(reopened.getByText("Check 1 · exit code 0")).toBeVisible();
    await expect(reopened.getByText("qa · succeeded · attempt 1")).toBeVisible();
  } finally {
    await app?.close();
    if (supervisor?.pid && supervisor.exitCode === null && supervisor.signalCode === null) {
      const exit = once(supervisor, "exit");
      writeFileSync(join(directory, "release"), "");
      writeFileSync(join(directory, "supervisor.stop"), "");
      const force = setTimeout(() => supervisor?.kill("SIGKILL"), 5000);
      try {
        await exit;
      } finally {
        clearTimeout(force);
      }
    }
    rmSync(directory, { recursive: true, force: true });
  }
});
