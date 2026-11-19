import sys

from orchestra.core import data_directory


def main():
    root = data_directory()
    if "--supervisor" in sys.argv:
        from orchestra.supervisor import run_supervisor
        run_supervisor(root)
    else:
        from orchestra.desktop import launch
        launch(root)


if __name__ == "__main__":
    main()
