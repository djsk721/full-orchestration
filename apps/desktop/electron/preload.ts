import { contextBridge, ipcRenderer } from "electron";
import type { DesktopApi, SnapshotEnvelope, SnapshotRequest } from "../src/contracts";

const desktop: DesktopApi = {
  async snapshot(jobId) {
    // Sandboxed preload can only require Electron. Keep the wire name literal here.
    const request: SnapshotRequest = { version: 1, jobId };
    const reply: SnapshotEnvelope = await ipcRenderer.invoke("jobs:snapshot:v1", request);
    if (reply?.version !== 1) throw new Error("Unsupported dashboard reply");
    return reply.projection;
  },
};

contextBridge.exposeInMainWorld("orchestration", Object.freeze(desktop));
