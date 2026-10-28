import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies API calls to the FastAPI backend (BACKEND_URL, default http://localhost:8000).
const target = process.env.BACKEND_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": target, "/health": target } },
});
