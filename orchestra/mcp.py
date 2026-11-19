from __future__ import annotations

import contextlib
import hmac
import json
import queue
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core import Invalid, digest, encode, require
from .processes import Child, env_for_process
from .runtime import http, secret

PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26")
MAX_MESSAGE = 2_000_000
SCHEMA_KEYS = frozenset(("type", "properties", "required", "additionalProperties", "items",
                         "anyOf", "allOf", "oneOf", "enum", "const", "description", "title", "default",
                         "examples", "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"))
TYPES = {"string": (str,), "object": (dict,), "array": (list,), "integer": (int,),
         "boolean": (bool,), "number": (int, float), "null": (type(None),)}


def schema_check(schema, level=0):
    require(isinstance(schema, dict) and level < 16 and schema.keys() <= SCHEMA_KEYS,
            "지원하지 않는 MCP 도구 스키마입니다.")
    kind = schema.get("type")
    require(kind is None or isinstance(kind, str) and kind in TYPES, "지원하지 않는 스키마 타입입니다.")
    props = schema.get("properties", {})
    require(isinstance(props, dict), "잘못된 스키마 속성입니다.")
    for child in props.values():
        schema_check(child, level + 1)
    needed = schema.get("required", [])
    require(isinstance(needed, list) and all(isinstance(key, str) for key in needed), "잘못된 required 스키마입니다.")
    for key in ("additionalProperties", "items"):
        if key in schema and type(schema[key]) is not bool:
            schema_check(schema[key], level + 1)
    for key in ("anyOf", "allOf", "oneOf"):
        if key in schema:
            require(isinstance(schema[key], list) and schema[key], "잘못된 조합 스키마입니다.")
            for child in schema[key]:
                schema_check(child, level + 1)
    if "enum" in schema:
        require(isinstance(schema["enum"], list) and schema["enum"], "잘못된 enum 스키마입니다.")
    for key in ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"):
        if key in schema:
            require(type(schema[key]) in (int, float), "잘못된 스키마 한도입니다.")


def matches(value, schema):
    if type(schema) is bool:
        return schema
    kind = schema.get("type")
    if kind and type(value) not in TYPES[kind]:
        return False
    if "const" in schema and encode(schema["const"]) != encode(value):
        return False
    if "enum" in schema and not any(encode(item) == encode(value) for item in schema["enum"]):
        return False
    for key in ("anyOf", "allOf", "oneOf"):
        if key in schema:
            checks = [matches(value, branch) for branch in schema[key]]
            if not {"anyOf": any(checks), "allOf": all(checks), "oneOf": sum(checks) == 1}[key]:
                return False
    if isinstance(value, dict):
        if not set(schema.get("required", [])) <= value.keys():
            return False
        props = schema.get("properties", {})
        return all(matches(item, props.get(key, schema.get("additionalProperties", True))) for key, item in value.items())
    if isinstance(value, (str, list)):
        lower, upper = ("minLength", "maxLength") if isinstance(value, str) else ("minItems", "maxItems")
        if not schema.get(lower, 0) <= len(value) <= schema.get(upper, MAX_MESSAGE):
            return False
        if isinstance(value, list):
            return all(matches(item, schema.get("items", True)) for item in value)
    if type(value) in (int, float):
        return schema.get("minimum", -float("inf")) <= value <= schema.get("maximum", float("inf"))
    return True


class MCPClient:
    def __init__(self, profile):
        self.profile = profile
        self.version = PROTOCOLS[0]
        self.session = None
        self.child = None
        self.seq = 0
        self.stream = queue.Queue(maxsize=32)
        self.closed = threading.Event()

    def __enter__(self):
        try:
            if self.profile["transport"] == "stdio":
                env = {key: secret(key) for key in self.profile.get("env", [])}
                self.child = Child(self.profile["command"], cwd=self.profile.get("cwd"),
                                   env=env_for_process(env), stdin=subprocess.PIPE)
                threading.Thread(target=self.read, daemon=True).start()
            init = self.request("initialize", {"protocolVersion": self.version, "capabilities": {},
                                              "clientInfo": {"name": "ModelOrchestration", "version": "1.0"}})
            self.version = init.get("protocolVersion")
            require(self.version in PROTOCOLS and "tools" in init.get("capabilities", {}), "MCP 도구 프로토콜을 지원하지 않습니다.")
            self.request("notifications/initialized", notify=True)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        self.closed.set()
        if self.child:
            self.child.close()
            self.child.proc.stdin.close()
            self.child.proc.stdout.close()
        elif self.session:
            with contextlib.suppress(Invalid, RuntimeError):
                http(self.profile["url"], headers=self.headers(), method="DELETE", timeout=3)

    def read(self):
        try:
            while not self.closed.is_set():
                line = self.child.proc.stdout.readline(MAX_MESSAGE + 1)
                if not line or len(line) > MAX_MESSAGE:
                    break
                self.stream.put(json.loads(line), timeout=2)
        except (OSError, ValueError, queue.Full):
            pass
        with contextlib.suppress(queue.Full):
            self.stream.put_nowait(None)

    def headers(self):
        headers = {key: secret(ref) for key, ref in self.profile.get("header_env", {}).items()}
        headers.update({"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": self.version})
        if self.session:
            headers["MCP-Session-Id"] = self.session
        return headers

    def request(self, method, args=None, notify=False):
        self.seq += 1
        message = {"jsonrpc": "2.0", "method": method}
        if args is not None:
            message["params"] = args
        if not notify:
            message["id"] = self.seq
        if self.child:
            try:
                self.child.proc.stdin.write(encode(message).encode() + b"\n")
                self.child.proc.stdin.flush()
                if notify:
                    return None
                for _ in range(32):
                    reply = self.stream.get(timeout=20)
                    require(isinstance(reply, dict), "MCP stdio 연결이 종료되었습니다.")
                    if reply.get("id") == self.seq and ("result" in reply or "error" in reply):
                        break
                else:
                    raise Invalid("MCP 메시지 순서를 확인할 수 없습니다.")
            except (OSError, queue.Empty) as exc:
                raise Invalid("MCP stdio 요청이 실패했습니다.") from exc
        else:
            _, headers, raw = http(self.profile["url"], message, self.headers(), timeout=20, limit=MAX_MESSAGE)
            if method == "initialize":
                self.session = headers.get("MCP-Session-Id")
            if notify:
                return None
            if "text/event-stream" in headers.get("Content-Type", ""):
                raw = b"\n".join(line[5:].lstrip() for line in raw.splitlines() if line.startswith(b"data:"))
            try:
                reply = json.loads(raw)
            except ValueError as exc:
                raise Invalid("MCP 응답 형식이 잘못되었습니다.") from exc
        require(isinstance(reply, dict) and reply.get("id") == self.seq and "error" not in reply
                and isinstance(reply.get("result"), dict), "MCP JSON-RPC 요청이 거절되었습니다.")
        return reply["result"]

    def catalog(self):
        catalog = {}
        cursor, seen = None, set()
        for _ in range(10):
            result = self.request("tools/list", {"cursor": cursor} if cursor else {})
            for tool in result.get("tools", []):
                name = tool.get("name")
                require(isinstance(name, str) and name not in catalog, "MCP 서버가 중복 도구를 반환했습니다.")
                catalog[name] = tool
            cursor = result.get("nextCursor")
            if not cursor:
                return catalog
            require(cursor not in seen, "MCP 페이지 커서가 반복되었습니다.")
            seen.add(cursor)
        raise Invalid("MCP 카탈로그가 지원 크기를 초과했습니다.")


def virtual_name(server, tool):
    norm = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{server}__{tool}")
    return norm if len(norm) <= 64 else norm[:50] + "_" + digest([server, tool])[:12]


def published(profile, spec, catalog, role=None, selected=None, native=False, *, agent=None):
    visible = {}
    for name, rule in spec.get("tools", {}).items():
        alias = virtual_name(profile, name)
        if name not in catalog or (selected is not None and alias not in selected):
            continue
        if native and (not rule.get("native", False) or rule["access"] != "read"):
            continue
        if rule.get("agents") and agent not in rule["agents"]:
            continue
        if role is not None and (role not in rule.get("roles", []) or rule["access"] == "write" and role != "developer"):
            continue
        tool = catalog[name]
        schema = tool.get("inputSchema")
        schema_check(schema)
        require(schema.get("type") == "object", "MCP 도구의 최상위 스키마는 object여야 합니다.")
        require(alias not in visible, "가상 MCP 도구 이름이 충돌합니다.")
        visible[alias] = (name, {"name": alias, "description": str(tool.get("description", ""))[:1200],
                                 "inputSchema": schema}, rule)
    return visible


def do_call(client, original, tool, arguments):
    require(isinstance(arguments, dict) and matches(arguments, tool["inputSchema"]), "MCP 도구 인자가 스키마와 일치하지 않습니다.")
    result = client.request("tools/call", {"name": original, "arguments": arguments})
    require(not result.get("isError"), "MCP 도구가 오류를 반환했습니다.")
    require(len(encode(result).encode()) <= 28000, "MCP 도구 결과가 허용 크기를 초과했습니다.")
    return result


class Gateway:
    def __init__(self, port, profiles, audit):
        self.profiles = profiles
        self.audit = audit
        self.port = port
        self.slots = threading.BoundedSemaphore(8)
        self.server = ThreadingHTTPServer(("127.0.0.1", port), self.handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def handler(self):
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(5)

            def log_message(self, *_):
                pass

            def do_GET(self):
                self.send_error(405)

            do_DELETE = do_GET

            def write_json(self, code, body=None):
                value = encode(body).encode() if body is not None else b""
                self.send_response(code)
                self.send_header("Content-Length", str(len(value)))
                if value:
                    self.send_header("Content-Type", "application/json")
                self.end_headers()
                if value:
                    self.wfile.write(value)

            def do_POST(self):
                expected = f"127.0.0.1:{gateway.port}"
                if self.headers.get("Host") != expected or self.headers.get("Origin") not in (None, f"http://{expected}"):
                    self.write_json(403)
                    return
                profile = self.path.removeprefix("/mcp/")
                spec = gateway.profiles.get(profile) if self.path.startswith("/mcp/") else None
                if not spec or not spec.get("gateway_token_env"):
                    self.write_json(404)
                    return
                try:
                    token = secret(spec["gateway_token_env"])
                    valid = len(token) >= 24 and hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)
                except (Invalid, TypeError):
                    valid = False
                if not valid:
                    gateway.audit(profile, "gateway.denied", {})
                    self.write_json(401)
                    return
                if not gateway.slots.acquire(blocking=False):
                    self.write_json(429)
                    return
                request_id = None
                name = None
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    require(0 < size <= MAX_MESSAGE, "MCP 요청이 너무 큽니다.")
                    msg = json.loads(self.rfile.read(size))
                    require(isinstance(msg, dict) and msg.get("jsonrpc") == "2.0", "유효하지 않은 MCP 요청입니다.")
                    request_id = msg.get("id")
                    method = msg.get("method")
                    params = msg.get("params", {})
                    require(isinstance(params, dict), "유효하지 않은 MCP 인자입니다.")
                    if request_id is None:
                        self.write_json(202)
                        return
                    if method == "initialize":
                        version = params.get("protocolVersion")
                        result = {"protocolVersion": version if version in PROTOCOLS else PROTOCOLS[0],
                                  "capabilities": {"tools": {}}, "serverInfo": {"name": "orchestra-gateway", "version": "1.0"}}
                    elif method == "ping":
                        result = {}
                    else:
                        require(method in ("tools/list", "tools/call"), "지원하지 않는 MCP 메서드입니다.")
                        with MCPClient(spec) as client:
                            available = published(profile, spec, client.catalog(), native=True)
                            if method == "tools/list":
                                result = {"tools": [row[1] for row in available.values()]}
                            else:
                                name = params.get("name")
                                require(isinstance(name, str) and name in available, "Gateway 도구 호출이 차단되었습니다.")
                                original, tool, _ = available[name]
                                result = do_call(client, original, tool, params.get("arguments", {}))
                                gateway.audit(profile, "gateway.call", {"name": name})
                    self.write_json(200, {"jsonrpc": "2.0", "id": request_id, "result": result})
                except (ValueError, OSError, RuntimeError, TypeError, KeyError):
                    gateway.audit(profile, "gateway.failed", {"name_hash": digest(name) if isinstance(name, str) else None})
                    with contextlib.suppress(OSError):
                        self.write_json(200, {"jsonrpc": "2.0", "id": request_id,
                                              "error": {"code": -32000, "message": "Request rejected by gateway"}})
                finally:
                    gateway.slots.release()

        return Handler
