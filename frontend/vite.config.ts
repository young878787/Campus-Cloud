import fs from "node:fs"
import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vite"

function templatesPlugin() {
  return {
    name: "virtual-templates",
    resolveId(id: string) {
      if (id === "virtual:templates") return "\0virtual:templates"
    },
    load(id: string) {
      if (id === '\0virtual:templates') {
        const jsonDir = path.resolve(__dirname, 'src/json')
        const jsonKeyPrefix = path.relative(__dirname, jsonDir).split(path.sep).join('/') + '/'
        if (!fs.existsSync(jsonDir)) return 'export default {}'
        const files = fs.readdirSync(jsonDir).filter(f => f.endsWith('.json'))
        const allData: Record<string, any> = {}
        for (const f of files) {
          try {
            allData[`${jsonKeyPrefix}${f}`] = JSON.parse(fs.readFileSync(path.join(jsonDir, f), 'utf-8'))
          } catch (e: unknown) {
            console.warn(
              `[templatesPlugin] Failed to load JSON file ${path.join(jsonDir, f)}:`,
              e
            )
          }
        }
        return `export default ${JSON.stringify(allData)}`
      }
    },
  }
}

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    headers: {
      "Cross-Origin-Opener-Policy": "same-origin-allow-popups",
    },
  },
  plugins: [
    templatesPlugin(),
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
  ],
})
