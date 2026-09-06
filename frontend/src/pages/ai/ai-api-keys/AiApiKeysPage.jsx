import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./AiApiKeysPage.module.scss";
import MIcon from "../../../components/MIcon";
import LoadingState from "../../../components/LoadingState/LoadingState";
import SharedEmptyState from "../../../components/EmptyState/EmptyState";
import { AiApiService } from "../../../services/aiApi";
import { useToast } from "../../../hooks/useToast";
import useAutoRefresh from "../../../hooks/useAutoRefresh";
import useDialogPresence from "../../../hooks/useDialogPresence";
import PageHeader from "../../../components/PageHeader/PageHeader";

const PAGE_SIZE = 50;
const ROLE_OPTIONS = ["student", "teacher", "admin"];
const CREATED_OPTIONS = ["all", "7d", "30d"];

function fmtTime(iso) {
  return iso ? new Date(iso).toLocaleString("zh-TW") : "—";
}

function fmtDate(iso) {
  return iso ? new Date(iso).toLocaleDateString("zh-TW") : "—";
}

function createdAfterFor(range) {
  if (range === "all") return undefined;
  const days = range === "7d" ? 7 : 30;
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
}

export function buildCredentialListParams({
  status,
  query,
  roles = [],
  createdRange = "all",
  page = 0,
  limit = PAGE_SIZE,
} = {}) {
  return {
    status: status && status !== "all" ? status : undefined,
    query: query?.trim() || undefined,
    user_role: roles,
    created_after: createdAfterFor(createdRange),
    skip: page * limit,
    limit,
  };
}

function roleLabel(role, t) {
  const key = role === "admin" ? "roleAdmin" : role === "teacher" ? "roleTeacher" : role === "student" ? "roleStudent" : null;
  return key ? t(`AiApiKeysPage.${key}`) : "—";
}

function StatusBadge({ item }) {
  const { t } = useTranslation("ai");
  const isActive = item.status === "active";
  return (
    <span className={`${styles.badge} ${isActive ? styles.badge_active : styles.badge_inactive}`}>
      <span className={styles.dot} />
      {isActive ? t("AiApiKeysPage.statusActive") : t("AiApiKeysPage.statusInactive")}
    </span>
  );
}

function RoleBadge({ role }) {
  const { t } = useTranslation("ai");
  if (!role) return <span className={styles.muted}>—</span>;
  return <span className={`${styles.roleBadge} ${styles[`roleBadge_${role}`]}`}>{roleLabel(role, t)}</span>;
}

function EmptyState({ hasFilters }) {
  const { t } = useTranslation("ai");
  return (
    <SharedEmptyState
      icon="vpn_key"
      title={t(hasFilters ? "AiApiKeysPage.emptyFilteredTitle" : "AiApiKeysPage.emptyTitle")}
    />
  );
}

function FilterPopover({ roles, createdRange, onToggleRole, onCreatedRangeChange, onClear }) {
  const { t } = useTranslation("ai");
  return (
    <div className={styles.filterPopover} role="dialog" aria-label={t("AiApiKeysPage.filterHeading")}>
      <div className={styles.filterPopoverHeader}>
        <strong>{t("AiApiKeysPage.filterHeading")}</strong>
        <span className={styles.filterPopoverHint}>{t("AiApiKeysPage.filterHint")}</span>
      </div>

      <fieldset className={styles.filterGroup}>
        <legend>{t("AiApiKeysPage.filterRole")}</legend>
        {ROLE_OPTIONS.map((role) => (
          <label key={role} className={styles.checkOption}>
            <input type="checkbox" checked={roles.includes(role)} onChange={() => onToggleRole(role)} />
            <span>{roleLabel(role, t)}</span>
          </label>
        ))}
      </fieldset>

      <fieldset className={styles.filterGroup}>
        <legend>{t("AiApiKeysPage.filterCreated")}</legend>
        {CREATED_OPTIONS.map((range) => (
          <label key={range} className={styles.checkOption}>
            <input
              type="radio"
              name="ai-api-key-created-range"
              value={range}
              checked={createdRange === range}
              onChange={() => onCreatedRangeChange(range)}
            />
            <span>{t(`AiApiKeysPage.created${range === "all" ? "All" : range === "7d" ? "7d" : "30d"}`)}</span>
          </label>
        ))}
      </fieldset>

      <button type="button" className={styles.clearFilters} onClick={onClear}>{t("AiApiKeysPage.clearFilters")}</button>
    </div>
  );
}

function DetailItem({ label, value, mono = false }) {
  return (
    <div className={styles.detailItem}>
      <dt>{label}</dt>
      <dd className={mono ? styles.mono : ""}>{value || "—"}</dd>
    </div>
  );
}

function DetailDrawer({ item, closing = false, onClose, onRevoke }) {
  const { t } = useTranslation("ai");
  const closeButtonRef = useRef(null);

  useEffect(() => {
    closeButtonRef.current?.focus();
  }, []);

  if (!item) return null;
  const isActive = item.status === "active";

  return (
    <div
      className={`${styles.drawerOverlay} ${closing ? styles.drawerOverlayOut : ""}`}
      role="presentation"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
    >
      <aside className={`${styles.drawer} ${closing ? styles.drawerOut : ""}`} role="dialog" aria-modal="true" aria-labelledby="ai-api-key-drawer-title">
        <div className={styles.drawerHeader}>
          <div className={styles.drawerHeading}>
            <span className={styles.drawerKicker}>{t("AiApiKeysPage.detailTitle")}</span>
            <h2 id="ai-api-key-drawer-title" className={styles.drawerTitle}>{item.api_key_name}</h2>
          </div>
          <button ref={closeButtonRef} type="button" className={styles.iconButton} onClick={onClose} aria-label={t("AiApiKeysPage.close")}>
            <MIcon name="close" size={18} />
          </button>
        </div>

        <div className={styles.drawerStatus}><StatusBadge item={item} /></div>

        <section className={styles.detailSection} aria-labelledby="ai-api-key-info-heading">
          <h3 id="ai-api-key-info-heading">{t("AiApiKeysPage.detailKeyInfo")}</h3>
          <dl className={styles.detailGrid}>
            <DetailItem label={t("AiApiKeysPage.detailPrefix")} value={item.api_key_prefix} mono />
            <DetailItem label={t("AiApiKeysPage.detailCreatedAt")} value={fmtTime(item.created_at)} />
            <DetailItem label={t("AiApiKeysPage.detailExpiresAt")} value={item.expires_at ? fmtTime(item.expires_at) : t("AiApiKeysPage.detailNeverExpires")} />
            <DetailItem label={t("AiApiKeysPage.detailRateLimit")} value={item.rate_limit ? `${item.rate_limit} / min` : "—"} />
          </dl>
        </section>

        <section className={styles.detailSection} aria-labelledby="ai-api-key-owner-heading">
          <h3 id="ai-api-key-owner-heading">{t("AiApiKeysPage.detailOwner")}</h3>
          <dl className={styles.detailGrid}>
            <DetailItem label={t("AiApiKeysPage.detailName")} value={item.user_full_name || item.user_email} />
            <DetailItem label={t("AiApiKeysPage.detailEmail")} value={item.user_email} />
            <DetailItem label={t("AiApiKeysPage.detailRole")} value={<RoleBadge role={item.user_role} />} />
          </dl>
        </section>

        <section className={styles.detailSection} aria-labelledby="ai-api-key-request-heading">
          <h3 id="ai-api-key-request-heading">{t("AiApiKeysPage.detailRequest")}</h3>
          <dl className={styles.detailGrid}>
            <DetailItem label={t("AiApiKeysPage.detailPurpose")} value={item.request_purpose} />
            <DetailItem label={t("AiApiKeysPage.detailReviewer")} value={item.reviewer_full_name || item.reviewer_email} />
            <DetailItem label={t("AiApiKeysPage.detailReviewedAt")} value={fmtTime(item.reviewed_at)} />
          </dl>
        </section>

        <section className={styles.detailSection} aria-labelledby="ai-api-key-activity-heading">
          <h3 id="ai-api-key-activity-heading">{t("AiApiKeysPage.detailActivity")}</h3>
          <dl className={styles.detailGrid}>
            <DetailItem label={t("AiApiKeysPage.detailLastUsedAt")} value={item.last_used_at ? fmtTime(item.last_used_at) : t("AiApiKeysPage.detailNeverUsed")} />
            {item.inactive_reason && <DetailItem label={t("AiApiKeysPage.detailInactiveReason")} value={item.inactive_reason === "revoked" ? t("AiApiKeysPage.inactiveReasonRevoked") : t("AiApiKeysPage.inactiveReasonExpired")} />}
            {item.revoked_at && <DetailItem label={t("AiApiKeysPage.detailRevokedAt")} value={fmtTime(item.revoked_at)} />}
          </dl>
        </section>

        {isActive && (
          <div className={styles.drawerFooter}>
            <button type="button" className={styles.btnDanger} onClick={() => onRevoke(item)}>
              <MIcon name="block" size={16} />{t("AiApiKeysPage.revokeAction")}
            </button>
          </div>
        )}
      </aside>
    </div>
  );
}

function RevokeDialog({ item, closing = false, onClose, onDone }) {
  const { t } = useTranslation("ai");
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  if (!item) return null;

  const handleRevoke = async () => {
    setBusy(true);
    try {
      await AiApiService.revokeCredential(item.id);
      toast.success(t("AiApiKeysPage.revokeSuccess"));
      onClose();
      onDone();
    } catch (error) {
      toast.error(error?.message ?? t("AiApiKeysPage.revokeError"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`${styles.dialogOverlay} ${closing ? styles.dialogOverlayOut : ""}`} role="presentation" onMouseDown={() => { if (!busy) onClose(); }}>
      <div className={styles.dialog} role="dialog" aria-modal="true" aria-labelledby="ai-api-key-revoke-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className={styles.dialogHeader}>
          <div className={styles.dialogIcon}><MIcon name="warning" size={20} /></div>
          <div>
            <h2 id="ai-api-key-revoke-title" className={styles.dialogTitle}>{t("AiApiKeysPage.revokeConfirmTitle")}</h2>
            <p className={styles.dialogDesc}>{t("AiApiKeysPage.revokeConfirmDesc", { name: item.api_key_name })}</p>
          </div>
        </div>
        <div className={styles.dialogFooter}>
          <button type="button" className={styles.btnOutline} onClick={onClose} disabled={busy}>{t("AiApiKeysPage.cancel")}</button>
          <button type="button" className={styles.btnDanger} onClick={handleRevoke} disabled={busy}>{busy ? t("AiApiKeysPage.revoking") : t("AiApiKeysPage.confirmRevoke")}</button>
        </div>
      </div>
    </div>
  );
}

export default function AiApiKeysPage() {
  const { t } = useTranslation("ai");
  const toast = useToast();
  const filterAreaRef = useRef(null);
  const [statusFilter, setStatusFilter] = useState("active");
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [roleFilters, setRoleFilters] = useState([]);
  const [createdRange, setCreatedRange] = useState("all");
  const [filterOpen, setFilterOpen] = useState(false);
  const [openMenuId, setOpenMenuId] = useState(null);
  const [selectedItem, setSelectedItem] = useState(null);
  const [deletingItem, setDeletingItem] = useState(null);
  const [page, setPage] = useState(0);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [allCount, setAllCount] = useState(0);
  const [activeCount, setActiveCount] = useState(0);
  const [inactiveCount, setInactiveCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const deleteDialog = useDialogPresence(deletingItem);
  const drawer = useDialogPresence(selectedItem);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(searchInput);
      setPage(0);
    }, 220);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    if (!filterOpen) return undefined;
    const closeOnOutside = (event) => {
      if (!filterAreaRef.current?.contains(event.target)) setFilterOpen(false);
    };
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setFilterOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [filterOpen]);

  useEffect(() => {
    if (!selectedItem) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setSelectedItem(null);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [selectedItem]);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await AiApiService.listAllCredentials(buildCredentialListParams({
        status: statusFilter,
        query,
        roles: roleFilters,
        createdRange,
        page,
      }));
      setRows(res?.data ?? []);
      setTotal(res?.count ?? 0);
      setAllCount(res?.total_count ?? res?.count ?? 0);
      setActiveCount(res?.active_count ?? 0);
      setInactiveCount(res?.inactive_count ?? 0);
    } catch (error) {
      if (!silent) toast.error(error?.message ?? t("AiApiKeysPage.loadError"));
    } finally {
      if (!silent) setLoading(false);
    }
  }, [createdRange, page, query, roleFilters, statusFilter, t, toast]);

  useEffect(() => { load(); }, [load]);
  useAutoRefresh(() => load(true));

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  useEffect(() => {
    if (page >= totalPages && page > 0) setPage(totalPages - 1);
  }, [page, totalPages]);

  const activeFilterCount = roleFilters.length + (createdRange === "all" ? 0 : 1);
  const hasFilters = Boolean(statusFilter !== "all" || query.trim() || roleFilters.length || createdRange !== "all");
  const tabs = useMemo(() => [
    { key: "active", label: t("AiApiKeysPage.tabActive"), count: activeCount },
    { key: "inactive", label: t("AiApiKeysPage.tabInactive"), count: inactiveCount },
    { key: "all", label: t("AiApiKeysPage.tabAll"), count: allCount },
  ], [activeCount, allCount, inactiveCount, t]);

  function toggleRole(role) {
    setRoleFilters((current) => current.includes(role) ? current.filter((item) => item !== role) : [...current, role]);
    setPage(0);
  }

  function clearFilters() {
    setRoleFilters([]);
    setCreatedRange("all");
    setFilterOpen(false);
    setPage(0);
  }

  function openDetails(item) {
    setOpenMenuId(null);
    setSelectedItem(item);
  }

  function onRowKeyDown(event, item) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openDetails(item);
    }
  }

  return (
    <div className={styles.page}>
      <PageHeader title={t("AiApiKeysPage.pageTitle")} subtitle={t("AiApiKeysPage.pageSubtitle")}>
        <div className={styles.headerSummary} aria-live="polite">
          <span>{activeCount} {t("AiApiKeysPage.summaryActive")}</span><span aria-hidden="true">·</span><span>{inactiveCount} {t("AiApiKeysPage.summaryInactive")}</span>
        </div>
      </PageHeader>

      <div className={styles.statusTabs} role="tablist" aria-label={t("AiApiKeysPage.statusTabsLabel")}>
        {tabs.map((tab) => (
          <button key={tab.key} type="button" role="tab" aria-selected={statusFilter === tab.key} className={`${styles.statusTab} ${statusFilter === tab.key ? styles.statusTabActive : ""}`} onClick={() => { setStatusFilter(tab.key); setPage(0); }}>
            {tab.label}<span className={styles.tabCount}>{tab.count}</span>
          </button>
        ))}
      </div>

      <div className={styles.toolbar}>
        <div className={styles.searchBox}>
          <MIcon name="search" size={17} />
          <input type="search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder={t("AiApiKeysPage.searchPlaceholder")} aria-label={t("AiApiKeysPage.searchPlaceholder")} />
          {searchInput && <button type="button" className={styles.clearSearch} onClick={() => setSearchInput("")} aria-label={t("AiApiKeysPage.clearSearch")}><MIcon name="close" size={15} /></button>}
        </div>
        <div ref={filterAreaRef} className={styles.filterArea}>
          <button type="button" className={`${styles.filterButton} ${activeFilterCount ? styles.filterButtonActive : ""}`} aria-haspopup="dialog" aria-expanded={filterOpen} onClick={() => setFilterOpen((current) => !current)}>
            <MIcon name="filter_alt" size={16} />{activeFilterCount ? t("AiApiKeysPage.filterActiveCount", { count: activeFilterCount }) : t("AiApiKeysPage.filterButton")}
          </button>
          {filterOpen && <FilterPopover roles={roleFilters} createdRange={createdRange} onToggleRole={toggleRole} onCreatedRangeChange={(value) => { setCreatedRange(value); setPage(0); }} onClear={clearFilters} />}
        </div>
      </div>

      <div className={styles.content}>
        {loading ? <LoadingState fullPage /> : rows.length === 0 ? <EmptyState hasFilters={hasFilters} /> : (
          <>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th scope="col" className={styles.th}>{t("AiApiKeysPage.colKeyName")}</th>
                    <th scope="col" className={styles.th}>{t("AiApiKeysPage.colUser")}</th>
                    <th scope="col" className={styles.th}>{t("AiApiKeysPage.colIdentity")}</th>
                    <th scope="col" className={styles.th}>{t("AiApiKeysPage.colKeyPrefix")}</th>
                    <th scope="col" className={styles.th}>{t("AiApiKeysPage.colStatus")}</th>
                    <th scope="col" className={styles.th}>{t("AiApiKeysPage.colCreatedAt")}</th>
                    <th scope="col" className={styles.th}>{t("AiApiKeysPage.colActions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((item) => (
                    <tr key={item.id} className={`${styles.tr} ${styles.trClickable}`} tabIndex={0} onClick={() => openDetails(item)} onKeyDown={(event) => onRowKeyDown(event, item)} aria-label={t("AiApiKeysPage.rowLabel", { name: item.api_key_name })}>
                      <td className={`${styles.td} ${styles.keyNameCell}`}>{item.api_key_name || "—"}</td>
                      <td className={styles.td}><div className={styles.userCell}><span className={styles.userName}>{item.user_full_name || "—"}</span><span className={styles.userEmail}>{item.user_email || "—"}</span></div></td>
                      <td className={styles.td}><RoleBadge role={item.user_role} /></td>
                      <td className={`${styles.td} ${styles.mono}`}>{item.api_key_prefix || "—"}</td>
                      <td className={styles.td}><StatusBadge item={item} /></td>
                      <td className={styles.td}>{fmtDate(item.created_at)}</td>
                      <td className={`${styles.td} ${styles.actionsCell}`} onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
                        <div className={styles.actionMenuArea}>
                          <button type="button" className={styles.iconButton} title={t("AiApiKeysPage.actionMenu")} aria-label={t("AiApiKeysPage.actionMenu")} aria-haspopup="menu" aria-expanded={openMenuId === item.id} onClick={() => setOpenMenuId((current) => current === item.id ? null : item.id)}><MIcon name="more_vert" size={18} /></button>
                          {openMenuId === item.id && <div className={styles.actionMenu} role="menu">
                            <button type="button" role="menuitem" onClick={() => openDetails(item)}><MIcon name="visibility" size={16} />{t("AiApiKeysPage.viewDetails")}</button>
                            {item.status === "active" && <button type="button" role="menuitem" className={styles.menuDanger} onClick={() => { setOpenMenuId(null); setDeletingItem(item); }}><MIcon name="block" size={16} />{t("AiApiKeysPage.revokeAction")}</button>}
                          </div>}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && <div className={styles.pagination}><span className={styles.paginationInfo}>{t("AiApiKeysPage.paginationInfo", { page: page + 1, totalPages, total })}</span><div className={styles.paginationBtns}><button type="button" className={styles.btnOutline} disabled={page === 0} onClick={() => setPage((current) => Math.max(0, current - 1))}>{t("AiApiKeysPage.prevPage")}</button><button type="button" className={styles.btnOutline} disabled={page + 1 >= totalPages} onClick={() => setPage((current) => current + 1)}>{t("AiApiKeysPage.nextPage")}</button></div></div>}
          </>
        )}
      </div>

      {drawer.open && <DetailDrawer item={drawer.item} closing={drawer.closing} onClose={() => setSelectedItem(null)} onRevoke={(item) => setDeletingItem(item)} />}
      {deleteDialog.open && <RevokeDialog item={deleteDialog.item} closing={deleteDialog.closing} onClose={() => setDeletingItem(null)} onDone={() => { setSelectedItem(null); load(); }} />}
    </div>
  );
}
