"""POSIX session containment and advisory file locks."""
import fcntl
import os
import subprocess
import sys
from pathlib import Path


class NativeChild:
    def __init__(self, argv, **options):
        reader, self.lifetime = os.pipe()
        if getattr(sys, "frozen", False):
            guard = [sys.executable, "--posix-process-guard"]
        else:
            guard = [sys.executable, "-I", str(Path(__file__).with_name("guard_posix.py"))]
        try:
            self.process = subprocess.Popen([*guard, str(reader), *argv], pass_fds=(reader,),
                                            start_new_session=True, **options)
        except BaseException:
            os.close(self.lifetime)
            raise
        finally:
            os.close(reader)

    def terminate_tree(self):
        if self.lifetime is not None:
            os.close(self.lifetime)
            self.lifetime = None


def acquire_lock(file):
    fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def release_lock(file):
    fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def detached_options():
    return {"start_new_session": True}


def validate_executable(path):
    return path
