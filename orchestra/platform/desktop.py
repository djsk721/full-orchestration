"""OS integration needed when a native desktop shell is in use."""
import contextlib
import os
import subprocess
import sys


def prepare_dpi():
    if os.name == "nt":
        import ctypes
        with contextlib.suppress(AttributeError, OSError):
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


def open_directory(path):
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
