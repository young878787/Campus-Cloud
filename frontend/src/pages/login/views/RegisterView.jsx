import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import MIcon from "../../../components/MIcon";
import Turnstile from "../../../components/Turnstile/Turnstile";
import { AccountService } from "../../../services/account";
import { useOctoScene, useOctoSubmit } from "../octoMood";
import BackButton from "./BackButton";
import styles from "../LoginPage.module.scss";

/** 註冊：填姓名與 Email，之後從驗證信的連結設定密碼（VerifySignupPage） */
export default function RegisterView({ onBack, turnstileSiteKey = "" }) {
  const { t } = useTranslation("login");
  const { loading, error, setError, run } = useOctoSubmit();
  useOctoScene("register");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [success, setSuccess] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState("");
  const turnstileRef = useRef(null);
  const turnstilePending = Boolean(turnstileSiteKey) && !turnstileToken;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (turnstilePending) {
      setError(t("LoginPage.turnstileRequired"));
      return;
    }
    const { ok } = await run(
      () => AccountService.signup({ email, full_name: fullName }, { turnstileToken }),
      t("LoginPage.registerErrorDefault"),
    );
    if (ok) setSuccess(true);
    // 機器人驗證的 token 只能用一次，送出失敗後換一個新的
    else turnstileRef.current?.reset();
  };

  return (
    <>
      <BackButton onClick={onBack}>{t("LoginPage.backToLogin")}</BackButton>
      <h1 className={styles.title}>{t("LoginPage.registerTitle")}</h1>

      {success ? (
        <div className={styles.successBox}>
          <MIcon name="check_circle" size={32} />
          <p>{t("LoginPage.registerSuccess")}</p>
          <button type="button" className={styles.btn} onClick={onBack}>
            {t("LoginPage.backToLogin")}
          </button>
        </div>
      ) : (
        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.field}>
            <label htmlFor="full-name">{t("LoginPage.fullNameLabel")}</label>
            <input
              id="full-name"
              type="text"
              placeholder={t("LoginPage.fullNamePlaceholder")}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="reg-email">{t("LoginPage.emailLabel")}</label>
            <input
              id="reg-email"
              type="email"
              placeholder={t("LoginPage.emailPlaceholderExample")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          {turnstileSiteKey && (
            <Turnstile
              ref={turnstileRef}
              siteKey={turnstileSiteKey}
              action="signup"
              onToken={setTurnstileToken}
            />
          )}

          {error && <p className={styles.error}>{error}</p>}

          <button type="submit" data-bombadil="danger" className={styles.btn} disabled={loading || turnstilePending}>
            {loading ? t("LoginPage.creating") : t("LoginPage.createAccount")}
          </button>
        </form>
      )}
    </>
  );
}
