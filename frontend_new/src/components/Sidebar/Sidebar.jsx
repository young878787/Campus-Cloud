import { useState } from "react";
import { useTheme } from "../../contexts/ThemeContext";
import styles from "./Sidebar.module.scss";

const MIcon = ({ name, size = 22 }) => (
  <span
    className="material-icons-outlined"
    style={{ fontSize: size, lineHeight: 1 }}
  >
    {name}
  </span>
);

const navItems = [
  { key: "overview", label: "總覽", icon: "dashboard" },
  { key: "firewall", label: "防火牆", icon: "security" },
  { key: "vm", label: "虛擬機器", icon: "computer" },
  { key: "images", label: "映像檔管理", icon: "album" },
  { key: "ai-api", label: "AI API", icon: "psychology" },
  { key: "ai-keys", label: "AI API Keys", icon: "vpn_key" },
  { key: "ai-new", label: "AI APIS New", icon: "api" },
  { key: "groups", label: "Groups", icon: "groups" },
  { key: "usage", label: "使用量", icon: "insert_chart_outlined" },
  { key: "settings", label: "System Settings", icon: "settings" },
  { key: "migration", label: "Migration Jobs", icon: "swap_horiz" },
  { key: "gateway", label: "Gateway VM", icon: "dns" },
  { key: "audit", label: "Audit Logs", icon: "receipt_long" },
];

export default function Sidebar({ collapsed, mobileOpen, onToggle, onClose }) {
  const [active, setActive] = useState("overview");
  const { theme, toggle: toggleTheme } = useTheme();

  const cls = [
    styles.sidebar,
    collapsed && styles.collapsed,
    mobileOpen && styles.mobileOpen,
  ]
    .filter(Boolean)
    .join(" ");

  const handleNav = (key) => {
    setActive(key);
    onClose?.();
  };

  return (
    <aside className={cls}>
      {/* ===== Brand ===== */}
      <div className={styles.brand} onClick={onToggle}>
        <span className={styles.brandIcon}>
          <MIcon name="bolt" size={18} />
        </span>
        {!collapsed && (
          <>
            <span className={styles.brandText}>FastAPI</span>
            <span className={styles.statusDot} />
          </>
        )}
      </div>

      {/* ===== Main nav ===== */}
      <nav className={styles.nav}>
        {navItems.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`${styles.navItem} ${active === item.key ? styles.active : ""}`}
            onClick={() => handleNav(item.key)}
            title={collapsed ? item.label : undefined}
          >
            <MIcon name={item.icon} size={20} />
            {!collapsed && <span className={styles.navLabel}>{item.label}</span>}
          </button>
        ))}
      </nav>

      {/* ===== Bottom section ===== */}
      <div className={styles.bottom}>
        <button
          type="button"
          className={styles.navItem}
          onClick={toggleTheme}
          title={collapsed ? "切換主題" : undefined}
        >
          <MIcon name={theme === "light" ? "dark_mode" : "light_mode"} size={20} />
          {!collapsed && (
            <span className={styles.navLabel}>
              {theme === "light" ? "深色模式" : "淺色模式"}
            </span>
          )}
        </button>

        <button type="button" className={styles.navItem}>
          <MIcon name="language" size={20} />
          {!collapsed && <span className={styles.navLabel}>語言 / Language</span>}
        </button>

        <button type="button" className={styles.navItem}>
          <MIcon name="apartment" size={20} />
          {!collapsed && <span className={styles.navLabel}>大廳</span>}
        </button>

        <div className={styles.user}>
          <div className={styles.avatar}>
            <MIcon name="person" size={18} />
          </div>
          {!collapsed && (
            <div className={styles.userInfo}>
              <span className={styles.userName}>lianqianyi</span>
              <span className={styles.userEmail}>11156023@ntub.edu.tw</span>
            </div>
          )}
        </div>
      </div>

      {/* ===== Footer ===== */}
      <div className={styles.footer}>
        {collapsed ? "CC" : "Campus Cloud · 2026"}
      </div>
    </aside>
  );
}
