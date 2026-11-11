import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// FastAPI sunucusu 127.0.0.1:8000 üzerinde çalışır ve CORS içermez.
// request_timeout_seconds=180 sınırına uyum için proxy timeout 190 saniyedir.
const PROXY_TIMEOUT_MS = 190_000;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/v1": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
        timeout: PROXY_TIMEOUT_MS,
        proxyTimeout: PROXY_TIMEOUT_MS,
      },
      "/health": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
        timeout: 10_000,
        proxyTimeout: 10_000,
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    proxy: {
      "/v1": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
        timeout: PROXY_TIMEOUT_MS,
        proxyTimeout: PROXY_TIMEOUT_MS,
      },
      "/health": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
        timeout: 10_000,
        proxyTimeout: 10_000,
      },
    },
  },
});
