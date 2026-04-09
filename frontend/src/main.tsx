import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"
import { toast } from "sonner"
import { ApiError, OpenAPI } from "./client"
import { ThemeProvider } from "./components/theme-provider"
import { Toaster } from "./components/ui/sonner"
import "./index.css"
import { LanguageProvider } from "./providers/LanguageProvider"
import { routeTree } from "./routeTree.gen"
import "./lib/i18n"

OpenAPI.BASE = import.meta.env.VITE_API_URL

// 解析 JWT payload，取得 exp（秒）。失敗回 0 代表視為已過期。
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

// Token 距離過期少於此秒數時就主動續期，避免打出去才吃到 401。
const REFRESH_THRESHOLD_SEC = 30

let refreshPromise: Promise<boolean> | null = null

async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem("refresh_token")
  if (!refreshToken) return false

  // 同時間只允許一個 refresh 在飛，其他呼叫者共享同一個 promise。
  if (refreshPromise) return refreshPromise

  refreshPromise = (async () => {
    try {
      const apiBase = import.meta.env.VITE_API_URL ?? ""
      const response = await fetch(`${apiBase}/api/v1/login/refresh-token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
      if (!response.ok) return false
      const data = await response.json()
      localStorage.setItem("access_token", data.access_token)
      if (data.refresh_token) {
        localStorage.setItem("refresh_token", data.refresh_token)
      }
      return true
    } catch {
      return false
    } finally {
      refreshPromise = null
    }
  })()
  return refreshPromise
}

// 主動式 token 取得：每次請求前檢查 exp，快過期就先換。
// 這能把絕大多數 401 在發生前就擋掉，避免 retry 退避造成長時間卡頓。
OpenAPI.TOKEN = async () => {
  const token = localStorage.getItem("access_token")
  if (!token) return ""
  const exp = getTokenExp(token)
  const nowSec = Math.floor(Date.now() / 1000)
  if (exp > 0 && exp - nowSec <= REFRESH_THRESHOLD_SEC) {
    const ok = await tryRefreshToken()
    if (ok) return localStorage.getItem("access_token") || ""
  }
  return token
}

const handleApiError = async (error: Error) => {
  if (error instanceof ApiError && error.status === 401) {
    const refreshed = await tryRefreshToken()
    if (refreshed) {
      // Token 刷新成功：重打所有失敗/快取的 query，否則 currentUser 等
      // 會停留在 undefined，導致 sidebar 等依賴使用者資訊的 UI 退化成未登入狀態。
      await queryClient.invalidateQueries()
    } else {
      localStorage.removeItem("access_token")
      localStorage.removeItem("refresh_token")
      toast.error("登入已過期，請重新登入")
      window.location.href = "/login"
    }
  } else if (error instanceof ApiError && error.status === 403) {
    // 403 代表已登入但無權限存取該資源，不應強制登出
    const detail =
      (error.body as { detail?: string } | undefined)?.detail ??
      "您沒有權限執行此操作"
    toast.error(detail)
  }
}
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 401/403 是授權問題，重試只會累積退避延遲（預設 retry=3，約等 7 秒）造成 UI 長時間卡住。
      // 其他錯誤維持預設的 3 次重試行為。
      retry: (failureCount, error) => {
        if (
          error instanceof ApiError &&
          (error.status === 401 || error.status === 403)
        ) {
          return false
        }
        return failureCount < 3
      },
    },
    mutations: {
      retry: false,
    },
  },
  queryCache: new QueryCache({
    onError: handleApiError,
  }),
  mutationCache: new MutationCache({
    onError: handleApiError,
  }),
})

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
