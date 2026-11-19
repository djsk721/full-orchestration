import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "build/renderer",
    target: "chrome156",
  },
});
