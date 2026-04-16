import { useState } from "react";
import styles from "./RequestReviewPage.module.scss";

const MIcon = ({ name, size = 20 }) => (
  <span className="material-icons-outlined" style={{ fontSize: size, lineHeight: 1 }}>
    {name}
  </span>
);

const TABS = [
  { key: "pending",  label: "待審核" },
  { key: "approved", label: "已通過" },
  { key: "rejected", label: "已拒絕" },
  { key: "all",      label: "全部"   },
];

const EMPTY_TEXT = {
  pending:  "目前沒有待審核的申請",
  approved: "目前沒有已通過的申請",
  rejected: "目前沒有已拒絕的申請",
  all:      "目前沒有任何申請紀錄",
};

const MOCK_REQUESTS = [];

function EmptyState({ tab }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon}>
        <MIcon name="assignment_turned_in" size={40} />
      </div>
      <h2 className={styles.emptyTitle}>沒有申請紀錄</h2>
      <p className={styles.emptyDesc}>{EMPTY_TEXT[tab]}</p>
    </div>
  );
}

export default function RequestReviewPage() {
  const [activeTab, setActiveTab] = useState("pending");
  const [requests] = useState(MOCK_REQUESTS);

  const filtered = activeTab === "all"
    ? requests
    : requests.filter((r) => r.status === activeTab);

  return (
    <div className={styles.page}>
      {/* ── 頁首 ── */}
      <div className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <h1 className={styles.pageTitle}>申請審核</h1>
          <p className={styles.pageSubtitle}>審核使用者的虛擬機/容器申請</p>
        </div>
        <div className={styles.tabs}>
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`${styles.tab} ${activeTab === tab.key ? styles.tabActive : ""}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── 內容 ── */}
      <div className={styles.content}>
        {filtered.length === 0 ? (
          <EmptyState tab={activeTab} />
        ) : (
          <div className={styles.list}>
            {filtered.map((r) => (
              <div key={r.id} className={styles.row}>
                <div className={styles.rowIcon}>
                  <MIcon name="computer" size={20} />
                </div>
                <div className={styles.rowMain}>
                  <span className={styles.rowName}>{r.name}</span>
                  <span className={styles.rowMeta}>{r.user} · {r.createdAt}</span>
                </div>
                <div className={styles.rowActions}>
                  <button type="button" className={styles.btnApprove}>核准</button>
                  <button type="button" className={styles.btnReject}>拒絕</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
