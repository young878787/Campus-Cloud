import { useState } from "react";
import { useAuth } from "../../contexts/AuthContext";
import styles from "./LoginPage.module.scss";

function LoginPage() {
  const { login } = useAuth();

  const [username,  setUsername]  = useState("");
  const [password,  setPassword]  = useState("");
  const [showPwd,   setShowPwd]   = useState(false);
  const [error,     setError]     = useState("");
  const [loading,   setLoading]   = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await login(username, password);
      // 登入成功後 App.jsx 會偵測到 user 並自動切換到主畫面
    } catch (err) {
      setError(err?.message ?? "登入失敗，請確認帳號與密碼");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <h1 className={styles.title}>Campus Cloud</h1>
        <p className={styles.subtitle}>雲端校園管理平台</p>

        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.field}>
            <label htmlFor="username">帳號</label>
            <input
              id="username"
              type="text"
              placeholder="請輸入帳號（Email）"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="password">密碼</label>
            <div className={styles.passwordWrap}>
              <input
                id="password"
                type={showPwd ? "text" : "password"}
                placeholder="請輸入密碼"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
                required
              />
              <button
                type="button"
                className={styles.eyeBtn}
                onClick={() => setShowPwd((v) => !v)}
                tabIndex={-1}
                aria-label={showPwd ? "隱藏密碼" : "顯示密碼"}
              >
                <span className="material-icons-outlined" style={{ fontSize: 20 }}>
                  {showPwd ? "visibility_off" : "visibility"}
                </span>
              </button>
            </div>
          </div>

          {error && <p className={styles.error}>{error}</p>}

          <button type="submit" className={styles.btn} disabled={loading}>
            {loading ? "登入中…" : "登入"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default LoginPage;
