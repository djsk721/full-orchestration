import sys

from orchestra.core import data_directory


def main():
    if sys.argv[1:2] == ["--posix-process-guard"] and sys.platform != "win32":
        from orchestra.platform.guard_posix import supervise
        raise SystemExit(supervise(int(sys.argv[2]), sys.argv[3:]))
    root = data_directory()
    if "--supervisor" in sys.argv:
        from orchestra.supervisor import run_supervisor
        run_supervisor(root)
    else:
        from orchestra.desktop import launch
        launch(root)


if __name__ == "__main__":
    main()
