import { useState } from "react";
import styles from "./DomainPage.module.scss";

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
        <MIcon name="domain" size={40} />
      </div>
      <h2 className={styles.emptyTitle}>尚無網域紀錄</h2>
      <p className={styles.emptyDesc}>請先連線至 Cloudflare 以載入 Zone 與 DNS 紀錄</p>
    </div>
  );
}

export default function DomainPage() {
  const [records] = useState(MOCK);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <h1 className={styles.pageTitle}>網域管理</h1>
          <p className={styles.pageSubtitle}>
            用同一個工作台完成 Cloudflare 供應商連線、Zone 檢視，以及 DNS record 的新增、調整與刪除。
          </p>
        </div>
        <button
          type="button"
          className={styles.btnSecondary}
          onClick={() => window.open("https://dash.cloudflare.com", "_blank")}
        >
          <MIcon name="open_in_new" size={16} />
          開啟 Cloudflare Dashboard
        </button>
      </div>

      <div className={styles.content}>
        {records.length === 0 ? (
          <EmptyState />
        ) : (
          <div className={styles.list}>
            {records.map((r) => (
              <div key={r.id} className={styles.row}>
                <div className={styles.rowIcon}>
                  <MIcon name="dns" size={20} />
                </div>
                <div className={styles.rowMain}>
                  <span className={styles.rowName}>{r.name}</span>
                  <span className={styles.rowMeta}>{r.type} · {r.content}</span>
                </div>
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
