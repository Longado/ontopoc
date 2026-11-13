import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

// the service the dev server forwards /api to; point it elsewhere to run next to another instance
const service = process.env.ONTOLOGY_API || "http://127.0.0.1:8767";

export default defineConfig({
  build: {
    outDir: "dist/client",
    rollupOptions: {
      input: { main: resolve(import.meta.dirname, "index.html"), legacy: resolve(import.meta.dirname, "legacy.html") },
    },
  },
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    proxy: {
      "/api/recall": { target: "http://127.0.0.1:8766", changeOrigin: true },
      "/api/ontology": { target: service, changeOrigin: true },
      "/api/workspace": { target: service, changeOrigin: true },
    },
    host: "0.0.0.0",
    allowedHosts: ["terminal.local"],
    warmup: {
      clientFiles: ["./src/app/main.jsx"],
    },
  },
  plugins: [react()],
});
