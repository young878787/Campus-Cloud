import { useState } from "react";
import styles from "./GroupsPage.module.scss";

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
        <MIcon name="groups" size={40} />
      </div>
      <h2 className={styles.emptyTitle}>尚無群組</h2>
      <p className={styles.emptyDesc}>點擊「建立群組」建立第一個課程或班級群組</p>
    </div>
  );
}

export default function GroupsPage() {
  const [groups] = useState(MOCK);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <h1 className={styles.pageTitle}>群組管理</h1>
          <p className={styles.pageSubtitle}>
            管理課程/班級群組，<span className={styles.accent}>批量分配虛擬機</span>
          </p>
        </div>
        <button type="button" className={styles.btnPrimary}>
          <MIcon name="add" size={16} />
          建立群組
        </button>
      </div>

      <div className={styles.content}>
        {groups.length === 0 ? (
          <EmptyState />
        ) : (
          <div className={styles.list}>
            {groups.map((g) => (
              <div key={g.id} className={styles.row}>
                <div className={styles.rowIcon}>
                  <MIcon name="groups" size={20} />
                </div>
                <div className={styles.rowMain}>
                  <span className={styles.rowName}>{g.name}</span>
                  <span className={styles.rowMeta}>{g.memberCount} 位成員 · 建立於 {g.createdAt}</span>
                </div>
                <div className={styles.rowActions}>
                  <button type="button" className={styles.actionBtn} title="管理">
                    <MIcon name="settings" size={16} />
                  </button>
                  <button type="button" className={`${styles.actionBtn} ${styles.actionBtnDanger}`} title="刪除">
                    <MIcon name="delete" size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
