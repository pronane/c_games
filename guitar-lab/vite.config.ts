import { defineConfig } from "vite";
export default defineConfig({
  // Runs locally; the notation library alone is ~1 MB, so the 500 kB web default only adds noise.
  build: { chunkSizeWarningLimit: 4000 },
  server: {
    host: "0.0.0.0",
    allowedHosts: [".e2b.app"],
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
