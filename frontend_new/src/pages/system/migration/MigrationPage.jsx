import { useState } from "react";
import styles from "./MigrationPage.module.scss";

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
        <MIcon name="move_down" size={40} />
      </div>
      <h2 className={styles.emptyTitle}>尚無遷移任務</h2>
      <p className={styles.emptyDesc}>目前沒有進行中或已完成的遷移作業</p>
    </div>
  );
}

export default function MigrationPage() {
  const [jobs] = useState(MOCK);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <h1 className={styles.pageTitle}>Migration Jobs</h1>
          <p className={styles.pageSubtitle}>追蹤虛擬機與容器的跨節點遷移進度與歷史紀錄</p>
        </div>
        <button type="button" className={styles.btnSecondary}>
          <MIcon name="sync" size={16} />
          重新整理
        </button>
      </div>

      <div className={styles.content}>
        {jobs.length === 0 ? (
          <EmptyState />
        ) : (
          <div className={styles.list}>
            {jobs.map((j) => (
              <div key={j.id} className={styles.row}>
                <div className={styles.rowIcon}>
                  <MIcon name="move_down" size={20} />
                </div>
                <div className={styles.rowMain}>
                  <span className={styles.rowName}>{j.name}</span>
                  <span className={styles.rowMeta}>{j.from} → {j.to} · {j.startedAt}</span>
                </div>
                <span className={`${styles.badge} ${styles[`badge_${j.status}`]}`}>{j.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
