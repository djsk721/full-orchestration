from __future__ import annotations

import ctypes
import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

from .core import Invalid, Stopped, require


def env_for_process(extra=None, inherit=False):
    if inherit:
        return os.environ.copy() | (extra or {})
    common = {"path", "systemroot", "windir", "pathext", "comspec", "temp", "tmp", "tmpdir",
              "lang", "lc_all", "userprofile", "home", "localappdata", "appdata", "xdg_config_home"}
    return {key: val for key, val in os.environ.items() if key.lower() in common} | (extra or {})


def executable(value, env=None):
    path = shutil.which(value, path=(env or os.environ).get("PATH"))
    require(path, f"실행 파일을 찾을 수 없습니다. {Path(value).name}")
    if os.name == "nt":
        require(Path(path).suffix.lower() in (".exe", ".com"),
                "Windows에서는 .exe 실행 파일을 사용하세요. Python 스크립트는 python.exe를 통해 실행할 수 있습니다.")
    return path


if os.name == "nt":
    from ctypes import wintypes as w

    class BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", w.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", w.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD),
        ]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimit), ("IoInfo", ctypes.c_uint64 * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.argtypes = [w.LPVOID, w.LPCWSTR]
    k32.CreateJobObjectW.restype = w.HANDLE
    k32.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD]
    k32.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    k32.CloseHandle.argtypes = [w.HANDLE]

    class ThreadEntry(ctypes.Structure):
        _fields_ = [(key, w.DWORD) for key in ("size", "usage", "tid", "owner")] + [
            ("base_priority", w.LONG), ("delta_priority", w.LONG), ("flags", w.DWORD),
        ]

    k32.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    k32.CreateToolhelp32Snapshot.restype = w.HANDLE
    k32.Thread32First.argtypes = [w.HANDLE, ctypes.POINTER(ThreadEntry)]
    k32.Thread32Next.argtypes = [w.HANDLE, ctypes.POINTER(ThreadEntry)]
    k32.OpenThread.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k32.OpenThread.restype = w.HANDLE
    k32.ResumeThread.argtypes = [w.HANDLE]
    k32.ResumeThread.restype = w.DWORD

    def resume_child(pid):
        snapshot = k32.CreateToolhelp32Snapshot(0x00000004, 0)  # TH32CS_SNAPTHREAD
        if snapshot == ctypes.c_void_p(-1).value:
            return False
        entry = ThreadEntry(size=ctypes.sizeof(ThreadEntry))
        try:
            more = k32.Thread32First(snapshot, ctypes.byref(entry))
            while more:
                if entry.owner == pid:
                    thread = k32.OpenThread(0x0002, False, entry.tid)  # THREAD_SUSPEND_RESUME
                    if not thread:
                        return False
                    try:
                        return k32.ResumeThread(thread) == 1
                    finally:
                        k32.CloseHandle(thread)
                entry.size = ctypes.sizeof(ThreadEntry)
                more = k32.Thread32Next(snapshot, ctypes.byref(entry))
            return False
        finally:
            k32.CloseHandle(snapshot)


class Child:
    def __init__(self, argv, *, cwd=None, env=None, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                 stderr=subprocess.DEVNULL):
        argv = [executable(argv[0], env), *argv[1:]]
        self.job = None
        # Suspend the first thread so descendants cannot start before Job Object assignment.
        flags = subprocess.CREATE_NO_WINDOW | 0x00000004 if os.name == "nt" else 0
        self.proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=stdin, stdout=stdout, stderr=stderr,
                                     creationflags=flags,
                                     start_new_session=os.name != "nt")
        if os.name == "nt":
            handle = k32.CreateJobObjectW(None, None)
            limits = ExtendedLimit()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not (handle and k32.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits))
                    and k32.AssignProcessToJobObject(handle, int(self.proc._handle)) and resume_child(self.proc.pid)):
                if handle:
                    k32.CloseHandle(handle)
                if self.proc.poll() is None:
                    try:
                        self.proc.kill()
                    except PermissionError:
                        # A Job Object close may have begun process termination.
                        pass
                self.proc.wait()
                for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
                    if stream:
                        stream.close()
                raise Invalid("Windows Job Object에서 자식 프로세스를 시작하지 못했습니다.")
            self.job = handle

    def close(self):
        if os.name == "nt":
            if self.job:
                k32.CloseHandle(self.job)
                self.job = None
        else:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)


def run(argv, *, cwd=None, env=None, timeout=60, stop=None, input_bytes=None, limit=4_000_000):
    child = Child(argv, cwd=cwd, env=env, stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
                  stderr=subprocess.STDOUT)
    output = bytearray()
    over_limit = threading.Event()

    def read():
        while block := child.proc.stdout.read1(65536):
            if len(output) + len(block) > limit:
                over_limit.set()
                break
            output.extend(block)

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
            if time.monotonic() >= until:
                raise TimeoutError("프로세스 실행 시간이 초과되었습니다.")
            reader.join(.05) if reader.is_alive() else time.sleep(.05)
        if over_limit.is_set():
            raise Invalid("프로세스 출력이 허용 크기를 초과했습니다.")
        return child.proc.returncode, bytes(output)
    finally:
        child.close()
        reader.join(1)
        if not reader.is_alive():
            child.proc.stdout.close()
