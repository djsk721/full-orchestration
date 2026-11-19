# Remote Worker management UX

**SSH → Test connection** shows an in-progress state and a timestamped result. The summary distinguishes SSH-only profiles, failed transfer, an incompatible or missing Worker, a reachable Worker without a recent Supervisor heartbeat, and an observed heartbeat. It lists the reported version, negotiated protocol range and capabilities. Raw connection evidence remains available on the Environments page.

Repeated clicks for the same profile share a pending check. The completion is ignored if the profile changed or another probe replaced it. **Worker health and upgrades** explains staging a separate server release, retaining the previous code and data, testing the deployment pointer, and switching back on failure. See [detailed upgrade and rollback guidance](orca-worker-compatibility.md).

| Verification | Evidence | Status |
| --- | --- | --- |
| Capability and health display | Tk and a real loopback Worker without a running Supervisor showed version, capabilities and the absence of a recent heartbeat | PASS |
| Repeated connection tests | Two requests shared one in-flight probe and received the same result in the real SSH UI fixture | PASS |
| Earlier Worker and missing feature | Earlier and current Worker handlers were tested over pinned loopback OpenSSH. Earlier repository access worked and unsupported Git was rejected. | PASS |
| Disconnect, reconnect, Worker restart and recovery | Real SSH fixture plus earlier/current protocol comparisons | PASS |
| Server update or rollback on an operator host | Manual guidance only. Local tests did not change an external Worker installation. | NOT VERIFIED |
| Automatic updates | No update mechanism in this release | NOT APPLICABLE |

No authorization gate or directory policy changed. Existing Request IDs, Git path checks and host-key pinning remain in the original execution path. [Remote Git workspace](../assets/screenshots/orca-workspace/production/remote-git-1440x900.png)
