import { useState } from "react";
import styles from "./ReverseProxyPage.module.scss";

const MIcon = ({ name, size = 20 }) => (
  <span className="material-icons-outlined" style={{ fontSize: size, lineHeight: 1 }}>
    {name}
  </span>
);

/* ── Mock data ─────────────────────────────────────── */
const MOCK_ROUTES = [];

const MOCK_TRAEFIK = {
  status: "unknown",
  entrypoints: [
    { name: "traefik", addr: "127.0.0.1:8080" },
    { name: "web",     addr: ":80"            },
    { name: "websecure", addr: ":443"         },
  ],
  http: { routers: 4, services: 4, middlewares: 3 },
  tcp:  { routers: 0, services: 0 },
  udp:  { routers: 0, services: 0 },
};

/* ── Sub-components ────────────────────────────────── */
function HowItWorks() {
  const [open, setOpen] = useState(false);

  const STEPS = [
    {
      icon: "edit_note",
      num: "1",
      title: "設定網域",
      desc: "輸入主機名稱、選擇 Cloudflare Zone，並指定要綁定的 VM 和 Port。",
    },
    {
      icon: "auto_awesome",
      num: "2",
      title: "系統自動設定",
      desc: "平台自動配置路由規則，開啟 HTTPS 時還會自動申請免費的 SSL 憑證。",
    },
    {
      icon: "open_in_browser",
      num: "3",
      title: "直接訪問",
      desc: "任何人都可以透過這個網址直接訪問你 VM 裡跑的網站或 API。",
    },
  ];

  const PREREQS = [
    "你的 VM 裡需要有一個正在執行的網站或 API 服務",
    "你需要知道服務跑在哪個 Port（Node.js 預設 3000、Flask 預設 5000、Nginx 預設 80）",
    "管理員需要先在 Cloudflare 域名管理設定預設 A/CNAME 指向與可用 Zone",
  ];

  return (
    <div className={styles.infoCard}>
      <button
        type="button"
        className={styles.infoToggle}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className={styles.infoToggleLeft}>
          <MIcon name="help_outline" size={16} />
          這是什麼？反向代理怎麼運作？
        </span>
        <span className={`${styles.infoChevron} ${open ? styles.open : ""}`}>
          <MIcon name="expand_more" size={18} />
        </span>
      </button>

      {open && (
        <div className={styles.infoBody}>
          <div className={styles.steps}>
            {STEPS.map((s) => (
              <div key={s.num} className={styles.step}>
                <div className={styles.stepNum}>{s.num}</div>
                <div className={styles.stepContent}>
                  <span className={styles.stepTitle}>{s.title}</span>
                  <span className={styles.stepDesc}>{s.desc}</span>
                </div>
              </div>
            ))}
          </div>

          <div className={styles.prereqBox}>
            <span className={styles.prereqTitle}>
              <MIcon name="checklist" size={15} />
              前置作業
            </span>
            <ul className={styles.prereqList}>
              {PREREQS.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

function RouteRow({ route }) {
  return (
    <div className={styles.row}>
      <div className={styles.rowIcon}>
        <MIcon name="swap_horiz" size={20} />
      </div>
      <div className={styles.rowMain}>
        <span className={styles.rowName}>{route.hostname}</span>
        <span className={styles.rowMeta}>
          {route.vm} · Port {route.port}
          {route.https && (
            <span className={styles.badge}>
              <MIcon name="lock" size={11} /> HTTPS
            </span>
          )}
        </span>
      </div>
      <div className={styles.rowStatus}>
        <span className={`${styles.statusDot} ${styles[route.status]}`} />
        {route.status === "active" ? "運作中" : "未知"}
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
  );
}

function EmptyState({ onAdd }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon}>
        <MIcon name="swap_horiz" size={36} />
      </div>
      <h2 className={styles.emptyTitle}>還沒有設定任何反向代理</h2>
      <p className={styles.emptyDesc}>
        將你 VM 裡跑的服務綁定到公開網域，讓外部可以直接訪問。
      </p>
      <button type="button" className={styles.btnPrimary} onClick={onAdd}>
        <MIcon name="add" size={16} />
        新增第一筆路由
      </button>
    </div>
  );
}

function TraefikPanel() {
  const [open, setOpen] = useState(false);
  const t = MOCK_TRAEFIK;

  const statusColor = t.status === "running" ? "running" : "unknown";

  return (
    <div className={styles.adminCard}>
      <button
        type="button"
        className={styles.adminToggle}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className={styles.adminToggleLeft}>
          <MIcon name="security" size={16} />
          管理員工具 — Traefik Runtime
          <span className={styles.adminBadge}>Admin</span>
        </span>
        <span className={`${styles.infoChevron} ${open ? styles.open : ""}`}>
          <MIcon name="expand_more" size={18} />
        </span>
      </button>

      {open && (
        <div className={styles.adminBody}>
          {/* Status row */}
          <div className={styles.adminMeta}>
            <span className={`${styles.statusPill} ${styles[statusColor]}`}>
              Traefik {t.status}
            </span>
            <span className={styles.statusPill}>
              {t.entrypoints.length} entrypoints
            </span>
          </div>

          {/* Stats grid */}
          <div className={styles.statsGrid}>
            {[
              { label: "HTTP",  data: t.http },
              { label: "TCP",   data: t.tcp  },
              { label: "UDP",   data: t.udp  },
            ].map(({ label, data }) => (
              <div key={label} className={styles.statCard}>
                <span className={styles.statLabel}>{label}</span>
                <dl className={styles.statList}>
                  <div>
                    <dt>Routers</dt>
                    <dd className={data.routers ? styles.numActive : styles.numZero}>{data.routers}</dd>
                  </div>
                  <div>
                    <dt>Services</dt>
                    <dd className={data.services ? styles.numActive : styles.numZero}>{data.services}</dd>
                  </div>
                  {data.middlewares !== undefined && (
                    <div>
                      <dt>Middlewares</dt>
                      <dd className={data.middlewares ? styles.numActive : styles.numZero}>{data.middlewares}</dd>
                    </div>
                  )}
                </dl>
              </div>
            ))}
          </div>

          {/* Entrypoints */}
          <div className={styles.entrySection}>
            <span className={styles.entrySectionLabel}>Entrypoints</span>
            <div className={styles.entryList}>
              {t.entrypoints.map((ep) => (
                <code key={ep.name} className={styles.entryChip}>
                  {ep.name} ({ep.addr})
                </code>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Page ──────────────────────────────────────────── */
export default function ReverseProxyPage() {
  const [routes] = useState(MOCK_ROUTES);

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div className={styles.pageHeading}>
          <h1 className={styles.pageTitle}>反向代理</h1>
          <p className={styles.pageSubtitle}>
            將 VM 內的服務綁定至公開網域，平台自動處理路由與 SSL 憑證。
          </p>
        </div>
        <button type="button" className={styles.btnPrimary}>
          <MIcon name="add" size={16} />
          新增路由
        </button>
      </div>

      {/* How it works */}
      <HowItWorks />

      {/* Route list / empty */}
      <div className={styles.content}>
        {routes.length === 0 ? (
          <EmptyState onAdd={() => {}} />
        ) : (
          <div className={styles.list}>
            {routes.map((r) => (
              <RouteRow key={r.id} route={r} />
            ))}
          </div>
        )}
      </div>

      {/* Admin: Traefik */}
      <TraefikPanel />
    </div>
  );
}
