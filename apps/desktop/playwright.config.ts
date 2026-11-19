import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "desktop.spec.ts",
  timeout: 30_000,
});
