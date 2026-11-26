import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { createColumnHelper, useTable } from "@tanstack/react-table";
import styles from "./AiApiKeysPage.module.scss";
import MIcon from "../../../components/MIcon";
import DataTable from "../../../components/DataTable/DataTable";
import { baseFeatures } from "../../../components/DataTable/features";
import { useTableFitContext } from "../../../components/DataTable/TableFitContext";
import useTableFit from "../../../hooks/useTableFit";
import Modal from "../../../components/Modal/Modal";
import LoadingState from "../../../components/LoadingState/LoadingState";
import SharedEmptyState from "../../../components/EmptyState/EmptyState";
import ErrorState from "../../../components/ErrorState/ErrorState";
import { AiApiService } from "../../../services/aiApi";
import { useAiApiCacheUpdater, useAllAiCredentialsQuery } from "../../../queries/aiApi";
import { useToast } from "../../../hooks/useToast";
import { useLoadError } from "../../../hooks/useQueryLoadState";
import useDialogPresence from "../../../hooks/useDialogPresence";
import PageHeader from "../../../components/PageHeader/PageHeader";
import SegmentedControl from "../../../components/SegmentedControl/SegmentedControl";
import Pagination from "../../../components/Pagination/Pagination";
import { formatDate, formatDateTime } from "../../../utils/formatDate";

const PAGE_SIZE = 50;
const EMPTY = Object.freeze([]);
const ROLE_OPTIONS = ["student", "teacher", "admin"];
const CREATED_OPTIONS = ["all", "7d", "30d"];

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
      {isActive
        ? t("AiApiKeysPage.statusActive")
        : t(item.inactive_reason === "deleted" ? "AiApiKeysPage.statusDeleted" : "AiApiKeysPage.statusInactive")}
    </span>
  );
}

/* 憑證表格的欄位（TanStack Table）。欄位定義放模組層級：v9 的 FlexRender 把函式型的 header／cell
   當元件掛載，render 裡新建會讓整格重新掛載。表頭文字取 meta.headerKey 的翻譯；撤銷經 table meta 交回頁面。
   資料沒變時表格的列不會重繪，切換語言只會重繪有用 useTranslation 的元件，
   所以依語系格式化日期的格子（formatDate 讀 i18n.language）自己訂閱語系 */
const columnHelper = createColumnHelper();

function HeaderLabel({ column }) {
  const { t } = useTranslation("ai");
  return t(column.columnDef.meta.headerKey);
}

/* ── 窄版收欄（useTableFit，樣式規範「表格」規則四） ──
   表格區不夠寬時依序收起建立日期、擁有者、申請用途、活動；金鑰、狀態、操作永遠在。
   擁有者、申請用途是「誰的、為什麼要」，收進金鑰名稱底下：擁有者併進原本的 Email 那一行（姓名 · Email），
   用途另起一行，兩行都單行截斷、全文在 title（Email 不會被從中間折成兩行）。
   兩個時間一律排在一起：只收建立日期時接在活動（最後使用時間）底下；兩個都收時依先後排在狀態徽章底下
   （只寫日期，完整時間在 title；沒用過的寫「尚未使用」，本身看得懂，不加欄名）。
   欄寬只寫在這裡：完整日期時間（英文 11/17/2026, 14:30:15）要 170px；狀態欄 160px 放得下收進來的
   「Activity 11/18/2026」「建立日期 2026/11/17」（日文的「アクティビティ」較長，會在日期前換行）；
   英文的 Delete 鈕要 120px；金鑰欄含 40px 圖示，220px 留 140px 給名稱與 Email。
   全部 1110px：1440（表格區約 1003～1018px）收掉建立日期剩 990px；1366 筆電（約 929～944px）再收擁有者剩 850px；
   1100 寬視窗（約 678px）再收申請用途剩 670px；1440 開著 AI 助手（約 567px）再收活動，只剩金鑰、狀態、操作 500px。
   手機（約 448px）收到底仍放不下，橫捲並固定金鑰欄 */
const CREDENTIAL_FIT_COLUMNS = Object.freeze([
  { id: "name", width: 220 },
  { id: "user_full_name", width: 140, fold: 2 },
  { id: "request_purpose", width: 180, fold: 3 },
  { id: "activity", width: 170, fold: 4 },
  { id: "status", width: 160 },
  { id: "created_at", width: 120, fold: 1 },
  { id: "actions", width: 120 },
]);

/* 擁有者收起時，名稱底下那一行改成「姓名 · Email」（沒有姓名就只有 Email） */
function ownerLine(item) {
  return [item.user_full_name, item.user_email].filter(Boolean).join(" · ");
}

function NameCell({ row }) {
  const fit = useTableFitContext();
  const item = row.original;
  const meta = fit.isFolded("user_full_name") ? ownerLine(item) : item.user_email;
  return (
    <div className={styles.nameCell}>
      <div className={styles.rowIcon}>
        <MIcon name="vpn_key" size={20} />
      </div>
      <div className={styles.rowMain}>
        <span className={styles.rowName} title={item.api_key_name || undefined}>{item.api_key_name || "—"}</span>
        <span className={styles.rowMeta} title={meta || undefined}>{meta || "—"}</span>
        {fit.isFolded("request_purpose") && item.request_purpose && (
          <span className={styles.rowMeta} title={item.request_purpose}>{item.request_purpose}</span>
        )}
      </div>
    </div>
  );
}

function TextCell({ getValue }) {
  const value = getValue();
  return <span className={styles.cellText} title={value || undefined}>{value || "—"}</span>;
}

/* 收進其他欄的時間：欄名＋日期，完整時間在 title（同 AI API 頁金鑰表收起的建立時間） */
function FoldedDateLine({ labelKey, value, ...rest }) {
  const { t } = useTranslation("ai");
  return (
    <div className={styles.foldedLine} title={formatDateTime(value)} {...rest}>
      {t(labelKey)} {formatDate(value)}
    </div>
  );
}

/* 收進狀態底下的活動（最後使用時間）；活動的導覽錨點跟著搬過來，收欄後導覽照樣指得到 */
function FoldedActivityLine({ item }) {
  const { t } = useTranslation("ai");
  if (!item.last_used_at) {
    return <div className={styles.foldedLine} data-guide="ai-keys-admin-activity">{t("AiApiKeysPage.detailNeverUsed")}</div>;
  }
  return <FoldedDateLine labelKey="AiApiKeysPage.detailActivity" value={item.last_used_at} data-guide="ai-keys-admin-activity" />;
}

/* 活動；窄版只收起建立日期時，建立日期接在底下（兩個時間排在一起） */
function ActivityCell({ row }) {
  const { t } = useTranslation("ai");
  const fit = useTableFitContext();
  const item = row.original;
  return (
    <>
      {item.last_used_at
        ? formatDateTime(item.last_used_at)
        : <span className={styles.cellMuted}>{t("AiApiKeysPage.detailNeverUsed")}</span>}
      {fit.isFolded("created_at") && <FoldedDateLine labelKey="AiApiKeysPage.colCreatedAt" value={item.created_at} />}
    </>
  );
}

/* 狀態；窄版兩個時間都收起時，依先後（建立→最後使用）接在徽章底下 */
function StatusCell({ row }) {
  const fit = useTableFitContext();
  const item = row.original;
  const timesFolded = fit.isFolded("activity") && fit.isFolded("created_at");
  return (
    <>
      <StatusBadge item={item} />
      {timesFolded && <FoldedDateLine labelKey="AiApiKeysPage.colCreatedAt" value={item.created_at} />}
      {timesFolded && <FoldedActivityLine item={item} />}
    </>
  );
}

function CreatedAtCell({ getValue }) {
  useTranslation("ai");
  return formatDate(getValue());
}

function RevokeCell({ row, table }) {
  const { t } = useTranslation("ai");
  const item = row.original;
  if (item.status !== "active") return "—";
  return (
    <button
      type="button"
      className={styles.rowRevokeBtn}
      data-guide="ai-keys-admin-revoke"
      onClick={() => table.options.meta.onRevoke(item)}
    >
      <MIcon name="block" size={16} />
      {t("AiApiKeysPage.revokeAction")}
    </button>
  );
}

function columnMeta(headerKey, extra) {
  return { headerKey, thClassName: styles.th, tdClassName: styles.td, ...extra };
}

/* 欄寬與收合順序在 CREDENTIAL_FIT_COLUMNS（id 要對得上） */
const credentialColumns = columnHelper.columns([
  columnHelper.display({ id: "name", header: HeaderLabel, cell: NameCell, meta: columnMeta("AiApiKeysPage.colName") }),
  columnHelper.accessor("user_full_name", { header: HeaderLabel, cell: TextCell, meta: columnMeta("AiApiKeysPage.detailOwner") }),
  columnHelper.accessor("request_purpose", { header: HeaderLabel, cell: TextCell, meta: columnMeta("AiApiKeysPage.detailPurpose") }),
  columnHelper.display({
    id: "activity",
    header: HeaderLabel,
    cell: ActivityCell,
    meta: columnMeta("AiApiKeysPage.detailActivity", { tdProps: { "data-guide": "ai-keys-admin-activity" } }),
  }),
  columnHelper.display({ id: "status", header: HeaderLabel, cell: StatusCell, meta: columnMeta("AiApiKeysPage.colStatus") }),
  columnHelper.accessor("created_at", { header: HeaderLabel, cell: CreatedAtCell, meta: columnMeta("AiApiKeysPage.colCreatedAt") }),
  columnHelper.display({ id: "actions", header: HeaderLabel, cell: RevokeCell, meta: columnMeta("AiApiKeysPage.colActions") }),
]);

const credentialRowClassName = () => styles.tr;

function EmptyState({ hasFilters, onClear }) {
  const { t } = useTranslation("ai");
  return (
    <SharedEmptyState
      icon="vpn_key"
      title={t(hasFilters ? "AiApiKeysPage.emptyFilteredTitle" : "AiApiKeysPage.emptyTitle")}
      action={hasFilters ? (
        <button type="button" className={styles.btnSecondary} onClick={onClear}>
          <MIcon name="filter_alt_off" size={16} />{t("EmptyState.clearFilters", { ns: "common" })}
        </button>
      ) : undefined}
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

function RevokeDialog({ item, closing = false, onClose, onDone }) {
  const { t } = useTranslation("ai");
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  if (!item) return null;

  const handleRevoke = async () => {
    setBusy(true);
    try {
      await AiApiService.deleteCredential(item.id);
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
    <Modal
      role="alertdialog"
      closing={closing}
      onClose={onClose}
      busy={busy}
      icon={<span className={styles.revokeIcon}><MIcon name="warning" size={20} /></span>}
      title={t("AiApiKeysPage.revokeConfirmTitle")}
      description={t("AiApiKeysPage.revokeConfirmDesc", { name: item.api_key_name })}
      actions={
        <>
          <button type="button" className={styles.btnSecondary} onClick={onClose} disabled={busy}>{t("AiApiKeysPage.cancel")}</button>
          <button data-bombadil="danger" type="button" className={styles.btnDanger} onClick={handleRevoke} disabled={busy}>{busy ? t("AiApiKeysPage.revoking") : t("AiApiKeysPage.confirmRevoke")}</button>
        </>
      }
    />
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
  const [deletingItem, setDeletingItem] = useState(null);
  const [page, setPage] = useState(0);
  const deleteDialog = useDialogPresence(deletingItem);

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

  /* 清單走 TanStack Query，以查詢條件為 key：快速切換分頁／篩選時舊條件較晚回來的回應只會進舊 key，
     不會蓋掉目前的清單；換條件時先留著上一份（keepPreviousData），不閃回載入畫面。
     背景 30 秒刷新、分頁隱藏時暫停。條件在變動時才組一次：建立時間篩選的起點固定在那一刻，
     不能每次 render 都重算（key 會一直換）。 */
  const listParams = useMemo(() => buildCredentialListParams({
    status: statusFilter,
    query,
    roles: roleFilters,
    createdRange,
    page,
  }), [statusFilter, query, roleFilters, createdRange, page]);
  const credentialsQuery = useAllAiCredentialsQuery(listParams);
  const aiCache = useAiApiCacheUpdater();
  const res = credentialsQuery.data;
  /* 錯誤畫面在背景重試期間不閃回載入中，按重試才回到載入中（見 useLoadError）。
     換條件時沿用上一份清單照常顯示；但這組條件失敗後，沒有資料時每次重抓 TanStack 都會把上一組條件的
     清單放回來當佔位資料，所以判斷錯誤時佔位資料不算資料，錯誤畫面才不會閃成上一組條件的清單 */
  const { error: loadError, retry: retryCredentials } = useLoadError(credentialsQuery);
  const loading = res === undefined && !loadError && (credentialsQuery.isPending || credentialsQuery.isFetching);
  const rows = res?.data ?? EMPTY;
  /* 伺服器分頁：頁碼由頁面管（決定查詢參數），表格只渲染當頁的列 */
  const table = useTable({
    features: baseFeatures,
    columns: credentialColumns,
    data: rows,
    getRowId: (item) => String(item.id),
    meta: { onRevoke: setDeletingItem },
  });
  const fit = useTableFit(CREDENTIAL_FIT_COLUMNS);
  const total = res?.count ?? 0;
  const allCount = res?.total_count ?? res?.count ?? 0;
  const activeCount = res?.active_count ?? 0;
  const inactiveCount = res?.inactive_count ?? 0;

  /* 這組條件一筆資料都還沒拿到就失敗才提醒（與原本的前景載入相同）；
     背景刷新失敗沿用畫面上的資料、不跳 toast。以訊息字串為依賴，同一個錯誤重試失敗不重複跳
     （錯誤取自 useLoadError：背景重試期間不會先清空再變回來，才不會每輪重跳） */
  const loadErrorMessage = loadError
    ? loadError.message ?? t("AiApiKeysPage.loadError")
    : null;
  useEffect(() => {
    if (loadErrorMessage) toast.error(loadErrorMessage);
  }, [loadErrorMessage, toast]);

  /* 撤銷後在背景重抓（清單留在畫面上），重抓失敗照原本提醒 */
  function refreshAfterRevoke() {
    aiCache.invalidateAllCredentials({ throwOnError: true })
      .catch((error) => toast.error(error?.message ?? t("AiApiKeysPage.loadError")));
  }

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

  return (
    <div className={styles.page}>
      <PageHeader title={t("AiApiKeysPage.pageTitle")} />

      <div className={styles.controlsRow}>
        <div className={styles.segmentGroup} data-guide="ai-keys-admin-status">
          <SegmentedControl
            className={styles.statusTabs}
            options={tabs.map(({ key, label, count }) => ({ value: key, label, badge: count }))}
            value={statusFilter}
            onChange={(value) => { setStatusFilter(value); setPage(0); }}
            ariaLabel={t("AiApiKeysPage.statusTabsLabel")}
          />
          <div ref={filterAreaRef} className={styles.filterArea} data-guide="ai-keys-admin-filter">
            <button type="button" className={`${styles.filterButton} ${activeFilterCount ? styles.filterButtonActive : ""}`} aria-haspopup="dialog" aria-expanded={filterOpen} onClick={() => setFilterOpen((current) => !current)}>
              <MIcon name="filter_alt" size={16} />{activeFilterCount ? t("AiApiKeysPage.filterActiveCount", { count: activeFilterCount }) : t("AiApiKeysPage.filterButton")}
            </button>
            {filterOpen && <FilterPopover roles={roleFilters} createdRange={createdRange} onToggleRole={toggleRole} onCreatedRangeChange={(value) => { setCreatedRange(value); setPage(0); }} onClear={clearFilters} />}
          </div>
        </div>

        <div className={styles.searchBox} data-guide="ai-keys-admin-search">
          <MIcon name="search" size={17} />
          <input type="search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder={t("AiApiKeysPage.searchPlaceholder")} aria-label={t("AiApiKeysPage.searchPlaceholder")} />
          {searchInput && <button type="button" className={styles.clearSearch} onClick={() => setSearchInput("")} aria-label={t("AiApiKeysPage.clearSearch")}><MIcon name="close" size={15} /></button>}
        </div>
      </div>

      <div className={styles.content}>
        {loading ? <LoadingState fullPage /> : loadError ? <ErrorState onRetry={() => retryCredentials()} /> : (
          rows.length === 0 ? <EmptyState hasFilters={hasFilters} onClear={() => {
            setStatusFilter("all");
            setSearchInput("");
            setQuery("");
            clearFilters();
          }} /> : (
            <>
              <div ref={fit.ref} className={styles.tableWrap} data-guide="ai-keys-admin-table">
                <DataTable table={table} fit={fit} className={styles.table} rowClassName={credentialRowClassName} />
              </div>

              {totalPages > 1 && (
                <Pagination
                  page={page}
                  totalPages={totalPages}
                  info={t("AiApiKeysPage.paginationInfo", { total })}
                  onChange={setPage}
                />
              )}
            </>
          )
        )}
      </div>

      {deleteDialog.open && <RevokeDialog item={deleteDialog.item} closing={deleteDialog.closing} onClose={() => setDeletingItem(null)} onDone={refreshAfterRevoke} />}
    </div>
  );
}
