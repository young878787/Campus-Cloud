import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import MIcon from "../../../components/MIcon";
import { useOctoMood, useOctoScene } from "../octoMood";
import styles from "../LoginPage.module.scss";

/* 裝置授權的狀態 → 章魚心情 */
const DEVICE_MOOD = { approving: "thinking", declining: "thinking", approved: "done", error: "error" };

/**
 * 桌面 App（SkyLab Connect）的裝置授權同意頁。授權流程在 LoginPage 跑，這裡只照狀態畫畫面。
 *
 * @param {"idle"|"approving"|"declining"|"approved"|"error"} status
 */
export default function DeviceApprovalView({ status, error, user, onApprove, onDecline }) {
  const { t } = useTranslation("login");
  const { setMood } = useOctoMood();
  useOctoScene("device");
  useEffect(() => {
    setMood(DEVICE_MOOD[status] ?? "idle");
  }, [status, setMood]);

  // 同意頁：授權必須由使用者明確按下，不可自動核准（防止釣魚連結）
  if (status === "idle") {
    return (
      <>
        <div className={styles.titleRow}>
          <span className={styles.deviceHero} aria-hidden="true">
            <MIcon name="devices" size={24} />
          </span>
          <h1 className={styles.title}>{t("LoginPage.deviceConsentTitle")}</h1>
        </div>
        {/* 要授權的是哪個帳號：獨立一塊、email 單獨一行，一眼看得到 */}
        <div className={styles.deviceAccount}>
          <MIcon name="account_circle" size={32} />
          <div className={styles.deviceAccountText}>
            <span>{t("LoginPage.deviceConsentAccountLabel")}</span>
            <strong>{user?.email ?? t("LoginPage.deviceConsentCurrentAccount")}</strong>
          </div>
        </div>
        <p className={styles.deviceScope}>{t("LoginPage.deviceConsentScope")}</p>
        {/* 防釣魚提醒：別人傳來的連結不要按授權 */}
        <p className={styles.deviceWarning}>
          <MIcon name="gpp_maybe" size={18} />
          <span>{t("LoginPage.deviceConsentHelp")}</span>
        </p>
        <div className={styles.deviceActions}>
          <button type="button" data-bombadil="danger" className={styles.btn} onClick={onApprove}>
            {t("LoginPage.deviceConsentApprove")}
          </button>
          <button type="button" className={styles.btnSecondary} onClick={onDecline}>
            {t("LoginPage.deviceConsentDecline")}
          </button>
        </div>
      </>
    );
  }

  if (status === "approved") {
    return (
      <>
        <h1 className={styles.title}>{t("LoginPage.deviceApprovedTitle")}</h1>
        <div className={styles.successBox}>
          <MIcon name="check_circle" size={40} />
          <p>{t("LoginPage.deviceApprovedMessage")}</p>
        </div>
      </>
    );
  }

  if (status === "error") {
    return (
      <>
        <h1 className={styles.title}>{t("LoginPage.deviceErrorTitle")}</h1>
        <p className={styles.error}>{error}</p>
        <p className={styles.hint}>{t("LoginPage.deviceErrorHelp")}</p>
        <a className={styles.btnLink} href="/dashboard">
          {t("LoginPage.backToSkyLab")}
        </a>
      </>
    );
  }

  return (
    <>
      <h1 className={styles.title}>
        {t(status === "declining" ? "LoginPage.deviceCancellingTitle" : "LoginPage.deviceConnectingTitle")}
      </h1>
      <div className={styles.deviceProgress} aria-live="polite">
        <MIcon name="sync" size={40} spin />
      </div>
    </>
  );
}
