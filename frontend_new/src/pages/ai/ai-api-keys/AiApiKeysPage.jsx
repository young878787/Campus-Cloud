import { useState } from "react";
import styles from "./AiApiKeysPage.module.scss";

const MIcon = ({ name, size = 20 }) => (
  <span className="material-icons-outlined" style={{ fontSize: size, lineHeight: 1 }}>
    {name}
  </span>
);

const MOCK = [];

function EmptyState() {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon}>
        <MIcon name="vpn_key" size={40} />
      </div>
      <h2 className={styles.emptyTitle}>尚無 API 金鑰</h2>
      <p className={styles.emptyDesc}>目前資料庫中沒有任何 AI API 金鑰紀錄</p>
    </div>
  );
}

export default function AiApiKeysPage() {
  const [keys] = useState(MOCK);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <h1 className={styles.pageTitle}>AI API 金鑰狀態</h1>
          <p className={styles.pageSubtitle}>
            查看目前資料庫中所有 AI API 金鑰紀錄與狀態（僅顯示現存紀錄）。
          </p>
        </div>
      </div>

      <div className={styles.content}>
        {keys.length === 0 ? (
          <EmptyState />
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  {["金鑰名稱", "擁有者", "狀態", "建立時間", "動作"].map((col) => (
                    <th key={col} className={styles.th}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.id} className={styles.tr}>
                    <td className={styles.td}>{k.name}</td>
                    <td className={styles.td}>{k.owner}</td>
                    <td className={styles.td}>
                      <span className={`${styles.badge} ${styles[`badge_${k.status}`]}`}>
                        {k.status === "active" ? "使用中" : "已停用"}
                      </span>
                    </td>
                    <td className={styles.td}>{k.createdAt}</td>
                    <td className={styles.td}>
                      <button type="button" className={`${styles.actionBtn} ${styles.actionBtnDanger}`} title="撤銷">
                        <MIcon name="block" size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
