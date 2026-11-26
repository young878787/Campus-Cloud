import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import PasswordRules from "../../components/PasswordRules/PasswordRules";
import { AccountService } from "../../services/account";
import { isPasswordStrong } from "../../utils/passwordPolicy";
import { useOctoSubmit } from "./octoMood";
import PageShell from "./PageShell";
import PasswordField from "./views/PasswordField";
import styles from "./LoginPage.module.scss";

function VerifySignupBody() {
  const { t } = useTranslation("login");
  const { loading, error, fail, run } = useOctoSubmit();
  const [token, setToken] = useState(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [outcome, setOutcome] = useState(""); // "" | "success" | "pending_review"
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    const url = new URL(window.location.href);
    setToken(new URLSearchParams(url.hash.slice(1)).get("token") || "");
    url.hash = "";
    window.history.replaceState(window.history.state, "", url);
  }, []);

  const submit = async (event) => {
    event.preventDefault();
    setSubmitted(true);
    if (!isPasswordStrong(password)) {
      fail(t("PasswordRules.notMet", { ns: "common" }));
      return;
    }
    if (password !== confirm) {
      fail(t("LoginPage.verifySignupMismatch"));
      return;
    }
    const { ok, result } = await run(
      () => AccountService.confirmSignup(token, password),
      t("LoginPage.verifySignupFailed"),
    );
    if (ok) setOutcome(result.message === "pending_review" ? "pending_review" : "success");
  };

  return (
    <>
      <h1 className={styles.title}>{t("LoginPage.verifySignupTitle")}</h1>
      {outcome ? (
        <p className={styles.successBox} role="status">
          {t(outcome === "pending_review" ? "LoginPage.verifySignupPendingReview" : "LoginPage.verifySignupSuccess")}
        </p>
      ) : token ? (
        <>
          <p className={styles.lead}>{t("LoginPage.verifySignupSetPassword")}</p>
          <form className={styles.form} onSubmit={submit}>
            <PasswordField
              id="signup-password"
              label={t("LoginPage.passwordLabel")}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={loading}
            >
              <PasswordRules password={password} invalid={submitted} />
            </PasswordField>
            <PasswordField
              id="signup-confirm"
              label={t("LoginPage.confirmPasswordLabel")}
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              disabled={loading}
            />
            {error && <p className={styles.error} role="alert">{error}</p>}
            <button data-bombadil="danger" className={styles.btn} type="submit" disabled={loading}>
              {loading ? t("LoginPage.verifySignupChecking") : t("LoginPage.verifySignupActivate")}
            </button>
          </form>
        </>
      ) : token === null ? (
        <p className={styles.lead} role="status">{t("LoginPage.verifySignupChecking")}</p>
      ) : (
        <p className={styles.error} role="alert">{t("LoginPage.verifySignupFailed")}</p>
      )}
      <p className={styles.footerText}>
        <a className={styles.link} href="/login">{t("LoginPage.backToLogin")}</a>
      </p>
    </>
  );
}

/** 註冊驗證信的連結（/verify-signup#token=…）：驗證信箱並設定密碼 */
export default function VerifySignupPage() {
  return (
    <PageShell scene="verify">
      <VerifySignupBody />
    </PageShell>
  );
}
