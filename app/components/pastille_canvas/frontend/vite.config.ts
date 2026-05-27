import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Streamlit custom components run inside an <iframe>. Vite's default
// base path is "/" which would break asset URLs when served from a sub-path.
// Use relative paths so the bundle works in any iframe context.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // Single-file bundle for easier Streamlit deployment
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
      },
    },
  },
});
