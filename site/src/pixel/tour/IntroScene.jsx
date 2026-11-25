import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import PixelSprite from "../PixelSprite";
import { ICONS, ICON_PALETTE } from "../icons";
import styles from "./Tour.module.scss";

const TOTAL = 40;
const SLOW_MS = 650;

/**
 * 開場畫面：一間 40 個座位的電腦教室。
 * 第 1 句全暗；第 2 句「以前一台一台裝」螢幕慢慢一台一台亮；第 3 句起交給 SkyLab，全班一起亮。
 */
export default function IntroScene({ beat }) {
  const { t } = useTranslation("pixel");
  const [slow, setSlow] = useState(0);

  useEffect(() => {
    if (beat !== 1) return undefined;
    setSlow(0);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setSlow(3);
      return undefined;
    }
    const id = window.setInterval(() => setSlow((n) => (n >= TOTAL ? n : n + 1)), SLOW_MS);
    return () => window.clearInterval(id);
  }, [beat]);

  const lit = beat === 0 ? 0 : beat === 1 ? slow : TOTAL;
  const all = beat >= 2;
  return (
    <div className={styles.intro}>
      <div className={styles.cloudRow} data-on={all || undefined} aria-hidden="true">
        <PixelSprite rows={ICONS.server} palette={ICON_PALETTE} cell={4} />
        <PixelSprite rows={ICONS.server} palette={ICON_PALETTE} cell={4} />
        <PixelSprite rows={ICONS.server} palette={ICON_PALETTE} cell={4} />
        <span>{t("tour.intro.cloud")}</span>
      </div>
      <div className={styles.introSeats} aria-hidden="true">
        {Array.from({ length: TOTAL }, (_, i) => (
          <i key={i} data-on={i < lit || undefined} style={{ "--d": all ? `${i * 25}ms` : "0ms" }} />
        ))}
      </div>
      <p className={styles.introCount} data-all={all || undefined}>
        {t("tour.intro.count", { n: lit, total: TOTAL })}
      </p>
    </div>
  );
}
