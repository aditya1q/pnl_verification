import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // "@/components/ui/button" -> src/components/ui/button (used by shadcn/ui)
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5174,
    strictPort: true,
    host: "0.0.0.0",
    proxy: {
      // This app's backend runs on 8002 (port 8001 is used by the trader-dashboard backend).
      // Override with API_URL if it runs elsewhere, e.g. API_URL=http://127.0.0.1:8001.
      "/api": process.env.API_URL || "http://127.0.0.1:8002",
    },
  },
});
