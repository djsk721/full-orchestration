import { join, posix, win32 } from "node:path";
import { readFile } from "node:fs/promises";

export function dataDirectory(env: Readonly<Record<string, string | undefined>>, platform: string, home: string,
  cwd?: string): string {
  const style = platform === "win32" ? win32 : posix;
  if (env.ORCHESTRA_DATA) {
    const expanded = env.ORCHESTRA_DATA.replace(/^~(?=$|[/\\])/, () => home);
    return cwd === undefined ? style.resolve(expanded) : style.resolve(cwd, expanded);
  }
  const base = platform === "win32" ? env.LOCALAPPDATA : env.XDG_DATA_HOME;
  return style.join(base || style.join(home, ".local", "share"), "ModelOrchestration");
}

export async function readJson(file: string): Promise<unknown> {
  const source = await readFile(file, "utf8");
  return JSON.parse(source.replace(/^\uFEFF/, "")) as unknown;
}

export function dashboardPath(root: string): string {
  return join(root, "state.db");
}
