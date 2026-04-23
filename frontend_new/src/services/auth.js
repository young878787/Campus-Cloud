/**
 * auth.js
 * 負責 token 的讀寫與清除，所有操作都集中在這裡。
 * 其他模組若需要 token，請透過這裡取得，不要直接讀 localStorage。
 */

const ACCESS_TOKEN_KEY  = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";

/** 解析 JWT payload，取得 exp（毫秒）；失敗回傳 null */
function parseJwtExpiry(token) {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.exp ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

export const AuthStorage = {
  getAccessToken()  { return localStorage.getItem(ACCESS_TOKEN_KEY);  },
  getRefreshToken() { return localStorage.getItem(REFRESH_TOKEN_KEY); },

  /** 取得 access token 的過期時間（ms），若無法解析回傳 null */
  getTokenExpiry() {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);
    return token ? parseJwtExpiry(token) : null;
  },

  setTokens({ access_token, refresh_token }) {
    localStorage.setItem(ACCESS_TOKEN_KEY, access_token);
    if (refresh_token) {
      localStorage.setItem(REFRESH_TOKEN_KEY, refresh_token);
    }
  },

  clearTokens() {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },

  isLoggedIn() {
    return Boolean(localStorage.getItem(ACCESS_TOKEN_KEY));
  },
};
