"""OpenSSH transport with profile-scoped host key pinning."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import shlex
from pathlib import Path, PurePosixPath

from .core import Invalid, Temporary, atomic_bytes, encode, ident, require
from .processes import env_for_process, run

KINDS = ("agent", "key", "agent+key")
PROTOCOL = 1
MAX_REQUEST = 400_000


def remote_path(path):
    require(isinstance(path, str) and path.startswith("/") and len(path) <= 2048 and not any(ord(c) < 32 for c in path),
            "원격 Linux 절대 경로가 필요합니다.")
    require(".." not in PurePosixPath(path).parts, "원격 경로에 상위 이동을 사용할 수 없습니다.")
    return path


def validate_profile(value):
    require(isinstance(value, dict), "SSH 프로필을 확인하세요.")
    name = value.get("name")
    require(isinstance(name, str) and name.strip() and len(name) <= 100, "호스트 이름을 입력하세요.")
    host = value.get("host", "")
    require(isinstance(host, str), "SSH 호스트 주소를 확인하세요.")
    if ":" in host:
        try:
            require(ipaddress.ip_address(host).version == 6 and "%" not in host, "IPv6 주소를 확인하세요.")
        except ValueError as exc:
            raise Invalid("IPv6 주소를 확인하세요.") from exc
    else:
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,251}", host), "호스트 주소에 DNS 이름이나 IP를 입력하세요.")
    require(isinstance(value.get("user"), str) and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@\\-]{0,127}", value["user"]),
            "SSH 사용자 이름을 확인하세요.")
    require(type(value.get("port", 22)) is int and 1 <= value.get("port", 22) <= 65535, "SSH 포트는 1~65535여야 합니다.")
    require(type(value.get("timeout", 8)) is int and 1 <= value.get("timeout", 8) <= 60, "연결 제한 시간은 1~60초입니다.")
    require(value.get("auth", "agent") in KINDS, "SSH 인증 방식을 선택하세요.")
    require(value.get("os", "linux") in ("linux", "windows"), "원격 OS를 선택하세요.")
    require(not set(value).intersection({"password", "private_key_contents", "passphrase", "token"}), "SSH 자격 증명은 키 경로 또는 Agent로 지정하세요.")
    if value.get("auth") in ("key", "agent+key"):
        key = value.get("identity", "")
        require(isinstance(key, str) and key.strip() and not any(ord(c) < 32 for c in key), "SSH 개인 키 파일 경로를 입력하세요.")
        require(Path(key).expanduser().is_absolute(), "개인 키 파일은 절대 경로여야 합니다.")
    if value.get("os", "linux") == "linux":
        for key in ("directory", "worker_dir"):
            if value.get(key):
                remote_path(value[key])
        interpreter = value.get("python") or "python3"
        require(isinstance(interpreter, str), "서버의 Python 실행 경로를 확인하세요.")
        if interpreter.startswith("/"):
            remote_path(interpreter)
        else:
            require(re.fullmatch(r"python[0-9.]{0,8}", interpreter), "서버의 Python 실행 경로를 확인하세요.")
    return {"port": 22, "timeout": 8, "auth": "agent", "os": "linux", **value}


def host_label(profile):
    return profile["host"] if profile["port"] == 22 else f'[{profile["host"]}]:{profile["port"]}'


def pin_path(root, profile_id):
    return root / "ssh" / f"{ident(profile_id)}.hosts"


def fingerprint(blob):
    return "SHA256:" + base64.b64encode(hashlib.sha256(base64.b64decode(blob, validate=True)).digest()).decode().rstrip("=")


def scan_keys(profile):
    profile = validate_profile(profile)
    code, raw = run(["ssh-keyscan", "-T", str(profile["timeout"]), "-p", str(profile["port"]),
                     "-t", "ed25519,ecdsa,rsa", "--", profile["host"]], env=ssh_env(), timeout=profile["timeout"] + 5,
                    limit=40000)
    keys = {}
    for line in raw.decode("ascii", errors="replace").splitlines():
        fields = line.split()
        if len(fields) != 3 or fields[1] not in ("ssh-ed25519", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384",
                                                  "ecdsa-sha2-nistp521", "ssh-rsa"):
            continue
        try:
            mark = fingerprint(fields[2])
        except ValueError:
            continue
        keys[mark] = (fields[1], fields[2])
    require(not code or keys, "SSH 호스트 키를 읽을 수 없습니다.")
    require(keys, "SSH 서버가 공개 호스트 키를 반환하지 않았습니다.")
    return keys


def pinned_key(root, profile_id, profile):
    path = pin_path(root, profile_id)
    if not path.is_file():
        return None
    try:
        host, algorithm, blob = path.read_text(encoding="ascii").strip().split()
        return (algorithm, fingerprint(blob)) if host == host_label(profile) else None
    except (ValueError, OSError):
        return None


def trust_key(root, profile_id, profile, selected, scanned):
    profile = validate_profile(profile)
    require(selected in scanned, "독립 경로에서 확인한 호스트 지문을 정확히 입력하세요.")
    algorithm, key = scanned[selected]
    require(fingerprint(key) == selected and re.fullmatch(r"[A-Za-z0-9_.-]+", algorithm), "호스트 공개 키 형식이 잘못되었습니다.")
    atomic_bytes(pin_path(root, profile_id), f"{host_label(profile)} {algorithm} {key}\n".encode("ascii"))


def ssh_env():
    return env_for_process({k: os.environ[k] for k in ("SSH_AUTH_SOCK",) if k in os.environ})


def ssh_arguments(root, profile_id, profile, *, terminal=False, command=None):
    profile = validate_profile(profile)
    require(pinned_key(root, profile_id, profile), "호스트 키를 확인하고 신뢰 지문을 등록하세요.")
    config = root / "ssh" / "client.conf"
    if not config.is_file():
        atomic_bytes(config, b"# Managed by Model Orchestration\n")
    path = pin_path(root, profile_id).resolve().as_posix().replace("%", "%%").replace('"', '\\"')
    options = [
        "StrictHostKeyChecking=yes", f'UserKnownHostsFile="{path}"', "GlobalKnownHostsFile=none",
        "UpdateHostKeys=no", "ForwardAgent=no", "ClearAllForwardings=yes", "ProxyCommand=none", "ProxyJump=none",
        "PasswordAuthentication=no", "KbdInteractiveAuthentication=no", "PreferredAuthentications=publickey",
        f'ConnectTimeout={profile["timeout"]}', "ServerAliveInterval=10", "ServerAliveCountMax=3",
        f"BatchMode={'no' if terminal else 'yes'}",
    ]
    args = ["ssh", "-F", str(config)]
    for option in options:
        args.extend(("-o", option))
    if profile["auth"] in ("key", "agent+key"):
        identity = Path(profile["identity"]).expanduser()
        require(identity.is_file(), "SSH 키 파일을 찾을 수 없습니다.")
        args.extend(("-o", "IdentitiesOnly=yes", "-i", str(identity)))
    if profile["auth"] == "key":
        args.extend(("-o", "IdentityAgent=none"))
    args.extend(("-tt" if terminal else "-T", "-p", str(profile["port"]), "-l", profile["user"], "--", profile["host"]))
    if command:
        args.append(command)
    return args


class SSHClient:
    def __init__(self, root, profile_id, profile):
        self.root, self.id, self.profile = root, profile_id, validate_profile(profile)

    def terminal(self, directory=None):
        command = None
        directory = directory or self.profile.get("directory")
        if directory and self.profile["os"] == "linux":
            command = f"cd -- {shlex.quote(remote_path(directory))} && exec \"${{SHELL:-/bin/sh}}\" -l"
        return ssh_arguments(self.root, self.id, self.profile, terminal=True, command=command)

    def _command(self, expression, *, payload=None, timeout=45):
        args = ssh_arguments(self.root, self.id, self.profile, command=expression)
        code, raw = run(args, env=ssh_env(), timeout=max(timeout, self.profile["timeout"] + 3),
                        input_bytes=payload, limit=2_000_000)
        if code:
            plain = raw.decode("utf-8", errors="replace").lower()
            if any(text in plain for text in ("host key verification failed", "remote host identification has changed", "no matching host key")):
                raise Invalid("SSH 호스트 키가 일치하지 않습니다. 신뢰 지문을 다시 확인하세요.")
            if "permission denied" in plain:
                raise Invalid("SSH 공개 키 인증에 실패했습니다. 키 경로 또는 SSH Agent를 확인하세요.")
            raise Temporary(f"SSH 명령 실패 (종료 코드 {code}). 연결과 Worker 설치 경로를 확인하세요.")
        return raw

    def test(self):
        if self.profile["os"] == "windows":
            return {"os": "Windows", "output": self._command("cmd.exe /c ver").decode("utf-8", errors="replace").strip()[:240]}
        raw = self._command("uname -s")
        return {"os": raw.decode("utf-8", errors="replace").strip()[:64]}

    def call(self, method, **params):
        require(self.profile["os"] == "linux", "Remote Worker는 Linux 실행 환경을 지원합니다.")
        directory = remote_path(self.profile.get("worker_dir"))
        request = encode({"version": PROTOCOL, "method": method, "params": params}).encode()
        require(len(request) <= MAX_REQUEST, "원격 작업 요청이 허용 크기를 초과했습니다.")
        python = shlex.quote(self.profile.get("python") or "python3")
        response = self._command(f"cd -- {shlex.quote(directory)} && exec {python} -m orchestra.remote",
                                 payload=request, timeout=45)
        try:
            value = json.loads(response)
        except (ValueError, UnicodeError) as exc:
            raise Invalid("Remote Worker가 호환되는 응답을 반환하지 않았습니다.") from exc
        require(isinstance(value, dict) and value.get("version") == PROTOCOL, "원격 Worker 프로토콜 버전이 일치하지 않습니다.")
        require(value.get("ok"), value.get("error", "원격 Worker 요청이 거절되었습니다."))
        return value["result"]
