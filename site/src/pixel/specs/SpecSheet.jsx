import { useTranslation } from "react-i18next";
import { ICONS, ICON_PALETTE } from "../icons";
import PixelSprite from "../PixelSprite";
import styles from "./SpecSheet.module.scss";

/*
 * 功能一覽：只放舊介紹頁（site/src/landing）本來就有的專業內容，照它的說法寫，不放數據
 * （舊頁 stats.json 的範本、容量、在線數、規則數、節點分數都是示範資料）。
 * 每組一個圖示＋幾條，文案在 specs.groups.<id>.items（陣列）。
 */
const GROUPS = [
  { id: "platform", icon: "server" },
  { id: "request", icon: "calendar" },
  { id: "class", icon: "people" },
  { id: "network", icon: "shield" },
  { id: "ai", icon: "sparkle" },
  { id: "connect", icon: "terminal" },
];

/**
 * 功能一覽：給要評估導入的人（學校資訊人員、評審）看的那一塊。
 * 六張標籤卡（上面一條像證件頭的標籤列：圖示＋名稱，下面幾條），專有名詞照實寫
 * （Proxmox VE、LXC、NAT、Reverse Proxy、OpenAI 相容）。
 */
export default function SpecSheet() {
  const { t } = useTranslation("pixel");
  return (
    <section className={styles.specs} id="specs" aria-labelledby="specs-title">
      <h2 className={styles.title} id="specs-title">
        {t("specs.title")}
      </h2>
      <div className={styles.groups}>
        {GROUPS.map((group) => (
          <article key={group.id} className={styles.group}>
            <h3>
              <span className={styles.groupIcon} aria-hidden="true">
                <PixelSprite rows={ICONS[group.icon]} palette={ICON_PALETTE} cell={2} />
              </span>
              {t(`specs.groups.${group.id}.title`)}
            </h3>
            <ul>
              {t(`specs.groups.${group.id}.items`, { returnObjects: true }).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
