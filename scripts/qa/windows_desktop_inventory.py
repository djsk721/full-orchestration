"""Collect desktop QA metadata without starting the workspace or exporting profile values."""
import argparse
from importlib.metadata import PackageNotFoundError, version
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from orchestra.core import data_directory
from orchestra.supervisor import read_config
from orchestra.workspace import read_workspace, scan_clis


def command(*argv):
    try:
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=8, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.decode("utf-8", errors="replace").strip()


def tool_version(path):
    output = command(path, "--version") if path else None
    if output and (match := re.search(r"(?m)^(?:[a-zA-Z0-9 -]+? )?v?(\d+\.\d+\.\d+)\b", output)):
        return match[1]
    return None


def repo_snapshot():
    if not (ROOT / ".git").exists():
        return {"checkout": "no .git"}
    git = shutil.which("git")
    if not git:
        return {"checkout": "git unavailable"}
    prefix = (git, "--no-optional-locks", "-c", "core.fsmonitor=false")
    changes = command(*prefix, "status", "--porcelain=v1")
    return {"checkout": "git", "revision": command(*prefix, "rev-parse", "HEAD"),
            "branch": command(*prefix, "branch", "--show-current") or None,
            "changed_entries": len(changes.splitlines()) if changes is not None else None}


def profile_snapshot(root):
    result = {"workspace_file_present": (root / "workspace.json").is_file(),
              "registry_file_present": (root / "registry.json").is_file()}
    try:
        workspace = read_workspace(root)
        result.update(projects=len(workspace["projects"]), ssh_profiles=len(workspace["hosts"]))
    except (OSError, ValueError, TypeError):
        result["workspace_status"] = "unreadable or invalid"
    try:
        registry = read_config(root)
        result["configured_counts"] = {name: len(registry[name]) for name in ("providers", "models", "runtimes")}
    except (OSError, ValueError, TypeError):
        result["registry_status"] = "unreadable or invalid"
    try:
        with (root / "state.db").open("rb") as database:
            result["sqlite_header_readable"] = database.read(16) == b"SQLite format 3\x00"
    except OSError:
        result["sqlite_header_readable"] = False
    try:
        heartbeat = json.loads((root / "supervisor.json").read_text(encoding="utf-8"))
        timestamp = heartbeat.get("at") if isinstance(heartbeat, dict) else None
        if type(timestamp) in (float, int) and 0 < timestamp < 1e11:
            result["supervisor_heartbeat_age_seconds"] = round(time.time() - timestamp, 1)
    except (OSError, ValueError, TypeError):
        pass
    return result


def tk_snapshot():
    try:
        import tkinter as tk
    except ImportError:
        return {"status": "Tk unavailable"}
    try:
        root = tk.Tk()
    except tk.TclError:
        return {"status": "Tk window unavailable"}
    try:
        root.withdraw()
        return {"version": root.tk.call("package", "provide", "Tk"),
                "windowing_system": root.tk.call("tk", "windowingsystem")}
    finally:
        root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=data_directory())
    args = parser.parse_args()
    packages = {}
    for package in ("pyte", "pywinpty", "psutil", "Pillow"):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = None
    supported = scan_clis()
    inventory = {
        "os": platform.platform(), "python": platform.python_version(), "tk": tk_snapshot(),
        "dependencies": packages, "checkout": repo_snapshot(), "profile": profile_snapshot(args.profile),
        "tools": {name: tool_version(shutil.which(name)) for name in ("node", "git")},
        "cli": {
            name: {"path_lookup": shutil.which(name.lower()), "workspace_path": supported[name]}
            for name in ("OpenCode", "Codex")
        },
    }
    print(json.dumps(inventory, indent=2))


if __name__ == "__main__":
    main()
