import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo, el frontend corre en :5173 y reenvía /api y /ws al backend :8000.
// En producción el backend sirve el build, así que las mismas rutas relativas funcionan.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
