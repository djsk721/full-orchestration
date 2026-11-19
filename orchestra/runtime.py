from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .core import Invalid, Stopped, Temporary, digest, require, settings
from .processes import Child, env_for_process


@dataclass(frozen=True)
class Route:
    model_id: str
    runtime_id: str | None
    harness_id: str
    model: dict
    runtime: dict | None
    harness: dict

    def event(self, task):
        return {"model_id": self.model_id, "runtime_id": self.runtime_id, "harness_id": self.harness_id,
                "agent_id": task["role"] + "/" + task["id"], "worktree_id": task["id"]}


def routes(config, task):
    options = []
    for name, model in config["models"].items():
        if task.get("model", name) != name or task["role"] not in model.get("roles", [task["role"]]):
            continue
        runtime_id = model.get("runtime")
        runtime = config["runtimes"].get(runtime_id)
        if runtime and runtime.get("context", 32768) < task.get("min_context", 1024):
            continue
        for harness_id in model.get("harnesses", ["managed"]):
            if task.get("harness", harness_id) != harness_id:
                continue
            harness = config["harnesses"][harness_id]
            if harness["kind"] != "managed" and not harness.get("trusted"):
                continue
            if task.get("tools") and harness["kind"] != "managed":
                continue
            score = (model.get("quality", 0) * 3 + model.get("reliability", 0) * 2
                     + model.get("tool_score", 0) * int(bool(task.get("tools") or task.get("paths"))) * 2
                     - model.get("cost", 0))
            options.append((-score, name, harness_id, Route(name, runtime_id, harness_id, model, runtime, harness)))
    return [row[-1] for row in sorted(options)]


def checked_url(url, *, local_only=False):
    parsed = urlsplit(url)
    require(parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password
            and not parsed.fragment and not parsed.query, "인증정보나 쿼리가 없는 HTTP(S) 주소가 필요합니다.")
    loopback = parsed.hostname in ("127.0.0.1", "::1", "localhost")
    require(not local_only or loopback, "모델 Runtime의 HTTP 주소는 루프백으로 제한됩니다.")
    require(parsed.scheme == "https" or loopback, "외부 연결에는 HTTPS가 필요합니다.")
    return parsed


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def http(url, data=None, headers=None, timeout=60, limit=4_000_000, method=None, *, local_only=False):
    checked_url(url, local_only=local_only)
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **(headers or {})},
                                     method=method)
        with HTTP.open(req, timeout=timeout) as response:
            if "text/event-stream" in response.headers.get("Content-Type", ""):
                lines, used = [], 0
                for line in response:
                    used += len(line)
                    require(used <= limit, "HTTP 응답이 허용 크기를 초과했습니다.")
                    lines.append(line)
                    if not line.strip():
                        data_lines = [row[5:].strip() for row in lines if row.startswith(b"data:")]
                        if data_lines:
                            try:
                                value = json.loads(b"\n".join(data_lines))
                            except ValueError:
                                value = {}
                            if isinstance(value, dict) and ("result" in value or "error" in value):
                                return response.status, response.headers, b"".join(lines)
                        lines.clear()
                return response.status, response.headers, b"".join(lines)
            raw = response.read(limit + 1)
            require(len(raw) <= limit, "HTTP 응답이 허용 크기를 초과했습니다.")
            return response.status, response.headers, raw
    except urllib.error.HTTPError as exc:
        if exc.code in (408, 429) or exc.code >= 500:
            raise Temporary(f"HTTP 서버 오류 ({exc.code}).") from exc
        raise Invalid(f"HTTP 요청이 거절되었습니다 ({exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise Temporary("HTTP 서버에 연결하지 못했습니다.") from exc


def secret(ref):
    value = os.environ.get(ref, "") if isinstance(ref, str) else ""
    require(bool(value), "자격증명 환경 변수를 찾을 수 없습니다.")
    return value


class RuntimePool:
    def __init__(self):
        self.lock = threading.Condition()
        self.active = {}

    @contextmanager
    def reserve(self, route, config, stop):
        if not route.runtime:
            yield None
            return
        runtime = route.runtime
        key = (route.runtime_id, digest(runtime))
        cfg = settings(config)
        endpoint = runtime.get("url", "http://127.0.0.1:8080").rstrip("/").removesuffix("/v1")
        gpu, ram = runtime.get("gpu_mb", 0), runtime.get("ram_mb", 0)
        require(gpu <= cfg["gpu_budget_mb"] and (not cfg["ram_budget_mb"] or ram <= cfg["ram_budget_mb"]),
                "Runtime 예약 요청이 자원 한도를 초과했습니다.")
        with self.lock:
            while True:
                if stop():
                    raise Stopped("Runtime 예약 중 중지되었습니다.")
                current = self.active.get(key)
                if current and current["count"] < runtime.get("slots", 1):
                    current["count"] += 1
                    break
                used_gpu = sum(item["gpu"] for item in self.active.values())
                used_ram = sum(item["ram"] for item in self.active.values())
                if (not current and not any(item["endpoint"] == endpoint for item in self.active.values())
                        and used_gpu + gpu <= cfg["gpu_budget_mb"]
                        and (not cfg["ram_budget_mb"] or used_ram + ram <= cfg["ram_budget_mb"])):
                    current = {"count": 1, "gpu": gpu, "ram": ram, "endpoint": endpoint,
                               "client": RuntimeClient(runtime), "start_lock": threading.Lock()}
                    self.active[key] = current
                    break
                self.lock.wait(.2)
        try:
            with current["start_lock"]:
                current["client"].start(route.model["model"], stop)
            yield current["client"]
        finally:
            with self.lock:
                current["count"] -= 1
                if not current["count"]:
                    self.active.pop(key)
                    current["client"].close()
                self.lock.notify_all()


class RuntimeClient:
    def __init__(self, config):
        self.config = config
        self.url = config.get("url", "http://127.0.0.1:8080").rstrip("/")
        self.parsed = checked_url(self.url, local_only=True)
        self.child = None
        self.headers = {}
        if config.get("auth_env"):
            self.headers["Authorization"] = "Bearer " + secret(config["auth_env"])
        self.key = None

    def start(self, model, stop):
        if self.config.get("ownership") != "managed":
            return
        if self.child and self.child.proc.poll() is None:
            require(self.key == model, "실행 중인 Managed Runtime의 모델이 일치하지 않습니다.")
            return
        config = self.config
        require(self.parsed.scheme == "http" and self.parsed.hostname == "127.0.0.1" and self.parsed.port
                and self.parsed.path in ("", "/v1") and not self.headers,
                "Managed llama.cpp URL은 인증이 없는 127.0.0.1 HTTP 주소와 고정 포트가 필요합니다.")
        model_path = Path(config["model_path"]).expanduser().resolve()
        require(model_path.is_file(), "GGUF 모델 파일을 찾을 수 없습니다.")
        try:
            self.request("/health", timeout=1)
        except Temporary:
            pass
        except Invalid:
            raise Invalid("Managed Runtime의 포트가 이미 사용 중입니다.") from None
        else:
            raise Invalid("Managed Runtime의 포트가 이미 사용 중입니다.")
        argv = [config["executable"], "--model", str(model_path), "--host", "127.0.0.1",
                "--port", str(self.parsed.port), "--alias", model, "--ctx-size",
                str(config.get("context", 32768) * config.get("slots", 1)),
                "--parallel", str(config.get("slots", 1)), "--n-gpu-layers", str(config.get("gpu_layers", 0)), "--jinja"]
        if config.get("gpu_layers", 0) == 0:
            argv.extend(("--device", "none", "--no-kv-offload", "--no-op-offload"))
        self.child = Child(argv, env=env_for_process(), stdout=subprocess.DEVNULL)
        self.key = model
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if stop():
                raise Stopped("Runtime 시작 중 중지되었습니다.")
            if self.child.proc.poll() is not None:
                raise Invalid("Managed llama.cpp 프로세스가 종료되었습니다.")
            try:
                self.request("/health", timeout=1)
                return
            except Temporary:
                time.sleep(.25)
        raise Temporary("Managed Runtime 시작 시간이 초과되었습니다.")

    def close(self):
        if self.child:
            self.child.close()
            self.child = None

    def request(self, path, data=None, timeout=60):
        root = self.url.removesuffix("/v1")
        _, _, raw = http(root + path, data, self.headers, timeout, local_only=True)
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise Invalid("Runtime 응답이 JSON 형식이 아닙니다.") from exc

    def chat(self, model, messages, tools, max_output, *, probe=False):
        body = {"model": model, "messages": messages, "max_tokens": max_output, "temperature": 0}
        if tools:
            body["tools"] = tools
        response = self.request("/v1/chat/completions", body, timeout=30 if probe else 120)
        try:
            choice = response["choices"][0]
            require(response["model"] == model, "응답 모델 ID가 요청 모델과 다릅니다.")
            message = choice["message"]
            require(isinstance(message, dict), "잘못된 모델 응답입니다.")
        except (KeyError, IndexError, TypeError) as exc:
            raise Invalid("잘못된 모델 응답입니다.") from exc
        return message, response.get("usage"), choice.get("finish_reason")

    def probe(self, route, task, emit):
        model = route.model["model"]
        runtime = self.config
        desired = {"model": model, "context": runtime.get("context", 32768),
                   "max_output": runtime.get("max_output", 2048)}
        effective = {"model": None, "context": None, "max_output": None, "slots": None, "template_hash": None}
        snapshot = {"desired": desired, "effective": effective, "validated": None,
                    "runtime_kind": runtime["kind"], "ownership": runtime.get("ownership", "attached"),
                    "config_hash": digest(runtime), "process_id": self.child.proc.pid if self.child else None}
        try:
            models = self.request("/v1/models")
            effective["model"] = next((item["id"] for item in models.get("data", []) if item.get("id") == model), None)
            require(effective["model"] == model, "Runtime에서 요청 모델 ID를 찾을 수 없습니다.")
            if runtime["kind"] == "llama.cpp":
                props = self.request("/props")
                generation = props.get("default_generation_settings", {})
                effective.update(context=generation.get("n_ctx"), slots=props.get("total_slots"),
                                 template_hash=digest(props["chat_template"]) if props.get("chat_template") else None)
                cap = generation.get("params", {}).get("n_predict")
                effective["max_output"] = cap if type(cap) is int and cap > 0 else None
                observed_model = props.get("model_alias")
                require(not observed_model or observed_model == model, "llama.cpp 모델 별칭이 요청값과 다릅니다.")
            elif runtime["kind"] == "ollama":
                running = self.request("/api/ps")
                item = next((entry for entry in running.get("models", []) if entry.get("name") == model), {})
                effective["context"] = item.get("context_length")
            else:
                item = next(entry for entry in models["data"] if entry["id"] == model)
                effective["context"] = item.get("context_length") or item.get("max_model_len")
                effective["max_output"] = item.get("max_output_tokens")
            context = effective["context"]
            require(type(context) is int and context >= task.get("min_context", 1024), "Runtime 실제 Context를 검증할 수 없거나 최소 한도 미만입니다.")
            slots = effective["slots"]
            require((type(slots) is int and slots >= runtime.get("slots", 1)) or
                    (slots is None and runtime.get("slots", 1) == 1), "Runtime 실제 추론 슬롯이 부족하거나 확인되지 않았습니다.")
            context = min(context, desired["context"])
            max_output = min(desired["max_output"], context // 4)
            cap = effective["max_output"]
            if type(cap) is int and cap > 0:
                max_output = min(max_output, cap)
            verify_tools = bool(route.harness["kind"] == "managed" or task.get("tools") or task.get("paths") or runtime.get("tool_probe"))
            if verify_tools:
                tool = {"type": "function", "function": {"name": "orchestra_probe", "description": "Read-only handshake.",
                                                          "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}}
                answer, usage, _ = self.chat(model, [{"role": "user", "content": "Call orchestra_probe with {} now. Do not answer in text."}],
                                            [tool], min(max_output, 128), probe=True)
                emit("model.usage", usage_payload(usage, "probe"))
                calls = answer.get("tool_calls") or []
                require(isinstance(calls, list) and len(calls) == 1 and calls[0].get("function", {}).get("name") == "orchestra_probe",
                        "읽기 전용 Tool Calling Probe가 실패했습니다.")
                args = calls[0]["function"].get("arguments")
                try:
                    args = json.loads(args) if isinstance(args, str) else args
                except ValueError:
                    args = None
                require(args == {}, "Tool Calling Probe 인자가 잘못되었습니다.")
            snapshot["validated"] = {"model": model, "context": context, "request_max_output": max_output,
                                     "tool_probe": verify_tools, "compaction_owner": route.harness_id}
        finally:
            emit("runtime.snapshot", snapshot)
        return snapshot["validated"]


def usage_payload(usage, phase):
    usage = usage if isinstance(usage, dict) else {}
    keys = ("prompt_tokens", "completion_tokens", "total_tokens", "cached_input_tokens")
    return {"phase": phase, **{key: usage.get(key) if type(usage.get(key)) is int else None for key in keys}}
