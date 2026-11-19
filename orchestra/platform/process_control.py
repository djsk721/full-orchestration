"""Select native process and lock operations at the application boundary."""
from contextlib import contextmanager
import os


def process_backend():
    if os.name == "nt":
        from . import processes_windows
        return processes_windows
    from . import processes_posix
    return processes_posix


@contextmanager
def process_lock(path):
    native = process_backend()
    with path.open("a+b") as file:
        if not file.tell():
            file.write(b"\0")
            file.flush()
        file.seek(0)
        try:
            native.acquire_lock(file)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            native.release_lock(file)
