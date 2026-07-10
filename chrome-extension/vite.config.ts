import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Content scripts from the same extension share ONE isolated-world lexical scope, so
// their top-level minified `const`/`let` (e.g. `r`) collide across files with
// "Identifier 'r' has already been declared". They have no imports, so wrapping each
// in an IIFE makes every top-level binding function-local and removes the clash.
const wrapContentScriptsIife = {
  name: "wrap-content-scripts-iife",
  generateBundle(_options: unknown, bundle: Record<string, { type: string; code?: string }>) {
    for (const [fileName, chunk] of Object.entries(bundle)) {
      if (fileName.startsWith("content-") && chunk.type === "chunk" && chunk.code) {
        chunk.code = `(()=>{\n${chunk.code}\n})();`;
      }
    }
  },
};

export default defineConfig({
  plugins: [react(), wrapContentScriptsIife],
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
