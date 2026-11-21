"""Read-only, bounded project files and Git previews shared by Tk and the SSH Worker."""
from __future__ import annotations

import difflib
import os
import re
import stat
from contextlib import ExitStack
from pathlib import PurePosixPath

from .core import Invalid, SECRET_FILE, require, scope_path
from .harness import workspace_path
from .platform.filesystem import is_link_or_reparse
from .processes import env_for_process, run

MAX_FILE = 200_000
DIRECTORY_LIMIT = 400
SEARCH_VISITS = 12000
SEARCH_RESULTS = 200
PROTECTED_FOLDERS = frozenset({".aws", ".docker", ".gnupg", ".kube", ".ssh"})
SEARCH_EXCLUSIONS = frozenset({"node_modules", ".venv", "__pycache__"})
PRIVATE_NAMES = re.compile(
    r"^(?:\.envrc|\.git-credentials|\.pypirc|\.env[-_].*"
    r"|\.?auth(?:[_-].*)?\.(?:json|toml|db|sqlite\d*)(?:-(?:wal|shm|journal))?"
    r"|\.?(?:credential|secret|token|apikey|api[_-]key|service[_-]account|client[_-]secret)s?(?:\.[^.]+)?"
    r"|id_(?:dsa|ecdsa|rsa|ed25519)(?:_sk)?|.+\.(?:p12|jks|kdbx))$",
    re.IGNORECASE,
)


def project_file_visible(relative):
    try:
        relative = scope_path(relative)
        relative.encode("utf-8")
    except (Invalid, UnicodeError):
        return False
    return (not SECRET_FILE.search(relative)
            and not any(part.casefold() in PROTECTED_FOLDERS or PRIVATE_NAMES.fullmatch(part)
                        for part in relative.split("/")))


def _safe_path(root, relative):
    require(project_file_visible(relative), "보호된 경로나 지원하지 않는 파일 이름입니다.")
    return workspace_path(root, relative)


def _entries(folder, relative):
    for child in folder.iterdir():
        name = (PurePosixPath(relative) / child.name).as_posix()
        if project_file_visible(name) and not is_link_or_reparse(child):
            try:
                mode = child.lstat().st_mode
            except FileNotFoundError:
                pass
            else:
                if stat.S_ISDIR(mode) or stat.S_ISREG(mode):
                    yield name, stat.S_ISDIR(mode)
                    continue
        yield None


def browse_project(root, relative="."):
    folder = root if relative == "." else _safe_path(root, relative)
    require(folder.is_dir(), "프로젝트 디렉터리를 찾을 수 없습니다.")
    entries = []
    truncated = False
    for index, entry in enumerate(_entries(folder, relative)):
        if index >= SEARCH_VISITS or len(entries) == DIRECTORY_LIMIT:
            truncated = True
            break
        if entry:
            entries.append(entry)
    return sorted(entries, key=lambda row: (not row[1], row[0].casefold())), truncated


def search_project_files(root, query):
    folders = ["."]
    matches = []
    visits = 0
    truncated = False
    while folders and not truncated:
        relative = folders.pop()
        try:
            folder = root if relative == "." else _safe_path(root, relative)
            for entry in _entries(folder, relative):
                visits += 1
                if visits > SEARCH_VISITS or len(matches) == SEARCH_RESULTS:
                    truncated = True
                    break
                if not entry:
                    continue
                path, directory = entry
                if directory:
                    if PurePosixPath(path).name not in SEARCH_EXCLUSIONS:
                        folders.append(path)
                elif query in path.casefold():
                    matches.append((path, False))
        except (OSError, Invalid):
            if relative == ".":
                raise
    return sorted(matches, key=lambda row: row[0].casefold()), truncated


def read_project_file(root, relative):
    path = _safe_path(root, relative)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    with ExitStack() as opened:
        anchored = os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY")
        if anchored:
            directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            descriptor = os.open(root, directory_flags)
            opened.callback(os.close, descriptor)
            parts = PurePosixPath(relative).parts
            for part in parts[:-1]:
                descriptor = os.open(part, directory_flags, dir_fd=descriptor)
                opened.callback(os.close, descriptor)
            fd = os.open(parts[-1], flags, dir_fd=descriptor)
        else:
            require(path.is_file(), "미리 볼 일반 파일을 선택하세요.")
            fd = os.open(path, flags)
        opened.callback(os.close, fd)
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), "미리 볼 일반 파일을 선택하세요.")
        if not anchored:
            require(os.path.samestat(info, _safe_path(root, relative).lstat()), "읽는 동안 파일 경로가 변경되었습니다.")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(MAX_FILE + 1)
        require(len(data) <= MAX_FILE, "200 KB 이하의 파일만 미리 볼 수 있습니다.")
        return data


def _preview_text(raw):
    require(b"\0" not in raw, "텍스트 파일만 미리 볼 수 있습니다.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise Invalid("UTF-8 텍스트 파일만 미리 볼 수 있습니다.") from error


def _read_git(root, *args, limit=300000):
    return run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root), *args],
               env=env_for_process({"LC_ALL": "C"}), timeout=8, limit=limit)


def project_git_status(root):
    code, output = _read_git(root, "status", "--porcelain=v2", "--branch", "-z", "--no-renames",
                             "--ignore-submodules=all", "--untracked-files=all")
    require(code == 0, "Git 작업 폴더 상태를 확인할 수 없습니다.")
    rows = {}
    branch = None
    for raw in output.split(b"\0"):
        if raw.startswith(b"# branch.head "):
            branch = os.fsdecode(raw.removeprefix(b"# branch.head "))
        elif raw.startswith(b"? "):
            name = os.fsdecode(raw[2:])
            if project_file_visible(name):
                rows.setdefault(name, "??")
        elif raw.startswith((b"1 ", b"u ")):
            parts = raw.split(b" ", 8 if raw.startswith(b"1 ") else 10)
            name = os.fsdecode(parts[-1])
            if project_file_visible(name):
                rows[name] = parts[1].decode("ascii").replace(".", " ")
    return branch, rows


def project_file_diff(root, relative, status):
    # Read only exact blob names. Git pathspecs can match descendants of a directory.
    path = _safe_path(root, relative)
    def blob(revision, changed):
        if (revision, changed) in {(":", "D"), ("HEAD:", "A")}:
            return b""
        code, value = _read_git(root, "cat-file", "blob", revision + relative, limit=MAX_FILE + 1)
        require(code == 0 and len(value) <= MAX_FILE, "Git 원본을 읽을 수 없거나 미리 보기 한도를 초과했습니다.")
        return value

    def patch(before, after, first, second):
        left, right = (_preview_text(value).splitlines(keepends=True) for value in (before, after))
        require(max(len(left), len(right)) <= 4000, "Diff 미리 보기의 최대 줄 수를 초과했습니다.")
        lines = difflib.unified_diff(left, right, first + relative, second + relative)
        return "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in lines)

    if status == "??":
        return patch(b"", read_project_file(root, relative), "a/", "b/")
    if "U" in status or status in {"AA", "DD"}:
        return "충돌 파일의 각 Git 단계는 Git 명령으로 확인하세요."
    index_status, worktree_status = status
    index = blob(":", index_status)
    sections = []
    if index_status != " ":
        sections.append("HEAD → Index\n" + patch(blob("HEAD:", index_status), index, "a/", "b/"))
    if worktree_status != " ":
        worktree = read_project_file(root, relative) if path.exists() and worktree_status != "D" else b""
        sections.append("Index → Worktree\n" + patch(index, worktree, "a/", "b/"))
    return "\n".join(sections)
