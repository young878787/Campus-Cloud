import { useState } from "react";
import styles from "./AiApiReviewPage.module.scss";

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
  pending:  "目前沒有符合條件的 AI API 申請",
  approved: "目前沒有已通過的 AI API 申請",
  rejected: "目前沒有已拒絕的 AI API 申請",
  all:      "目前沒有任何 AI API 申請紀錄",
};

const MOCK = [];

function EmptyState({ tab }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon}>
        <MIcon name="assignment_turned_in" size={40} />
      </div>
      <p className={styles.emptyDesc}>{EMPTY_TEXT[tab]}</p>
    </div>
  );
}

export default function AiApiReviewPage() {
  const [activeTab, setActiveTab] = useState("pending");

  const filtered = activeTab === "all" ? MOCK : MOCK.filter((r) => r.status === activeTab);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <h1 className={styles.pageTitle}>AI API 審核</h1>
          <p className={styles.pageSubtitle}>審核申請並核發 API 存取參數。</p>
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

      <div className={styles.content}>
        {filtered.length === 0 ? (
          <EmptyState tab={activeTab} />
        ) : (
          <div className={styles.list}>
            {filtered.map((r) => (
              <div key={r.id} className={styles.row}>
                <div className={styles.rowIcon}>
                  <MIcon name="psychology" size={20} />
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
