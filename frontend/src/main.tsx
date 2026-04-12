import { QueryClientProvider } from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"

import { OpenAPI } from "./client"
import { ThemeProvider } from "./components/theme-provider"
import { Toaster } from "./components/ui/sonner"
import "./index.css"
import "./lib/i18n"
import { queryClient } from "./lib/queryClient"
import { LanguageProvider } from "./providers/LanguageProvider"
import { routeTree } from "./routeTree.gen"
import { AuthSessionService } from "./services/authSession"

OpenAPI.BASE = import.meta.env.VITE_API_URL

function getTokenExp(token: string): number {
  try {
    const payload = token.split(".")[1]
    if (!payload) return 0
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/")
    const json = atob(normalized)
    const data = JSON.parse(json) as { exp?: number }
    return typeof data.exp === "number" ? data.exp : 0
  } catch {
    return 0
  }
}

const REFRESH_THRESHOLD_SEC = 30

OpenAPI.TOKEN = async () => {
  const token = AuthSessionService.getAccessToken()
  if (!token) return ""

  const exp = getTokenExp(token)
  const nowSec = Math.floor(Date.now() / 1000)

  if (exp > 0 && exp - nowSec <= REFRESH_THRESHOLD_SEC) {
    const ok = await AuthSessionService.refreshAccessToken()
    if (ok) return AuthSessionService.getAccessToken() || ""
  }

  return token
}

const router = createRouter({ routeTree })

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LanguageProvider
      defaultLanguage="zh-TW"
      storageKey="campus-cloud-language"
    >
      <ThemeProvider defaultTheme="light" storageKey="vite-ui-theme">
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
          <Toaster richColors closeButton />
        </QueryClientProvider>
      </ThemeProvider>
    </LanguageProvider>
  </StrictMode>,
)
