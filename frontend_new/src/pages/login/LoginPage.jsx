import { useState } from "react";
import styles from "./LoginPage.module.scss";

function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    console.log("登入資訊：", { username, password });
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
              placeholder="請輸入帳號"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="password">密碼</label>
            <input
              id="password"
              type="password"
              placeholder="請輸入密碼"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <button type="submit" className={styles.btn}>
            登入
          </button>
        </form>
      </div>
    </div>
  );
}

export default LoginPage;
