# Workspace stability QA

The measurements below record the earlier candidate. For the matched rerun after optimizing terminal parsing and drawing, see [terminal performance and multi-session QA](terminal-performance-qa.md).

The repeated-workload test holds two PTYs idle, then runs three equal rounds in one Tk process. Each round cycles between two projects, starts two sessions, verifies PID reuse when refocusing, changes split direction and size, toggles Focus, closes both sessions, and renders an 8,000-line burst. A 20 ms Tk timer samples event-loop delay. The burst measurement starts at process launch and ends when the final line is visible. The child count samples the native process tree. Each round samples RSS after cleanup and an idle settling window.

```bash
xvfb-run -a python tests/smoke_workspace_stability.py --cycles 60 --rounds 3 --idle-seconds 15
python tests/smoke_workspace_ssh.py --typescript --legacy-ref e76e876
```

| Case | Scope | Status |
| --- | --- | --- |
| Repeated terminal lifecycles | Native Linux PTYs with controlled fixture CLI output, process identities and cleanup | PASS |
| Large tree, oversized diff and 8,000-line burst | Actual temporary Git and filesystem reads, with caps and visible final output | PASS |
| Corrupt and newer layouts, restart without process launch | Saved file remains until explicit reset. Normal layouts restore placeholders. | PASS |
| SSH and Worker restart/reconnect | Isolated native OpenSSH and actual Worker lifecycle | PASS |
| Supervisor restart, cancellation and SQLite recovery | Existing detached Supervisor and Python recovery regressions | PASS |
| Long-duration production memory behavior | Equal workloads in this pass compare warm-up and post-cleanup retention. They do not establish long-duration memory behavior. | PARTIAL |
| Windows-specific terminal stability | Native script prepared | NOT VERIFIED |

Scoped fixes update the active terminal label immediately on focus changes and bound terminal parsing work per Tk callback. The terminal scheduler drains a busy queue more frequently and uses the existing idle interval after the queue empties. These changes preserve bounded scrollback and automatic backpressure. Resource measurements refer to the Tk process on the shared Linux host and exclude child CPU and RSS.

## Measured Linux rounds

| Equal workload | Wall / desktop CPU | Settled RSS | Tk delay p95 / max | Burst to visible last line |
| --- | --- | --- | --- | --- |
| Round 1 | 19.19 s / 10.02 s | 58.1 MiB | 51.05 / 78.70 ms | 2.34 s |
| Round 2 | 20.40 s / 10.77 s | 60.3 MiB | 52.90 / 77.44 ms | 2.53 s |
| Round 3 | 20.30 s / 10.78 s | 60.7 MiB | 56.39 / 90.36 ms | 2.50 s |

Two resident idle terminals used 0.19 CPU seconds over 15 wall seconds. The workload created and reaped 360 fixture PTYs, with two live children at each round's sampled peak and zero after cleanup. RSS began at 50.1 MiB. Most retention came in the first round, followed by smaller increases in equivalent rounds. This is consistent with warming caches and allocator retention. A three-round run cannot rule out a slow leak.

The pre-change run showed 228–345 ms maximum Tk delays and took 1.58–1.62 s per output burst. The final run reduced observed maximum delay and took 2.34–2.53 s to display the burst. These are observed results on the shared host, with a throughput tradeoff and scheduling variance.

[1920×1080 split terminals](../assets/screenshots/orca-workspace/production/split-terminals-1920x1080.png) · [940×650 Files](../assets/screenshots/orca-workspace/production/project-files-small.png)
