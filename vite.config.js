import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "path";

export default defineConfig({
  root: ".", // <-- assicurati che la root sia il progetto corrente
  plugins: [vue()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    open: true,
    fs: {
      strict: false, // disattiva il limite rigido
      allow: [path.resolve(__dirname)], // consenti tutto dentro la root
    },
    watch: {
      ignored: ["**/backend/downloads/**"],
    },
  },
  optimizeDeps: {
    exclude: ["backend/downloads"],
  },
});
