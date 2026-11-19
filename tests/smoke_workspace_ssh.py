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

from orchestra.core import Invalid, Temporary
from orchestra.remote import register_project
from orchestra.ssh import SSHClient, fingerprint, scan_keys, ssh_env, trust_key
from orchestra.store import Store
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

    def wait_for_sshd(daemon):
        for _ in range(70):
            if daemon.poll() is not None:
                raise AssertionError(log.read_text())
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.15):
                    return
            except OSError:
                time.sleep(.04)
        raise AssertionError("sshd did not start")

    def await_condition(predicate, timeout=18):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if result := predicate():
                return result
            time.sleep(.1)
        raise AssertionError("Worker did not reach the expected state")

    def assert_terminal_output(shell, marker):
        shell.write(f"printf '%s\\n' {marker}\r")
        expected = f"\r\n{marker}\r\n".encode()
        received = bytearray()
        deadline = time.monotonic() + 8
        while expected not in received and time.monotonic() < deadline:
            readable, _, _ = select.select([shell.master], [], [], .2)
            if readable:
                chunk = shell.read()
                if not chunk:
                    break
                received.extend(chunk)
        assert expected in received, "SSH terminal did not return the expected marker"

    with log.open("wb") as handle:
        daemon = subprocess.Popen([executable, "-D", "-e", "-f", str(config)], stderr=handle)
        try:
            wait_for_sshd(daemon)
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
                assert_terminal_output(shell, "orch-remote-pty-ok")
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
            # Wait for the process-owned lock to be released, even if its status file is fresh.
            await_condition(lambda: reconnected.call("info")["heartbeat"] is None)
            assert reconnected.call("status", job=receipt)["heartbeat"] is None
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
            start_offline, release_offline = root / "offline-started", root / "offline-release"
            offline_qa = """from pathlib import Path
import sys,time
start,release = map(Path,sys.argv[1:])
start.touch()
deadline = time.monotonic() + 30
while not release.exists() and time.monotonic() < deadline:
    time.sleep(.05)
raise SystemExit(0 if release.exists() else 9)
"""
            detached = draft_plan(project | {"host": "local"}, "Complete while disconnected", STRATEGIES[2],
                                  qa=[[sys.executable, "-c", offline_qa, str(start_offline), str(release_offline)]])
            offline_id = reconnected.call("submit", request_id="2" * 32, plan=detached)["id"]
            await_condition(start_offline.exists)
            before = reconnected.call("status", job=offline_id)
            [before_task] = before["tasks"]
            cursor = before["events"][-1]["seq"]
            daemon.terminate()
            daemon.wait(timeout=5)
            try:
                reconnected.call("status", job=offline_id, after=cursor)
            except Temporary:
                pass
            else:
                raise AssertionError("status appeared available while sshd was down")
            release_offline.touch()
            snapshot = Store(state)
            await_condition(lambda: snapshot.job(offline_id)["state"] == "SUCCEEDED")
            daemon = subprocess.Popen([executable, "-D", "-e", "-f", str(config)], stderr=handle)
            wait_for_sshd(daemon)
            fresh_terminal = Pty(reconnected.terminal(str(repo)), None, ssh_env())
            try:
                assert_terminal_output(fresh_terminal, "orch-remote-pty-reconnected")
            finally:
                fresh_terminal.close()
            after = reconnected.call("status", job=offline_id, after=cursor)
            assert after["state"] == "SUCCEEDED" and after["heartbeat"] is None
            assert after["id"] == offline_id and [item["id"] for item in after["tasks"]] == [before_task["id"]]
            assert after["events"] and all(event["seq"] > cursor for event in after["events"])
            assert reconnected.call("submit", request_id="2" * 32, plan=detached)["id"] == offline_id
            start_cancel, release_cancel = root / "cancel-started", root / "cancel-release"
            cancellation = draft_plan(project | {"host": "local"}, "Cancel from SSH", STRATEGIES[2],
                                      qa=[[sys.executable, "-c", offline_qa, str(start_cancel), str(release_cancel)]])
            cancel_id = reconnected.call("submit", request_id="3" * 32, plan=cancellation)["id"]
            await_condition(start_cancel.exists)
            reconnected.call("action", job=cancel_id, action="cancel")
            cancelled = await_condition(lambda: (row := reconnected.call("status", job=cancel_id))["state"] == "CANCELLED" and row)
            assert cancelled["heartbeat"] is None and cancelled["tasks"][0]["state"] == "CANCELLED"
            assert sum(event["event_type"] == "job.request" for event in cancelled["events"]) == 1
            assert [event["payload"].get("status") for event in cancelled["events"]
                    if event["event_type"] == "qa.interrupted"] == ["stopped"]
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
            print("Real loopback OpenSSH: pinning, disconnect and offline completion, Worker restart, recovery, deduplication and cancellation passed.")
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
