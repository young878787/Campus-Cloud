import { useState } from "react";
import styles from "./ResourcesPage.module.scss";

const MIcon = ({ name, size = 20 }) => (
  <span className="material-icons-outlined" style={{ fontSize: size, lineHeight: 1 }}>
    {name}
  </span>
);

/* ── 假資料（之後換成 API） ── */
const MOCK_RESOURCES = [];

const STATUS_MAP = {
  running:  { label: "運行中", color: "success" },
  stopped:  { label: "已停止", color: "warning" },
  error:    { label: "錯誤",   color: "danger"  },
};

function StatusBadge({ status }) {
  const s = STATUS_MAP[status] ?? { label: status, color: "muted" };
  return <span className={`${styles.badge} ${styles[`badge_${s.color}`]}`}>{s.label}</span>;
}

function ResourceCard({ resource }) {
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <div className={styles.cardIcon}>
          <MIcon name={resource.icon ?? "storage"} size={22} />
        </div>
        <div className={styles.cardMeta}>
          <span className={styles.cardName}>{resource.name}</span>
          <span className={styles.cardType}>{resource.type}</span>
        </div>
        <StatusBadge status={resource.status} />
      </div>

      <div className={styles.cardBody}>
        {resource.specs && (
          <div className={styles.specGrid}>
            {resource.specs.map((s) => (
              <div key={s.label} className={styles.specItem}>
                <span className={styles.specLabel}>{s.label}</span>
                <span className={styles.specValue}>{s.value}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className={styles.cardFooter}>
        <span className={styles.cardDate}>建立於 {resource.createdAt}</span>
        <div className={styles.cardActions}>
          <button type="button" className={styles.actionBtn} title="管理">
            <MIcon name="settings" size={16} />
          </button>
          <button type="button" className={`${styles.actionBtn} ${styles.actionBtnDanger}`} title="刪除">
            <MIcon name="delete" size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}

function EmptyState({ onCreate }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon}>
        <MIcon name="dns" size={48} />
      </div>
      <h2 className={styles.emptyTitle}>尚無資源</h2>
      <p className={styles.emptyDesc}>
        您申請通過的虛擬機/容器將會顯示在這裡
      </p>
      <button type="button" className={styles.emptyBtn} onClick={onCreate}>
        <MIcon name="add" size={18} />
        建立資源
      </button>
    </div>
  );
}

export default function ResourcesPage() {
  const [resources] = useState(MOCK_RESOURCES);

  return (
    <div className={styles.page}>
      {/* ── 頁首 ── */}
      <div className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <h1 className={styles.pageTitle}>我的資源</h1>
          <p className={styles.pageSubtitle}>
            查看與管理您申請通過的虛擬機和容器
          </p>
        </div>

        <div className={styles.pageActions}>
          <button type="button" className={styles.btnSecondary}>
            <MIcon name="download" size={16} />
            下載連線工具
          </button>
          <button type="button" className={styles.btnPrimary}>
            <MIcon name="sync" size={16} />
            重新整理
          </button>
        </div>
      </div>

      {/* ── 內容 ── */}
      <div className={styles.content}>
        {resources.length === 0 ? (
          <EmptyState onCreate={() => {}} />
        ) : (
          <div className={styles.grid}>
            {resources.map((r) => (
              <ResourceCard key={r.id} resource={r} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
