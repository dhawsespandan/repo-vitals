import react from "@vitejs/plugin-react";
// `defineConfig` comes from vitest/config, not vite, so the `test` block below
// is typed rather than silently ignored.
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The browser must talk to the API on its own origin in every
    // environment, so one HttpOnly session cookie works with no CORS and no
    // CSRF special-casing (§2). Vercel does this with a rewrite in
    // production; this proxy is the dev-server equivalent.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
