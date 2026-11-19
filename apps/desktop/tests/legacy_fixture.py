"""Build a disposable compatibility database through the real Python Store."""

import json
import sys
import subprocess
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from orchestra.core import Invalid, atomic_json, config_check, defaults, plan_check
from orchestra.execution_state import ready_tasks
from orchestra.runtime import RuntimePool, routes
from orchestra.store import Store
from orchestra.supervisor import JobRunner, ordered


def main():
    directory = Path(sys.argv[1])
    if sys.argv[1] == "--policies":
        results = []
        for case in json.load(sys.stdin):
            try:
                config = config_check(case["config"])
                plan = plan_check(case["plan"], config)
                results.append([[[route.model_id, route.harness_id] for route in routes(config, task)] for task in plan["tasks"]])
            except Invalid:
                results.append(None)
        print(json.dumps(results))
        return
    if sys.argv[1] == "--dag":
        cases = json.load(sys.stdin)
        results = []
        for nodes in cases:
            plan = {
                "title": "DAG compatibility",
                "repo": str(Path.cwd()),
                "target": "main",
                "tasks": [
                    {"id": node["id"], "depends": node["dependencies"], "role": "explorer",
                     "prompt": "Inspect", "acceptance": "Complete"}
                    for node in nodes
                ],
            }
            try:
                plan_check(plan, defaults())
                order, ancestry = ordered(plan["tasks"])
                results.append({"order": order, "ancestry": {key: sorted(values) for key, values in ancestry.items()}})
            except Invalid:
                results.append(None)
        print(json.dumps(results))
        return
    if sys.argv[1] == "--admission":
        results = []
        for case in json.load(sys.stdin):
            order, ancestry = ordered([{"id": node["id"], "depends": node["dependencies"]} for node in case["nodes"]])
            rows = {key: {"state": row["state"], "available": row["availableAt"]} for key, row in case["rows"]}
            results.append(ready_tasks(order, ancestry, rows, case["active"], case["now"], case["workers"]))
        print(json.dumps(results))
        return
    store = Store(directory)
    if sys.argv[2:] == ["--reopen"]:
        return
    persist_install = sys.argv[2:] == ["--installer-persistence"]
    if sys.argv[2:] in (["--qa-failure"], ["--running"]):
        failure = sys.argv[2] == "--qa-failure"
        repo = directory / "fixture repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "--allow-empty", "-qm", "fixture"], check=True)
        command = [sys.executable, "-c"]
        wait_for_release = """
from pathlib import Path
import sys, time
started, release = map(Path, sys.argv[1:])
started.touch()
deadline = time.monotonic() + 20
while not release.exists() and time.monotonic() < deadline:
    time.sleep(.05)
raise SystemExit(0 if release.exists() else 9)
"""
        check = command + (["raise SystemExit(7)"] if failure else
                           [wait_for_release, str(directory / "started"), str(directory / "release")])
        plan = {"title": "Integration failure fixture" if failure else "Independent Supervisor run",
                "repo": str(repo), "target": "main", "background": not failure,
                "tasks": [{"id": "qa", "role": "qa", "prompt": "Run checks", "acceptance": "Run the requested tests",
                           "qa": [command + ["raise SystemExit(0)"]]}],
                "qa": [check]}
        config = defaults()
        if not failure:
            config["settings"].update(background=True, heartbeat_sec=1, lease_sec=4)
            atomic_json(directory / "registry.json", config)
        job = store.submit(plan_check(plan, config), config, None)
        if failure:
            assert store.claim(job, "compatibility fixture")
            JobRunner(store, RuntimePool(), store.job(job), threading.Event(), lambda _: True, threading.Lock()).work()
            assert store.job(job)["state"] == "FAILED"
        print(json.dumps({"id": job}))
        return
    if len(sys.argv) > 2 and not persist_install:
        store.event(sys.argv[2], "qa", "qa.followup", {"private": "PRIVATE_EVENT"})
        return
    plan = {
        "title": "문서 verification",
        "repo": str(directory.resolve()),
        "target": "main",
        "background": True,
        "tasks": [
            {"id": "review", "role": "reviewer", "depends": [],
             "prompt": "PRIVATE_PROMPT", "acceptance": "Pass"},
            {"id": "qa", "role": "qa", "depends": ["review"],
             "prompt": "Run QA", "acceptance": "Exit zero", "qa": [["git", "--version"]]},
        ],
    }
    config = defaults()
    config["settings"]["background"] = True
    if persist_install:
        atomic_json(directory / "registry.json", config)
        atomic_json(directory / "workspace.json", {"schema_version": 1, "projects": {}, "hosts": {}, "default_model": ""})
    job = store.submit(plan, config, None)
    store.set_task(job, "review", "SUCCEEDED", attempt=1)
    store.set_task(job, "qa", "SUCCEEDED", attempt=1)
    store.event(job, "qa", "qa.result", {"private": "PRIVATE_EVENT", "exit_code": 0})
    store.set_job(job, "AWAITING_APPROVAL", result={
        "candidate": "a" * 40,
        "qa": [{"index": 1, "exit_code": 0}],
    })
    print(json.dumps({"id": job}))


if __name__ == "__main__":
    main()
