import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Production: served behind Apache at https://openlegal.algomation.io/app/
//   Apache strips the /app/ prefix and forwards to nginx in the frontend
//   container. Vite's `base: "/app/"` puts /app/ in front of all asset URLs
//   so they go back through the right Apache location. React Router
//   gets basename="/app" in main.tsx to match.
export default defineConfig({
  plugins: [react()],
  base: "/app/",
  server: {
    host: "0.0.0.0",
    port: 8080,
    strictPort: true,
    proxy: {
      "/api":  { target: "http://localhost:8002", changeOrigin: true },
      "/uapf": { target: "http://localhost:8002", changeOrigin: true },
    },
  },
  preview: { host: "0.0.0.0", port: 8080 },
  build: { outDir: "dist", sourcemap: true },
});
