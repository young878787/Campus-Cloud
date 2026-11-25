import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { createColumnHelper, useTable } from "@tanstack/react-table";
import styles from "./AuditPage.module.scss";
import MIcon from "../../../components/MIcon";
import DataTable from "../../../components/DataTable/DataTable";
import { baseFeatures } from "../../../components/DataTable/features";
import { useTableFitContext } from "../../../components/DataTable/TableFitContext";
import useTableFit from "../../../hooks/useTableFit";
import LoadingState from "../../../components/LoadingState/LoadingState";
import SharedEmptyState from "../../../components/EmptyState/EmptyState";
import { useToast } from "../../../hooks/useToast";
import { useLoadFailureMessage, useQueryView } from "../../../hooks/useQueryLoadState";
import { useConfirm } from "../../../components/ConfirmDialog/ConfirmProvider";
import { downloadBlob } from "../../../services/api";
import { AuditLogsService } from "../../../services/auditLogs";
import {
  useAuditActionsQuery,
  useAuditLogsQuery,
  useAuditStatsQuery,
  useAuditUsersQuery,
} from "../../../queries/auditLogs";
import PageHeader from "../../../components/PageHeader/PageHeader";
import Pagination from "../../../components/Pagination/Pagination";
import { formatDateTime } from "../../../utils/formatDate";

const PAGE_SIZE = 50;
/** 匯出一次最多幾筆；後端同樣有上限，兩邊要對齊 */
const EXPORT_LIMIT = 10000;
/** 搜尋框即時查詢的防抖間隔（ms）；下拉與日期改變則立即查詢 */
const SEARCH_DEBOUNCE = 300;

const EMPTY = Object.freeze([]);

/** date input（yyyy-mm-dd）轉 ISO；end 補到當日 23:59:59 */
function toIso(dateStr, endOfDay = false) {
  if (!dateStr) return "";
  return new Date(`${dateStr}T${endOfDay ? "23:59:59" : "00:00:00"}`).toISOString();
}

/** 本地時區的今天（yyyy-mm-dd）；不用 toISOString 以免 UTC 跨日 */
export function todayDateStr(now = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** yyyy-mm-dd 字串可直接用字典序比較；任一為空視為「範圍合法」 */
export function isDateRangeValid(startDate, endDate) {
  if (!startDate || !endDate) return true;
  return startDate <= endDate;
}

/** 稽核日誌只有過去的紀錄，起訖任一端落在今天以後就不合法 */
export function isDateInFuture(dateStr, today = todayDateStr()) {
  return Boolean(dateStr) && dateStr > today;
}

/**
 * 更新起訖日期並維持「起始 ≤ 結束」且不超過今天：
 * 選到今天以後 → 校正為今天；
 * 起始被改到結束之後 → 結束跟著移到同一天；結束被改到起始之前 → 起始跟著移到同一天。
 */
export function applyDateField(filters, name, value, today = todayDateStr()) {
  const clamped = isDateInFuture(value, today) ? today : value;
  const next = { ...filters, [name]: clamped };
  if (isDateRangeValid(next.startDate, next.endDate)) return next;
  if (name === "startDate") next.endDate = clamped;
  else next.startDate = clamped;
  return next;
}

function EmptyState({ hasFilter, onClear }) {
  const { t } = useTranslation("system");
  return (
    <SharedEmptyState
      icon={hasFilter ? "search_off" : "receipt_long"}
      title={hasFilter ? t("AuditPage.emptyNoResult") : t("AuditPage.emptyNone")}
      action={hasFilter ? <button type="button" className={styles.btnSecondary} onClick={onClear}><MIcon name="filter_alt_off" size={16} />{t("EmptyState.clearFilters", { ns: "common" })}</button> : undefined}
    />
  );
}

/** 表頭文字（header 是元件，可以直接用 hook） */
function ColTitle({ name }) {
  const { t } = useTranslation("system");
  return t(`AuditPage.${name}`);
}

/* ── 窄版收欄（useTableFit） ──
   表格區不夠寬時依序收起 VMID、IP、操作、使用者；時間（第一欄，捲動時固定的那欄）與內容永遠在。
   VMID 與操作收進內容欄（操作徽章在內容上方、「VMID 101」在下方），IP 收到使用者底下；
   使用者再收起時，連同 IP 一起接在時間底下。
   欄寬只寫在這裡：完整時間（英文 11/17/2026, 14:30:15）要 170px；操作徽章 200px 放得下約 23 字元的代碼
   （更長的 vm_request_submit_auto_approved 在徽章內截斷，title 看全文）；內容兩行截斷，滑過看全文。
   全部欄 980px，1440 筆電（約 1003px）不用收；1366 筆電（約 929px）收掉 VMID 剩 900px；
   1100 寬視窗（約 678px）與 1440 開著 AI 助手（約 567px）再收 IP、操作剩 560px；手機（約 448px）收掉使用者剩 370px */
const AUDIT_FIT_COLUMNS = Object.freeze([
  { id: "created_at", width: 170 },
  { id: "user", width: 190, fold: 4 },
  { id: "action", width: 200, fold: 3 },
  { id: "details", width: 200 },
  { id: "vmid", width: 80, fold: 1 },
  { id: "ip_address", width: 140, fold: 2 },
]);

function ActionBadge({ action }) {
  return <span className={styles.actionBadge} title={action}>{action}</span>;
}

/* 使用者欄：姓名＋email，收起的 IP 接在底下（IP 本身看得出是什麼，不加欄名） */
function UserCell({ log }) {
  const { t } = useTranslation("system");
  const fit = useTableFitContext();
  return (
    <div className={styles.cellStack}>
      <span className={styles.userName}>{log.user_full_name ?? (log.user_email ? "—" : t("AuditPage.systemUser"))}</span>
      <span className={styles.subLine} title={log.user_email ?? undefined}>{log.user_email ?? ""}</span>
      {fit.isFolded("ip_address") && log.ip_address && <span className={styles.subLine}>{log.ip_address}</span>}
    </div>
  );
}

/* 收起的使用者（連同已收起的 IP）接在時間底下：只寫有的值，沒有姓名就不放「—」 */
function FoldedUserLines({ log }) {
  const { t } = useTranslation("system");
  const fit = useTableFitContext();
  if (!fit.isFolded("user")) return null;
  const name = log.user_full_name ?? (log.user_email ? null : t("AuditPage.systemUser"));
  return (
    <>
      {name && <div className={styles.subLine}>{name}</div>}
      {log.user_email && <div className={styles.subLine} title={log.user_email}>{log.user_email}</div>}
      {fit.isFolded("ip_address") && log.ip_address && <div className={styles.subLine}>{log.ip_address}</div>}
    </>
  );
}

/* 內容欄：收起的操作徽章在上方、VMID 在下方（光看數字看不出是什麼，加欄名） */
function DetailsCell({ log }) {
  const fit = useTableFitContext();
  return (
    <div className={styles.cellStack}>
      {fit.isFolded("action") && <ActionBadge action={log.action} />}
      <span className={styles.detailsText}>{log.details}</span>
      {fit.isFolded("vmid") && log.vmid != null && <span className={styles.subLine}>VMID {log.vmid}</span>}
    </div>
  );
}

const columnHelper = createColumnHelper();

/* 欄位定義放模組層級：FlexRender 把函式型的 header／cell 當元件掛載，render 裡新建會整格重新掛載。
   時間留在 cell 函式裡格式化：它每次都拿到新的 lang，切換語言時跟著換格式 */
const auditColumns = columnHelper.columns([
  columnHelper.accessor("created_at", {
    header: () => <ColTitle name="colTime" />,
    cell: ({ row }) => <>{formatDateTime(row.original.created_at)}<FoldedUserLines log={row.original} /></>,
    meta: { thClassName: styles.th, tdClassName: `${styles.td} ${styles.tdNowrap}` },
  }),
  columnHelper.display({
    id: "user",
    header: () => <ColTitle name="colUser" />,
    cell: ({ row }) => <UserCell log={row.original} />,
    meta: { thClassName: styles.th, tdClassName: styles.td },
  }),
  columnHelper.accessor("action", {
    header: () => <ColTitle name="colAction" />,
    cell: ({ row }) => <ActionBadge action={row.original.action} />,
    meta: { thClassName: styles.th, tdClassName: styles.td },
  }),
  columnHelper.accessor("details", {
    header: () => <ColTitle name="colContent" />,
    cell: ({ row }) => <DetailsCell log={row.original} />,
    /* 全文放在 td 的 title，滑過可看被截斷的內容 */
    meta: {
      thClassName: styles.th,
      tdClassName: styles.td,
      tdProps: (row) => ({ title: row.original.details ?? undefined }),
    },
  }),
  columnHelper.accessor("vmid", {
    header: "VMID",
    cell: ({ row }) => row.original.vmid ?? "—",
    meta: { thClassName: styles.th, tdClassName: styles.td },
  }),
  columnHelper.accessor("ip_address", {
    header: "IP",
    cell: ({ row }) => row.original.ip_address ?? "—",
    /* IPv6 放不下時在欄內截斷，title 看全文 */
    meta: {
      thClassName: styles.th,
      tdClassName: `${styles.td} ${styles.tdTruncate}`,
      tdProps: (row) => ({ title: row.original.ip_address ?? undefined }),
    },
  }),
]);

export default function AuditPage() {
  const { t } = useTranslation("system");
  const toast = useToast();
  const confirm = useConfirm();
  const [exporting, setExporting] = useState(false);
  const [page, setPage] = useState(0);

  /** 篩選條件一改就即時查詢；搜尋框另有防抖，避免每個字元都打 API */
  const [filters, setFilters] = useState({
    search: "",
    action: "",
    userId: "",
    startDate: "",
    endDate: "",
  });
  const [debouncedSearch, setDebouncedSearch] = useState("");
  /** 目前生效的搜尋字串：用來判斷是否真的變了，不在 setState updater 裡做副作用 */
  const debouncedSearchRef = useRef("");

  useEffect(() => {
    const next = filters.search.trim();
    const timer = setTimeout(() => {
      if (debouncedSearchRef.current === next) return;
      debouncedSearchRef.current = next;
      setDebouncedSearch(next);
      setPage(0);
    }, SEARCH_DEBOUNCE);
    return () => clearTimeout(timer);
  }, [filters.search]);

  const queryParams = useMemo(() => ({
    skip: page * PAGE_SIZE,
    limit: PAGE_SIZE,
    search: debouncedSearch || undefined,
    action: filters.action || undefined,
    userId: filters.userId || undefined,
    startTime: toIso(filters.startDate) || undefined,
    endTime: toIso(filters.endDate, true) || undefined,
  }), [debouncedSearch, filters.action, filters.userId, filters.startDate, filters.endDate, page]);

  /* 清單與摘要走 TanStack Query：每組篩選一份快取，換條件時保留上一組畫面（半透明）直到新資料回來；
     較晚回來的舊條件結果只會寫進它自己那份快取，蓋不掉目前條件的畫面。
     原本只在條件改變時查詢，不背景輪詢，這裡照舊 */
  const logsQuery = useAuditLogsQuery(queryParams, { refetchInterval: false });
  const logs = logsQuery.data?.data ?? EMPTY;
  const count = logsQuery.data?.count ?? 0;
  /* 同一串失敗只提示一次、首載失敗後切回視窗不閃回整頁載入中（沒資料時 v5 每次重抓（切回視窗）都把 status 改回 pending、清掉 error） */
  const loadFailedMessage = useLoadFailureMessage(logsQuery, t("Error.generic", { ns: "common" }));
  const logsView = useQueryView(logsQuery);
  /* 伺服器分頁：頁碼由 page 決定查詢參數，表格只渲染當頁的列 */
  const table = useTable({
    features: baseFeatures,
    columns: auditColumns,
    data: logs,
    getRowId: (log) => String(log.id),
  });
  const fit = useTableFit(AUDIT_FIT_COLUMNS);
  useEffect(() => {
    if (loadFailedMessage) toast.error(loadFailedMessage);
  }, [loadFailedMessage, toast]);

  /* 日期連續改動（手動打年份會逐位觸發）時，較晚回來的舊區間摘要不能蓋掉新區間的；
     摘要抓不到就把卡片收掉，不要留著上一個日期區間的數字誤導人 */
  const statsParams = useMemo(() => ({
    startTime: toIso(filters.startDate) || undefined,
    endTime: toIso(filters.endDate, true) || undefined,
  }), [filters.startDate, filters.endDate]);
  const statsQuery = useAuditStatsQuery(statsParams, { refetchInterval: false });
  const stats = statsQuery.isError ? null : statsQuery.data ?? null;

  /* 篩選選單；抓不到就留空選單（靜默） */
  const actionOptions = useAuditActionsQuery().data ?? EMPTY;
  const userOptions = useAuditUsersQuery().data ?? EMPTY;

  const hasFilter = Boolean(
    filters.search.trim() || filters.action || filters.userId || filters.startDate || filters.endDate,
  );
  const totalPages = Math.max(Math.ceil(count / PAGE_SIZE), 1);
  /** 載入過之後的重新查詢：保留畫面、半透明，不整頁換成 loading 動畫 */
  const isInitialLoading = logsView.loading;
  const loading = logsQuery.isFetching;

  function setField(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
    if (name !== "search") setPage(0);
  }

  function setDateField(name, value) {
    setFilters((prev) => applyDateField(prev, name, value));
    setPage(0);
  }

  function resetFilters() {
    setFilters({ search: "", action: "", userId: "", startDate: "", endDate: "" });
    setPage(0);
  }

  async function handleExport() {
    if (exporting) return;
    /* 沒有任何篩選＝要把整個稽核庫拉下來，先問一次再送 */
    if (!hasFilter) {
      const ok = await confirm({
        title: t("AuditPage.exportAllConfirmTitle"),
        message: t("AuditPage.exportAllConfirmMessage", { limit: EXPORT_LIMIT }),
        confirmText: t("AuditPage.exportCsv"),
      });
      if (!ok) return;
    }
    setExporting(true);
    try {
      const blob = await AuditLogsService.exportCsv({ ...queryParams, limit: EXPORT_LIMIT });
      downloadBlob(blob, `audit-logs-${new Date().toISOString().slice(0, 10)}.csv`);
      toast.success(t("AuditPage.toastExported"));
    } catch (err) {
      toast.error(err?.message ?? t("AuditPage.toastExportFailed"));
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className={styles.page}>
      <PageHeader title={t("AuditPage.pageTitle")}>
        <button
          type="button"
          className={styles.btnSecondary}
          onClick={handleExport}
          disabled={exporting}
          data-guide="audit-export"
        >
          <MIcon name="download" size={16} />
          {exporting ? t("AuditPage.exporting") : t("AuditPage.exportCsv")}
        </button>
      </PageHeader>

      {stats && (
        <div className={styles.summaryGrid} data-guide="audit-summary">
          <div className={styles.summaryItem}>
            <span>{t("AuditPage.statTotal")}</span>
            <strong>{stats.total}</strong>
          </div>
          <div className={styles.summaryItem}>
            <span>{t("AuditPage.statDanger")}</span>
            <strong className={styles.summaryDanger}>{stats.danger}</strong>
          </div>
          <div className={styles.summaryItem}>
            <span>{t("AuditPage.statLoginFailed")}</span>
            <strong className={styles.summaryDanger}>{stats.login_failed}</strong>
          </div>
          <div className={styles.summaryItem}>
            <span>{t("AuditPage.statActiveUsers")}</span>
            <strong>{stats.active_users}</strong>
          </div>
        </div>
      )}

      <form className={styles.toolbar} onSubmit={(e) => e.preventDefault()} data-guide="audit-filters">
        <div className={styles.searchBox}>
          <MIcon name="search" size={16} />
          <input
            value={filters.search}
            onChange={(e) => setField("search", e.target.value)}
            placeholder={t("AuditPage.searchPlaceholder")}
          />
        </div>

        <select
          className={styles.filterSelect}
          value={filters.action}
          onChange={(e) => setField("action", e.target.value)}
        >
          <option value="">{t("AuditPage.allActions")}</option>
          {actionOptions.map((a) => (
            <option key={a.value} value={a.value}>
              {a.category ? `[${a.category}] ` : ""}{a.value}
            </option>
          ))}
        </select>

        <select
          className={styles.filterSelect}
          value={filters.userId}
          onChange={(e) => setField("userId", e.target.value)}
        >
          <option value="">{t("AuditPage.allUsers")}</option>
          {userOptions.map((u) => (
            <option key={u.id} value={u.id}>
              {u.full_name ? `${u.full_name}（${u.email}）` : u.email}
            </option>
          ))}
        </select>

        {/* 日期欄沒填時在 iOS／iPadOS 是一格空白（原生日期欄沒有 placeholder），
            所以欄位名稱常駐在框裡，各瀏覽器都看得出這格是什麼 */}
        <label className={styles.dateField}>
          <span>{t("AuditPage.startDate")}</span>
          <input
            type="date"
            value={filters.startDate}
            onChange={(e) => setDateField("startDate", e.target.value)}
          />
        </label>
        <label className={styles.dateField}>
          <span>{t("AuditPage.endDate")}</span>
          <input
            type="date"
            value={filters.endDate}
            onChange={(e) => setDateField("endDate", e.target.value)}
          />
        </label>

        {hasFilter && (
          <button type="button" className={styles.btnSecondary} onClick={resetFilters}>
            <MIcon name="filter_alt_off" size={16} />
            {t("AuditPage.clear")}
          </button>
        )}
      </form>

      <div className={`${styles.content} ${loading && !isInitialLoading ? styles.refreshing : ""}`} aria-busy={loading}>
        {isInitialLoading ? (
          <LoadingState fullPage text={t("AuditPage.loading")} />
        ) : logs.length === 0 ? (
          <EmptyState hasFilter={hasFilter} onClear={resetFilters} />
        ) : (
          <>
            <div ref={fit.ref} className={styles.tableWrap} data-guide="audit-table">
              <DataTable table={table} className={styles.table} fit={fit} rowClassName={() => styles.tr} />
            </div>

            <Pagination
              page={page}
              totalPages={totalPages}
              info={t("AuditPage.paginationInfo", { count })}
              onChange={setPage}
            />
          </>
        )}
      </div>
    </div>
  );
}
