import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import fs from "fs";

function templatesPlugin() {
  return {
    name: "virtual-templates",
    resolveId(id) {
      if (id === "virtual:templates") return "\0virtual:templates";
    },
    load(id) {
      if (id === "\0virtual:templates") {
        const jsonDir = path.resolve(__dirname, "../frontend/src/json");
        if (!fs.existsSync(jsonDir)) return "export default {}";
        const files = fs.readdirSync(jsonDir).filter((f) => f.endsWith(".json"));
        const allData = {};
        for (const f of files) {
          try {
            allData[f] = JSON.parse(fs.readFileSync(path.join(jsonDir, f), "utf-8"));
          } catch (e) {
            console.warn(`[templatesPlugin] Failed to load ${f}:`, e);
          }
        }
        return `export default ${JSON.stringify(allData)}`;
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), templatesPlugin()],
  server: {
    port: 5174,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: `
          @use "@/assets/styles/variables" as *;
          @use "@/assets/styles/mixins" as *;
        `,
      },
    },
  },
});
