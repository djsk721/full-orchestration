"""Native data locations, writes, and repository path identity."""
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".orchestra-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def data_directory() -> Path:
    override = os.environ.get("ORCHESTRA_DATA")
    if override:
        return Path(override).expanduser().resolve()
    base = os.environ.get("LOCALAPPDATA") if os.name == "nt" else os.environ.get("XDG_DATA_HOME")
    return Path(base or Path.home() / ".local" / "share") / "ModelOrchestration"


def path_in(path: str, scopes: list[str], *, case_sensitive: bool) -> bool:
    if not case_sensitive:
        path = path.casefold()
        scopes = [scope.casefold() for scope in scopes]
    return any(path == scope or path.startswith(scope + "/") for scope in scopes)


def case_sensitive_paths() -> bool:
    return os.name != "nt"


def repository_identity(path: str) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def is_link_or_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    # st_file_attributes is available for Windows reparse points on Python 3.11,
    # before pathlib added is_junction. This covers links that stay inside the repo.
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )
