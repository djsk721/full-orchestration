from __future__ import annotations

import base64
import json
import os
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from orchestra.core import Invalid, defaults, path_in
from orchestra.observability import agent_rows
from orchestra.remote import PROTOCOL, dispatch, register_project
from orchestra.ssh import SSHClient, fingerprint, pinned_key, ssh_arguments, trust_key, validate_profile
from orchestra.store import Store
from orchestra.terminal import Pty
from orchestra.workspace import STRATEGIES, draft_plan, inspect_project, plan_routes, put_project, save_registry


def init_repo(path):
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    (path / "checked.txt").write_text("ready", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "checked.txt"], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        init_repo(self.repo)

    def test_project_and_guided_qa_work_without_models(self):
        project = inspect_project(self.repo)
        self.assertEqual(project["branch"], "main")
        key = put_project(self.root, project | {"name": "Fixture"})
        workspace = json.loads((self.root / "workspace.json").read_bytes())
        self.assertEqual(workspace["projects"][key]["path"], str(self.repo.resolve()))
        plan = draft_plan(project, "Run a check", STRATEGIES[2], qa=[[sys.executable, "-c", "raise SystemExit(0)"]])
        self.assertEqual(plan_routes(plan, defaults()), {"qa": []})
        with self.assertRaises(Invalid):
            draft_plan(project, "Change a file", STRATEGIES[1], paths=["checked.txt"])
        advanced = draft_plan(project, "Change a file", STRATEGIES[1],
                              paths=["checked.txt"], qa=[[sys.executable, "-c", "raise SystemExit(0)"]])
        self.assertEqual(advanced["tasks"][1]["depends"], ["develop"])

    def test_registry_migrates_preserves_supported_values_and_backs_up(self):
        file = self.root / "registry.json"
        raw = b'{ "models": {}, "settings": { "parallel_jobs": 5 } }\n'
        file.write_bytes(raw)
        approved = save_registry(self.root, json.loads(raw))
        self.assertEqual(approved["schema_version"], 1)
        self.assertEqual(approved["settings"]["parallel_jobs"], 5)
        backups = list((self.root / "backups" / "registry.json").glob("*.json"))
        self.assertEqual([path.read_bytes() for path in backups], [raw])
        snapshot = file.read_bytes()
        with self.assertRaises(Invalid):
            save_registry(self.root, approved | {"unknown": True})
        self.assertEqual(file.read_bytes(), snapshot)

    def test_agent_projection_uses_observations_and_missing_tokens(self):
        task = {"id": "extract", "role": "explorer"}
        job = {"plan": {"tasks": [task]}, "state": "RUNNING",
               "config": {"models": {"chosen": {"provider": "local"}}}}
        states = {"extract": {"state": "RUNNING", "attempt": 1}}
        def event(seq, typ, payload):
            return {"seq": seq, "event_type": typ, "timestamp": 100 + seq, "task_id": "extract",
                    "agent_id": "explorer/extract", "model_id": "chosen", "harness_id": "managed", "payload": payload}
        events = [event(1, "task.state", {"state": "RUNNING"}), event(2, "model.usage", {"prompt_tokens": 42})]
        [projection] = agent_rows(job, states, events, now=110)
        self.assertEqual((projection["state"], projection["provider"], projection["elapsed"]), ("RUNNING", "local", 9))
        self.assertEqual(projection["input"], 42)
        self.assertIsNone(projection["output"])
        [projection] = agent_rows(job | {"state": "CANCELLED"}, states, events, now=110)
        self.assertEqual(projection["state"], "CANCELLED")

    def test_mcp_agent_constraint_applies_to_catalog_and_native(self):
        from orchestra.mcp import published
        spec = {"tools": {"find": {"access": "read", "roles": ["explorer"], "agents": ["explorer/first"], "native": True}}}
        catalog = {"find": {"inputSchema": {"type": "object"}}}
        self.assertIn("data__find", published("data", spec, catalog, "explorer", agent="explorer/first"))
        self.assertFalse(published("data", spec, catalog, "explorer", agent="explorer/other"))
        self.assertFalse(published("data", spec, catalog, native=True))

    def test_host_key_pinning_has_no_insecure_transport_fallback(self):
        profile = validate_profile({"name": "Lab", "host": "server.example", "user": "operator", "port": 2222})
        with self.assertRaises(Invalid):
            ssh_arguments(self.root, "lab", profile)
        blob = base64.b64encode(b"simulated host public key").decode()
        mark = fingerprint(blob)
        with self.assertRaises(Invalid):
            trust_key(self.root, "lab", profile, "SHA256:unexpected", {mark: ("ssh-ed25519", blob)})
        trust_key(self.root, "lab", profile, mark, {mark: ("ssh-ed25519", blob)})
        self.assertEqual(pinned_key(self.root, "lab", profile), ("ssh-ed25519", mark))
        args = ssh_arguments(self.root, "lab", profile)
        self.assertIn("StrictHostKeyChecking=yes", args)
        self.assertIn("ForwardAgent=no", args)
        self.assertIn("PasswordAuthentication=no", args)
        self.assertIsNone(pinned_key(self.root, "lab", profile | {"host": "other.example"}))
        terminal = SSHClient(self.root, "lab", profile).terminal("/tmp/a b")
        self.assertIn("'/tmp/a b'", terminal[-1])
        self.assertIn(chr(34) + chr(36) + "{SHELL:-/bin/sh}" + chr(34), terminal[-1])

    @unittest.skipUnless(os.name == "posix", "Linux Worker support")
    def test_remote_protocol_executes_and_recovers_one_id(self):
        root = self.root / "worker"
        project = register_project(root, self.repo)
        plan = draft_plan(project | {"host": "fixture"}, "Run remote QA", STRATEGIES[2],
                          qa=[[sys.executable, "-c", "from pathlib import Path; assert Path('checked.txt').read_text() == 'ready'"]])
        def call(method, **params):
            return dispatch(root, {"version": PROTOCOL, "method": method, "params": params})
        self.assertEqual(call("validate", plan=plan), {"qa": []})
        run_key = "0" * 32
        job = call("submit", request_id=run_key, plan=plan)["id"]
        try:
            finish = time.monotonic() + 10
            while time.monotonic() < finish:
                observed = call("status", job=job, after=0)
                if observed["state"] in {"SUCCEEDED", "FAILED"}:
                    break
                time.sleep(.08)
            self.assertEqual(observed["state"], "SUCCEEDED", observed)
            self.assertTrue(any(event["event_type"] == "qa.result" for event in observed["events"]))
            self.assertEqual(call("submit", request_id=run_key, plan=plan)["id"], job)
            self.assertEqual(len(Store(root).list_jobs()), 1)
            with self.assertRaises(Invalid):
                call("submit", request_id=run_key, plan=plan | {"title": "different"})
            with self.assertRaises(Invalid):
                call("browse", repo=project["path"], path="../")
            content = call("download", repo=project["path"], path="checked.txt")
            self.assertEqual(base64.b64decode(content["content"]), b"ready")
            with self.assertRaises(Invalid):
                call("upload", repo=project["path"], name="sample", content="YQ==", upload_id="1" * 32)
            pending = plan | {"title": "Cancel remote QA", "tasks": [plan["tasks"][0] | {
                "qa": [[sys.executable, "-c", "import time; time.sleep(8)"]],
            }]}
            to_cancel = call("submit", request_id="2" * 32, plan=pending)["id"]
            call("action", job=to_cancel, action="cancel")
            until = time.monotonic() + 5
            while time.monotonic() < until and call("status", job=to_cancel)["state"] != "CANCELLED":
                time.sleep(.06)
            self.assertEqual(call("status", job=to_cancel)["state"], "CANCELLED")
        finally:
            (root / "supervisor.stop").touch()
            until = time.monotonic() + 5
            while (root / "supervisor.json").exists() and time.monotonic() < until:
                time.sleep(.05)

    @unittest.skipUnless(os.name == "posix", "Linux PTY smoke")
    def test_pty_sends_input_renders_ansi_and_resizes_process(self):
        code = "import os; print('\\x1b[32mREADY\\x1b[0m', flush=True); print(input(), os.get_terminal_size(), flush=True)"
        pty = Pty([sys.executable, "-c", code], self.repo, dict(os.environ))
        try:
            pty.resize(27, 91)
            data = bytearray()
            [readable, _, _] = select.select([pty.master], [], [], 5)
            self.assertTrue(readable)
            data.extend(pty.read())
            self.assertIn(b"\x1b[32mREADY\x1b[0m", data)
            pty.write("terminal-input\r")
            until = time.monotonic() + 5
            while b"columns=91, lines=27" not in data and time.monotonic() < until:
                [ready, _, _] = select.select([pty.master], [], [], .2)
                if ready:
                    result = pty.read()
                    if not result:
                        break
                    data.extend(result)
            self.assertIn(b"terminal-input", data)
            self.assertIn(b"columns=91, lines=27", data)
        finally:
            pty.close()

    @unittest.skipIf(os.name == "nt", "Linux path case semantics")
    def test_linux_path_scope_distinguishes_case(self):
        self.assertTrue(path_in("Src/file", ["Src"]))
        self.assertFalse(path_in("src/file", ["Src"]))


if __name__ == "__main__":
    unittest.main()
