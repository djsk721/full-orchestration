"""One Python contract suite for the Linux and Windows backend paths."""
from __future__ import annotations

import os
import queue
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from orchestra.core import Invalid, defaults
from orchestra import desktop_contract
from orchestra.platform.command_line import format_commands, parse_commands
from orchestra.harness import workspace_path
from orchestra.platform.filesystem import atomic_bytes, path_in
from orchestra.platform.terminal import create_pty
from orchestra.processes import run
from orchestra.store import Store


def wait_for_file(path, timeout=10):
    end = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < end:
        time.sleep(.025)


class NativeAdapterTest(unittest.TestCase):
    def test_argument_round_trip_and_explicit_filesystem_policy(self):
        argv = [[sys.executable, "-c", 'print("spaces here")'], ["git", "show", "a path", "with\\backslash"]]
        self.assertEqual(parse_commands(format_commands(argv)), argv)
        self.assertTrue(path_in("src/a", ["Src"], case_sensitive=False))
        self.assertFalse(path_in("src/a", ["Src"], case_sensitive=True))
        self.assertFalse(path_in("src-tests/a", ["src"], case_sensitive=False))

    def test_worktree_guard_rejects_a_reparse_point_within_scope(self):
        with tempfile.TemporaryDirectory(prefix="orchestra-reparse-") as directory:
            root = Path(directory)
            allowed = root / "allowed"
            allowed.mkdir()
            original = Path.lstat

            def attributes(path):
                if path == allowed:
                    return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
                return original(path)

            with patch.object(Path, "lstat", attributes):
                with self.assertRaises(Invalid):
                    workspace_path(root, "allowed/file.txt", ["allowed"])

    @unittest.skipUnless(os.name == "nt", "requires a native Windows directory junction")
    def test_worktree_guard_rejects_a_real_windows_junction(self):
        with tempfile.TemporaryDirectory(prefix="orchestra-native-reparse-") as directory:
            root = Path(directory)
            workspace, outside = root / "workspace", root / "outside"
            workspace.mkdir()
            outside.mkdir()
            junction = workspace / "allowed"
            subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
                           check=True, capture_output=True)
            try:
                self.assertTrue(junction.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
                with self.assertRaises(Invalid):
                    workspace_path(workspace, "allowed/file.txt", ["allowed"])
            finally:
                junction.rmdir()

    @unittest.skipUnless(os.name == "nt", "requires native Windows read-only file attributes")
    def test_windows_atomic_save_keeps_read_only_file(self):
        with tempfile.TemporaryDirectory(prefix="orchestra-readonly-") as directory:
            path = Path(directory) / "settings.json"
            path.write_bytes(b"original")
            path.chmod(stat.S_IREAD)
            try:
                with self.assertRaises(PermissionError):
                    atomic_bytes(path, b"replacement")
                self.assertEqual(path.read_bytes(), b"original")
                self.assertEqual(list(path.parent.iterdir()), [path])
            finally:
                path.chmod(stat.S_IWRITE)

    def test_timeout_terminates_a_real_descendant(self):
        with tempfile.TemporaryDirectory(prefix="orchestra-child-tree-") as directory:
            marker = str(Path(directory) / "descendant-survived")
            ready = Path(directory) / "descendant-started"
            descendant = (
                "from pathlib import Path; import sys,time; "
                "Path(sys.argv[1]).touch(); time.sleep(4); Path(sys.argv[2]).touch()"
            )
            parent = ("import subprocess,sys,time; "
                      "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3]]); time.sleep(8)")
            with self.assertRaises(TimeoutError):
                run([sys.executable, "-c", parent, descendant, str(ready), marker], timeout=2.5)
            self.assertTrue(ready.exists(), "fixture descendant did not reach its start marker")
            time.sleep(2.0)
            self.assertFalse(Path(marker).exists(), "native timeout left the descendant running")

    def test_controller_hard_exit_terminates_a_real_descendant(self):
        with tempfile.TemporaryDirectory(prefix="orchestra-child-owner-") as directory:
            started = Path(directory) / "started"
            effect = Path(directory) / "survived"
            workload = (
                "from pathlib import Path; import sys,time; "
                "Path(sys.argv[1]).touch(); time.sleep(3); Path(sys.argv[2]).touch()"
            )
            controller = subprocess.Popen([
                sys.executable, "-c",
                "import sys; from orchestra.processes import run; run([sys.executable, '-c', *sys.argv[1:]])",
                workload, str(started), str(effect),
            ])
            try:
                wait_for_file(started)
                self.assertTrue(started.exists(), "contained command never started")
            finally:
                controller.kill()
                controller.wait(timeout=10)
            wait_for_file(effect, 3.4)
            self.assertFalse(effect.exists(), "command outlived its forcibly terminated controller")

    def test_native_terminal_inputs_and_resizes_interactive_process(self):
        with tempfile.TemporaryDirectory(prefix="orchestra-adapter-pty-") as directory:
            child = ("import os; print('\\x1b[32mREADY\\x1b[0m',flush=True); "
                     "value=input(); size=os.get_terminal_size(); print(f'RECEIVED:{value}:{size.columns}:{size.lines}',flush=True)")
            terminal = create_pty([sys.executable, "-c", child], Path(directory), os.environ.copy(), 25, 80)
            received = queue.Queue()

            def read():
                try:
                    while chunk := terminal.read():
                        received.put(chunk)
                except (EOFError, OSError):
                    pass

            thread = threading.Thread(target=read, daemon=True)
            thread.start()
            buffer = bytearray()

            def wait_for(marker):
                limit = time.monotonic() + 8
                while marker not in buffer and time.monotonic() < limit:
                    try:
                        buffer.extend(received.get(timeout=.15))
                    except queue.Empty:
                        pass
                self.assertIn(marker, buffer)

            try:
                wait_for(b"READY")
                self.assertIn(b"\x1b[", buffer)
                terminal.resize(27, 91)
                terminal.write("backend-check\r")
                wait_for(b"RECEIVED:backend-check:91:27")
            finally:
                terminal.close()
                thread.join(2)
            self.assertFalse(thread.is_alive())


class StateConsistencyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="orchestra-store-contract-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.plan = {"title": "Fixture", "repo": str(self.root), "target": "main", "tasks": [{"id": "task"}]}
        self.config = defaults()

    @staticmethod
    def compete(function, count=6):
        barrier = threading.Barrier(count)

        def actor(index):
            barrier.wait(10)
            return function(index)

        with ThreadPoolExecutor(max_workers=count) as executor:
            return list(executor.map(actor, range(count)))

    def test_concurrent_remote_submissions_and_claims_have_one_identity(self):
        def submit(_):
            return Store(self.root).submit(self.plan, self.config, None, request_id="a" * 32)
        ids = self.compete(submit)
        self.assertEqual(len(set(ids)), 1)
        job = ids[0]
        claims = self.compete(lambda index: Store(self.root).claim(job, str(index)))
        self.assertEqual(claims.count(True), 1)
        states = [event["payload"]["state"] for event in self.store.events(job)]
        self.assertEqual(states, ["QUEUED", "PREPARING"])

    def test_cancel_persists_when_completion_is_already_in_flight(self):
        job = self.store.submit(self.plan, self.config, None)
        self.assertTrue(self.store.claim(job, "worker"))
        self.store.set_job(job, "RUNNING", release=False)
        self.store.request(job, "cancel")
        self.assertFalse(self.store.set_job(job, "VERIFYING", release=False))
        self.store.set_job(job, "SUCCEEDED", result={"candidate": "a" * 40})
        item = self.store.job(job)
        self.assertEqual(item["state"], "CANCELLED")
        self.assertIsNone(item["result"])
        self.assertIsNone(item["owner"])
        self.assertEqual(self.store.events(job)[-1]["payload"]["state"], "CANCELLED")

    def test_cancel_and_completion_publish_one_terminal_state_under_contention(self):
        job = self.store.submit(self.plan, self.config, None)
        self.assertTrue(self.store.claim(job, "worker"))
        self.store.set_job(job, "RUNNING", release=False)

        def finish(index):
            store = Store(self.root)
            if index == 0:
                try:
                    store.request(job, "cancel")
                    return "accepted"
                except Invalid:
                    return "already completed"
            store.set_job(job, "SUCCEEDED", result={"qa": []})
            return "released"

        cancellation, _ = self.compete(finish, count=2)
        expected = "CANCELLED" if cancellation == "accepted" else "SUCCEEDED"
        item = self.store.job(job)
        self.assertEqual(item["state"], expected)
        self.assertIsNone(item["owner"])
        terminal = [event["payload"]["state"] for event in self.store.events(job)
                    if event["event_type"] == "job.state" and event["payload"]["state"] in ("CANCELLED", "SUCCEEDED")]
        self.assertEqual(terminal, [expected])

    def test_same_candidate_requires_current_revision_and_successful_qa(self):
        job = self.store.submit(self.plan, self.config, None)
        candidate = "a" * 40
        evidence = {"candidate": candidate, "approval_revision": "1" * 32, "qa": [{"index": 1, "exit_code": 0}]}
        self.store.set_job(job, "AWAITING_APPROVAL", result=evidence)
        new_cycle = evidence | {"approval_revision": "2" * 32}
        self.store.set_job(job, "AWAITING_APPROVAL", result=new_cycle)
        for supplied in (None, evidence["approval_revision"]):
            with self.assertRaises(Invalid):
                self.store.request(job, "merge", candidate, approval_revision=supplied)
        self.store.set_job(job, "AWAITING_APPROVAL", result=new_cycle | {"qa": [{"index": 1, "exit_code": 7}]})
        with self.assertRaises(Invalid):
            self.store.request(job, "merge", candidate, approval_revision=new_cycle["approval_revision"])
        self.store.set_job(job, "AWAITING_APPROVAL", result=new_cycle)
        self.store.request(job, "merge", candidate, approval_revision=new_cycle["approval_revision"])
        [event] = [entry for entry in self.store.events(job) if entry["event_type"] == "job.request"]
        self.assertEqual(event["payload"]["approval_revision"], new_cycle["approval_revision"])

    def test_concurrent_tool_approval_is_consumed_once(self):
        job = self.store.submit(self.plan, self.config, None)
        self.store.approval(job, "task", "token", "tool", {})
        self.store.set_task(job, "task", "AWAITING_TOOL")
        self.store.set_job(job, "AWAITING_TOOL")

        def decide(index):
            try:
                Store(self.root).decide(job, "task", "token", index == 0)
                return True
            except Invalid:
                return False

        self.assertEqual(self.compete(decide).count(True), 1)
        self.assertEqual(self.store.job(job)["state"], "QUEUED")
        self.assertEqual(self.store.tasks(job)["task"]["state"], "QUEUED")
        self.assertEqual(sum(e["event_type"] == "tool.decision" for e in self.store.events(job)), 1)

    def test_recovery_preserves_checkpoint_and_uncertain_write(self):
        job = self.store.submit(self.plan, self.config, None)
        self.store.claim(job, "old-owner")
        self.store.set_task(job, "task", "RUNNING")
        self.store.checkpoint(job, "task", {"step": "tool"}, None)
        self.store.call_start(job, "task", "effect")
        self.store.recover(True, "new-owner")
        self.assertEqual(self.store.job(job)["owner"], "old-owner")
        with self.store.connect(write=True) as conn:
            conn.execute("UPDATE jobs SET heartbeat=0 WHERE id=?", (job,))
        self.store.recover(True, "new-owner")
        self.assertEqual(self.store.job(job)["state"], "QUEUED")
        self.assertEqual(self.store.tasks(job)["task"]["checkpoint"], {"step": "tool"})
        with self.assertRaises(Invalid):
            self.store.call_start(job, "task", "effect")

    def test_interrupted_writer_rolls_back_job_and_event_together(self):
        job = self.store.submit(self.plan, self.config, None)
        started = self.root / "uncommitted"
        script = """
from pathlib import Path
import sqlite3, sys, time
db = sqlite3.connect(sys.argv[1], isolation_level=None)
db.execute("BEGIN IMMEDIATE")
db.execute("UPDATE jobs SET state='RUNNING' WHERE id=?", (sys.argv[2],))
db.execute("INSERT INTO events(job, type, at, payload) VALUES (?, 'test.uncommitted', 1, '{}')", (sys.argv[2],))
Path(sys.argv[3]).touch()
time.sleep(30)
"""
        writer = subprocess.Popen([sys.executable, "-c", script, str(self.store.path), job, str(started)])
        try:
            wait_for_file(started)
            self.assertTrue(started.exists())
            self.assertEqual(self.store.job(job)["state"], "QUEUED")
            self.assertEqual([e["event_type"] for e in self.store.events(job)], ["job.state"])
        finally:
            writer.kill()
            writer.wait(timeout=10)
        restarted = Store(self.root)
        with restarted.connect() as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertTrue(restarted.claim(job, "recovered"))
        self.assertEqual([e["payload"]["state"] for e in restarted.events(job)], ["QUEUED", "PREPARING"])

    def test_projection_install_is_atomic_and_preserves_legacy_data(self):
        job = self.store.submit(self.plan, self.config, None, request_id="b" * 32)
        self.store.checkpoint(job, "task", {"step": "resume"}, None)
        with self.store.connect(write=True) as conn:
            views = conn.execute("SELECT name FROM sqlite_schema WHERE type='view' AND name GLOB 'desktop_*'").fetchall()
            for view in views:
                conn.execute(f'DROP VIEW "{view[0]}"')
        with self.assertRaisesRegex(RuntimeError, "interruption"):
            with self.store.connect(write=True) as conn:
                desktop_contract.install(conn)
                self.assertTrue(desktop_contract.installed(conn))
                raise RuntimeError("interruption")
        with self.store.connect() as conn:
            self.assertFalse(desktop_contract.installed(conn))
            self.assertEqual(conn.execute("SELECT count(*) FROM sqlite_schema WHERE type='view'").fetchone()[0], 0)
        results = self.compete(lambda _: Store(self.root).remote_receipt("b" * 32)["job"])
        self.assertEqual(results, [job] * 6)
        self.assertEqual(self.store.tasks(job)["task"]["checkpoint"], {"step": "resume"})
        with self.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT version FROM desktop_contract").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 0)

    def test_retry_does_not_display_previous_integration_checks(self):
        job = self.store.submit(self.plan, self.config, None)
        self.store.set_job(job, "VERIFYING", release=False)
        self.store.event(job, None, "qa.result", {"index": 1, "exit_code": 5})
        self.store.set_job(job, "FAILED")
        with self.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT exit_code FROM desktop_qa_v1 WHERE job=?", (job,)).fetchone()[0], 5)
        self.store.request(job, "retry")
        with self.store.connect() as conn:
            self.assertIsNone(conn.execute("SELECT exit_code FROM desktop_qa_v1 WHERE job=?", (job,)).fetchone())

    def test_worker_snapshot_is_one_transaction_during_concurrent_commit(self):
        job = self.store.submit(self.plan, self.config, None)
        fetch_events = self.store.events_tx

        def commit_after_read_started(conn, *args):
            other = Store(self.root)
            with other.connect(write=True) as writer:
                writer.execute("UPDATE jobs SET state='RUNNING' WHERE id=?", (job,))
                writer.execute("UPDATE tasks SET state='RUNNING' WHERE job=?", (job,))
                other.event_tx(writer, job, None, "job.state", {"state": "RUNNING"})
            return fetch_events(conn, *args)

        with patch.object(self.store, "events_tx", side_effect=commit_after_read_started):
            item, tasks, events = self.store.status_snapshot(job, 0, 150)
        self.assertEqual(item["state"], "QUEUED")
        self.assertEqual(tasks["task"]["state"], "QUEUED")
        self.assertEqual([event["payload"]["state"] for event in events], ["QUEUED"])
        item, tasks, events = self.store.status_snapshot(job, events[-1]["seq"], 150)
        self.assertEqual(item["state"], "RUNNING")
        self.assertEqual(tasks["task"]["state"], "RUNNING")
        self.assertEqual([event["payload"]["state"] for event in events], ["RUNNING"])
