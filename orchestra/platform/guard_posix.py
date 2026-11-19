"""Keep a managed process group tied to its controller's lifetime."""
from contextlib import suppress
import os
import select
import signal
import subprocess
import sys


def supervise(descriptor, argv):
    # Only the controller owns the write end. A hard exit closes it in the kernel.
    lifetime = select.poll()
    lifetime.register(descriptor)
    if lifetime.poll(0):
        return 1
    try:
        payload = subprocess.Popen(argv, process_group=0)
    except OSError as error:
        print(f"Could not start managed process (errno {error.errno}).", file=sys.stderr)
        return 126
    try:
        while payload.poll() is None:
            if lifetime.poll(50):
                break
    finally:
        # Also clean up descendants when a command exits before its children.
        with suppress(ProcessLookupError):
            os.killpg(payload.pid, signal.SIGKILL)
        payload.wait()
    if payload.returncode < 0:
        code = -payload.returncode
        if code not in (signal.SIGKILL, signal.SIGSTOP):
            signal.signal(code, signal.SIG_DFL)
        os.kill(os.getpid(), code)
        return 128 + code
    return payload.returncode


if __name__ == "__main__":
    raise SystemExit(supervise(int(sys.argv[1]), sys.argv[2:]))
