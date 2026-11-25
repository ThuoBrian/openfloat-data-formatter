/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API that `just api` runs. In development Vite serves the page and
// forwards these paths to it, so the page and the API share an origin the way
// they will once FastAPI serves the built page itself.
const API = "http://127.0.0.1:8000";
const API_PATHS = [
  "/health",
  "/settings",
  "/preview",
  "/validate",
  "/transform",
  "/rejected-rows",
  "/statement-report",
  "/shutdown",
];

export default defineConfig({
  plugins: [react()],
  build: {
    // Into the Python package, where FastAPI serves it from and where it is
    // committed: staff install from GitHub's zip and never run Node, so the
    // built page has to be in the repo. CI rebuilds it and fails on any diff.
    outDir: "../src/openfloat_formatter/web",
    emptyOutDir: true,
  },
  server: {
    // 127.0.0.1, never all interfaces: the page handles files with personal data.
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(API_PATHS.map((path) => [path, { target: API }])),
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
