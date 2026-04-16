import { useState } from "react";
import styles from "./AuditPage.module.scss";

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
        <MIcon name="receipt_long" size={40} />
      </div>
      <h2 className={styles.emptyTitle}>尚無操作紀錄</h2>
      <p className={styles.emptyDesc}>系統操作紀錄將會顯示在這裡</p>
    </div>
  );
}

export default function AuditPage() {
  const [logs] = useState(MOCK);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <h1 className={styles.pageTitle}>稽核日誌</h1>
          <p className={styles.pageSubtitle}>查看所有系統操作記錄</p>
        </div>
        <button
          type="button"
          className={styles.btnSecondary}
          onClick={() => {}}
        >
          <MIcon name="download" size={16} />
          匯出 CSV
        </button>
      </div>

      <div className={styles.content}>
        {logs.length === 0 ? (
          <EmptyState />
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  {["時間", "使用者", "操作", "目標", "IP"].map((col) => (
                    <th key={col} className={styles.th}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} className={styles.tr}>
                    <td className={styles.td}>{log.time}</td>
                    <td className={styles.td}>{log.user}</td>
                    <td className={styles.td}>{log.action}</td>
                    <td className={styles.td}>{log.target}</td>
                    <td className={styles.td}>{log.ip}</td>
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
