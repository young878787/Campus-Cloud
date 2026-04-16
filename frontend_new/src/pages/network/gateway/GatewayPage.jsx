import { useState } from "react";
import styles from "./GatewayPage.module.scss";

const MIcon = ({ name, size = 20 }) => (
  <span className="material-icons-outlined" style={{ fontSize: size, lineHeight: 1 }}>
    {name}
  </span>
);

const TABS = [
  { key: "connection", label: "連線設定" },
  { key: "haproxy",    label: "haproxy"  },
  { key: "traefik",    label: "Traefik"  },
  { key: "frps",       label: "frps"     },
  { key: "frpc",       label: "frpc"     },
];

const EMPTY_TEXT = {
  connection: "尚未設定連線資訊",
  haproxy:    "尚無 haproxy 設定",
  traefik:    "尚無 Traefik 設定",
  frps:       "尚無 frps 設定",
  frpc:       "尚無 frpc 設定",
};

function EmptyState({ tab }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon}>
        <MIcon name="dns" size={40} />
      </div>
      <h2 className={styles.emptyTitle}>{EMPTY_TEXT[tab]}</h2>
    </div>
  );
}

export default function GatewayPage() {
  const [activeTab, setActiveTab] = useState("connection");

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <div className={styles.titleRow}>
            <h1 className={styles.pageTitle}>Gateway VM 管理</h1>
            <div className={styles.ipBadge}>
              <MIcon name="check_circle" size={12} />
              192.168.100.143
            </div>
          </div>
          <p className={styles.pageSubtitle}>管理 haproxy、Traefik、frp 服務設定與狀態</p>
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
        <EmptyState tab={activeTab} />
      </div>
    </div>
  );
}
