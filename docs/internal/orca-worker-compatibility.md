# Remote Worker compatibility

The existing JSON envelope remains version 1. The Worker advertises an implementation version and an explicit supported protocol range inside the read-only `info` response. A lightweight probe skips metrics and runtime initialization on current Workers. The existing full status response and older clients remain supported.

| Observation | Behavior |
| --- | --- |
| Current Worker with overlapping protocol | The SSH panel shows implementation version, both protocol endpoints and available capabilities. Git status and diff are separately gated. |
| Legacy version-1 response without metadata | Base job and Files reads stay available. An existing `git_context` flag can advertise read-only Git. Without that flag, Git shows update guidance before requesting a missing method. |
| Different wire version or nonoverlapping advertised range | The operation stops with an incompatibility message and client/server protocol evidence. |
| Transport loss or outdated peer | Existing cached remote status remains an observation. Explicit reconnect repeats compatibility negotiation over the same pinned SSH connection. Existing remote job IDs and event cursors remain authoritative. |

The automated comparison used the prior Worker entry point from `e76e876` with shared compatible modules and current Worker code on the same real loopback OpenSSH server. It verified old repository access, rejection of unavailable Git, and current status/diff capabilities. Unit cases cover transitional Git flags, malformed manifests, and incompatible ranges and wire envelopes. The SSH integration also exercises changed-key rejection, allowlisted Git paths, disconnected jobs, recovery and duplicate prevention.

Run the comparison from a checkout containing that revision with `python tests/smoke_workspace_ssh.py --legacy-ref e76e876 --typescript` after building the TypeScript adapter.

## Server-admin upgrade and rollback

After the operator approves maintenance, stage the new Worker code in a separate server directory. Preserve the old release, the host key, the runtime configuration and the Worker data directory. Use the same worker account and the same explicit `ORCHESTRA_REMOTE_DATA` for both releases. Back up the quiesced data directory through the server's normal procedure before changing a deployment pointer. Keep active runs on their existing version until they finish or reach a verified maintenance state.

If the workstation profile uses a stable server-side release pointer, switch that pointer and click **Test connection** or **Reconnect** to read the new manifest and existing job status. Maintain the previous target for rollback. With an existing fixed profile that references recoverable jobs, use the administrator's deployment mechanism to preserve the profile's location and job identity. Do not replace the client profile to simulate migration. If the new release fails preflight, switch the pointer back while quiesced and retest with the same SSH identity and state. A future release with state migration would require its own database rollback procedure. This change has no deployment or configuration migration command.
