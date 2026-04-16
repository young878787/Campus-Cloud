import { useState } from "react";
import styles from "./SettingsPage.module.scss";

const MIcon = ({ name, size = 20 }) => (
  <span className="material-icons-outlined" style={{ fontSize: size, lineHeight: 1 }}>
    {name}
  </span>
);

const TABS = [
  { key: "overview",  label: "叢集概覽", icon: "layers"         },
  { key: "pve",       label: "PVE 連線",  icon: "device_hub"    },
  { key: "scheduler", label: "資源排程",  icon: "settings_input_component" },
  { key: "nodes",     label: "節點管理",  icon: "lock"          },
  { key: "storage",   label: "Storage",   icon: "storage"       },
];

const EMPTY_TEXT = {
  overview:  "尚無叢集資料",
  pve:       "尚未設定 PVE 連線",
  scheduler: "尚無資源排程設定",
  nodes:     "尚無節點資料",
  storage:   "尚無 Storage 設定",
};

function EmptyState({ tab }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon}>
        <MIcon name="settings" size={40} />
      </div>
      <h2 className={styles.emptyTitle}>{EMPTY_TEXT[tab]}</h2>
    </div>
  );
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState("overview");

  return (
    <div className={styles.page}>
      {/* ── 頁首 ── */}
      <div className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <div className={styles.titleRow}>
            <h1 className={styles.pageTitle}>系統設定</h1>
            <div className={styles.ipBadge}>
              <MIcon name="check_circle" size={12} />
              192.168.100.2
            </div>
          </div>
          <p className={styles.pageSubtitle}>
            管理 Proxmox VE 連線、節點、Storage 與資源排程設定。
          </p>
        </div>

        {/* ── Tabs ── */}
        <div className={styles.tabs}>
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`${styles.tab} ${activeTab === tab.key ? styles.tabActive : ""}`}
              onClick={() => setActiveTab(tab.key)}
            >
              <MIcon name={tab.icon} size={16} />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── 內容 ── */}
      <div className={styles.content}>
        <EmptyState tab={activeTab} />
      </div>
    </div>
  );
}
