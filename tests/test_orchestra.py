from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from orchestra.core import Invalid, atomic_json, config_check, defaults, plan_check
from orchestra.discovery import discover, migrate, rollback
from orchestra.gitgate import GitGate
from orchestra.harness import workspace_path
from orchestra.mcp import Gateway, virtual_name
from orchestra.runtime import RuntimeClient, routes
from orchestra.store import Store
from orchestra.supervisor import Supervisor

TOOLS = [
    {"name": "lookup", "description": "Lookup", "inputSchema": {
        "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}},
    {"name": "mutate", "description": "Mutate", "inputSchema": {
        "type": "object", "properties": {}, "additionalProperties": False}},
]


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, data, code=200):
        raw = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        with suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/v1/models":
            return self.send({"data": [{"id": "test-model"}]})
        if self.path == "/props":
            return self.send({"default_generation_settings": {"n_ctx": 32768, "params": {"n_predict": 4096}},
                              "total_slots": 3, "model_alias": "test-model", "chat_template": "test"})
        return self.send({}, 404)

    def do_POST(self):
        msg = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/mcp":
            method = msg["method"]
            if method == "initialize":
                result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}, "serverInfo": {"name": "test", "version": "1"}}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                if msg["params"]["name"] == "mutate":
                    self.server.writes += 1
                    if self.server.stall_write:
                        self.server.released.wait(8)
                        return
                    if self.server.drop_write_response:
                        self.close_connection = True
                        return
                result = {"content": [{"type": "text", "text": "success"}]}
            else:
                return self.send({}, 202)
            return self.send({"jsonrpc": "2.0", "id": msg["id"], "result": result})
        if self.path != "/v1/chat/completions":
            return self.send({}, 404)
        messages = msg["messages"]
        names = {item["function"]["name"] for item in msg.get("tools", [])}
        context = messages[1]["content"] if len(messages) > 1 else ""
        if "provider timeout" in context:
            self.server.inference_requests += 1
            if self.server.inference_requests == 1:
                self.server.released.wait(8)
                return
        if "crash checkpoint" in context:
            self.server.stalled.set()
            self.server.released.wait(12)
        if "orchestra_probe" in names:
            name, args = "orchestra_probe", {}
        elif "ui workflow" in context and "write_file" in names and messages[-1]["role"] != "tool":
            self.server.stalled.set()
            self.server.released.wait(12)
            name, args = "write_file", {"path": "ui-result.txt", "content": "approved change\n"}
        elif "write a.txt" in context and messages[-1]["role"] != "tool":
            self.server.barrier.wait(timeout=15)
            name, args = "write_file", {"path": "a.txt", "content": "A\n"}
        elif "write b.txt" in context and messages[-1]["role"] != "tool":
            self.server.barrier.wait(timeout=15)
            name, args = "write_file", {"path": "b.txt", "content": "B\n"}
        elif "inspect both" in context and len(messages) < 6:
            name, args = "read_file", {"path": "a.txt" if len(messages) <= 2 else "b.txt"}
        elif "external write" in context and messages[-1]["role"] != "tool":
            name, args = "fixture__mutate", {}
        elif "try denied" in context and messages[-1]["role"] != "tool":
            name, args = "write_file", {"path": "a.txt", "content": "wrong"}
        else:
            text = "Completed"
            if "inspect both" in context:
                outputs = [json.loads(item["content"]) for item in messages if item["role"] == "tool"]
                text = "REVIEW: PASS" if outputs == [{"text": "A\n"}, {"text": "B\n"}] else "REVIEW: FAIL"
            if "try denied" in context:
                text = "REVIEW: PASS" if "error" in json.loads(messages[-1]["content"]) else "REVIEW: FAIL"
            if "ui workflow" in context and "write_file" not in names:
                text = "REVIEW: PASS"
            return self.send({"model": "test-model", "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                              "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25}})
        calls = [{"id": "call-" + str(len(messages)), "type": "function",
                  "function": {"name": name, "arguments": json.dumps(args)}}]
        return self.send({"model": "test-model", "choices": [{"message": {"content": None, "tool_calls": calls},
                           "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28}})


@contextmanager
def http_fixture():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    server.barrier = threading.Barrier(2)
    server.writes = 0
    server.drop_write_response = False
    server.stall_write = False
    server.inference_requests = 0
    server.stalled = threading.Event()
    server.released = threading.Event()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.STDOUT).decode().strip()


def config(url):
    cfg = defaults()
    cfg["settings"].update(background=True, allow_background_write=True, heartbeat_sec=1, lease_sec=4, parallel_tasks=3)
    cfg["models"]["model"] = {"provider": "local", "model": "test-model", "runtime": "local", "harnesses": ["managed"]}
    cfg["runtimes"]["local"] = {"kind": "llama.cpp", "ownership": "attached", "url": url, "context": 65000,
                               "max_output": 16000, "slots": 3}
    return config_check(cfg)


def task(key, prompt, role="explorer", **opts):
    return {"id": key, "role": role, "prompt": prompt, "acceptance": "Verify outcome.", **opts}


class OrchestrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "data"
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "Test")
        git(self.repo, "config", "user.email", "test@example.com")
        (self.repo / "initial.txt").write_text("initial", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "fixture")
        self.store = Store(self.root)

    def plan(self, tasks, qa=None):
        return {"title": "Fixture", "repo": str(self.repo), "target": "main", "background": True, "tasks": tasks, "qa": qa or []}

    def poll(self, job, state, timeout=35):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            item = self.store.job(job)
            if item["state"] in state:
                return item
            if item["state"] in ("FAILED", "CANCELLED"):
                self.fail(str(self.store.report(job)))
            time.sleep(.1)
        self.fail(str(self.store.report(job)))

    @contextmanager
    def daemon(self, cfg):
        atomic_json(self.root / "registry.json", cfg)
        supervisor = Supervisor(self.root)
        thread = threading.Thread(target=supervisor.serve, daemon=True)
        thread.start()
        try:
            yield
        finally:
            supervisor.closed.set()
            thread.join(10)
            self.assertFalse(thread.is_alive())

    def test_parallel_dag_review_and_approved_merge(self):
        with http_fixture() as (_, url):
            cfg = config(url)
            check = [sys.executable, "-c", "from pathlib import Path; assert Path('a.txt').read_text() == 'A\\n'; assert Path('b.txt').read_text() == 'B\\n'"]
            plan = self.plan([
                task("a", "write a.txt", "developer", paths=["a.txt"]),
                task("b", "write b.txt", "developer", paths=["b.txt"]),
                task("review", "inspect both", "reviewer", depends=["a", "b"]),
            ], [check])
            job = self.store.submit(plan_check(plan, cfg), cfg, None)
            with self.daemon(cfg):
                result = self.poll(job, {"AWAITING_APPROVAL"})["result"]
                self.assertFalse((self.repo / "a.txt").exists())
                with self.assertRaises(Invalid):
                    self.store.request(job, "merge", result["base"], approval_revision=result["approval_revision"])
                self.store.request(job, "merge", result["candidate"], approval_revision=result["approval_revision"])
                self.poll(job, {"MERGED"})
                self.assertEqual(git(self.repo, "rev-parse", "HEAD"), result["candidate"])
                self.assertEqual((self.repo / "a.txt").read_text(), "A\n")
                self.assertTrue(self.store.report(job)["tokens"])

    def test_qa_failure_blocks_merge_and_duplicate_submit(self):
        with http_fixture() as (_, url):
            cfg = config(url)
            plan = self.plan([task("review", "try denied", "reviewer")], [[sys.executable, "-c", "raise SystemExit(7)"]])
            job = self.store.submit(plan_check(plan, cfg), cfg, None)
            self.assertEqual(self.store.submit(plan, cfg, None), job)
            with self.daemon(cfg):
                self.poll(job, {"FAILED"})
                with self.assertRaises(Invalid):
                    self.store.request(job, "merge", "arbitrary")
                self.assertTrue(any(e["event_type"] == "qa.result" and e["payload"]["exit_code"] == 7
                                    for e in self.store.events(job)))

    def test_stale_approval_and_moved_git_branch_cannot_integrate(self):
        with http_fixture() as (fixture, url):
            fixture.released.set()
            cfg = config(url)
            plan = self.plan([task("change", "ui workflow", "developer", paths=["ui-result.txt"])],
                             [[sys.executable, "-c", "from pathlib import Path; assert Path('ui-result.txt').is_file()"]])
            job = self.store.submit(plan_check(plan, cfg), cfg, None)
            with self.daemon(cfg):
                result = self.poll(job, {"AWAITING_APPROVAL"})["result"]
                candidate = result["candidate"]
                stale = "0" * 32
                with self.assertRaises(Invalid):
                    self.store.request(job, "merge", candidate, approval_revision=stale)
                with self.assertRaises(Invalid):
                    self.store.request(job, "merge", candidate)
                self.assertEqual(self.store.job(job)["state"], "AWAITING_APPROVAL")
                git(self.repo, "commit", "--allow-empty", "-m", "advanced externally")
                moved = git(self.repo, "rev-parse", "HEAD")
                self.store.request(job, "merge", candidate, approval_revision=result["approval_revision"])
                self.poll(job, {"FAILED"})
                self.assertEqual(git(self.repo, "rev-parse", "HEAD"), moved)
                self.assertFalse((self.repo / "ui-result.txt").exists())
                self.assertTrue(any("대상 브랜치가 이동" in event["payload"].get("reason", "")
                                    for event in self.store.events(job)))
                with self.assertRaises(Invalid):
                    self.store.request(job, "merge", candidate, approval_revision=result["approval_revision"])

    def test_candidate_worktree_modifications_reject_approval(self):
        with http_fixture() as (fixture, url):
            fixture.released.set()
            cfg = config(url)
            plan = self.plan([task("change", "ui workflow", "developer", paths=["ui-result.txt"])],
                             [[sys.executable, "-c", "from pathlib import Path; assert Path('ui-result.txt').is_file()"]])
            job = self.store.submit(plan_check(plan, cfg), cfg, None)
            with self.daemon(cfg):
                evidence = self.poll(job, {"AWAITING_APPROVAL"})["result"]
                candidate = self.root / "worktrees" / job / "_integration" / "ui-result.txt"
                candidate.write_text("changed after verification", encoding="utf-8")
                self.store.request(job, "merge", evidence["candidate"], approval_revision=evidence["approval_revision"])
                self.poll(job, {"FAILED"})
                self.assertEqual(git(self.repo, "rev-parse", "HEAD"), evidence["base"])
                self.assertFalse((self.repo / "ui-result.txt").exists())
                self.assertIn("승인된 QA 후보가 변경", self.store.events(job)[-1]["payload"]["reason"])

    def test_git_worktree_preserves_unicode_space_and_long_paths(self):
        repo = self.repo.with_name("프로젝트 with spaces")
        self.repo.rename(repo)
        self.repo = repo
        git(repo, "config", "core.longpaths", "true")
        relative = Path("하위 폴더") / ("q" * 90) / ("r" * 90) / ("s" * 90) / "테스트.txt"
        source = repo / relative
        self.assertGreater(len(str(source)), 260)
        try:
            source.parent.mkdir(parents=True)
            source.write_text("checked", encoding="utf-8")
        except OSError as error:
            if os.name == "nt" and getattr(error, "winerror", None) == 206:
                self.skipTest("Windows long paths are disabled on this host")
            raise
        git(repo, "add", "--", relative.as_posix())
        git(repo, "commit", "-m", "long Unicode test path")
        plan = self.plan([task("qa", "verify files", "qa", qa=[["git", "--version"]])])
        job = self.store.submit(plan, defaults(), None)
        gate = GitGate(self.store, self.store.job(job), lambda: False)
        worktree = gate.worktree("qa", gate.base())
        self.assertEqual((worktree / relative).read_text(encoding="utf-8"), "checked")
        self.assertEqual(gate.changed(worktree), [])

    def test_provider_timeout_retries_from_managed_checkpoint(self):
        original = RuntimeClient.request

        def short_inference(client, path, data=None, timeout=60):
            return original(client, path, data, min(timeout, .4) if data and timeout == 120 else timeout)

        with http_fixture() as (fixture, url), patch.object(RuntimeClient, "request", short_inference):
            cfg = config(url)
            plan = self.plan([task("explore", "provider timeout")])
            job = self.store.submit(plan_check(plan, cfg), cfg, None)
            try:
                with self.daemon(cfg):
                    self.poll(job, {"SUCCEEDED"})
                row = self.store.tasks(job)["explore"]
                self.assertEqual(row["attempt"], 2)
                self.assertEqual(fixture.inference_requests, 2)
                self.assertTrue(any("시간이 초과" in item["payload"].get("reason", "")
                                    for item in self.store.events(job) if item["event_type"] == "route.failed"))
            finally:
                fixture.released.set()

    def test_runtime_gate_and_dag_scope(self):
        with http_fixture() as (_, url):
            cfg = config(url)
            spec = task("x", "inspect")
            route = routes(cfg, spec)[0]
            log = []
            client = RuntimeClient(route.runtime)
            output = client.probe(route, spec, lambda tag, payload: log.append((tag, payload)))
            self.assertEqual((output["context"], output["request_max_output"]), (32768, 4096))
            self.assertEqual(log[-1][1]["desired"]["context"], 65000)
            with self.assertRaises(Invalid):
                client.probe(route, spec | {"min_context": 40000}, lambda *_: None)
            with self.assertRaises(Invalid):
                client.probe(type(route)(**(route.__dict__ | {"model": {"model": "different"}})), spec, lambda *_: None)
            with self.assertRaises(Invalid):
                plan_check(self.plan([task("a", "a", depends=["b"]), task("b", "b", depends=["a"])]), cfg)
            with self.assertRaises(Invalid):
                plan_check(self.plan([task("a", "a", "developer", paths=["src"]),
                                      task("b", "b", "developer", paths=["src/main.py"])]), cfg)
            with self.assertRaises(Invalid):
                workspace_path(self.repo, "../outside")

    def test_native_mcp_migration_and_rollback(self):
        token = "fixture-key-" + ("x" * 30)
        with http_fixture() as (_, url), patch.dict(os.environ, {"ORCH_TEST_TOKEN": token}):
            cfg = config(url)
            spec = {"transport": "http", "url": url + "/mcp", "gateway_token_env": "ORCH_TEST_TOKEN",
                    "tools": {"lookup": {"access": "read", "roles": ["explorer"], "native": True},
                              "mutate": {"access": "write", "roles": ["developer"], "native": True}}}
            cfg["mcp"]["fixture"] = spec
            gateway = Gateway(0, cfg["mcp"], lambda *args: None)
            gateway.port = gateway.server.server_port
            cfg["settings"]["gateway_port"] = gateway.port
            gateway.start()
            try:
                target = self.repo / "opencode.json"
                atomic_json(target, {"x": "keep", "mcp": {"existing": {"type": "remote", "url": url + "/mcp", "oauth": False}}})
                before = target.read_bytes()
                records, _ = discover(self.repo)
                record = next(item for item in records if item["path"] == str(target.resolve()))
                self.assertEqual(target.read_bytes(), before)
                with self.assertRaises(Invalid):
                    migrate(self.root, cfg, record, "fixture", "mutate", {}, self.repo)
                self.assertEqual(target.read_bytes(), before)
                from orchestra.discovery import gateway_probe
                with patch("orchestra.discovery.gateway_probe", side_effect=[
                    gateway_probe(cfg, "fixture", "lookup", {"query": "a"}), Invalid("simulated post-write failure")
                ]):
                    with self.assertRaisesRegex(Invalid, "원본을 복원했습니다"):
                        migrate(self.root, cfg, record, "fixture", "lookup", {"query": "a"}, self.repo)
                self.assertEqual(target.read_bytes(), before)
                key = migrate(self.root, cfg, record, "fixture", "lookup", {"query": "a"}, self.repo)
                current = json.loads(target.read_bytes())
                self.assertEqual(current["x"], "keep")
                self.assertEqual(set(current["mcp"]), {"orchestra_fixture"})
                self.assertNotIn(token.encode(), target.read_bytes())
                target.write_bytes(b"{}")
                with self.assertRaises(Invalid):
                    rollback(self.root, key)
                atomic_json(target, current)
                rollback(self.root, key)
                self.assertEqual(target.read_bytes(), before)
            finally:
                gateway.close()

    def test_external_write_waits_for_approval_and_reuses_checkpoint(self):
        with http_fixture() as (fixture, url):
            cfg = config(url)
            cfg["mcp"]["fixture"] = {"transport": "http", "url": url + "/mcp",
                                      "tools": {"mutate": {"access": "write", "roles": ["developer"]}}}
            plan = self.plan([task("write", "external write", "developer", tools=[virtual_name("fixture", "mutate")])])
            job = self.store.submit(plan_check(plan, cfg), cfg, None)
            with self.daemon(cfg):
                self.poll(job, {"AWAITING_TOOL"})
            self.assertEqual(fixture.writes, 0)
            [request] = self.store.approvals(job)
            self.store.decide(job, request["task"], request["key"], True)
            with self.daemon(cfg):
                self.poll(job, {"SUCCEEDED"})
            self.assertEqual(fixture.writes, 1)

    def test_lost_mcp_response_after_effect_blocks_automatic_retry(self):
        with http_fixture() as (fixture, url):
            fixture.drop_write_response = True
            cfg = config(url)
            cfg["mcp"]["fixture"] = {"transport": "http", "url": url + "/mcp",
                                      "tools": {"mutate": {"access": "write", "roles": ["developer"]}}}
            plan = self.plan([task("write", "external write", "developer", tools=[virtual_name("fixture", "mutate")])])
            job = self.store.submit(plan_check(plan, cfg), cfg, None)
            with self.daemon(cfg):
                self.poll(job, {"AWAITING_TOOL"})
                [request] = self.store.approvals(job)
                self.store.decide(job, request["task"], request["key"], True)
                self.poll(job, {"FAILED"})
            self.assertEqual(fixture.writes, 1)
            with self.assertRaises(Invalid):
                Store(self.root).request(job, "retry")
            with self.daemon(cfg):
                self.assertEqual(self.store.job(job)["state"], "FAILED")
            self.assertEqual(fixture.writes, 1)

    def test_mcp_write_timeout_is_audited_and_never_retried(self):
        from orchestra.mcp import http

        def short_tool_call(url, data=None, headers=None, **options):
            if data and data.get("method") == "tools/call":
                options["timeout"] = .4
            return http(url, data, headers, **options)

        with http_fixture() as (fixture, url), patch("orchestra.mcp.http", short_tool_call):
            fixture.stall_write = True
            cfg = config(url)
            cfg["mcp"]["fixture"] = {"transport": "http", "url": url + "/mcp",
                                      "tools": {"mutate": {"access": "write", "roles": ["developer"]}}}
            plan = self.plan([task("write", "external write", "developer", tools=[virtual_name("fixture", "mutate")])])
            job = self.store.submit(plan_check(plan, cfg), cfg, None)
            try:
                with self.daemon(cfg):
                    self.poll(job, {"AWAITING_TOOL"})
                    [approval] = self.store.approvals(job)
                    self.store.decide(job, approval["task"], approval["key"], True)
                    self.poll(job, {"FAILED"})
                self.assertEqual(fixture.writes, 1)
                with self.assertRaises(Invalid):
                    Store(self.root).request(job, "retry")
                uncertain = [item for item in self.store.events(job) if item["event_type"] == "tool.call"
                             and item["payload"]["status"] == "uncertain"]
                self.assertEqual(len(uncertain), 1)
            finally:
                fixture.released.set()

    def test_attached_opencode_reuses_local_runtime_and_limits(self):
        from orchestra.harness import attached

        with http_fixture() as (_, url):
            cfg = config(url)
            cfg["harnesses"]["external"] = {"kind": "opencode", "executable": "opencode",
                                            "trusted": True, "allow_write": True}
            cfg["models"]["model"]["harnesses"].append("external")
            spec = task("explore", "inspect", harness="external")
            route = routes(cfg, spec)[0]
            client = RuntimeClient(route.runtime)
            validated = client.probe(route, spec, lambda *_: None)
            observed = []

            def fake_cli(argv, **kwargs):
                if argv[-1] == "--version":
                    return 0, b"2.1.0"
                self.assertIn("--standalone", argv)
                self.assertIn("orchestralocal/test-model", argv)
                value = json.loads(Path(kwargs["env"]["OPENCODE_CONFIG"]).read_bytes())
                provider = value["providers"]["orchestralocal"]
                self.assertEqual(provider["settings"]["baseURL"], url + "/v1")
                self.assertEqual(provider["models"]["test-model"]["limit"], {"context": 32768, "output": 4096})
                return 0, b'{"type":"text","part":{"text":"Attached analysis"}}'

            with patch("orchestra.harness.run", side_effect=fake_cli):
                self.assertEqual(attached(route, spec, self.repo, client, validated,
                                          lambda *event: observed.append(event), lambda: False), "Attached analysis")
            self.assertEqual(observed[0][1]["internal_config"], "not_verifiable")

    def test_expired_lease_recovers_and_unknown_effect_cannot_be_retried(self):
        with http_fixture() as (_, url):
            cfg = config(url)
            plan = self.plan([task("explore", "inspect")])
            job = self.store.submit(plan_check(plan, cfg), cfg, None)
            self.assertTrue(self.store.claim(job, "previous"))
            self.store.set_task(job, "explore", "RUNNING", attempt=1)
            self.store.recover(True, "new")
            self.assertEqual(self.store.job(job)["owner"], "previous")
            with self.store.connect(write=True) as conn:
                conn.execute("UPDATE jobs SET heartbeat=? WHERE id=?", (time.time() - 10, job))
            self.store.recover(True, "new")
            self.assertEqual(self.store.job(job)["state"], "QUEUED")
            self.assertEqual(self.store.tasks(job)["explore"]["state"], "QUEUED")
            self.assertIsNone(self.store.call_start(job, "explore", "uncertain"))
            with self.assertRaises(Invalid):
                self.store.call_start(job, "explore", "uncertain")
            self.store.set_job(job, "FAILED")
            with self.assertRaises(Invalid):
                self.store.request(job, "retry")
            self.store.call_end(job, "explore", "uncertain", {"done": True})
            self.assertEqual(self.store.call_start(job, "explore", "uncertain"), {"done": True})

    def test_qa_node_executes_without_a_model(self):
        cfg = defaults()
        cfg["settings"]["background"] = True
        check = [sys.executable, "-c", "from pathlib import Path; assert Path('initial.txt').read_text() == 'initial'"]
        plan = self.plan([task("qa", "check the fixture", "qa", qa=[check])])
        job = self.store.submit(plan_check(plan, cfg), cfg, None)
        with self.daemon(cfg):
            self.poll(job, {"SUCCEEDED"})
        report = self.store.report(job)
        self.assertEqual(report["tasks"]["qa"]["result"]["qa"][0]["exit_code"], 0)
        self.assertEqual(report["tokens"], [])

    def test_supervisor_crash_resumes_durable_checkpoint(self):
        with http_fixture() as (fixture, url):
            cfg = config(url)
            atomic_json(self.root / "registry.json", cfg)
            plan = self.plan([task("explore", "crash checkpoint")])
            job = self.store.submit(plan_check(plan, cfg), cfg, None)
            cmd = [sys.executable, str(Path(__file__).resolve().parents[1] / "ModelOrchestration.pyw"), "--supervisor"]
            env = os.environ | {"ORCHESTRA_DATA": str(self.root)}
            first = subprocess.Popen(cmd, env=env)
            try:
                self.assertTrue(fixture.stalled.wait(10))
                before = self.store.tasks(job)["explore"]
                self.assertEqual(before["checkpoint"]["step"], "agent")
                self.assertEqual(before["attempt"], 1)
            finally:
                first.kill()
                first.wait(timeout=10)
                fixture.released.set()
            second = subprocess.Popen(cmd, env=env)
            try:
                self.poll(job, {"SUCCEEDED"})
                self.assertEqual(self.store.tasks(job)["explore"]["attempt"], 2)
                self.assertTrue(any(event["event_type"] == "job.recovered" for event in self.store.events(job)))
            finally:
                (self.root / "supervisor.stop").touch()
                try:
                    second.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    second.kill()
                    second.wait()

    def test_supervisor_process_detach_and_reconnect(self):
        with http_fixture() as (_, url):
            cfg = config(url)
            atomic_json(self.root / "registry.json", cfg)
            self.store.presence("ui-one")
            plan = self.plan([task("explore", "inspect")])
            job = self.store.submit(plan_check(plan, cfg), cfg, None)
            cmd = [sys.executable, str(Path(__file__).resolve().parents[1] / "ModelOrchestration.pyw"), "--supervisor"]
            env = os.environ | {"ORCHESTRA_DATA": str(self.root)}
            child = subprocess.Popen(cmd, env=env)
            try:
                self.store.presence("ui-one", active=False)
                self.poll(job, {"SUCCEEDED"})
                self.store.presence("ui-two")
                self.assertIsNone(child.poll())
                self.assertEqual(Store(self.root).job(job)["state"], "SUCCEEDED")
            finally:
                (self.root / "supervisor.stop").touch()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


if __name__ == "__main__":
    unittest.main()
