from __future__ import annotations

import ast
import os
import time
from pathlib import Path

from .core import Invalid, path_in, require
from .processes import env_for_process, run


class GitGate:
    def __init__(self, store, job, stop):
        self.store = store
        self.job = job
        self.repo = Path(job["plan"]["repo"]).resolve()
        self.root = store.root / "worktrees" / job["id"]
        self.hooks = store.root / "no-hooks"
        self.hooks.mkdir(exist_ok=True)
        self.stop = stop

    def git(self, cwd, *args, timeout=120, interrupt=True):
        argv = ["git", "-c", f"core.hooksPath={self.hooks.as_posix()}", "-c", "commit.gpgsign=false",
                "-c", "core.fsmonitor=false", "-c", "core.quotePath=false", *args]
        code, out = run(argv, cwd=cwd, env=env_for_process(), timeout=timeout,
                        stop=self.stop if interrupt else None)
        if code:
            raise Invalid(f"Git {args[0]} 실패 (종료 코드 {code}). 저장소 및 Worktree 상태를 확인하세요.")
        return out

    def ref(self):
        ref = "refs/heads/" + self.job["plan"]["target"]
        self.git(self.repo, "check-ref-format", ref)
        return ref

    def base(self):
        require(Path(os.fsdecode(self.git(self.repo, "rev-parse", "--show-toplevel").strip())).resolve() == self.repo,
                "저장소의 최상위 디렉터리를 선택하세요.")
        return self.git(self.repo, "rev-parse", "--verify", self.ref() + "^{commit}").decode().strip()

    def worktree(self, name, base, commits=()):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / name
        if path.exists():
            self.git(self.repo, "worktree", "remove", "--force", str(path))
        self.git(self.repo, "worktree", "add", "--quiet", "--detach", str(path), base)
        for commit in commits:
            self.pick(path, commit)
        return path

    def pick(self, path, commit):
        self.git(path, "-c", "user.name=Model Orchestration", "-c", "user.email=orchestration@localhost",
                 "cherry-pick", "--no-gpg-sign", commit)

    def head(self, path):
        return self.git(path, "rev-parse", "HEAD").decode().strip()

    def changed(self, path):
        patches = self.git(path, "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z", "HEAD", "--")
        extras = self.git(path, "ls-files", "--others", "--exclude-standard", "-z", "--")
        return sorted({os.fsdecode(item).replace(os.sep, "/") for item in (patches + extras).split(b"\0") if item})

    def commit(self, path, key, head, allowed):
        require(self.head(path) == head, "작업 중 Git HEAD가 변경되었습니다.")
        changed = self.changed(path)
        require(all(path_in(file, allowed) for file in changed), "작업이 허용 범위 밖의 파일을 변경했습니다.")
        if not changed:
            return None, changed
        self.git(path, "add", "-A", "--")
        staged = self.git(path, "diff", "--cached", "--name-only", "--no-renames", "-z", "HEAD", "--")
        require(all(path_in(os.fsdecode(name), allowed) for name in staged.split(b"\0") if name),
                "스테이징 후 작업의 변경 범위를 다시 검증하지 못했습니다.")
        modes = self.git(path, "diff", "--cached", "--raw", "--no-renames", "-z", "HEAD", "--").split(b"\0")[::2]
        require(all(not ({b"120000", b"160000"} & set(record.lstrip(b":").split()[:2])) for record in modes),
                "Worktree 변경에 심볼릭 링크 또는 서브모듈이 포함되어 있습니다.")
        self.git(path, "-c", "user.name=Model Orchestration", "-c", "user.email=orchestration@localhost",
                 "commit", "--no-verify", "-m", f"Orchestration task {key}")
        return self.head(path), changed

    def qa(self, path, commands, task=None, route=None):
        before = self.head(path)
        require(not self.changed(path), "QA 시작 전에 커밋되지 않은 변경이 있습니다.")
        evidence = []
        for i, argv in enumerate(commands, 1):
            start = time.monotonic()
            code, _ = run(argv, cwd=path, env=env_for_process(), timeout=600, stop=self.stop)
            record = {"index": i, "exit_code": code, "elapsed_sec": round(time.monotonic() - start, 3)}
            self.store.event(self.job["id"], task, "qa.result", record, route)
            require(code == 0, f"QA 명령 {i} 실패 (종료 코드 {code}).")
            require(self.head(path) == before and not self.changed(path), "QA 명령이 Git 변경을 만들었습니다.")
            evidence.append(record)
        return evidence

    def integrate(self, base, commits):
        path = self.worktree("_integration", base, commits)
        candidate = self.head(path)
        evidence = self.qa(path, self.job["plan"].get("qa", []))
        return {"base": base, "candidate": candidate if commits else None, "qa": evidence}

    def apply(self, result):
        ref = self.ref()
        candidate = result["candidate"]
        path = self.root / "_integration"
        require(self.head(path) == candidate and result["qa"] and not self.changed(path),
                "승인된 QA 후보가 변경되었습니다.")
        current = self.base()
        if current == candidate:
            return
        require(current == result["base"], "QA 이후 대상 브랜치가 이동했습니다.")
        self.git(self.repo, "merge-base", "--is-ancestor", current, candidate)
        worktrees = self.git(self.repo, "worktree", "list", "--porcelain").split(b"\n")
        checked_out = None
        for line in worktrees:
            if line.startswith(b"worktree "):
                encoded = line[9:]
                if encoded.startswith(b'"'):
                    encoded = ast.literal_eval("b" + encoded.decode("ascii"))
                directory = Path(os.fsdecode(encoded)).resolve()
            if line == ("branch " + ref).encode():
                checked_out = directory
                break
        if checked_out is None:
            self.git(self.repo, "update-ref", ref, candidate, current, interrupt=False)
        else:
            require(checked_out == self.repo and not self.changed(checked_out),
                    "대상 브랜치는 선택한 저장소의 깨끗한 Worktree에 있어야 합니다.")
            require(self.git(self.repo, "symbolic-ref", "HEAD").decode().strip() == ref
                    and self.head(self.repo) == current, "병합 직전에 대상 브랜치가 변경되었습니다.")
            self.git(self.repo, "merge", "--ff-only", "--no-edit", "--no-overwrite-ignore", candidate, interrupt=False)
