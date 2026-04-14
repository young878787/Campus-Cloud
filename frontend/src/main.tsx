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
import {
  prepareOpenApiRequestAuth,
  resolveOpenApiToken,
} from "./services/openApiAuth"

OpenAPI.BASE = import.meta.env.VITE_API_URL

OpenAPI.PREPARE_REQUEST = prepareOpenApiRequestAuth
OpenAPI.TOKEN = resolveOpenApiToken

const router = createRouter({ routeTree })

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

const rootElement = document.getElementById("root")

if (!rootElement) {
  throw new Error("Root element not found")
}

ReactDOM.createRoot(rootElement).render(
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
