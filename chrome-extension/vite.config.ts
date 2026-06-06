import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
    minify: true,
    rollupOptions: {
      input: {
        // Side panel (main UI – full meeting room)
        sidepanel: resolve(__dirname, "sidepanel.html"),
        // Toolbar popup (quick status + controls)
        popup: resolve(__dirname, "popup.html"),
        // Background service worker
        "service-worker": resolve(__dirname, "src/background/service-worker.ts"),
        // Content scripts (one per injection context)
        "content-meeting": resolve(__dirname, "src/content/meeting-detector.ts"),
        "content-overlay": resolve(__dirname, "src/content/injected-overlay.ts"),
      },
      output: {
        // Keep entry names predictable so manifest.json can reference them
        entryFileNames: (chunk) => {
          if (chunk.name === "service-worker") return "service-worker.js";
          if (chunk.name.startsWith("content-")) return `${chunk.name}.js`;
          return "[name].js";
        },
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: "[name].[ext]",
      },
    },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
