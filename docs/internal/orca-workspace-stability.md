# Workspace stability and resource usage

The Linux native smoke cycles independent PTYs in two disposable Git projects 30 times while changing focus, splitting, resizing, and hiding and restoring side panels. It tracks unique PTY process IDs and checks that terminal closure reaps the associated children. It then consumes 8,000 output lines, checks bounded scrollback, and verifies cleanup. The same scenario checks a 500-file tree and a diff beyond the preview limit.

Hidden terminal widgets now keep consuming PTY data without repeatedly rebuilding their Tk text surface. Mapping the widget redraws from the live screen buffer. Destroying a task detail removes its text widget from the theme registry. Invalid and newer-version layout files open with a safe default and remain on disk until the user explicitly resets the layout. Saved session placeholders require deliberate launch.

The extended run held two live PTYs for 60 seconds. Desktop CPU was 0.84 seconds during that interval, about 1.4% of one core. It then opened and reaped 240 PTY processes across 120 cycles in 34.56 seconds, using 18.23 seconds of desktop CPU. Sampled RSS rose from 49.5 MiB to 57.5 MiB, with two threads and no child processes left at the end. The measurement covered the desktop process under Xvfb and excluded CLI children from the CPU and RSS totals. These measurements cover a short stress exercise. Longer production sessions and other platforms need a separate resource baseline.

Run the extended scenario with `xvfb-run -a python tests/smoke_workspace_stability.py --cycles 120 --idle-seconds 60`.

Existing automated cases separately recover a real Supervisor through a persisted checkpoint, handle a paused or killed Worker, and exercise pinned SSH reconnection. The workflow verifies that closing a detached job view leaves actual Supervisor work running.

## Windows readiness

The Windows adapter uses pywinpty ConPTY, UTF-8 transfer, explicit resize, and forced process cleanup. Tk calls the Windows DPI-awareness helper on launch and chooses available Windows fonts through the existing theme system. The PyInstaller launcher remains an independent Windows package. Windows-native ConPTY, Korean IME composition, clipboard, drive and extended paths, high-DPI and font rendering, and installer startup require a native Windows run. The Linux smoke does not validate those platform-specific behaviors.
