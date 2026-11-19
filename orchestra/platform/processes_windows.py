"""Win32 Job Object containment and byte-range locks."""
from __future__ import annotations

import ctypes
import msvcrt
import subprocess
from pathlib import Path

from ..core import Invalid

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

class NativeChild:
    def __init__(self, argv, **options):
        # Attach the suspended process before any descendant can be launched.
        self.process = subprocess.Popen(argv, creationflags=subprocess.CREATE_NO_WINDOW | 0x00000004, **options)
        handle = k32.CreateJobObjectW(None, None)
        limits = ExtendedLimit()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not (handle and k32.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits))
                and k32.AssignProcessToJobObject(handle, int(self.process._handle)) and resume_child(self.process.pid)):
            if handle:
                k32.CloseHandle(handle)
            if self.process.poll() is None:
                try:
                    self.process.kill()
                except PermissionError:
                    # A Job Object close may have begun process termination.
                    pass
            self.process.wait()
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                if stream:
                    stream.close()
            raise Invalid("Windows Job Object에서 자식 프로세스를 시작하지 못했습니다.")
        self.handle = handle

    def terminate_tree(self):
        if self.handle:
            k32.CloseHandle(self.handle)
            self.handle = None


def acquire_lock(file):
    msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)


def release_lock(file):
    file.seek(0)
    msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)


def detached_options():
    return {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}


def validate_executable(path):
    if Path(path).suffix.lower() not in (".exe", ".com"):
        raise Invalid("Windows에서는 .exe 실행 파일을 사용하세요. Python 스크립트는 python.exe를 통해 실행할 수 있습니다.")
    return path
