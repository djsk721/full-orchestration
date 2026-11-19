"""Observe installed CLIs without dumping their output, credentials, or config."""
import json
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from orchestra.core import Invalid
from orchestra.processes import env_for_process, run
from orchestra.workspace import scan_clis

HARNESS = {"OpenCode": True, "Codex": True, "Gemini CLI": False, "Antigravity": False}
VERSION = re.compile(rb"(?m)^(?:(?:codex-cli|opencode|gemini-cli|antigravity(?: cli)?|agy)\s+)?v?(\d+\.\d+\.\d+(?:[-+][\w.-]+)?)\s*$",
                     re.IGNORECASE)


def probe(executable, arguments, directory, extra=None):
    try:
        return run([executable, *arguments], cwd=directory, env=env_for_process(extra), timeout=10, limit=120_000)
    except TimeoutError:
        return "TIMEOUT", b""
    except (Invalid, OSError):
        return "UNAVAILABLE", b""


def main():
    paths = scan_clis()
    with TemporaryDirectory(prefix="orchestra-harness-inventory-") as directory:
        for name, supported in HARNESS.items():
            executable = paths[name]
            result = {"harness": name, "execution_adapter": supported, "detected": executable is not None,
                      "startup": "NOT VERIFIED", "authentication": "NOT VERIFIED", "inference": "NOT VERIFIED"}
            if executable:
                isolated = ({f"XDG_{kind}_HOME": str(Path(directory) / kind.lower())
                             for kind in ("DATA", "CACHE", "STATE", "CONFIG")} if name == "OpenCode" else None)
                code, output = probe(executable, ["--version"], directory, isolated)
                result["startup"] = "PASS" if code == 0 else "FAIL"
                if code == 0 and (version := VERSION.search(output)):
                    result["version"] = version[1].decode("ascii")
                elif code != 0:
                    result["startup_reason"] = code
                if name == "Codex" and code == 0:
                    status, _ = probe(executable, ["login", "status"], directory)
                    result["authentication"] = "STORED CREDENTIALS REPORTED" if status == 0 else "NOT VERIFIED"
            print(json.dumps(result))
        print(json.dumps({"harness": "Managed", "execution_adapter": True,
                          "inference": "NOT VERIFIED", "loopback_fixture": "covered by integration tests"}))


if __name__ == "__main__":
    main()
