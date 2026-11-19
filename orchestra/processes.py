from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .core import Invalid, Stopped, require
from .platform.process_control import process_backend


def env_for_process(extra=None, inherit=False):
    if inherit:
        return os.environ.copy() | (extra or {})
    common = {"path", "systemroot", "windir", "pathext", "comspec", "temp", "tmp", "tmpdir",
              "lang", "lc_all", "userprofile", "home", "localappdata", "appdata",
              "xdg_config_home", "xdg_data_home", "xdg_cache_home", "xdg_state_home"}
    return {key: val for key, val in os.environ.items() if key.lower() in common} | (extra or {})


def executable(value, env=None):
    path = shutil.which(value, path=(env or os.environ).get("PATH"))
    require(path, f"실행 파일을 찾을 수 없습니다. {Path(value).name}")
    return process_backend().validate_executable(path)


class Child:
    def __init__(self, argv, *, cwd=None, env=None, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                 stderr=subprocess.DEVNULL):
        native = process_backend()
        self.child = native.NativeChild([executable(argv[0], env), *argv[1:]],
                                        cwd=cwd, env=env, stdin=stdin, stdout=stdout, stderr=stderr)
        self.proc = self.child.process

    def close(self):
        self.child.terminate_tree()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)


def run(argv, *, cwd=None, env=None, timeout=60, stop=None, input_bytes=None, limit=4_000_000, on_line=None):
    child = Child(argv, cwd=cwd, env=env, stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
                  stderr=subprocess.STDOUT)
    output = bytearray()
    over_limit = threading.Event()
    read_error = []

    def read():
        consumed = 0
        try:
            while block := child.proc.stdout.read1(65536):
                if len(output) + len(block) > limit:
                    over_limit.set()
                    break
                output.extend(block)
                if on_line:
                    while (end := output.find(b"\n", consumed)) != -1:
                        on_line(bytes(output[consumed:end]))
                        consumed = end + 1
            if on_line and consumed < len(output):
                on_line(bytes(output[consumed:]))
        except (OSError, RuntimeError, ValueError) as exc:
            read_error.append(exc)

    def write():
        try:
            with child.proc.stdin as pipe:
                pipe.write(input_bytes)
        except (BrokenPipeError, OSError):
            pass

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    if input_bytes is not None:
        threading.Thread(target=write, daemon=True).start()
    until = time.monotonic() + timeout
    try:
        while child.proc.poll() is None or reader.is_alive():
            if stop and stop():
                raise Stopped("중지 요청을 받았습니다.")
            if over_limit.is_set():
                raise Invalid("프로세스 출력이 허용 크기를 초과했습니다.")
            if read_error:
                raise Invalid("프로세스 출력을 처리하지 못했습니다.") from read_error[0]
            if time.monotonic() >= until:
                raise TimeoutError("프로세스 실행 시간이 초과되었습니다.")
            reader.join(.05) if reader.is_alive() else time.sleep(.05)
        if over_limit.is_set():
            raise Invalid("프로세스 출력이 허용 크기를 초과했습니다.")
        if read_error:
            raise Invalid("프로세스 출력을 처리하지 못했습니다.") from read_error[0]
        return child.proc.returncode, bytes(output)
    finally:
        child.close()
        reader.join(1)
        if not reader.is_alive():
            child.proc.stdout.close()
