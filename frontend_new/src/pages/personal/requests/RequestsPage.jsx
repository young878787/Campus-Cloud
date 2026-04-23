import { useState } from "react";
import styles from "./RequestsPage.module.scss";
import RequestFormPage from "./RequestFormPage";

const MIcon = ({ name, size = 20 }) => (
  <span className="material-icons-outlined" style={{ fontSize: size, lineHeight: 1 }}>
    {name}
  </span>
);

/* ─── Mock data ──────────────────────────────────────── */
const MOCK_REQUESTS = [];

const STATUS_MAP = {
  pending:  { label: "審核中", color: "warning", icon: "schedule"     },
  approved: { label: "已核准", color: "success", icon: "check_circle" },
  rejected: { label: "已拒絕", color: "danger",  icon: "cancel"       },
};

/* ─── Sub-components ─────────────────────────────────── */
function StatusBadge({ status }) {
  const s = STATUS_MAP[status] ?? { label: status, color: "muted", icon: "info" };
  return (
    <span className={`${styles.badge} ${styles[`badge_${s.color}`]}`}>
      <MIcon name={s.icon} size={11} />
      {s.label}
    </span>
  );
}

function RequestCard({ req }) {
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <div className={styles.cardIcon}>
          <MIcon name={req.icon ?? "computer"} size={22} />
        </div>
        <div className={styles.cardMeta}>
          <span className={styles.cardName}>{req.name}</span>
          <span className={styles.cardType}>{req.type}</span>
        </div>
        <StatusBadge status={req.status} />
      </div>

      {req.specs && (
        <div className={styles.specGrid}>
          {req.specs.map((s) => (
            <div key={s.label} className={styles.specItem}>
              <span className={styles.specLabel}>{s.label}</span>
              <span className={styles.specValue}>{s.value}</span>
            </div>
          ))}
        </div>
      )}

      <div className={styles.cardFooter}>
        <span className={styles.cardDate}>申請於 {req.createdAt}</span>
        <button type="button" className={styles.cardDetailBtn} title="查看詳情">
          <MIcon name="arrow_forward" size={15} />
          查看詳情
        </button>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon}>
        <MIcon name="description" size={40} />
      </div>
      <h2 className={styles.emptyTitle}>尚無申請紀錄</h2>
      <p className={styles.emptyDesc}>你送出的虛擬機／容器申請將會顯示在這裡</p>
    </div>
  );
}

/* ─── Page ───────────────────────────────────────────── */
export default function RequestsPage() {
  const [requests] = useState(MOCK_REQUESTS);
  const [view, setView] = useState("list"); // "list" | "create"

  if (view === "create") {
    return (
      <RequestFormPage
        key="create"
        className={styles.animSlideInRight}
        onBack={() => setView("list")}
      />
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <h1 className={styles.pageTitle}>我的申請</h1>
          <p className={styles.pageSubtitle}>管理你的虛擬機與容器申請</p>
        </div>
        <button
          type="button"
          className={styles.btnPrimary}
          onClick={() => setView("create")}
        >
          <MIcon name="add" size={16} />
          申請資源
        </button>
      </div>

      <div className={styles.content}>
        {requests.length === 0 ? (
          <EmptyState />
        ) : (
          <div className={styles.grid}>
            {requests.map((r) => (
              <RequestCard key={r.id} req={r} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}