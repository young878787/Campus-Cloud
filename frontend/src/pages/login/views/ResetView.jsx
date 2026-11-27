import { useState } from "react";
import { useTranslation } from "react-i18next";
import MIcon from "../../../components/MIcon";
import PasswordRules from "../../../components/PasswordRules/PasswordRules";
import { AccountService } from "../../../services/account";
import { isPasswordStrong } from "../../../utils/passwordPolicy";
import { useOctoScene, useOctoSubmit } from "../octoMood";
import PasswordField from "./PasswordField";
import styles from "../LoginPage.module.scss";

/** 重設密碼：從重設信的連結（帶 token）進來，設定新密碼 */
export default function ResetView({ token, onDone }) {
  const { t } = useTranslation("login");
  const { loading, error, fail, run } = useOctoSubmit();
  useOctoScene("reset");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitted(true);
    if (!isPasswordStrong(password)) {
      fail(t("PasswordRules.notMet", { ns: "common" }));
      return;
    }
    if (password !== confirm) {
      fail(t("LoginPage.passwordMismatch"));
      return;
    }
    const { ok } = await run(
      () => AccountService.resetPassword(token, password),
      t("LoginPage.resetPasswordErrorDefault"),
    );
    if (ok) setSuccess(true);
  };

  return (
    <>
      <h1 className={styles.title}>{t("LoginPage.resetPasswordTitle")}</h1>

      {success ? (
        <div className={styles.successBox}>
          <MIcon name="check_circle" size={32} />
          <p>{t("LoginPage.resetPasswordSuccess")}</p>
          <button type="button" className={styles.btn} onClick={onDone}>
            {t("LoginPage.goToLogin")}
          </button>
        </div>
      ) : (
        <form className={styles.form} onSubmit={handleSubmit}>
          <PasswordField
            id="reset-password"
            label={t("LoginPage.newPasswordLabel")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
          >
            <PasswordRules password={password} invalid={submitted} />
          </PasswordField>

          <PasswordField
            id="reset-confirm"
            label={t("LoginPage.confirmNewPasswordLabel")}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            disabled={loading}
            placeholder={t("LoginPage.confirmNewPasswordPlaceholder")}
          />

          {error && <p className={styles.error}>{error}</p>}

          <button type="submit" data-bombadil="danger" className={styles.btn} disabled={loading}>
            {loading ? t("LoginPage.updating") : t("LoginPage.updatePassword")}
          </button>
        </form>
      )}
    </>
  );
}
