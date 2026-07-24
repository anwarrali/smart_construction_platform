import { defineConfig } from "vite";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import babel from "@rolldown/plugin-babel";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), babel({ presets: [reactCompilerPreset()] })],
  css: {
    postcss: "./postcss.config.js",
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy all /api calls to the FastAPI backend.
      // VITE_BACKEND_URL should be the full host URL, e.g. http://backend:8000
      "/api": {
        target: process.env.VITE_BACKEND_URL || "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
      "/ws": {
        target: process.env.VITE_WS_URL || "ws://localhost:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
