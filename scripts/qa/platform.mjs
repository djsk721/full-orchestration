import { join } from "node:path";
import { readdirSync } from "node:fs";

export function withDisplay(command, args) {
  return process.platform === "linux" && !process.env.DISPLAY
    ? ["xvfb-run", ["-a", command, ...args]]
    : [command, args];
}

export function desktopPackage(root) {
  const release = join(root, "apps", "desktop", "release");
  if (process.platform === "linux") {
    return {
      script: "package:linux",
      executable: () => join(release, "linux-unpacked", "model-orchestration-preview"),
      image: () => {
        const images = readdirSync(release).filter((name) => name.endsWith(".AppImage"));
        if (images.length !== 1) throw new Error("expected exactly one AppImage in the release directory");
        return join(release, images[0]);
      },
    };
  }
  if (process.platform === "win32") {
    return {
      script: "package:windows",
      executable: () => {
        const unpacked = join(release, "win-unpacked");
        const binary = readdirSync(unpacked).find((name) =>
          ["model-orchestration-preview.exe", "Model Orchestration Preview.exe"].includes(name));
        if (!binary) throw new Error("packaged Windows preview executable was not found");
        return join(unpacked, binary);
      },
    };
  }
  throw new Error("Packaging is configured for Linux and Windows");
}
