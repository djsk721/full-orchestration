"""Parse and render user-entered QA arguments using the local OS convention."""
import os
import shlex

from ..core import require


def parse_commands(text):
    commands = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if os.name == "nt":
            # Use Windows' native argv quoting rules. Prefix a dummy executable because
            # CommandLineToArgvW applies different rules to the very first word.
            import ctypes
            from ctypes import wintypes
            shell = ctypes.WinDLL("shell32")
            kernel = ctypes.WinDLL("kernel32")
            shell.CommandLineToArgvW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int))
            shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
            kernel.LocalFree.argtypes = (wintypes.HLOCAL,)
            kernel.LocalFree.restype = wintypes.HLOCAL
            count = ctypes.c_int()
            items = shell.CommandLineToArgvW("orchestra " + line.strip(), ctypes.byref(count))
            require(items, "QA 명령을 분리할 수 없습니다.")
            try:
                commands.append([items[i] for i in range(1, count.value)])
            finally:
                kernel.LocalFree(ctypes.cast(items, wintypes.HLOCAL))
        else:
            commands.append(shlex.split(line))
    return commands


def format_commands(commands):
    if os.name == "nt":
        from subprocess import list2cmdline
        return "\n".join(list2cmdline(command) for command in commands)
    return "\n".join(shlex.join(command) for command in commands)


