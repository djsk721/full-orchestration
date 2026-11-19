"""Collect a redacted Codex CLI smoke record from a dedicated QA profile."""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from orchestra.core import Invalid
from orchestra.processes import env_for_process, run

MARKER = "ORCHESTRA_RC_OK"


def credential_file_present(path):
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        return False
    tokens = value.get("tokens")
    api_key = value.get("OPENAI_API_KEY")
    return (isinstance(api_key, str) and bool(api_key.strip())) or (
        isinstance(tokens, dict) and isinstance(tokens.get("access_token"), str)
        and bool(tokens["access_token"].strip()))


def parse_record(output, result):
    completed = False
    reply = False
    failed = False
    token_keys = ("input_tokens", "cached_input_tokens", "output_tokens")
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if not isinstance(value, dict):
            continue
        kind = value.get("type")
        if kind == "turn.completed":
            completed = True
            usage = value.get("usage") or {}
            if isinstance(usage, dict):
                result["usage"] = {key: usage[key] for key in token_keys
                                   if type(usage.get(key)) is int and usage[key] >= 0}
            model = value.get("model")
            if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,90}", model):
                result["reported_model"] = model
        elif kind == "item.completed":
            item = value.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                reply |= item.get("text") == MARKER
        elif kind in ("error", "turn.failed"):
            failed = True
    result["completed"] = completed
    result["expected_reply_observed"] = reply
    return completed and reply and not failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path, help="Existing test-only Codex home with file-backed authentication")
    parser.add_argument("--model", required=True)
    parser.add_argument("--execute", action="store_true", help="Run one authorized synthetic inference")
    parser.add_argument("--report", type=Path, help="New file for the redacted inference record")
    args = parser.parse_args()
    profile = args.profile.expanduser().resolve()
    personal = {Path.home().joinpath(".codex").resolve()}
    if configured := os.environ.get("CODEX_HOME"):
        personal.add(Path(configured).expanduser().resolve())
    if not profile.is_dir() or profile in personal:
        parser.error("Select an existing dedicated Codex directory separate from the active profile.")
    auth = profile / "auth.json"
    if auth.is_symlink() or not auth.is_file():
        parser.error("The dedicated directory must contain a regular, file-backed Codex login.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,89}", args.model):
        parser.error("Select a concrete model identifier.")
    if args.execute and (not args.report or args.report.exists() or not args.report.parent.is_dir()):
        parser.error("Choose a new report file in an existing test directory.")
    executable = shutil.which("codex")
    if not executable:
        parser.error("Codex is not installed.")

    result = {"execution_id": uuid.uuid4().hex, "provider": "OpenAI", "harness": "Codex CLI",
              "requested_model": args.model, "reported_model": None, "usage": None,
              "status": "NOT VERIFIED", "completed": False, "expected_reply_observed": False}
    with tempfile.TemporaryDirectory(prefix="orchestra-codex-qa-") as directory:
        workspace = Path(directory) / "empty"
        workspace.mkdir()
        credential_store = Path(directory) / "cli-profile"
        credential_store.mkdir(mode=0o700)
        env = env_for_process({"CODEX_HOME": str(credential_store)})
        try:
            # OAuth refreshes may update the test copy. The supplied profile remains untouched.
            copied_auth = credential_store / "auth.json"
            shutil.copyfile(auth, copied_auth)
            copied_auth.chmod(0o600)
            version_code, version_text = run([executable, "--version"], cwd=workspace, env=env, timeout=10)
            version = re.search(rb"(?m)^codex-cli (\d+\.\d+\.\d+(?:[-+][\w.-]+)?)\s*$", version_text)
            result["startup"] = "PASS" if version_code == 0 and version else "FAIL"
            if version:
                result["version"] = version[1].decode("ascii")
            login, _ = run([executable, "login", "status"], cwd=workspace, env=env, timeout=10)
            result["authentication"] = ("STORED CREDENTIALS REPORTED"
                                        if login == 0 and credential_file_present(copied_auth) else "NOT VERIFIED")
        except (Invalid, OSError, ValueError):
            result["preflight_error"] = "CLI unavailable or timed out"
        if not args.execute or result.get("startup") != "PASS" or result.get("authentication") != "STORED CREDENTIALS REPORTED":
            print(json.dumps(result))
            return 1 if args.execute else 0

        argv = [executable, "--ask-for-approval", "never", "exec", "--json", "--ephemeral",
                "--ignore-user-config", "--skip-git-repo-check", "--sandbox", "read-only",
                "-c", 'model_provider="openai"', "-c", 'web_search="disabled"',
                "--model", args.model, "-"]
        started = time.monotonic()
        with args.report.open("x", encoding="utf-8") as report:
            try:
                code, output = run(argv, cwd=workspace, env=env, timeout=90, limit=400_000,
                                   input_bytes=f"Reply with exactly {MARKER}. Do not use any tools.\n".encode())
                result["exit_code"] = code
                complete = parse_record(output, result)
                matching_model = result["reported_model"] in (None, args.model)
                result["status"] = "PASS" if code == 0 and complete and matching_model else "FAIL"
            except KeyboardInterrupt:
                result["status"] = "CANCELLED"
            except TimeoutError:
                result["status"] = "TIMEOUT"
            except (Invalid, OSError):
                result["status"] = "FAIL"
            result["duration_seconds"] = round(time.monotonic() - started, 3)
            json.dump(result, report, indent=2)
            report.write("\n")
    print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
