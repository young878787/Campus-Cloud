import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import styles from "../LoginPage.module.scss";

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "";
let googleIdentityScriptPromise;

function loadGoogleIdentityScript() {
  if (window.google?.accounts?.id) return Promise.resolve();

  if (!googleIdentityScriptPromise) {
    googleIdentityScriptPromise = new Promise((resolve, reject) => {
      const existingScript = document.getElementById("google-identity-services");
      if (existingScript) {
        existingScript.addEventListener("load", resolve, { once: true });
        existingScript.addEventListener("error", reject, { once: true });
        return;
      }

      const script = document.createElement("script");
      script.id = "google-identity-services";
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  return googleIdentityScriptPromise;
}

/**
 * 「或」分隔線＋Google 登入鈕；沒設定 VITE_GOOGLE_CLIENT_ID 就整塊不出現。
 * onCredential、onError 要是穩定的參考（useCallback），不然按鈕會一直重畫。
 *
 * @param {boolean} busy 正在用 Google 憑證登入：按鈕變淡不能按，底下顯示提示
 */
export default function GoogleSignIn({ busy, onCredential, onError }) {
  const { t } = useTranslation("login");
  const buttonRef = useRef(null);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return undefined;

    let cancelled = false;
    loadGoogleIdentityScript()
      .then(() => {
        if (cancelled || !buttonRef.current) return;

        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: (response) => {
            const credential = response?.credential;
            if (!credential) {
              onError(t("LoginPage.googleNoCredential"));
              return;
            }
            onCredential(credential);
          },
          ux_mode: "popup",
        });

        buttonRef.current.innerHTML = "";
        window.google.accounts.id.renderButton(buttonRef.current, {
          theme: "outline",
          size: "large",
          type: "standard",
          text: "signin_with",
          shape: "rectangular",
          logo_alignment: "left",
          width: Math.min(buttonRef.current.clientWidth || 360, 400),
        });
      })
      .catch(() => {
        if (!cancelled) onError(t("Error.generic", { ns: "common" }));
      });

    return () => {
      cancelled = true;
    };
  }, [onCredential, onError, t]);

  if (!GOOGLE_CLIENT_ID) return null;
  return (
    <div className={styles.oauthArea}>
      <div className={styles.divider}>
        <span>{t("LoginPage.orDivider")}</span>
      </div>
      <div className={busy ? styles.googleBusy : undefined}>
        <div
          ref={buttonRef}
          data-bombadil="danger"
          className={styles.googleButton}
          aria-label={t("LoginPage.googleSignInAriaLabel")}
        />
      </div>
      {busy && <p className={styles.oauthHint}>{t("LoginPage.googleLoggingIn")}</p>}
    </div>
  );
}
