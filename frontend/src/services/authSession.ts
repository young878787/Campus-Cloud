import { OpenAPI } from "@/client"
import { request as __request } from "@/client/core/request"

type AuthTokens = {
  access_token: string
  refresh_token?: string | null
}

const ACCESS_TOKEN_KEY = "access_token"
const REFRESH_TOKEN_KEY = "refresh_token"

let _refreshPromise: Promise<boolean> | null = null

export const AuthSessionService = {
  getAccessToken() {
    return typeof window === "undefined"
      ? null
      : localStorage.getItem(ACCESS_TOKEN_KEY)
  },

  getRefreshToken() {
    return typeof window === "undefined"
      ? null
      : localStorage.getItem(REFRESH_TOKEN_KEY)
  },

  setTokens(tokens: AuthTokens) {
    localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
    if (tokens.refresh_token) {
      localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
    }
  },

  clearTokens() {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  },

  async loginWithGoogle(idToken: string): Promise<AuthTokens> {
    const tokens = await __request<AuthTokens>(OpenAPI, {
      method: "POST",
      url: "/api/v1/login/google",
      body: { id_token: idToken },
      mediaType: "application/json",
    })
    this.setTokens(tokens)
    return tokens
  },

  async refreshAccessToken(): Promise<boolean> {
    if (_refreshPromise) return _refreshPromise

    _refreshPromise = (async () => {
      const refreshToken = this.getRefreshToken()
      if (!refreshToken) return false

      try {
        const tokens = await __request<AuthTokens>(OpenAPI, {
          method: "POST",
          url: "/api/v1/login/refresh-token",
          body: { refresh_token: refreshToken },
          mediaType: "application/json",
        })
        this.setTokens(tokens)
        return true
      } catch {
        return false
      }
    })().finally(() => {
      _refreshPromise = null
    })

    return _refreshPromise
  },
}
