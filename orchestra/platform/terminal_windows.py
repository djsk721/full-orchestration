"""Windows ConPTY. pywinpty is required only on this platform."""
from ..core import Invalid


class NativePty:
    def __init__(self, argv, cwd, env, lines, columns):
        try:
            from winpty import Backend, PtyProcess
        except ImportError as exc:
            raise Invalid("Windows 터미널에 pywinpty가 필요합니다. requirements-desktop.txt를 설치하세요.") from exc
        self.pty = PtyProcess.spawn(argv, cwd=str(cwd) if cwd else None,
                                    env=env, dimensions=(lines, columns), backend=str(Backend.ConPTY))

    def read(self):
        while True:
            data = self.pty.read(8192)
            if data or not self.pty.isalive():
                return data.encode("utf-8")

    def write(self, data):
        self.pty.write(data)

    def resize(self, lines, columns):
        self.pty.setwinsize(lines, columns)

    def close(self):
        self.pty.close(force=True)


def operator_shell():
    return ["powershell.exe", "-NoLogo"]
