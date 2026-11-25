import { useTranslation } from "react-i18next";
import { AVATARS } from "../avatars";
import styles from "./RoleKicker.module.scss";

/*
 * 這一頁是誰在用：身分頭像＋名稱排成一小行，放在說明標題的上面（校園區各頁共用）。
 * 文字顏色可由外層用 --kicker-color 指定（泡泡是固定白底，其他地方跟著日夜）。
 */
export default function RoleKicker({ roles }) {
  const { t } = useTranslation("pixel");
  return (
    <p className={styles.kicker}>
      {roles.map((role) => (
        <span key={role} className={styles.role}>
          <i aria-hidden="true" dangerouslySetInnerHTML={{ __html: AVATARS[role] }} />
          {t(`fork.${role}.name`)}
        </span>
      ))}
    </p>
  );
}
