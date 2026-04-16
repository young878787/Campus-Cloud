import { useState, useRef, useEffect } from "react";
import { useTheme } from "../../contexts/ThemeContext";
import { useAuth }  from "../../contexts/AuthContext";
import styles from "./Sidebar.module.scss";

const MIcon = ({ name, size = 22 }) => (
  <span
    className="material-icons-outlined"
    style={{ fontSize: size, lineHeight: 1 }}
  >
    {name}
  </span>
);

const navGroups = [
  {
    key: "personal",
    label: "個人",
    icon: "person",
    items: [
      { key: "dashboard",    label: "儀表板",  icon: "dashboard" },
      { key: "my-resources", label: "我的資源", icon: "inventory_2" },
      { key: "my-requests",  label: "我的申請", icon: "assignment" },
    ],
  },
  {
    key: "network",
    label: "網路",
    icon: "router",
    items: [
      { key: "firewall",      label: "防火牆",     icon: "security" },
      { key: "reverse-proxy", label: "反向代理",   icon: "swap_horiz" },
      { key: "domain",        label: "網域管理",   icon: "domain" },
      { key: "gateway",       label: "Gateway VM", icon: "dns" },
    ],
  },
  {
    key: "resource",
    label: "資源",
    icon: "storage",
    items: [
      { key: "resource-mgmt",  label: "資源管理", icon: "storage" },
      { key: "request-review", label: "申請審核", icon: "fact_check" },
    ],
  },
  {
    key: "ai",
    label: "AI 服務",
    icon: "smart_toy",
    items: [
      { key: "ai-api",        label: "AI API",        icon: "psychology" },
      { key: "ai-api-review", label: "AI API Review", icon: "rate_review" },
      { key: "ai-api-keys",   label: "AI API Keys",   icon: "vpn_key" },
    ],
  },
  {
    key: "system",
    label: "系統管理",
    icon: "tune",
    items: [
      { key: "groups",    label: "Groups",          icon: "groups" },
      { key: "admin",     label: "管理員",           icon: "admin_panel_settings" },
      { key: "settings",  label: "System Settings", icon: "settings" },
      { key: "migration", label: "Migration Jobs",  icon: "move_down" },
      { key: "audit",     label: "Audit Logs",      icon: "receipt_long" },
    ],
  },
];

function NavGroup({ group, active, onSelect, collapsed, onExpand }) {
  const [open, setOpen] = useState(
    group.items.some((i) => i.key === active)
  );

  const hasActive = group.items.some((i) => i.key === active);

  const handleHeaderClick = () => {
    if (collapsed) {
      onExpand();
      setOpen(true);
    } else {
      setOpen((o) => !o);
    }
  };

  return (
    <div className={styles.group}>
      <button
        type="button"
        className={`${styles.groupHeader} ${hasActive ? styles.groupHeaderActive : ""}`}
        onClick={handleHeaderClick}
        title={collapsed ? group.label : undefined}
      >
        <MIcon name={group.icon} size={20} />
        {!collapsed && (
          <>
            <span className={styles.groupLabel}>{group.label}</span>
            <span className={`${styles.groupChevron} ${open ? styles.open : ""}`}>
              <MIcon name="chevron_right" size={16} />
            </span>
          </>
        )}
      </button>

      <div
        className={`${styles.groupItems} ${!collapsed && open ? styles.groupItemsOpen : ""}`}
      >
        <div className={styles.groupItemsInner}>
          {group.items.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`${styles.navItem} ${active === item.key ? styles.active : ""}`}
              onClick={() => onSelect(item.key)}
            >
              <MIcon name={item.icon} size={20} />
              <span className={styles.navLabel}>{item.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/** 通用彈出選單，供外觀與語言共用 */
function SelectPopup({ options, value, onSelect, onClose, triggerRef }) {
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      const inPopup = ref.current?.contains(e.target);
      const inTrigger = triggerRef?.current?.contains(e.target);
      if (!inPopup && !inTrigger) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose, triggerRef]);

  return (
    <div className={styles.appearancePopup} ref={ref}>
      {options.map((opt) => (
        <button
          key={opt.key}
          type="button"
          className={`${styles.appearanceOption} ${value === opt.key ? styles.appearanceOptionActive : ""}`}
          onClick={() => { onSelect(opt.key); onClose(); }}
        >
          {opt.flag
            ? <span className={styles.optionFlag}>{opt.flag}</span>
            : <MIcon name={opt.icon} size={18} />
          }
          <span>{opt.label}</span>
        </button>
      ))}
    </div>
  );
}

function UserPopup({ user, onLogout, onClose, triggerRef }) {
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      const inPopup = ref.current?.contains(e.target);
      const inTrigger = triggerRef?.current?.contains(e.target);
      if (!inPopup && !inTrigger) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose, triggerRef]);

  return (
    <div className={styles.userPopup} ref={ref}>
      <div className={styles.userPopupHeader}>
        <div className={styles.userPopupAvatar}>
          {user?.full_name?.[0]?.toUpperCase() ?? user?.email?.[0]?.toUpperCase() ?? "U"}
        </div>
        <div className={styles.userPopupInfo}>
          <span className={styles.userName}>{user?.full_name ?? "—"}</span>
          <span className={styles.userEmail}>{user?.email ?? "—"}</span>
        </div>
      </div>
      <div className={styles.userPopupDivider} />
      <button type="button" className={styles.userPopupItem} onClick={onClose}>
        <MIcon name="settings" size={18} />
        <span>User Settings</span>
      </button>
      <button
        type="button"
        className={`${styles.userPopupItem} ${styles.userPopupItemDanger}`}
        onClick={() => { onClose(); onLogout(); }}
      >
        <MIcon name="logout" size={18} />
        <span>Log Out</span>
      </button>
    </div>
  );
}

const THEME_OPTIONS = [
  { key: "light",  label: "淺色", icon: "light_mode" },
  { key: "dark",   label: "深色", icon: "dark_mode" },
  { key: "system", label: "系統", icon: "monitor" },
];

const LANG_OPTIONS = [
  { key: "zh-TW", label: "繁體中文", flag: "🇹🇼" },
  { key: "en",    label: "English",  flag: "🇬🇧" },
  { key: "ja",    label: "日本語",   flag: "🇯🇵" },
];

export default function Sidebar({ collapsed, mobileOpen, onToggle, onClose, activePage, onNavigate }) {
  const [active, setActive] = useState(activePage ?? "dashboard");
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const [lang, setLang] = useState("zh-TW");
  const appearanceBtnRef = useRef(null);
  const langBtnRef = useRef(null);
  const userBtnRef = useRef(null);
  const { mode, setMode } = useTheme();
  const { user, logout } = useAuth();

  const cls = [
    styles.sidebar,
    collapsed && styles.collapsed,
    mobileOpen && styles.mobileOpen,
  ]
    .filter(Boolean)
    .join(" ");

  const handleNav = (key) => {
    setActive(key);
    onNavigate?.(key);
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
            <span className={styles.brandText}>Campus Cloud</span>
          </>
        )}
      </div>

      {/* ===== Main nav ===== */}
      <nav className={styles.nav}>
        {navGroups.map((group) => (
          <NavGroup
            key={group.key}
            group={group}
            active={active}
            onSelect={handleNav}
            collapsed={collapsed}
            onExpand={onToggle}
          />
        ))}
      </nav>

      {/* ===== Bottom section ===== */}
      <div className={styles.bottom}>
        {/* 外觀選擇 */}
        <div className={styles.appearanceWrap}>
          {appearanceOpen && (
            <SelectPopup
              options={THEME_OPTIONS}
              value={mode}
              onSelect={setMode}
              onClose={() => setAppearanceOpen(false)}
              triggerRef={appearanceBtnRef}
            />
          )}
          <button
            ref={appearanceBtnRef}
            type="button"
            className={`${styles.navItem} ${appearanceOpen ? styles.active : ""}`}
            onClick={() => setAppearanceOpen((o) => !o)}
            title={collapsed ? "外觀" : undefined}
          >
            <MIcon name="palette" size={20} />
            {!collapsed && <span className={styles.navLabel}>外觀</span>}
          </button>
        </div>

        {/* 語言選擇 */}
        <div className={styles.appearanceWrap}>
          {langOpen && (
            <SelectPopup
              options={LANG_OPTIONS}
              value={lang}
              onSelect={setLang}
              onClose={() => setLangOpen(false)}
              triggerRef={langBtnRef}
            />
          )}
          <button
            ref={langBtnRef}
            type="button"
            className={`${styles.navItem} ${langOpen ? styles.active : ""}`}
            onClick={() => setLangOpen((o) => !o)}
            title={collapsed ? "語言" : undefined}
          >
            <MIcon name="language" size={20} />
            {!collapsed && <span className={styles.navLabel}>語言 / Language</span>}
          </button>
        </div>

        {/* 使用者資料 */}
        <div className={styles.appearanceWrap}>
          {userOpen && (
            <UserPopup
              user={user}
              onLogout={logout}
              onClose={() => setUserOpen(false)}
              triggerRef={userBtnRef}
            />
          )}
          <button
            ref={userBtnRef}
            type="button"
            className={`${styles.user} ${userOpen ? styles.userActive : ""}`}
            onClick={() => setUserOpen((o) => !o)}
            title={collapsed ? (user?.full_name ?? user?.email) : undefined}
          >
            <div className={styles.avatar}>
              {user?.full_name?.[0]?.toUpperCase() ?? user?.email?.[0]?.toUpperCase() ?? "U"}
            </div>
            {!collapsed && (
              <>
                <div className={styles.userInfo}>
                  <span className={styles.userName}>{user?.full_name ?? "—"}</span>
                  <span className={styles.userEmail}>{user?.email ?? "—"}</span>
                </div>
                <MIcon name={userOpen ? "expand_more" : "unfold_more"} size={16} />
              </>
            )}
          </button>
        </div>
      </div>
    </aside>
  );
}
