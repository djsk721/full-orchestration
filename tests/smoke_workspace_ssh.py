import argparse
import getpass
import json
import os
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from shutil import which

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestra.core import Invalid
from orchestra.remote import register_project
from orchestra.ssh import SSHClient, fingerprint, scan_keys, ssh_env, trust_key
from orchestra.terminal import Pty
from orchestra.supervisor import read_config
from orchestra.workspace import STRATEGIES, draft_plan, save_registry

parser = argparse.ArgumentParser(description="Verify a headless Worker through a real OpenSSH connection.")
parser.add_argument("--typescript", action="store_true", help="also verify the built TypeScript SSH adapter")
args = parser.parse_args()
source = Path(__file__).resolve().parents[1]

with tempfile.TemporaryDirectory(prefix="orchestra-ssh-qa-") as name:
    root = Path(name)
    repo = root / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "--allow-empty", "-qm", "Fixture"], check=True)
    state = root / "worker"
    project = register_project(state, repo)
    registry = read_config(state)
    registry["settings"].update(heartbeat_sec=1, lease_sec=4)
    save_registry(state, registry)
    for ident in ("host", "operator"):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(root / ident)], check=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    user = getpass.getuser()
    config = root / "sshd_config"
    config.write_text(f"""Port {port}
ListenAddress 127.0.0.1
HostKey {root / 'host'}
AuthorizedKeysFile {root / 'operator.pub'}
PidFile {root / 'sshd.pid'}
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM no
StrictModes no
SetEnv ORCHESTRA_REMOTE_DATA={state}
AllowUsers {user}
""")
    log = root / "ssh.log"
    executable = which("sshd") or "/usr/sbin/sshd"
    with log.open("wb") as handle:
        daemon = subprocess.Popen([executable, "-D", "-e", "-f", str(config)], stderr=handle)
        try:
            for _ in range(70):
                if daemon.poll() is not None:
                    raise AssertionError(log.read_text())
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.15):
                        break
                except OSError:
                    time.sleep(.04)
            spec = {"name": "Loopback", "host": "127.0.0.1", "port": port, "user": user,
                    "identity": str(root / "operator"), "auth": "key", "worker_dir": str(source),
                    "python": sys.executable}
            client = SSHClient(root / "client", "local", spec)
            try:
                client.test()
            except Invalid:
                pass
            else:
                raise AssertionError("Unknown fingerprint accepted")
            alg, blob, *_ = (root / "host.pub").read_text().split()
            observed = scan_keys(client.profile)
            check = fingerprint(blob)
            assert observed[check] == (alg, blob)
            trust_key(client.root, client.id, client.profile, check, observed)
            assert client.test()["os"] == "Linux"
            fake = (root / "operator.pub").read_text().split()[1]
            mismatch = fingerprint(fake)
            trust_key(client.root, client.id, client.profile, mismatch, {mismatch: ("ssh-ed25519", fake)})
            try:
                client.test()
            except Invalid as problem:
                assert "호스트 키가 일치하지 않습니다" in str(problem)
            else:
                raise AssertionError("Changed host key accepted")
            trust_key(client.root, client.id, client.profile, check, observed)
            assert client.call("info")["repos"] == [str(repo)]
            shell = Pty(client.terminal(str(repo)), None, ssh_env())
            try:
                shell.write("printf '%s\\n' orch-remote-pty-ok\r")
                received = bytearray()
                deadline = time.monotonic() + 5
                while b"\r\norch-remote-pty-ok\r\n" not in received and time.monotonic() < deadline:
                    ready, _, _ = select.select([shell.master], [], [], .2)
                    if ready:
                        chunk = shell.read()
                        if not chunk:
                            break
                        received.extend(chunk)
                assert b"\r\norch-remote-pty-ok\r\n" in received, received[-1000:]
                started, log_effects = root / "qa-started", root / "qa-effects"
                qa = r"""from pathlib import Path
import sys, time
started, effects = map(Path, sys.argv[1:])
if not started.exists():
    started.touch()
    time.sleep(12)
    with effects.open("a") as output:
        output.write("interrupted process survived\n")
else:
    with effects.open("a") as output:
        output.write("recovered run\n")
"""
                plan = draft_plan(project | {"host": "local"}, "Run a remote check", STRATEGIES[2],
                                  qa=[[sys.executable, "-c", qa, str(started), str(log_effects)]])
                key = "1" * 32
                receipt = client.call("submit", request_id=key, plan=plan)["id"]
                deadline = time.monotonic() + 12
                while not started.exists() and time.monotonic() < deadline:
                    time.sleep(.05)
                assert started.exists(), client.call("status", job=receipt)["state"]
                assert client.call("status", job=receipt)["state"] == "RUNNING"
            finally:
                shell.close()
            reconnected = SSHClient(root / "client", "local", spec)
            assert reconnected.call("status", job=receipt)["state"] == "RUNNING"
            worker = state / "supervisor.json"
            old_pid = json.loads(worker.read_text())["pid"]
            os.kill(old_pid, signal.SIGKILL)
            assert reconnected.call("submit", request_id=key, plan=plan)["id"] == receipt
            deadline = time.monotonic() + 25
            while True:
                status = reconnected.call("status", job=receipt)
                if status["state"] in ("SUCCEEDED", "FAILED", "CANCELLED") or time.monotonic() >= deadline:
                    break
                time.sleep(.5)
            assert status["state"] == "SUCCEEDED", status["state"]
            assert json.loads(worker.read_text())["pid"] != old_pid
            assert [task["attempt"] for task in status["tasks"]] == [2]
            assert sum(event["event_type"] == "job.recovered" for event in status["events"]) == 1
            # Let the killed attempt's original delay expire before checking for external effects.
            time.sleep(max(0, started.stat().st_mtime + 12.5 - time.time()))
            assert log_effects.read_text() == "recovered run\n"
            assert reconnected.call("submit", request_id=key, plan=plan)["id"] == receipt
            if args.typescript:
                client_root = root / "client"
                (client_root / "workspace.json").write_text(json.dumps({"schema_version": 1, "hosts": {"local": spec}}), encoding="utf-8")
                cli = source / "apps" / "desktop" / "build" / "main" / "tools" / "inspect.js"
                def inspect(*arguments):
                    output = subprocess.check_output(["node", str(cli), *arguments],
                        env=os.environ | {"ORCHESTRA_DATA": str(client_root)}, text=True)
                    return json.loads(output)
                assert inspect("worker-info", "local")["registeredProjects"] == 1
                first = inspect("worker-status", "local", receipt)
                assert first["state"] == "SUCCEEDED" and first["nextCursor"] > 0
                following = inspect("worker-status", "local", receipt, str(first["nextCursor"]))
                assert following["events"] == [] and following["nextCursor"] == first["nextCursor"]
                print("TypeScript adapter read the same Python Worker run and cursor over OpenSSH.")
            print("Real loopback OpenSSH: pinning, PTY disconnection, Worker hard restart, lease recovery and deduplication passed.")
        except Exception:
            print(log.read_text(), file=sys.stderr)
            raise
        finally:
            (state / "supervisor.stop").touch()
            until = time.monotonic() + 4
            while (state / "supervisor.json").exists() and time.monotonic() < until:
                time.sleep(.05)
            daemon.terminate()
            daemon.wait(timeout=5)
