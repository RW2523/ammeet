import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Single SPA serving both Tauri windows; tauri.conf.json points each window at
// index.html with a `?window=settings|overlay` query param.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
  },
  envPrefix: ["VITE_", "TAURI_ENV_"],
  build: {
    target: "es2022",
    outDir: "dist",
    sourcemap: false,
  },
});
