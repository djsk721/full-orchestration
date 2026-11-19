"""Exercise the installed OpenCode binary through the Supervisor and a scripted API."""
import json
import os
import sys
import tempfile
import threading
from contextlib import suppress
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestra.core import config_check, plan_check
from orchestra.runtime import RuntimePool
from orchestra.store import Store
from orchestra.supervisor import JobRunner
from orchestra.workspace import scan_clis
from test_orchestra import Fixture, config, git, http_fixture, task


def reply(self):
    size = int(self.headers.get("Content-Length") or 0)
    message = json.loads(self.rfile.read(size))
    assert self.path == "/v1/chat/completions"
    assert message["model"] == "test-model"
    self.server.requests += 1
    messages = message["messages"]
    user_messages = "\n".join(str(item.get("content", "")) for item in messages if item["role"] == "user")
    if "ORCHESTRA_OPENCODE_CANCEL" in user_messages:
        self.server.stalled.set()
        self.server.released.wait(20)
        return
    if "ORCHESTRA_OPENCODE_FAIL" in user_messages:
        self.server.error_seen = True
        self.send({"error": {"message": "Synthetic OpenCode request rejected", "type": "invalid_request_error"}}, 400)
        return
    tools = {item["function"]["name"]: item["function"].get("parameters", {}) for item in message.get("tools", [])}
    self.server.saw_read_tool |= "read" in tools
    outputs = [item.get("content") for item in messages if item["role"] == "tool"]
    delta = {"content": "ORCHESTRA_OPENCODE_SMOKE"}
    finish = "stop"
    if outputs:
        self.server.saw_read_response = True
        for tag in ("denied", "permission", "invalid", "required", "not found", "blocked", "rejected"):
            if any(tag in str(value).lower() for value in outputs):
                self.server.read_diagnostics.add(tag)
        if any("orchestra-worktree-data" in str(value) for value in outputs):
            self.server.observed_read = True
    elif "read" in tools:
        properties = tools["read"].get("properties", {})
        path_key = next((key for key in ("filePath", "path", "file_path") if key in properties), "filePath")
        delta = {"tool_calls": [{"index": 0, "id": "fixture-read", "type": "function",
                  "function": {"name": "read", "arguments": json.dumps({path_key: str(self.server.read_path)})}}]}
        finish = "tool_calls"
    if message.get("stream"):
        chunks = []
        for value, stop in (({"role": "assistant", **delta}, None), ({}, finish)):
            chunks.append({"id": "fixture", "object": "chat.completion.chunk", "created": 1, "model": "test-model",
                           "choices": [{"index": 0, "delta": value, "finish_reason": stop}]})
        body = ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        with suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(body)
    else:
        for call in delta.get("tool_calls", []):
            call.pop("index")
        self.send({"id": "fixture", "object": "chat.completion", "created": 1, "model": "test-model",
                   "choices": [{"index": 0, "message": {"role": "assistant", **delta}, "finish_reason": finish}]})


def main():
    executable = scan_clis()["OpenCode"]
    if not executable:
        print("OpenCode installed-binary loopback: NOT VERIFIED (binary not detected)")
        return
    with tempfile.TemporaryDirectory(prefix="orchestra-opencode-") as directory, http_fixture() as (server, url):
        root = Path(directory)
        repo = root / "repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        (repo / "marker.txt").write_text("orchestra-worktree-data", encoding="utf-8")
        git(repo, "add", "marker.txt")
        git(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "-m", "OpenCode fixture")
        store = Store(root / "data")
        registry = config(url)
        registry["settings"]["job_timeout_sec"] = 35
        registry["harnesses"]["opencode"] = {"kind": "opencode", "executable": executable, "trusted": True}
        registry["models"]["model"]["harnesses"] = ["opencode"]
        registry = config_check(registry)
        plan = {"title": "Installed OpenCode check", "repo": str(repo), "target": "main", "background": True,
                "tasks": [task("probe", "Read marker.txt, then reply ORCHESTRA_OPENCODE_SMOKE", harness="opencode",
                               read_paths=["marker.txt"])]}
        job = store.submit(plan_check(plan, registry), registry, None)
        assert store.claim(job, "fixture supervisor")
        server.requests = 0
        server.observed_read = False
        server.saw_read_tool = False
        server.saw_read_response = False
        server.read_diagnostics = set()
        server.error_seen = False
        server.read_path = store.root / "worktrees" / job / "probe" / "marker.txt"
        xdg = {f"XDG_{kind}_HOME": str(root / kind.lower()) for kind in ("DATA", "CACHE", "STATE", "CONFIG")}
        with patch.dict(os.environ, xdg), patch.object(Fixture, "do_POST", reply):
            JobRunner(store, RuntimePool(), store.job(job), threading.Event(), lambda _: True, threading.Lock()).work()
            verify_completed(store, job, server)
            closing = threading.Event()
            cancel_plan = plan | {"title": "Installed OpenCode cancellation",
                                  "tasks": [task("probe", "ORCHESTRA_OPENCODE_CANCEL", harness="opencode")]}
            cancel = store.submit(plan_check(cancel_plan, registry), registry, None)
            assert store.claim(cancel, "fixture supervisor")
            runner = JobRunner(store, RuntimePool(), store.job(cancel), closing, lambda _: True, threading.Lock())
            thread = threading.Thread(target=runner.work)
            thread.start()
            try:
                assert server.stalled.wait(26), "installed OpenCode did not reach its cancellation fixture"
                store.request(cancel, "cancel")
                thread.join(8)
                assert not thread.is_alive(), "installed OpenCode did not stop on cancellation"
                assert store.job(cancel)["state"] == "CANCELLED"
            finally:
                closing.set()
                server.released.set()
                thread.join(8)
            failure_plan = plan | {"title": "Installed OpenCode error",
                                   "tasks": [task("probe", "ORCHESTRA_OPENCODE_FAIL", harness="opencode")]}
            failed = store.submit(plan_check(failure_plan, registry), registry, None)
            assert store.claim(failed, "fixture supervisor")
            JobRunner(store, RuntimePool(), store.job(failed), threading.Event(), lambda _: True, threading.Lock()).work()
            assert server.error_seen and store.job(failed)["state"] == "FAILED"
        print("OpenCode installed-binary loopback: PASS (subprocess, model, read tool, cancellation, errors and history with scripted API)")


def verify_completed(store, job, server):
    report = store.report(job)
    if report["state"] != "SUCCEEDED":
        kinds = sorted({event["event_type"] for event in report["events"]})
        raise AssertionError(f"Installed OpenCode returned {report['state']} after {server.requests} requests ({kinds})")
    artifact = Path(report["tasks"]["probe"]["result"]["artifact"])
    assert server.requests > 0 and "ORCHESTRA_OPENCODE_SMOKE" in artifact.read_text(encoding="utf-8")
    assert server.observed_read, (
        f"OpenCode did not return the worktree read [tool={server.saw_read_tool}, "
        f"result={server.saw_read_response}, diagnostics={sorted(server.read_diagnostics)}]"
    )
    assert any(event["event_type"] == "harness.snapshot" for event in report["events"])


if __name__ == "__main__":
    main()
