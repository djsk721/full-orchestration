import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { nodeProcess } from "../adapters/process";
import { openSshWorker } from "../adapters/openssh";
import { WorkerClient } from "../core/worker";

test("Node process adapter sends stdin without a shell and separates diagnostics", async () => {
  const value = "argument $ ; & with spaces";
  const result = await nodeProcess.execute({ command: process.execPath,
    argv: ["-e", "const fs=require('node:fs'); console.log(process.argv[1],fs.readFileSync(0,'utf8')); console.error('diagnostic')", value],
    input: "request-body", timeoutMs: 10_000, limitBytes: 1024 });
  assert.equal(result.code, 0);
  assert.equal(result.stdout.trim(), value + " request-body");
  assert.equal(result.stderr.trim(), "diagnostic");
});

test("Node direct requests enforce real process timeouts and output bounds", async () => {
  await assert.rejects(nodeProcess.execute({ command: process.execPath, argv: ["-e", "setTimeout(()=>{},5000)"],
    timeoutMs: 100, limitBytes: 1024 }), /timed out/);
  await assert.rejects(nodeProcess.execute({ command: process.execPath, argv: ["-e", "console.log('a'.repeat(5000))"],
    timeoutMs: 10_000, limitBytes: 256 }), /limit/);
});

test("OpenSSH adapter binds a saved pin, uses safe argv, and rejects pin rotation before the next request", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "orchestra ssh adapter "));
  t.after(() => rm(root, { recursive: true, force: true }));
  const key = join(root, "ssh", "fixture.hosts");
  await mkdir(join(root, "ssh"));
  await writeFile(join(root, "workspace.json"), JSON.stringify({ schema_version: 1, hosts: {
    fixture: { host: "example.invalid", user: "operator", port: 2200, worker_dir: "/srv/a b's", os: "linux", auth: "agent" },
  } }));
  const runner = { async execute(options: Parameters<typeof nodeProcess.execute>[0]) {
    assert.equal(options.command, "ssh");
    assert.equal(options.argv[1], "none");
    assert(options.argv.includes("StrictHostKeyChecking=yes"));
    assert(options.argv.includes("ForwardAgent=no"));
    assert.equal(options.argv.at(-1), "cd -- '/srv/a b'\\''s' && exec 'python3' -m orchestra.remote");
    assert.equal(JSON.parse(options.input!).method, "info");
    return { code: 0, stderr: "test banner", stdout: '{"version":1,"ok":true,"result":{"os":"Linux","heartbeat":null,"repos":["/repo"],"models":{}}}' };
  } };
  await assert.rejects(openSshWorker(root, "fixture", runner), /ENOENT/);
  await writeFile(key, "[example.invalid]:2200 ssh-ed25519 " + Buffer.from("original").toString("base64"));
  const worker = new WorkerClient(await openSshWorker(root, "fixture", runner));
  assert.equal((await worker.info()).registeredProjects, 1);
  await writeFile(key, "[example.invalid]:2200 ssh-ed25519 " + Buffer.from("changed").toString("base64"));
  await assert.rejects(worker.info(), /changed/);
});
