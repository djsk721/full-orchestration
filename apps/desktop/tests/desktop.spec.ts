import { expect, test, _electron as electron } from "@playwright/test";
import { execFileSync, spawn } from "node:child_process";
import { once } from "node:events";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function launch(directory: string, profileDirectory = join(directory, "browser-profile"), useDefaultData = false) {
  const executablePath = process.env.ORCHESTRA_PREVIEW_EXECUTABLE;
  const software = ["--disable-gpu", "--disable-gpu-compositing", `--user-data-dir=${profileDirectory}`];
  const options = executablePath ? { args: software, executablePath } : { args: [...software, "."] };
  const env = { ...process.env, ORCHESTRA_DATA: directory };
  if (useDefaultData) delete env.ORCHESTRA_DATA;
  return electron.launch({ ...options, env });
}

const installerData = process.env.ORCHESTRA_INSTALLER_DATA;
if (installerData) {
  test("the installed app opens retained execution history and leaves it untouched", async ({}, testInfo) => {
    const database = join(installerData, "state.db");
    const before = readFileSync(database);
    const app = await launch(installerData, testInfo.outputPath("installer-browser-profile"), process.platform === "win32");
    try {
      const window = await app.firstWindow();
      await window.getByRole("button", { name: /문서 verification/ }).click();
      await expect(window.getByText("Check 1 · exit code 0")).toBeVisible();
    } finally {
      await app.close();
    }
    expect(readFileSync(database)).toEqual(before);
  });
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
    const tasks = window.getByRole("searchbox", { name: "Search tasks" });
    await tasks.fill("not a task");
    await expect(window.getByText("No tasks match this search.")).toBeVisible();
    await tasks.fill("qa");
    await expect(window.getByText("Depends on review")).toBeVisible();
    await tasks.clear();
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
    await window.getByRole("searchbox", { name: "Search job history" }).fill("missing title");
    await expect(window.getByText("No jobs match these filters.")).toBeVisible();
    await window.getByRole("searchbox", { name: "Search job history" }).fill("문서");
    await expect(job).toBeVisible();
    await window.getByRole("searchbox", { name: "Search job history" }).fill(id);
    await window.getByLabel("Job state").selectOption("AWAITING_APPROVAL");
    await expect(job).toBeVisible();
    const setVersion = (version: number) => execFileSync(python, ["-c",
      "import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); db.execute('PRAGMA user_version='+sys.argv[2]); db.close()",
      database, String(version)]);
    setVersion(2);
    await expect(window.getByRole("status")).toContainText("Showing the last loaded snapshot");
    const cached = window.getByText(/Cached snapshot from/).locator("time");
    const lastGood = await cached.getAttribute("datetime");
    expect(lastGood).toBeTruthy();
    await expect(window.getByText("qa.followup")).toBeVisible();
    await window.getByRole("searchbox", { name: "Search job history" }).clear();
    await expect(cached).toHaveAttribute("datetime", lastGood!);
    setVersion(0);
    await expect(window.getByRole("status")).toHaveCount(0);
    const current = window.getByText(/Last refreshed/).locator("time");
    await expect(current).not.toHaveAttribute("datetime", lastGood!);
    execFileSync(python, [fixture, directory, "--qa-failure"]);
    await window.getByLabel("Job state").selectOption("FAILED");
    await expect(job).toHaveCount(0);
    await expect(window.getByRole("button", { name: /Integration failure fixture/ })).toBeVisible();
    await window.getByLabel("Job state").selectOption("AWAITING_APPROVAL");
    if (!process.env.ORCHESTRA_PREVIEW_EXECUTABLE && process.env.ORCHESTRA_QA_SCREENSHOT) {
      await window.screenshot({ path: process.env.ORCHESTRA_QA_SCREENSHOT });
    }
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
    const app = await launch(missingPath, join(directory, "browser-profile"));
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
