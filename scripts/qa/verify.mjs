import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { desktopPackage, withDisplay } from "./platform.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const args = new Set(process.argv.slice(2));
if ([...args].some((arg) => !["--core-only", "--package-only", "--ui", "--ssh", "--package", "--harness"].includes(arg)) ||
    ((args.has("--core-only") || args.has("--package-only")) && args.size > 1)) {
  console.error("Usage: npm run verify -- [--core-only | --package-only | [--ui] [--package] [--ssh] [--harness]]");
  process.exit(2);
}
const npmCli = process.env.npm_execpath;
if (!npmCli) {
  console.error("Start the suite with npm run verify.");
  process.exit(2);
}
const cpuEnvironment = { ...process.env, LIBGL_ALWAYS_SOFTWARE: "1" };
const python = process.env.PYTHON || "python";

function run(label, executable, args, { display = false, extra = {} } = {}) {
  console.log(`\n${label} [${process.platform}]`);
  const [command, commandArgs] = display ? withDisplay(executable, args) : [executable, args];
  const result = spawnSync(command, commandArgs, {
    cwd: root, env: { ...cpuEnvironment, ...extra }, stdio: "inherit", windowsHide: !display,
  });
  if (result.error) console.error(result.error.message);
  if (result.status !== 0) process.exit(result.status || 1);
}
function npm(label, args, options) {
  run(label, process.execPath, [npmCli, ...args], options);
}

npm("Strict TypeScript build", ["run", "build"]);
if (args.has("--core-only")) {
  run("Portable orchestration tests without Python, desktop, network, or native execution",
    process.execPath, ["--test", "apps/desktop/build/main/tests/domain.test.js"]);
  process.exit(0);
}
if (!args.has("--package-only")) {
  npm("TypeScript contracts, Python parity and adapter tests", ["test"]);
  run("Python regression and native adapter contracts", python, ["-m", "unittest", "discover", "-s", "tests", "-v"]);
}
if (args.has("--ui")) {
  npm("Electron UI from source", ["run", "test:e2e"], { display: true });
  const koreanTk = { display: true, extra: { ORCHESTRA_LANG: "ko" } };
  run("Tk UI and native terminal", python, ["tests/smoke_workspace_ui.py"], koreanTk);
  run("Tk project, Provider, Agent, QA and Git integration", python, ["tests/smoke_workspace_flow.py"], koreanTk);
  const workspaceArgs = args.has("--ssh") && process.platform === "linux" ? ["--ssh"] : [];
  run("Tk integrated workspace with real PTY sessions", python, ["tests/smoke_integrated_workspace.py", ...workspaceArgs], koreanTk);
  run("Tk workspace localization and compact layout", python, ["tests/smoke_workspace_localization.py"], { display: true });
  run("Tk first-run Git, Provider discovery and terminal launch", python, ["tests/smoke_workspace_onboarding.py"], koreanTk);
  run("Tk clean profile through language selection and first approval", python, ["tests/smoke_workspace_first_run.py"], { display: true });
}
if (args.has("--ssh")) {
  if (process.platform === "linux") {
    run("Live loopback SSH and headless Worker from Python and TypeScript",
      python, ["tests/smoke_workspace_ssh.py", "--typescript"]);
  } else {
    console.log(`\nLive loopback SSH [${process.platform}]: NOT VERIFIED (requires a local Linux sshd fixture).`);
  }
}
if (args.has("--harness")) {
  run("Optional installed Harness startup and authentication inventory", python, ["scripts/qa/harness_inventory.py"]);
  run("Installed OpenCode with a scripted loopback API", python, ["tests/smoke_installed_opencode.py"]);
  run("Multi-agent Supervisor pipeline with installed OpenCode and loopback models", python, ["tests/smoke_multi_agent_orchestration.py"]);
}
if (args.has("--package") || args.has("--package-only")) {
  const packaging = desktopPackage(root);
  npm("Native Electron packaging", ["run", packaging.script]);
  npm("Packaged Electron UI", ["run", "test:e2e"], {
    display: true, extra: { ORCHESTRA_PREVIEW_EXECUTABLE: packaging.executable() },
  });
  if (packaging.image) {
    npm("Electron AppImage extract-and-run", ["run", "test:e2e"], {
      display: true, extra: { APPIMAGE_EXTRACT_AND_RUN: "1", ORCHESTRA_PREVIEW_EXECUTABLE: packaging.image() },
    });
  }
}
