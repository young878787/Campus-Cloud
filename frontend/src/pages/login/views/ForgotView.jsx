import { useState } from "react";
import { useTranslation } from "react-i18next";
import MIcon from "../../../components/MIcon";
import { AccountService } from "../../../services/account";
import { useOctoScene, useOctoSubmit } from "../octoMood";
import BackButton from "./BackButton";
import styles from "../LoginPage.module.scss";

/** 忘記密碼：輸入 Email，寄出重設連結 */
export default function ForgotView({ onBack }) {
  const { t } = useTranslation("login");
  const { loading, error, run } = useOctoSubmit();
  useOctoScene("forgot");
  const [email, setEmail] = useState("");
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const { ok } = await run(
      () => AccountService.requestPasswordRecovery(email),
      t("LoginPage.forgotPasswordErrorDefault"),
    );
    if (ok) setSuccess(true);
  };

  return (
    <>
      <BackButton onClick={onBack}>{t("LoginPage.backToLogin")}</BackButton>
      <h1 className={styles.title}>{t("LoginPage.forgotPasswordTitle")}</h1>

      {success ? (
        <div className={styles.successBox}>
          <MIcon name="mark_email_read" size={32} />
          <p>{t("LoginPage.resetLinkSent")}</p>
        </div>
      ) : (
        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.field}>
            <label htmlFor="forgot-email">{t("LoginPage.emailLabel")}</label>
            <input
              id="forgot-email"
              type="email"
              placeholder={t("LoginPage.emailPlaceholderExample")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          {error && <p className={styles.error}>{error}</p>}

          <button type="submit" data-bombadil="danger" className={styles.btn} disabled={loading}>
            {loading ? t("LoginPage.sending") : t("LoginPage.sendResetLink")}
          </button>
        </form>
      )}
    </>
  );
}
