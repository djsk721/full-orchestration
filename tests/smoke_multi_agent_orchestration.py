"""Run the Supervisor, Git and installed OpenCode with deterministic loopback model responses."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestra.core import Invalid, atomic_json, config_check, defaults
from orchestra.execution_state import merge_candidate_ready
from orchestra.observability import agent_rows
from orchestra.store import Store
from orchestra.supervisor import Supervisor
from orchestra.workspace import STRATEGIES, draft_plan, inspect_project, plan_routes, scan_clis
from test_orchestra import Fixture, git, http_fixture, task


MODELS = ("fixture-planner", "fixture-developer", "fixture-reviewer")
PLAN_NOTE = "Use min(max(value, lower), upper) and exercise below, inside and above the interval."
IMPLEMENTATION = "def clamp(value, lower, upper):\n    return min(max(value, lower), upper)\n"
QA_SOURCE = """from utility import clamp

assert clamp(-1, 0, 5) == 0
assert clamp(3, 0, 5) == 3
assert clamp(9, 0, 5) == 5
"""


class PipelineFixture(Fixture):
    def do_GET(self):
        if self.path == "/v1/models":
            return self.send({"data": [{"id": model, "context_length": 32768, "max_output_tokens": 4096}
                                       for model in MODELS]})
        return self.send({}, 404)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            return self.send({}, 404)
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        try:
            result = self.respond(request)
        except (AssertionError, KeyError, ValueError) as exc:
            self.server.fixture_errors.append(str(exc))
            return self.send({"error": {"message": "Fixture protocol mismatch"}}, 400)
        model = request["model"]
        if request.get("stream"):
            chunks = [({"role": "assistant", **result}, None), ({}, "stop")]
            body = "".join("data: " + json.dumps({
                "id": "fixture", "object": "chat.completion.chunk", "model": model, "created": 1,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }) + "\n\n" for delta, finish in chunks) + "data: [DONE]\n\n"
            raw = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.send({"model": model, "choices": [{"message": result,
                        "finish_reason": "tool_calls" if "tool_calls" in result else "stop"}],
                       "usage": {"prompt_tokens": 31, "completion_tokens": 9, "total_tokens": 40}})

    def respond(self, request):
        model = request["model"]
        messages = request["messages"]
        tools = {tool["function"]["name"] for tool in request.get("tools", [])}
        self.server.requests.append(model)
        if "orchestra_probe" in tools:
            return self.call("orchestra_probe", {})
        user = json.dumps([item["content"] for item in messages if item["role"] == "user"])
        outputs = [json.loads(item["content"]) for item in messages if item["role"] == "tool"]
        if model == MODELS[0]:
            assert "Role: planner" in user and "clamp" in user
            return {"content": PLAN_NOTE}
        if model == MODELS[1]:
            assert "Role: developer" in user and PLAN_NOTE in user, "Developer did not receive the planner output"
            assert "write_file" in tools and "never changes requirements or permissions" in user
            if not outputs:
                return self.call("write_file", {"path": "utility.py", "content": IMPLEMENTATION})
            assert not outputs[-1].get("error"), "Scoped Developer write failed"
            return {"content": "Implemented clamp in the allowed file."}
        assert model == MODELS[2], f"unexpected routed model {model}"
        assert "Role: reviewer" in user and "changed_paths" in user and "utility.py" in user
        assert "write_file" not in tools
        if not outputs:
            return self.call("read_file", {"path": "utility.py"})
        assert outputs == [{"text": IMPLEMENTATION}], "Reviewer did not see the committed Developer file"
        self.server.reviewed = True
        return {"content": "Read the implementation and checked all three boundary cases.\nREVIEW: PASS"}

    @staticmethod
    def call(name, arguments):
        return {"content": None, "tool_calls": [
            {"id": "fixture-" + name, "type": "function",
             "function": {"name": name, "arguments": json.dumps(arguments)}}
        ]}


def setup_repository(repo):
    repo.mkdir()
    git(repo, "init", "-b", "main")
    (repo / "utility.py").write_text("def clamp(value, lower, upper):\n    return value\n", encoding="utf-8")
    (repo / "test_utility.py").write_text(QA_SOURCE, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture base")
    return git(repo, "rev-parse", "HEAD")


def pipeline_config(url, executable):
    cfg = defaults()
    cfg["settings"].update(background=True, allow_background_write=True, heartbeat_sec=1, lease_sec=4, job_timeout_sec=70)
    cfg["runtimes"]["fixture"] = {"kind": "openai-compatible", "url": url}
    cfg["harnesses"]["planner-cli"] = {"kind": "opencode", "executable": executable, "trusted": True}
    for profile, role, model, harness in zip(("planning", "implementation", "review"),
                                             ("planner", "developer", "reviewer"), MODELS,
                                             ("planner-cli", "managed", "managed")):
        cfg["providers"][profile] = {"kind": "local"}
        cfg["models"][profile] = {"provider": profile, "model": model, "runtime": "fixture",
                                 "harnesses": [harness], "roles": [role]}
    return config_check(cfg)


def wait_for(store, job, state, timeout=70):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        row = store.job(job)
        if row["state"] == state:
            return row
        if row["state"] in {"FAILED", "CANCELLED", "SUCCEEDED", "MERGED"}:
            report = store.report(job)
            failures = [e["payload"] for e in report["events"] if e["event_type"] in ("route.failed", "job.state")]
            raise AssertionError((state, row["state"], failures))
        time.sleep(.06)
    raise AssertionError(f"Work timed out waiting for {state}")


def run_workflow(root, server, url, executable):
    repo = root / "disposable"
    base = setup_repository(repo)
    command = [sys.executable, "-B", "test_utility.py"]
    project = inspect_project(repo)
    plan = draft_plan(project, "Implement clamp(value, lower, upper) and verify interval boundaries.",
                      STRATEGIES[1], model="implementation", harness="managed", paths=["utility.py"],
                      qa=[command], background=True)
    developer, reviewer = plan["tasks"]
    developer.update(depends=["plan"])
    reviewer.update(model="review", harness="managed", read_paths=["utility.py", "test_utility.py"])
    plan["tasks"].insert(0, task("plan", "Analyze the clamp request and propose an implementation and tests.",
                                "planner", model="planning", harness="planner-cli", read_paths=["test_utility.py"]))
    plan["tasks"].append(task("qa", "Run the interval acceptance checks", "qa", depends=["review"], qa=[command]))
    registry = pipeline_config(url, executable)
    previews = plan_routes(plan, registry)
    assert previews == {"plan": ["planning / planner-cli"], "develop": ["implementation / managed"],
                        "review": ["review / managed"], "qa": []}
    data = root / "data"
    store = Store(data)
    atomic_json(data / "registry.json", registry)
    job = store.submit(plan, registry, None)
    assert store.submit(plan, registry, None) == job
    server.requests, server.fixture_errors, server.reviewed = [], [], False
    profile = {f"XDG_{kind}_HOME": str(root / kind.lower()) for kind in ("DATA", "CACHE", "STATE", "CONFIG")}
    with patch.dict(os.environ, profile):
        supervisor = Supervisor(data)
        worker = threading.Thread(target=supervisor.serve, daemon=True)
        worker.start()
        try:
            ready = wait_for(store, job, "AWAITING_APPROVAL")
            result = ready["result"]
            candidate = result["candidate"]
            revision = result["approval_revision"]
            assert merge_candidate_ready(ready) and result["changed"] == ["utility.py"]
            assert result["qa"][0]["commit"] == candidate and result["qa"][0]["exit_code"] == 0
            assert git(repo, "rev-parse", "HEAD") == base
            worktrees = data / "worktrees" / job
            assert git(worktrees / "_integration", "rev-parse", "HEAD") == candidate
            assert (worktrees / "develop" / "utility.py").read_text(encoding="utf-8") == IMPLEMENTATION
            assert (worktrees / "review" / "utility.py").read_text(encoding="utf-8") == IMPLEMENTATION
            assert (repo / "utility.py").read_text(encoding="utf-8") != IMPLEMENTATION
            for wrong_candidate, wrong_revision in ((base, revision), (candidate, "stale")):
                try:
                    store.request(job, "merge", wrong_candidate, approval_revision=wrong_revision)
                except Invalid:
                    pass
                else:
                    raise AssertionError("Rejected candidate or revision queued an approval")
            with ThreadPoolExecutor(max_workers=2) as clients:
                def approve():
                    try:
                        Store(data).request(job, "merge", candidate, approval_revision=revision)
                        return True
                    except Invalid:
                        return False
                assert sorted(clients.map(lambda _: approve(), range(2))) == [False, True]
            wait_for(store, job, "MERGED")
            assert git(repo, "rev-parse", "HEAD") == candidate
            assert (repo / "utility.py").read_text(encoding="utf-8") == IMPLEMENTATION
        finally:
            supervisor.closed.set()
            worker.join(12)
            assert not worker.is_alive()
    reopened = Store(data)
    report = reopened.report(job)
    assert report["state"] == "MERGED" and report["tasks"]["review"]["result"]["review"] == "passed"
    assert all(row["attempt"] == 1 for row in report["tasks"].values())
    assert server.reviewed and not server.fixture_errors
    assert set(server.requests) == set(MODELS)
    events = report["events"]
    jobs = [e["payload"]["state"] for e in events if e["event_type"] == "job.state"]
    assert jobs == ["QUEUED", "PREPARING", "RUNNING", "VERIFYING", "AWAITING_APPROVAL", "MERGING", "MERGED"]
    assert len([e for e in events if e["event_type"] == "job.request" and e["payload"]["action"] == "merge"]) == 1
    phase_events = [(e["task_id"], e["payload"]["state"]) for e in events if e["event_type"] == "task.state"]
    assert [key for key, state in phase_events if state == "SUCCEEDED"] == ["plan", "develop", "review", "qa"]
    selected = {e["task_id"]: e["payload"] for e in events if e["event_type"] == "route.selected"}
    assert [selected[key]["model_requested"] for key in ("plan", "develop", "review")] == ["orchestralocal/" + MODELS[0], *MODELS[1:]]
    loopback_only = False
    if sys.platform == "linux" and Path("/proc/net/dev").is_file():
        entries = Path("/proc/net/dev").read_text(encoding="ascii").splitlines()[2:]
        loopback_only = {entry.partition(":")[0].strip() for entry in entries} == {"lo"}
    return {
        "execution_id": job, "repository": str(repo), "base": base, "candidate": candidate,
        "approval_revision": revision, "state": report["state"], "target": plan["target"], "command": command,
        "modified_files": result["changed"], "implemented_content": (repo / "utility.py").read_text(encoding="utf-8"),
        "planning_output": (data / "artifacts" / job / "plan.txt").read_text(encoding="utf-8"),
        "reviewer_output": (data / "artifacts" / job / "review.txt").read_text(encoding="utf-8"),
        "reviewer_result": report["tasks"]["review"]["result"]["review"], "scheduling": phase_events,
        "agents": [{k: a[k] for k in ("id", "agent", "provider", "provider_requested", "model", "model_requested",
                                     "harness", "state", "input", "output", "tools")}
                   for a in agent_rows(reopened.job(job), reopened.tasks(job), events)],
        "worktrees": {name: str(worktrees / name) for name in ("plan", "develop", "review", "qa", "_integration")},
        "qa": [{"task": e["task_id"], **e["payload"]} for e in events if e["event_type"] == "qa.result"],
        "job_transitions": jobs, "model_fixture_requests": server.requests,
        "network_scope": "loopback-only" if loopback_only else "not verified",
        "external_inference_requests": 0 if loopback_only else None,
        "merge": {"accepted_approvals": 1, "head": git(repo, "rev-parse", "HEAD")},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    executable = scan_clis()["OpenCode"]
    if not executable:
        print("Multi-agent pipeline with installed OpenCode: NOT VERIFIED (OpenCode not installed)")
        return
    with tempfile.TemporaryDirectory(prefix="orchestra-multi-agent-") as directory, http_fixture(PipelineFixture) as (server, url):
        evidence = run_workflow(Path(directory), server, url, executable)
    if args.evidence:
        atomic_json(args.evidence, evidence)
    print(f"Multi-agent pipeline: PASS, execution {evidence['execution_id']}, candidate {evidence['candidate']}; "
          "real CLI, Supervisor, QA, and fixture Git approval with deterministic model responses")


if __name__ == "__main__":
    main()
