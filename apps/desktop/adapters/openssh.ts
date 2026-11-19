import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { isIP } from "node:net";
import { join, resolve } from "node:path";
import { expect, id, object, own, string } from "../core/configuration";
import type { WorkerTransport } from "../core/worker";
import type { ProcessPort } from "./process";
import { nodeProcess } from "./process";
import { readJson } from "./filesystem";

const safeWorkerPath = (value: unknown): value is string => typeof value === "string" && value.length <= 2048 &&
  value.startsWith("/") && !value.split("/").includes("..") && !/[\x00-\x1f]/.test(value);
const quote = (value: string) => "'" + value.replaceAll("'", "'\\''") + "'";

interface LinuxHost {
  host: string;
  user: string;
  port: number;
  timeout: number;
  auth: "agent" | "key" | "agent+key";
  identity?: string;
  directory: string;
  python: string;
}

function profile(value: unknown): LinuxHost {
  const entry = object(value, "SSH profile");
  expect((entry.os ?? "linux") === "linux", "SSH profile OS", "the Worker runs on Linux");
  const host = string(entry.host, "SSH host");
  expect(isIP(host) || /^[a-zA-Z0-9][a-zA-Z0-9.-]{0,251}$/.test(host), "SSH host", "expected a single host");
  const user = string(entry.user, "SSH user");
  expect(/^[a-zA-Z0-9_][a-zA-Z0-9_.@\\-]{0,127}$/.test(user), "SSH user", "invalid account name");
  const port = entry.port ?? 22;
  const timeout = entry.timeout ?? 8;
  const auth = entry.auth ?? "agent";
  expect(typeof port === "number" && Number.isInteger(port) && port >= 1 && port <= 65535, "SSH port", "invalid port");
  expect(typeof timeout === "number" && Number.isInteger(timeout) && timeout >= 1 && timeout <= 60, "SSH timeout", "invalid timeout");
  expect(auth === "agent" || auth === "key" || auth === "agent+key", "SSH authentication", "expected public key authentication");
  const identity = auth !== "agent" ? string(entry.identity, "SSH key path") : undefined;
  expect(!identity || !/[\x00-\x1f]/.test(identity), "SSH key path", "invalid identity path");
  const directory = entry.worker_dir;
  const python = entry.python || "python3";
  expect(safeWorkerPath(directory), "Worker directory", "expected an absolute Linux path");
  expect(typeof python === "string" && (safeWorkerPath(python) || /^python[0-9.]{0,8}$/.test(python)),
    "Worker Python", "invalid interpreter");
  return { host, user, port, timeout, auth, identity, directory, python };
}

function pinContents(source: string, label: string): string {
  const fields = source.trim().split(/\s+/);
  const [host, algorithm, material] = fields;
  expect(fields.length === 3 && host === label && typeof algorithm === "string" && typeof material === "string" &&
    /^(?:ssh-ed25519|ecdsa-sha2-nistp(?:256|384|521)|ssh-rsa)$/.test(algorithm) &&
    /^[a-zA-Z0-9+/]+={0,2}$/.test(material), "SSH host key", "an existing trusted key for this host is required");
  return "SHA256:" + createHash("sha256").update(Buffer.from(material, "base64")).digest("base64").replace(/=+$/, "");
}

/** Uses the same operator-pinned host file as Python. This transport never scans or accepts a new key. */
export async function openSshWorker(root: string, hostId: string, runner = nodeProcess): Promise<WorkerTransport> {
  const key = id(hostId, "host profile ID");
  const workspace = object(await readJson(join(root, "workspace.json")), "workspace");
  expect((workspace.schema_version ?? 1) === 1, "workspace schema", "unsupported version");
  const hosts = object(workspace.hosts, "workspace hosts");
  expect(own(hosts, key), "host profile ID", "profile does not exist");
  const host = profile(hosts[key]);
  const pin = resolve(root, "ssh", key + ".hosts");
  const label = host.port === 22 ? host.host : "[" + host.host + "]:" + host.port;
  const expectedPin = pinContents(await readFile(pin, "ascii"), label);
  const knownHosts = pin.replaceAll("\\", "/").replaceAll("%", "%%").replaceAll('"', '\\"');
  const options = [
    "StrictHostKeyChecking=yes", `UserKnownHostsFile="${knownHosts}"`, "GlobalKnownHostsFile=none", "UpdateHostKeys=no",
    "ForwardAgent=no", "ClearAllForwardings=yes", "ProxyCommand=none", "ProxyJump=none",
    "PasswordAuthentication=no", "KbdInteractiveAuthentication=no", "PreferredAuthentications=publickey",
    `ConnectTimeout=${host.timeout}`, "ServerAliveInterval=10", "ServerAliveCountMax=3", "BatchMode=yes",
  ];
  const argv = ["-F", "none", ...options.flatMap((option) => ["-o", option])];
  if (host.identity) argv.push("-o", "IdentitiesOnly=yes", "-i", host.identity);
  if (host.auth === "key") argv.push("-o", "IdentityAgent=none");
  argv.push("-T", "-p", String(host.port), "-l", host.user, "--", host.host,
    `cd -- ${quote(host.directory)} && exec ${quote(host.python)} -m orchestra.remote`);

  return {
    async exchange(input) {
      expect(pinContents(await readFile(pin, "ascii"), label) === expectedPin, "SSH host key", "trusted key changed since connection setup");
      const result = await runner.execute({ command: "ssh", argv, input, timeoutMs: Math.max(45, host.timeout + 3) * 1000, limitBytes: 2_000_000 });
      if (result.code !== 0) {
        const error = result.stderr.toLowerCase();
        if (/host key verification failed|remote host identification has changed|no matching host key/.test(error)) {
          throw new Error("SSH host key does not match the trusted pin");
        }
        if (error.includes("permission denied")) throw new Error("SSH public-key authentication failed");
        throw new Error("SSH Worker request failed");
      }
      return result.stdout;
    },
  };
}
