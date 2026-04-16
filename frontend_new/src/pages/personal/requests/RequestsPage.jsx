import { useState } from "react";
import styles from "./RequestsPage.module.scss";

const MIcon = ({ name, size = 20 }) => (
  <span className="material-icons-outlined" style={{ fontSize: size, lineHeight: 1 }}>
    {name}
  </span>
);

const MOCK_REQUESTS = [];

const STATUS_MAP = {
  pending:  { label: "審核中", color: "warning", icon: "schedule" },
  approved: { label: "已核准", color: "success", icon: "check_circle" },
  rejected: { label: "已拒絕", color: "danger",  icon: "cancel" },
};

function StatusBadge({ status }) {
  const s = STATUS_MAP[status] ?? { label: status, color: "muted", icon: "info" };
  return (
    <span className={`${styles.badge} ${styles[`badge_${s.color}`]}`}>
      <MIcon name={s.icon} size={12} />
      {s.label}
    </span>
  );
}

function RequestRow({ req }) {
  return (
    <div className={styles.row}>
      <div className={styles.rowIcon}>
        <MIcon name={req.icon ?? "computer"} size={20} />
      </div>
      <div className={styles.rowMain}>
        <span className={styles.rowName}>{req.name}</span>
        <span className={styles.rowMeta}>{req.type} · 申請於 {req.createdAt}</span>
      </div>
      <StatusBadge status={req.status} />
      <button type="button" className={styles.rowAction} title="查看詳情">
        <MIcon name="chevron_right" size={20} />
      </button>
    </div>
  );
}

function EmptyState({ onCreate }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon}>
        <MIcon name="description" size={40} />
      </div>
      <h2 className={styles.emptyTitle}>目前沒有申請紀錄</h2>
      <p className={styles.emptyDesc}>
        點擊「申請資源」按鈕即可送出第一筆虛擬機申請
      </p>
    </div>
  );
}

export default function RequestsPage() {
  const [requests] = useState(MOCK_REQUESTS);

  return (
    <div className={styles.page}>
      {/* ── 頁首 ── */}
      <div className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <h1 className={styles.pageTitle}>我的申請</h1>
          <p className={styles.pageSubtitle}>查看 VM／容器申請紀錄與審核狀態</p>
        </div>
        <button type="button" className={styles.btnPrimary}>
          <MIcon name="add" size={16} />
          申請資源
        </button>
      </div>

      {/* ── 內容 ── */}
      <div className={styles.content}>
        {requests.length === 0 ? (
          <EmptyState />
        ) : (
          <div className={styles.list}>
            {requests.map((r) => (
              <RequestRow key={r.id} req={r} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
