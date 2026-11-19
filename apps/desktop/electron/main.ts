import { app, BrowserWindow, ipcMain, net, protocol, session } from "electron";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { loadConfig } from "./config";
import { readDashboard } from "./legacy-store";
import { isSnapshotRequest, snapshotChannel } from "../src/contracts";
import type { SnapshotEnvelope } from "../src/contracts";

const entry = "orchestration://desktop/";
const renderer = join(__dirname, "../../renderer");
const config = loadConfig();
let window: BrowserWindow | null = null;
let readWarning = false;

protocol.registerSchemesAsPrivileged([
  { scheme: "orchestration", privileges: { standard: true, secure: true } },
]);

// Report categories without paths, SQLite statements, event bodies, or configuration values.
function log(event: string, level: "info" | "warn" = "info"): void {
  const record = JSON.stringify({ at: new Date().toISOString(), level, event });
  console[level](record);
}

function createWindow(): void {
  const desktop = new BrowserWindow({
    width: 1200,
    height: 820,
    minWidth: 420,
    backgroundColor: "#142640",
    webPreferences: {
      preload: join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      nodeIntegrationInSubFrames: false,
      sandbox: true,
      webviewTag: false,
      devTools: !app.isPackaged,
    },
  });
  window = desktop;
  desktop.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  desktop.webContents.on("will-navigate", (event) => event.preventDefault());
  desktop.webContents.on("will-frame-navigate", (event) => event.preventDefault());
  desktop.webContents.on("will-attach-webview", (event) => event.preventDefault());
  desktop.on("closed", () => { window = null; });
  void desktop.loadURL(entry).catch(() => log("desktop.load_failed", "warn"));
}

void app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, complete) => complete(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  protocol.handle("orchestration", async (request) => {
    const url = new URL(request.url);
    if (request.method !== "GET" || url.host !== "desktop" || url.username || url.password || url.search) {
      return new Response(null, { status: 404 });
    }
    const pathname = url.pathname;
    const resource = pathname === "/" ? "index.html" : pathname.slice(1);
    if (pathname !== "/" && !/^\/assets\/[a-zA-Z0-9_-]+\.(?:js|css)$/.test(pathname)) {
      return new Response(null, { status: 404 });
    }
    try {
      return await net.fetch(pathToFileURL(join(renderer, resource)).href);
    } catch {
      return new Response(null, { status: 404 });
    }
  });
  ipcMain.handle(snapshotChannel, (event, ...args: unknown[]): SnapshotEnvelope => {
    const frame = event.senderFrame;
    const request = args[0];
    if (event.sender !== window?.webContents || !frame || frame.parent !== null || frame.url !== entry ||
        args.length !== 1 || !isSnapshotRequest(request)) {
      throw new Error("Invalid dashboard request");
    }
    try {
      const result = readDashboard(config.databasePath, request.jobId);
      readWarning = false;
      return { version: 1, projection: result };
    } catch {
      if (!readWarning) log("dashboard.database_unavailable", "warn");
      readWarning = true;
      return { version: 1, projection: { status: "unavailable" } };
    }
  });
  createWindow();
  log("desktop.ready");
}).catch(() => {
  log("desktop.start_failed", "warn");
  app.exit(1);
});

app.on("window-all-closed", () => app.quit());
