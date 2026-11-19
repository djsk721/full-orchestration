import { homedir } from "node:os";
import { dashboardPath, dataDirectory } from "../adapters/filesystem";

export { dataDirectory };

export function loadConfig() {
  return { databasePath: dashboardPath(dataDirectory(process.env, process.platform, homedir())) };
}
