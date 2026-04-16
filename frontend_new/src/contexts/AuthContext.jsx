/**
 * AuthContext.jsx
 * 提供全域的認證狀態與操作：
 *   - user        當前用戶資料（null 表示未登入）
 *   - loading     初始化時驗證 token 的 loading 狀態
 *   - login()     登入，成功後更新 user
 *   - logout()    登出，清除 token 與 user
 */

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { AuthStorage } from "../services/auth";
import { apiGet, apiPostForm } from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null);
  const [loading, setLoading] = useState(true); // 啟動時驗證 token

  /** 啟動時若有 token，嘗試取得當前用戶以確認 token 仍有效 */
  useEffect(() => {
    if (!AuthStorage.isLoggedIn()) {
      setLoading(false);
      return;
    }

    apiGet("/api/v1/users/me")
      .then(setUser)
      .catch(() => {
        // token 無效或過期，清除
        AuthStorage.clearTokens();
      })
      .finally(() => setLoading(false));
  }, []);

  /**
   * login - 呼叫後端取得 token，並載入用戶資料
   * @param {string} username  email
   * @param {string} password
   * @throws {{ status, message }} 登入失敗時
   */
  const login = useCallback(async (username, password) => {
    const tokens = await apiPostForm("/api/v1/login/access-token", {
      username,
      password,
    });
    AuthStorage.setTokens(tokens);

    const me = await apiGet("/api/v1/users/me");
    setUser(me);
  }, []);

  /** logout - 清除 token 與用戶狀態 */
  const logout = useCallback(() => {
    AuthStorage.clearTokens();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

/** useAuth - 取得認證 context，必須在 AuthProvider 內使用 */
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
