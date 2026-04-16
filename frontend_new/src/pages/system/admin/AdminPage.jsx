import { useState } from "react";
import styles from "./AdminPage.module.scss";

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
        <MIcon name="manage_accounts" size={40} />
      </div>
      <h2 className={styles.emptyTitle}>尚無使用者</h2>
      <p className={styles.emptyDesc}>點擊「新增使用者」建立第一個帳戶</p>
    </div>
  );
}

export default function AdminPage() {
  const [users] = useState(MOCK);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <h1 className={styles.pageTitle}>使用者管理</h1>
          <p className={styles.pageSubtitle}>管理使用者帳戶與權限</p>
        </div>
        <button type="button" className={styles.btnPrimary}>
          <MIcon name="add" size={16} />
          新增使用者
        </button>
      </div>

      <div className={styles.content}>
        {users.length === 0 ? (
          <EmptyState />
        ) : (
          <div className={styles.list}>
            {users.map((u) => (
              <div key={u.id} className={styles.row}>
                <div className={styles.rowAvatar}>{u.name?.[0] ?? "U"}</div>
                <div className={styles.rowMain}>
                  <span className={styles.rowName}>{u.name}</span>
                  <span className={styles.rowMeta}>{u.email}</span>
                </div>
                <span className={`${styles.badge} ${styles[`badge_${u.role}`]}`}>{u.role}</span>
                <div className={styles.rowActions}>
                  <button type="button" className={styles.actionBtn} title="編輯">
                    <MIcon name="edit" size={16} />
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
