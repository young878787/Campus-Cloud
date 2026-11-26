import { useState, useRef, useEffect, useCallback, useId } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth }  from "../../contexts/AuthContext";
import { useUnsavedChanges } from "../../contexts/UnsavedChangesContext";
import { currentLanguage, setLanguage } from "../../i18n";
import useScrollEdges from "../../hooks/useScrollEdges";
import useDialogPresence from "../../hooks/useDialogPresence";
import styles from "./Sidebar.module.scss";
import MIcon from "../MIcon";
import Avatar from "../Avatar/Avatar";
import OctoMark from "../OctoPet/OctoMark";
import JobsButton from "../Jobs/JobsButton";
import ActionMenu from "../ActionMenu/ActionMenu";
import ListboxPopover from "../ListboxPopover/ListboxPopover";
import { canTeachUser, canViewStudentCourses, isAdminUser } from "../../utils/roles";

const topItems = [
  { key: "dashboard", labelKey: "Sidebar.topDashboard", icon: "dashboard" },
];

/* 確認頁沿用舊網址 /quick-template/:id，側欄仍要亮在「快速練習」 */
const activeKeyAliases = { "quick-template": "quick-create" };

const navGroups = [
  {
    key: "resource",
    labelKey: "Sidebar.groupResource",
    icon: "storage",
    items: [
      { key: "my-resources",  labelKey: "Sidebar.itemMyResources",    icon: "inventory_2" },
      { key: "my-requests",   labelKey: "Sidebar.itemMyRequests",    icon: "assignment" },
      { key: "resource-mgmt", labelKey: "Sidebar.itemResourceMgmt",    icon: "storage", adminOnly: true },
      { key: "templates",     labelKey: "Sidebar.itemTemplates",    icon: "library_books", instructorOnly: true },
    ],
  },
  {
    key: "review",
    labelKey: "Sidebar.groupReview",
    icon: "fact_check",
    items: [
      { key: "request-review", labelKey: "Sidebar.itemRequestReview", icon: "fact_check", adminOnly: true },
      { key: "batch-review",   labelKey: "Sidebar.itemBatchReview", icon: "library_add_check", adminOnly: true },
      { key: "ai-api-review",  labelKey: "Sidebar.itemAiApiReview", icon: "rate_review", adminOnly: true },
    ],
  },
  {
    key: "network",
    labelKey: "Sidebar.groupNetwork",
    icon: "router",
    items: [
      { key: "firewall",      labelKey: "Sidebar.itemFirewall",     icon: "security" },
      /* 對外網址沒有獨立頁面；從防火牆拓撲頁或資源詳情「進階設定 › 防火牆」的連線對話框發布 */
    ],
  },
  {
    key: "ai",
    labelKey: "Sidebar.groupAi",
    icon: "support_agent",
    items: [
      { key: "ai-api",        labelKey: "Sidebar.itemAiApi",   icon: "psychology" },
      { key: "ai-api-keys",   labelKey: "Sidebar.itemAiApiKeys", icon: "vpn_key", adminOnly: true },
      /* AI 用量監控已移到「監控與日誌」 */
      /* PVE 維運助手不放側欄：管理者首頁就是它的入口，那裡同時看得到待處理的問題 */
    ],
  },
  {
    key: "teaching",
    labelKey: "Sidebar.groupTeaching",
    icon: "school",
    items: [
      { key: "courses", labelKey: "Sidebar.topCourses", icon: "school", studentCoursesOnly: true },
      { key: "class-management", labelKey: "Sidebar.itemClassManagement", icon: "groups_2", instructorOnly: true },
      { key: "course-template-management", labelKey: "Sidebar.itemCourseTemplateManagement", icon: "view_quilt", instructorOnly: true },
      /* 快速練習對所有登入者開放（後端 quick-practice 沒有角色限制） */
      { key: "quick-create", labelKey: "Sidebar.itemQuickCreate", icon: "bolt" },
    ],
  },
  {
    key: "monitoring",
    labelKey: "Sidebar.groupMonitoring",
    icon: "insights",
    items: [
      { key: "monitoring",    labelKey: "Sidebar.itemMonitoring",       icon: "monitor_heart", adminOnly: true },
      { key: "ai-monitoring", labelKey: "Sidebar.itemAiMonitoring", icon: "query_stats", adminOnly: true },
      { key: "jobs",          labelKey: "Sidebar.itemJobs",       icon: "task_alt" },
      { key: "audit",         labelKey: "Sidebar.itemAudit",     icon: "receipt_long", adminOnly: true },
      /* 帳號設定「關於」分頁送進來的問題回報與建議 */
      { key: "feedback",      labelKey: "Sidebar.itemFeedback",  icon: "rate_review", adminOnly: true },
    ],
  },
];

/* 系統管理已移出主導覽分類：由底部「管理員設定」進入專屬核心側欄（僅管理員），路由沿用原本的網址 */
const adminSettingsItems = [
  { key: "admin",           labelKey: "Sidebar.itemAdmin",          icon: "admin_panel_settings" },
  { key: "ip-management",   labelKey: "Sidebar.itemIpManagement",   icon: "lan" },
  { key: "domain",          labelKey: "Sidebar.itemDomain",         icon: "domain" },
  { key: "gateway",         labelKey: "Sidebar.itemGateway",        icon: "dns" },
  /* 原「系統設定」的七個分頁，2026-09 各自升格為獨立頁面 */
  { key: "pve-connections", labelKey: "Sidebar.itemPveConnections", icon: "device_hub" },
  { key: "scheduler",       labelKey: "Sidebar.itemScheduler",      icon: "settings_input_component" },
  { key: "governance",      labelKey: "Sidebar.itemGovernance",     icon: "policy" },
  { key: "ldap",            labelKey: "Sidebar.itemLdap",           icon: "badge" },
  { key: "storage",         labelKey: "Sidebar.itemStorage",        icon: "storage" },
  { key: "gpu-mgmt",        labelKey: "Sidebar.itemGpuMgmt",        icon: "memory" },
];

/** 釘選狀態存 localStorage，跨 session 保留（不可用時僅本次瀏覽生效） */
const PIN_STORAGE_KEY = "skylab.sidebarPins";

function loadPinnedKeys() {
  try {
    const stored = JSON.parse(window.localStorage.getItem(PIN_STORAGE_KEY) ?? "[]");
    return Array.isArray(stored) ? stored : [];
  } catch {
    return [];
  }
}

function savePinnedKeys(keys) {
  try {
    window.localStorage.setItem(PIN_STORAGE_KEY, JSON.stringify(keys));
  } catch {
    // localStorage 不可用時釘選僅本次瀏覽生效
  }
}

function NavGroup({ group, active, onSelect, collapsed, onExpand, pinnedKeys, onTogglePin, defaultOpen = false }) {
  const { t } = useTranslation("common");
  const [open, setOpen] = useState(
    defaultOpen || group.items.some((i) => i.key === active)
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
        title={collapsed ? t(group.labelKey) : undefined}
        aria-label={t(group.labelKey)}
        aria-expanded={!collapsed && open}
      >
        <MIcon name={group.icon} size={20} />
        {!collapsed && (
          <>
            <span className={styles.groupLabel}>{t(group.labelKey)}</span>
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
          {group.items.map((item) => {
            const pinned = pinnedKeys.includes(item.key);
            return (
              <div key={item.key} className={styles.navItemRow}>
                <button
                  type="button"
                  className={`${styles.navItem} ${active === item.key ? styles.active : ""}`}
                  onClick={() => onSelect(item.key)}
                  aria-label={t(item.labelKey)}
                >
                  <span className={styles.navLabel}>{t(item.labelKey)}</span>
                </button>
                <button
                  type="button"
                  className={`${styles.pinBtn} ${pinned ? styles.pinBtnPinned : ""}`}
                  onClick={() => onTogglePin(item.key)}
                  title={pinned ? t("Sidebar.unpin") : t("Sidebar.pin")}
                  aria-label={pinned ? t("Sidebar.unpin") : t("Sidebar.pin")}
                  aria-pressed={pinned}
                >
                  <MIcon name="push_pin" size={14} filled={pinned} />
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* 語言名稱用各自的語言寫，不放國旗：Windows 不畫國旗 emoji，只會變成 TW／GB／JP 字母 */
const LANG_OPTIONS = [
  { value: "zh-TW", label: "繁體中文" },
  { value: "en",    label: "English" },
  { value: "ja",    label: "日本語" },
];

export default function Sidebar({ collapsed, mobileOpen, onToggle, onClose }) {
  const { t, i18n } = useTranslation("common");
  const navigate = useNavigate();
  const location = useLocation();
  const routeKey = location.pathname.split("/")[1] || "dashboard";
  const active   = activeKeyAliases[routeKey] ?? routeKey;
  const lang = currentLanguage(i18n.language);
  /* 側欄底部的語言、帳號選單：貼著側欄外緣彈出、跟側欄同一套玻璃（同背景任務），關閉時保留 130ms 離場動畫 */
  const [langOpen, setLangOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const langMenu = useDialogPresence(langOpen, 130);
  const userMenu = useDialogPresence(userOpen, 130);
  const langBtnRef = useRef(null);
  const userBtnRef = useRef(null);
  const langMenuId = useId();
  const userMenuId = useId();
  const { user, logout } = useAuth();
  const { confirmLeave } = useUnsavedChanges();
  const isAdmin = isAdminUser(user);
  const canTeach = canTeachUser(user);
  const canViewCourses = canViewStudentCourses(user);
  /* 身在系統管理頁面時，整支側欄切換成「管理員設定」核心側欄 */
  const inAdminSettings = isAdmin && adminSettingsItems.some((item) => item.key === active);
  const visibleNavGroups = navGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) =>
        (!item.adminOnly || isAdmin) && (!item.instructorOnly || canTeach) && (!item.studentCoursesOnly || canViewCourses)
      ),
    }))
    .filter((group) => group.items.length > 0);

  const [pinnedKeys, setPinnedKeys] = useState(loadPinnedKeys);
  const togglePin = useCallback((key) => {
    setPinnedKeys((prev) => {
      const next = prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key];
      savePinnedKeys(next);
      return next;
    });
  }, []);
  // 只留權限內看得到的項目；沒權限的釘選保留在 storage，換帳號登入不會消失
  const visibleItems = visibleNavGroups.flatMap((group) => group.items);
  const pinnedItems = pinnedKeys
    .map((key) => visibleItems.find((item) => item.key === key))
    .filter(Boolean);

  // 導覽捲到一半時，在被裁的那一側畫漸層淡出（捲軸是藏起來的）
  const navScroll = useScrollEdges();

  const cls = [
    styles.sidebar,
    collapsed && styles.collapsed,
    mobileOpen && styles.mobileOpen,
  ]
    .filter(Boolean)
    .join(" ");

  const handleNav = async (key) => {
    if (!(await confirmLeave())) return;
    navigate(`/${key}`);
    onClose?.();
  };

  /* 收合／展開有寬度動畫，貼著側欄外緣的選單會對不準，切換時直接收起 */
  useEffect(() => {
    setLangOpen(false);
    setUserOpen(false);
  }, [collapsed]);

  const userMenuItems = [
    { key: "settings", label: t("Sidebar.userSettings"), icon: "settings", onSelect: () => handleNav("account") },
    {
      key: "logout",
      label: t("Sidebar.logOut"),
      icon: "logout",
      danger: true,
      bombadil: true,
      onSelect: async () => {
        /* 登出會被路由守衛直接導到登入頁，不觸發 beforeunload，要先確認未儲存的表單 */
        if (await confirmLeave()) logout();
      },
    },
  ];

  return (
    <aside className={cls}>
      {/* ===== Brand ===== */}
      <div className={styles.brand} onClick={() => window.innerWidth >= 1024 && onToggle?.()}>
        {/* 品牌標誌＝靜態的章魚學士（跟 AI 助手同一隻），不再用 favicon 點陣圖 */}
        <span className={styles.brandIcon}>
          <OctoMark size={28} label="SkyLab" />
        </span>
        {!collapsed && (
          <>
            <span className={styles.brandText}>SkyLab</span>
          </>
        )}
      </div>

      <div className={styles.divider} />

      {/* ===== Main nav ===== */}
      {inAdminSettings ? (
        <nav className={styles.nav} ref={navScroll.ref} data-scroll-edges={navScroll.edges}>
          {/* 麵包屑：左半的「主控台」是返回入口，右半標示目前在哪個模式。
              收合時只剩箭頭鈕（放不下文字） */}
          {collapsed ? (
            <button
              type="button"
              className={styles.backItem}
              onClick={() => handleNav("dashboard")}
              title={t("Sidebar.backToConsole")}
              aria-label={t("Sidebar.backToConsole")}
            >
              <MIcon name="arrow_back" size={16} />
            </button>
          ) : (
            <>
              <div className={styles.breadcrumb}>
                <button
                  type="button"
                  className={styles.crumbLink}
                  onClick={() => handleNav("dashboard")}
                  aria-label={t("Sidebar.backToConsole")}
                >
                  {t("Sidebar.console")}
                </button>
                <MIcon name="chevron_right" size={14} />
                <span className={styles.crumbCurrent}>{t("Sidebar.adminSettings")}</span>
              </div>
            </>
          )}
          {adminSettingsItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`${styles.navItem} ${active === item.key ? styles.active : ""}`}
              onClick={() => handleNav(item.key)}
              title={collapsed ? t(item.labelKey) : undefined}
              aria-label={t(item.labelKey)}
            >
              <MIcon name={item.icon} size={20} />
              {!collapsed && <span className={styles.navLabel}>{t(item.labelKey)}</span>}
            </button>
          ))}
        </nav>
      ) : (
      <nav className={styles.nav} ref={navScroll.ref} data-scroll-edges={navScroll.edges}>
        {topItems.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`${styles.navItem} ${active === item.key ? styles.active : ""}`}
            onClick={() => handleNav(item.key)}
            title={collapsed ? t(item.labelKey) : undefined}
            aria-label={t(item.labelKey)}
          >
            <MIcon name={item.icon} size={20} />
            {!collapsed && <span className={styles.navLabel}>{t(item.labelKey)}</span>}
          </button>
        ))}
        {/* 釘選的快速捷徑（保留釘選順序） */}
        {pinnedItems.map((item) => (
          <div key={`pinned-${item.key}`} className={styles.navItemRow}>
            <button
              type="button"
              className={`${styles.navItem} ${active === item.key ? styles.active : ""}`}
              onClick={() => handleNav(item.key)}
              title={collapsed ? t(item.labelKey) : undefined}
              aria-label={t(item.labelKey)}
            >
              <MIcon name={item.icon} size={20} />
              {!collapsed && <span className={styles.navLabel}>{t(item.labelKey)}</span>}
            </button>
            {!collapsed && (
              <button
                type="button"
                className={`${styles.pinBtn} ${styles.pinBtnPinned}`}
                onClick={() => togglePin(item.key)}
                title={t("Sidebar.unpin")}
                aria-label={t("Sidebar.unpin")}
              >
                <MIcon name="push_pin" size={14} filled />
              </button>
            )}
          </div>
        ))}
        {visibleNavGroups.map((group) => (
          <NavGroup
            key={group.key}
            group={group}
            active={active}
            onSelect={handleNav}
            collapsed={collapsed}
            onExpand={onToggle}
            pinnedKeys={pinnedKeys}
            onTogglePin={togglePin}
            /* 學生的「課程」收在教學群組裡，預設展開才不用多點一下 */
            defaultOpen={group.key === "teaching" && !canTeach}
          />
        ))}
      </nav>
      )}

      {/* ===== Bottom section ===== */}
      <div className={styles.divider} />

      <div className={styles.bottom}>
        {/* 管理員設定：系統管理頁面的入口，進入後側欄切換成核心側欄 */}
        {isAdmin && (
          <button
            type="button"
            className={`${styles.navItem} ${inAdminSettings ? styles.active : ""}`}
            onClick={() => handleNav("admin")}
            title={collapsed ? t("Sidebar.adminSettings") : undefined}
            aria-label={t("Sidebar.adminSettings")}
          >
            <MIcon name="admin_panel_settings" size={20} />
            {!collapsed && <span className={styles.navLabel}>{t("Sidebar.adminSettings")}</span>}
          </button>
        )}

        {/* 背景任務（全站入口，狀態由 DashboardLayout 的 JobsProvider 提供） */}
        <JobsButton collapsed={collapsed} />

        {/* 語言選擇 */}
        <button
          ref={langBtnRef}
          type="button"
          data-bombadil="danger"
          className={`${styles.navItem} ${langOpen ? styles.active : ""}`}
          onClick={() => setLangOpen((v) => !v)}
          onKeyDown={(event) => {
            // 跟原生下拉一樣：上下鍵直接展開
            if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
            event.preventDefault();
            setLangOpen(true);
          }}
          title={collapsed ? "語言" : undefined}
          aria-label="語言 / Language"
          aria-haspopup="listbox"
          aria-expanded={langOpen}
          aria-controls={langOpen ? langMenuId : undefined}
        >
          <MIcon name="language" size={20} />
          {!collapsed && <span className={styles.navLabel}>語言 / Language</span>}
          {!collapsed && <span className={styles.navHint}>{LANG_OPTIONS.find((o) => o.value === lang)?.label}</span>}
        </button>
        {langMenu.open && (
          <ListboxPopover
            id={langMenuId}
            anchorRef={langBtnRef}
            ariaLabel="語言 / Language"
            options={LANG_OPTIONS}
            value={lang}
            onSelect={setLanguage}
            onClose={() => setLangOpen(false)}
            closing={langMenu.closing}
            placement="side"
          />
        )}

        {/* 使用者資料 */}
        <button
          ref={userBtnRef}
          type="button"
          className={`${styles.user} ${userOpen ? styles.userActive : ""}`}
          onClick={() => setUserOpen((v) => !v)}
          title={collapsed ? (user?.full_name ?? user?.email) : undefined}
          aria-label={t("Sidebar.userMenuAriaLabel", { name: user?.full_name ?? user?.email ?? "" })}
          aria-haspopup="menu"
          aria-expanded={userOpen}
          aria-controls={userOpen ? userMenuId : undefined}
        >
          <Avatar user={user} size={32} className={styles.avatar} />
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
        {userMenu.open && (
          <ActionMenu
            id={userMenuId}
            anchorRef={userBtnRef}
            ariaLabel={t("Sidebar.userMenuAriaLabel", { name: user?.full_name ?? user?.email ?? "" })}
            items={userMenuItems}
            onClose={() => setUserOpen(false)}
            closing={userMenu.closing}
            placement="side"
            header={(
              <div className={styles.menuUser}>
                <Avatar user={user} size={32} />
                <div className={styles.menuUserText}>
                  <span className={styles.menuUserName}>{user?.full_name ?? "—"}</span>
                  <span className={styles.menuUserEmail}>{user?.email ?? "—"}</span>
                </div>
              </div>
            )}
          />
        )}
      </div>
    </aside>
  );
}
