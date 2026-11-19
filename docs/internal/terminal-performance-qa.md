# Terminal performance and multi-session QA

Linux PTY throughput, output integrity and lifecycle checks are **PASS**. Tail latency under multiple busy panes is **PARTIAL** against a 90 ms target. Native Windows results cover single-terminal and two-pane workloads on a GitHub-hosted Windows runner.

## Measurements

Linux Xvfb with a 1,280 × 800 workspace, Python 3.11.5 and pyte 0.8.2. The reusable benchmark launches real subprocesses behind native PTYs in temporary Git projects. The fixture emits 8,000 numbered, cyan Korean-text rows per session and a completion marker. Each scenario ran three times before and after the change. A 20 ms Tk timer measures lateness. The delay percentiles and completion time in the table are medians of the three runs. The maximum is the highest observed value across the runs. CPU time includes the desktop and its reader threads. Child resources are outside the CPU and RSS measurement.

| Workload | Elapsed before → after | Tk median before → after | Tk P95 before → after | Tk P99 before → after | Tk max before → after | Desktop CPU before → after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| One terminal | 1.923 → 0.806 s | 11.2 → 7.9 ms | 36.2 → 30.4 ms | 64.3 → 46.9 ms | 99 → 88 ms | 1.42 → 0.57 s |
| Two, horizontal split | 2.163 → 0.800 s | 13.8 → 14.0 ms | 53.2 → 38.8 ms | 90.9 → 69.6 ms | 111 → 119 ms | 2.07 → 0.71 s |
| Two, vertical split | 1.922 → 0.864 s | 14.0 → 12.2 ms | 41.2 → 46.5 ms | 97.7 → 92.9 ms | 147 → 125 ms | 1.80 → 0.72 s |
| Four, two projects and both splits | 4.133 → 1.762 s | 53.1 → 41.1 ms | 107.3 → 68.7 ms | 141.6 → 105.5 ms | 171 → 158 ms | 3.95 → 1.61 s |

The benchmark measures from the write that triggers an already-running fixture through the display of its final line. Hidden tabs continue parsing and are brought into view to verify their final paint. The four-session workload repeatedly changes project, tab and pane; the optimized runs completed eight, eight and nine transitions before the output finished. Shorter runs allow fewer transitions. Peak sampled desktop RSS across all benchmark scenarios was 82.3 MiB before and 83.7 MiB after, including instrumentation that stores the captured bytes. The main thread samples RSS at Tk pump boundaries, so brief peaks between those samples may escape measurement.

### Comparable historical workload

The existing soak test also timed its original plain-text burst from launching a fresh PTY to visible line 7,999. Each round opened and closed 120 temporary PTYs while alternating project, split direction, workspace size and focus mode. Three rounds reaped 360 PTYs per version, with zero children after each round.

| Round | 8,000 lines before → after | Tk P95 before → after | Tk max before → after | Settled RSS before → after |
| --- | ---: | ---: | ---: | ---: |
| 1 | 2.627 → 1.650 s | 56.8 → 48.3 ms | 93.6 → 79.2 ms | 57.9 → 58.8 MiB |
| 2 | 2.535 → 1.699 s | 53.8 → 50.7 ms | 133.6 → 93.2 ms | 60.2 → 61.7 MiB |
| 3 | 2.367 → 1.578 s | 54.5 → 48.8 ms | 89.0 → 87.1 ms | 60.7 → 62.0 MiB |

Median elapsed time fell about 35%, to 1.65 s. The optimized maximum exceeded 90 ms in one round. Settled RSS rose about 1.3 MiB by the third round. Two idle PTYs used 0.22 desktop CPU seconds over 15 seconds after the change, compared with 0.23 seconds before. Short repeated workloads cannot establish the memory profile of all-day sessions.

## Bottleneck and change

| One-session phase | Before → after | Interpretation |
| --- | ---: | --- |
| PTY read median size across runs | 567 → 375 bytes | Native read boundaries varied with scheduling. The same bytes reached the parser. |
| PTY read wait P95 | 5.11 → 3.96 ms | Reader timing includes blocking wall time on its own thread. |
| Queue depth peak | 48 → 48 chunks | The existing bounded FIFO applied backpressure in both versions. |
| Queue put median of per-run maxima | 89.2 → 67.8 ms | The reader still waits for space during sustained bursts. |
| ANSI parser time, median total per run | 1,231 → 441 ms | Parsing was the dominant measured phase. |
| Visible Tk draw time, median total per run | 106.8 → 71.1 ms | Visible paints fell from a median 55 to 35; hidden panes still parse. |

A separate cProfile run on fixed 2 KiB slices found 2.19 million calls to the pyte history screen's attribute interceptor, accounting for 0.74 s of 1.93 s under profiling. Static binding of pyte's own event wrappers removes repeated wrapper construction and ordinary attribute interception. The same profile took 1.01 s afterward. Native I/O, the UTF-8 decoder, ANSI events, alternate buffer dispatch, and pyte history hooks stay in the execution path. Tk renders a viewport with one tagged text insert. Busy panes now yield after an 8 ms slice between complete reads and reschedule after 4 ms while a backlog remains. One full read can exceed the slice. Empty queues keep a 35 ms poll interval.

## Integrity and interaction

| Check | Result | Evidence |
| --- | --- | --- |
| Complete ordered output across all four scenarios | PASS | All 27 sessions per version received all 8,000 numbered rows, with zero missing and zero duplicates. UTF-8 Korean text and ANSI sequences matched, and Tk displayed the final cyan row. |
| Retained scrollback and alternate-screen behavior | PASS | The added integrity assertions compare the actual retained screen/history rows to the last contiguous suffix and enforce the 1,500-row history cap. Parser parity tests compare fragmented ANSI input, truecolor, underline, reverse video, wide and combining characters, cursor visibility, margins and paging against pyte. |
| Input during simultaneous output | PASS | A focused pane received Return through Tk and displayed its isolated response in 88 ms during an unrelated pane's sustained 4,000-line output. |
| Selection reuse and cleanup | PASS | Reopening an existing session from the other project preserved the same view and PID. A 360-process candidate soak and the four-scenario benchmark reaped every owned PTY child. |
| Both splits below 90 ms under saturation | PARTIAL | The single-terminal maximum was 88 ms in the targeted benchmark. Two and four terminals exceeded 90 ms in some runs. |
| User workstation, all-day workload or Windows throughput | NOT VERIFIED | Measurements use a shared Linux host and bounded exercise durations. |

Run with the desktop Python dependencies installed.

```bash
xvfb-run -a python tests/benchmark_workspace_terminal.py
xvfb-run -a python tests/smoke_workspace_stability.py --cycles 60 --rounds 3 --idle-seconds 15
npm run verify -- --ui --package
```

The benchmark writes one JSON record per scenario and round. Each includes elapsed time, delay percentiles, process CPU, sampled RSS, read sizes and waits, queue peaks, parse and draw timings, and output integrity.

## Published candidate repeat

On the Linux host, the same three-round dataset and output integrity assertions produced the following measurements. CPU and elapsed time are medians. Maximum delay and peak RSS are the highest observed across the three runs.

| Workload | Elapsed | Tk median / P95 / P99 / max | Desktop CPU | Peak RSS |
| --- | ---: | ---: | ---: | ---: |
| Single terminal | 0.802 s | 5.7 / 18.0 / 65.2 / 119.7 ms | 0.60 s | 80.0 MiB |
| Two, horizontal | 0.805 s | 12.4 / 38.0 / 89.2 / 120.9 ms | 0.71 s | 82.4 MiB |
| Two, vertical | 0.868 s | 13.4 / 42.5 / 77.6 / 126.6 ms | 0.76 s | 82.8 MiB |
| Four, two projects | 1.684 s | 37.1 / 89.8 / 110.0 / 154.7 ms | 1.60 s | 81.6 MiB |

The queue reached 48 chunks and retained scrollback reached 1,500 rows. Each four-session round switched project and tab eight times. All 27 sessions delivered every expected numbered row once, passed the retained-history checks, and reaped all of their PTY children. Throughput and integrity are **PASS**. Tail latency remains **PARTIAL**.

The separate 360-PTY soak after the Windows startup correction measured 1.566, 1.704 and 1.788 s for its plain-text 8,000-line bursts. The median was 1.704 s, compared with the 1.650 s optimized baseline and 2.535 s before the optimization. Maximum Tk delay in the three rounds was 77–80 ms. Settled desktop RSS peaked at 62.0 MiB and every round finished with zero child processes.

Windows measurements and their separately executed native workload appear in [native Windows test results](windows-native-test-results.md).
