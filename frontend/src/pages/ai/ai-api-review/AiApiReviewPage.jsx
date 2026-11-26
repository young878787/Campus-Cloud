import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { createColumnHelper, useTable } from "@tanstack/react-table";
import styles from "./AiApiReviewPage.module.scss";
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
import { useAiApiCacheUpdater, useAllAiRequestsQuery } from "../../../queries/aiApi";
import { useToast } from "../../../hooks/useToast";
import { useLoadError } from "../../../hooks/useQueryLoadState";
import useDialogPresence from "../../../hooks/useDialogPresence";
import PageHeader from "../../../components/PageHeader/PageHeader";
import SegmentedControl from "../../../components/SegmentedControl/SegmentedControl";
import DataToolbar from "../../../components/DataToolbar/DataToolbar";
import BatchBar, { BatchAction, BatchDivider } from "../../../components/DataToolbar/BatchBar";
import SelectCheckbox from "../../../components/DataToolbar/SelectCheckbox";
import BatchReviewDialog from "../../../components/BatchReviewDialog/BatchReviewDialog";
import useRowSelection from "../../../hooks/useRowSelection";
import { runBatch } from "../../../utils/runBatch";
import { formatDate, formatDateTime } from "../../../utils/formatDate";

function EmptyState() {
  const { t } = useTranslation("ai");
  return <SharedEmptyState icon="assignment_turned_in" title={t("AiApiReviewPage.emptyTitle")} />;
}

/* ── Review Dialog ── */
function ReviewDialog({ open, onClose, request, action, onDone }) {
  const { t } = useTranslation("ai");
  const toast = useToast();
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  // 關閉時先播放離場動畫再卸載
  const presence = useDialogPresence(open);

  if (!presence.open || !request) return null;

  const isApprove = action === "approved";

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await AiApiService.reviewRequest(request.id, {
        status: action,
        review_comment: comment || null,
      });
      toast.success(isApprove ? t("AiApiReviewPage.approveSuccess") : t("AiApiReviewPage.rejectSuccess"));
      setComment("");
      onClose();
      onDone();
    } catch (e) {
      toast.error(e?.message ?? t("AiApiReviewPage.actionError"));
    } finally {
      setSubmitting(false);
    }
  };

  /* 外框（遮罩、Esc、焦點、捲動鎖）交給共用 Modal；送出中 Esc／點遮罩都不關 */
  return (
    <Modal
      closing={presence.closing}
      onClose={onClose}
      busy={submitting}
      size="md"
      title={isApprove ? t("AiApiReviewPage.approveDialogTitle") : t("AiApiReviewPage.rejectDialogTitle")}
      actions={
        <>
          <button type="button" className={styles.btnSecondary} onClick={onClose} disabled={submitting}>
            {t("AiApiReviewPage.cancel")}
          </button>
          <button
            data-bombadil="danger"
            type="button"
            className={isApprove ? styles.btnPrimary : styles.btnDanger}
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? t("AiApiReviewPage.processing") : isApprove ? t("AiApiReviewPage.confirmApprove") : t("AiApiReviewPage.confirmReject")}
          </button>
        </>
      }
    >
      <div className={styles.dialogBody}>
        <div className={styles.dialogInfo}>
          <div>{t("AiApiReviewPage.dialogApplicant", { value: request.user_full_name || request.user_email })}</div>
          <div>{t("AiApiReviewPage.dialogKeyName", { value: request.api_key_name })}</div>
          <div>{t("AiApiReviewPage.dialogAppliedAt", { value: formatDateTime(request.created_at, t("AiApiReviewPage.notReviewed")) })}</div>
          <div className={styles.dialogPurpose}>{t("AiApiReviewPage.dialogPurpose", { value: request.purpose })}</div>
        </div>
        <textarea
          className={styles.dialogTextarea}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder={t("AiApiReviewPage.commentPlaceholder")}
          maxLength={2000}
          rows={4}
        />
      </div>
    </Modal>
  );
}

/* ── ReviewActions in table row ── */
function ReviewActions({ item, onDone }) {
  const { t } = useTranslation("ai");
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);

  if (item.status !== "pending") {
    return (
      <span className={styles.reviewComment} title={item.review_comment || undefined}>
        {item.review_comment || "—"}
      </span>
    );
  }

  return (
    <>
      <div className={styles.actions} data-guide="ai-review-actions">
        <button
          type="button"
          className={`${styles.actionBtn} ${styles.actionBtnOk}`}
          title={t("AiApiReviewPage.actionApprove")}
          onClick={() => setApproveOpen(true)}
        >
          <MIcon name="check" size={16} />
          {t("AiApiReviewPage.actionApprove")}
        </button>
        <button
          type="button"
          className={`${styles.actionBtn} ${styles.actionBtnDanger}`}
          title={t("AiApiReviewPage.actionReject")}
          onClick={() => setRejectOpen(true)}
        >
          <MIcon name="close" size={16} />
          {t("AiApiReviewPage.actionReject")}
        </button>
      </div>
      <ReviewDialog
        open={approveOpen}
        onClose={() => setApproveOpen(false)}
        request={item}
        action="approved"
        onDone={onDone}
      />
      <ReviewDialog
        open={rejectOpen}
        onClose={() => setRejectOpen(false)}
        request={item}
        action="rejected"
        onDone={onDone}
      />
    </>
  );
}

/* ── 申請表格（TanStack Table）──
   欄位定義放模組層級：v9 的 FlexRender 把函式型的 header／cell 當元件掛載，render 裡新建會讓整格重新掛載。
   表頭文字取 meta.headerKey 的翻譯；審核完成後的重抓經 table meta 交回頁面，
   核准／拒絕對話框的開關狀態仍由每列的 ReviewActions 自己管。
   勾選欄（批量通過／拒絕）只有待審的列有勾選框，勾選狀態一樣經 table meta 傳入 */
const columnHelper = createColumnHelper();

const STATUS_LABEL_KEYS = {
  pending: "AiApiReviewPage.statusPending",
  approved: "AiApiReviewPage.statusApproved",
  rejected: "AiApiReviewPage.statusRejected",
};

function HeaderLabel({ column }) {
  const { t } = useTranslation("ai");
  return t(column.columnDef.meta.headerKey);
}

/* ── 窄版收欄（useTableFit，樣式規範「表格」規則四） ──
   表格區不夠寬時依序收起審核時間、申請時間、申請者、用途；勾選、金鑰名稱、狀態、操作永遠在。
   兩個時間一律排在一起：只收審核時間時接在申請時間底下；兩個都收時依先後排在狀態徽章底下
   （只寫日期，完整時間在 title；還沒審核的不寫審核時間，狀態徽章已經是「待審核」）。
   申請者、用途是「誰、為什麼要這把金鑰」，收進金鑰名稱底下（金鑰名稱是這一列的名字：勾選框、批量對話框都用它）。
   欄寬只寫在這裡：完整日期時間（2026/09/10 14:30:15）要 170px；英文的 Pending Review 徽章要 160px；
   英文的 Approve／Reject 兩顆鈕並排要 200px；勾選框 16px 加左右內距是 48px。
   有勾選欄時全部 1258px：1440（表格區約 1003px）、1366 筆電（約 929～944px）收掉兩個時間剩 918px；
   1100 寬視窗（約 678px）再收申請者、用途剩 558px，1440 開著 AI 助手（約 567px）也放得下。
   手機（約 448px）收到底仍放不下，橫捲並固定第一欄（勾選欄）與操作欄，金鑰名稱會跟著捲。
   沒有待審的分頁不畫勾選欄，少 48px（收到底 510px）；手機上固定的第一欄就是金鑰名稱 */
const REQUEST_FIT_COLUMNS = Object.freeze([
  { id: "applicant", width: 180, fold: 3 },
  { id: "api_key_name", width: 150 },
  { id: "purpose", width: 180, fold: 4 },
  { id: "status", width: 160 },
  { id: "created_at", width: 170, fold: 2 },
  { id: "reviewed_at", width: 170, fold: 1 },
  { id: "actions", width: 200 },
]);

const SELECTABLE_FIT_COLUMNS = Object.freeze([{ id: "select", width: 48, pinNext: true }, ...REQUEST_FIT_COLUMNS]);

function applicantName(r) {
  return r.user_full_name || r.user_email;
}

/* 收進金鑰名稱底下的申請者一行：「姓名 · Email」（沒有姓名就只有 Email） */
function applicantLine(r) {
  return [applicantName(r), r.user_full_name && r.user_email].filter(Boolean).join(" · ");
}

/* 用途：表格裡只放前 60 字（單行截斷），完整內容在 title 與審核對話框 */
function purposePreview(purpose) {
  return (purpose ?? "").length > 60 ? `${purpose.slice(0, 60)}…` : purpose;
}

function ApplicantCell({ row }) {
  const r = row.original;
  return (
    <div className={styles.userCell}>
      <span className={styles.userName}>{applicantName(r)}</span>
      {r.user_full_name && r.user_email && (
        <span className={styles.userEmail}>{r.user_email}</span>
      )}
    </div>
  );
}

/* 窄版收欄時金鑰名稱底下多畫：申請者（姓名 · Email）一行、用途一行（單行截斷）；
   用途的導覽錨點跟著搬過來，收欄後導覽照樣指得到 */
function KeyNameCell({ row }) {
  const fit = useTableFitContext();
  const r = row.original;
  return (
    <>
      <div className={styles.keyName}>{r.api_key_name}</div>
      {fit.isFolded("applicant") && (
        <div className={`${styles.foldedLine} ${styles.foldedTruncate}`} title={applicantLine(r)}>
          {applicantLine(r)}
        </div>
      )}
      {fit.isFolded("purpose") && r.purpose && (
        <div className={`${styles.foldedLine} ${styles.foldedTruncate}`} title={r.purpose} data-guide="ai-review-purpose">
          {purposePreview(r.purpose)}
        </div>
      )}
    </>
  );
}

function PurposeCell({ row }) {
  const r = row.original;
  return (
    <span className={styles.purposeCell} title={r.purpose}>
      {purposePreview(r.purpose)}
    </span>
  );
}

/* 收進其他欄的時間：欄名＋日期，完整時間在 title（同 AI API 頁金鑰表收起的建立時間） */
function FoldedTimeLine({ labelKey, value }) {
  const { t } = useTranslation("ai");
  return (
    <div className={styles.foldedLine} title={formatDateTime(value)}>
      {t(labelKey)} {formatDate(value)}
    </div>
  );
}

/* error：上一次批量沒成功的那筆（{ action, reason }），原因標在狀態底下。
   窄版兩個時間都收起時，依先後接在後面 */
function StatusCell({ item, error }) {
  const { t } = useTranslation("ai");
  const fit = useTableFitContext();
  const status = item.status;
  const labelKey = STATUS_LABEL_KEYS[status];
  const timesFolded = fit.isFolded("created_at");
  return (
    <>
      <span className={`${styles.badge} ${styles[`badge_${status}`]}`}>
        <span className={styles.dot} />
        {labelKey ? t(labelKey) : status}
      </span>
      {error && (
        <div className={styles.rowError}>
          {t("AiApiReviewPage.batchFailedReason", {
            action: t(error.action === "approved" ? "AiApiReviewPage.actionApprove" : "AiApiReviewPage.actionReject"),
            reason: error.reason,
          })}
        </div>
      )}
      {timesFolded && <FoldedTimeLine labelKey="AiApiReviewPage.colAppliedAt" value={item.created_at} />}
      {timesFolded && fit.isFolded("reviewed_at") && item.reviewed_at && (
        <FoldedTimeLine labelKey="AiApiReviewPage.colReviewedAt" value={item.reviewed_at} />
      )}
    </>
  );
}

function DateTimeCell({ getValue }) {
  const { t } = useTranslation("ai");
  return formatDateTime(getValue(), t("AiApiReviewPage.notReviewed"));
}

/* 申請時間；窄版只收起審核時間時，審核時間接在底下（兩個時間排在一起） */
function CreatedAtCell({ row, getValue }) {
  const fit = useTableFitContext();
  const reviewedAt = row.original.reviewed_at;
  return (
    <>
      <DateTimeCell getValue={getValue} />
      {fit.isFolded("reviewed_at") && reviewedAt && (
        <FoldedTimeLine labelKey="AiApiReviewPage.colReviewedAt" value={reviewedAt} />
      )}
    </>
  );
}

function ActionsCell({ row, table }) {
  /* 審核完成時才讀 meta，拿到的是頁面當下的重抓函式 */
  return <ReviewActions item={row.original} onDone={() => table.options.meta.onReviewed()} />;
}

function SelectAllHeader({ checked, indeterminate, onToggle }) {
  const { t } = useTranslation("ai");
  return (
    <SelectCheckbox
      cell
      checked={checked}
      indeterminate={indeterminate}
      onToggle={onToggle}
      ariaLabel={t("AiApiReviewPage.selectAllAria")}
    />
  );
}

function RowSelectCell({ item, selected, onToggle }) {
  const { t } = useTranslation("ai");
  if (item.status !== "pending") return null;
  return (
    <SelectCheckbox
      cell
      checked={selected}
      onToggle={(shiftKey) => onToggle(item.id, shiftKey)}
      ariaLabel={t("AiApiReviewPage.selectRowAria", { name: item.api_key_name })}
    />
  );
}

function columnMeta(headerKey, extra) {
  return { headerKey, thClassName: styles.th, tdClassName: styles.td, ...extra };
}

/* 勾選：整格都是點擊範圍；Shift 點選連選一段 */
const selectColumn = columnHelper.display({
  id: "select",
  header: ({ table }) => <SelectAllHeader {...table.options.meta.selectAll} />,
  cell: ({ row, table }) => (
    <RowSelectCell
      item={row.original}
      selected={table.options.meta.isSelected(row.original.id)}
      onToggle={table.options.meta.onToggleSelect}
    />
  ),
  meta: {
    thClassName: styles.th,
    tdClassName: styles.td,
    tdProps: { "data-guide": "ai-review-row-select" },
  },
});

/* 欄寬與收合順序在 REQUEST_FIT_COLUMNS（id 要對得上） */
const dataColumns = [
  columnHelper.display({ id: "applicant", header: HeaderLabel, cell: ApplicantCell, meta: columnMeta("AiApiReviewPage.colApplicant") }),
  columnHelper.accessor("api_key_name", { header: HeaderLabel, cell: KeyNameCell, meta: columnMeta("AiApiReviewPage.colKeyName") }),
  columnHelper.display({
    id: "purpose",
    header: HeaderLabel,
    cell: PurposeCell,
    meta: columnMeta("AiApiReviewPage.colPurpose", { tdProps: { "data-guide": "ai-review-purpose" } }),
  }),
  columnHelper.display({
    id: "status",
    header: HeaderLabel,
    cell: ({ row, table }) => <StatusCell item={row.original} error={table.options.meta.batchErrors[row.original.id]} />,
    meta: columnMeta("AiApiReviewPage.colStatus"),
  }),
  columnHelper.accessor("created_at", { header: HeaderLabel, cell: CreatedAtCell, meta: columnMeta("AiApiReviewPage.colAppliedAt") }),
  columnHelper.accessor("reviewed_at", { header: HeaderLabel, cell: DateTimeCell, meta: columnMeta("AiApiReviewPage.colReviewedAt") }),
  columnHelper.display({ id: "actions", header: HeaderLabel, cell: ActionsCell, meta: columnMeta("AiApiReviewPage.colActions") }),
];

/* 這個分頁沒有待審的列（已通過／已拒絕）就不留一欄空的勾選欄 */
const requestColumns = columnHelper.columns(dataColumns);
const selectableColumns = columnHelper.columns([selectColumn, ...dataColumns]);

/* ── Main ── */
/* 後端 /ai-api/requests 的 limit 上限 */
const REQUEST_LIST_LIMIT = 100;
const EMPTY = Object.freeze([]);

/* 狀態篩選交給後端：清單上限 100 筆且新到舊，前端自己篩會讓比最新 100 筆還舊的待審申請看不到。
   非目前分頁只取 1 筆，拿 count 給角標。 */
function tabParams(key, activeTab) {
  return {
    status: key === "all" ? undefined : key,
    limit: key === activeTab ? REQUEST_LIST_LIMIT : 1,
  };
}

function tabCount(query) {
  return query.data?.count ?? query.data?.data?.length ?? 0;
}

export default function AiApiReviewPage() {
  const { t } = useTranslation("ai");
  const toast = useToast();
  const [activeTab, setActiveTab] = useState("pending");

  const TABS = [
    { key: "pending",  label: t("AiApiReviewPage.tabPending") },
    { key: "approved", label: t("AiApiReviewPage.tabApproved") },
    { key: "rejected", label: t("AiApiReviewPage.tabRejected") },
    { key: "all",      label: t("AiApiReviewPage.tabAll") },
  ];

  /* 四個分頁各一份查詢（hook 固定四次、不在迴圈裡呼叫），以「狀態＋筆數上限」為 key：
     切換分頁時較晚回來的舊分頁回應只會進舊 key，不會蓋掉目前分頁，也不會提早收掉載入畫面。
     背景 30 秒刷新、分頁隱藏時暫停；角標在換分頁時沿用上一份筆數（keepPreviousData）。 */
  const pendingQuery = useAllAiRequestsQuery(tabParams("pending", activeTab));
  const approvedQuery = useAllAiRequestsQuery(tabParams("approved", activeTab));
  const rejectedQuery = useAllAiRequestsQuery(tabParams("rejected", activeTab));
  const allQuery = useAllAiRequestsQuery(tabParams("all", activeTab));
  const aiCache = useAiApiCacheUpdater();
  const tabQueries = { pending: pendingQuery, approved: approvedQuery, rejected: rejectedQuery, all: allQuery };
  const activeQuery = tabQueries[activeTab];
  const counts = {
    pending: tabCount(pendingQuery),
    approved: tabCount(approvedQuery),
    rejected: tabCount(rejectedQuery),
    all: tabCount(allQuery),
  };

  /* 清單要等這個分頁自己的完整資料（上限 100 筆）回來才顯示：佔位資料是上一個 key（只取 1 筆的角標查詢） */
  const rowsReady = activeQuery.data !== undefined && !activeQuery.isPlaceholderData;
  /* 四個查詢各自記錯誤狀態（見 useLoadError）：背景重試期間錯誤畫面維持，按重試才回到載入中。
     沒有資料時每次重抓 TanStack 都會把佔位資料放回來，所以佔位資料也當成沒資料交給它 */
  const pendingLoad = useLoadError(pendingQuery);
  const approvedLoad = useLoadError(approvedQuery);
  const rejectedLoad = useLoadError(rejectedQuery);
  const allLoad = useLoadError(allQuery);
  const tabLoads = { pending: pendingLoad, approved: approvedLoad, rejected: rejectedLoad, all: allLoad };
  const activeLoadError = tabLoads[activeTab].error;
  const loadError = !rowsReady && Boolean(activeLoadError);
  const loading = !rowsReady && !loadError && (activeQuery.isPending || activeQuery.isFetching);
  const requests = rowsReady ? activeQuery.data?.data ?? EMPTY : EMPTY;

  /* 重試：四個分頁一起重抓（與原本重抓全部清單相同），沒資料的回到載入中 */
  function retryLoad() {
    Object.values(tabLoads).forEach((load) => load.retry());
  }

  /* 目前分頁一筆資料都還沒拿到就失敗才提醒（與原本的前景載入相同）；背景刷新失敗不跳 toast。
     錯誤取自 useLoadError：背景重試期間不會先清空再變回來，同一個錯誤不會每輪重跳 */
  const loadErrorMessage = activeLoadError
    ? activeLoadError.message ?? t("AiApiReviewPage.loadError")
    : null;
  useEffect(() => {
    if (loadErrorMessage) toast.error(loadErrorMessage);
  }, [loadErrorMessage, toast]);

  /* 審核後在背景重抓所有分頁（清單留在畫面上），重抓失敗照原本提醒 */
  function refreshAfterReview() {
    aiCache.invalidateAllRequests({ throwOnError: true })
      .catch((e) => toast.error(e?.message ?? t("AiApiReviewPage.loadError")));
  }

  const filtered = useMemo(() => {
    if (activeTab === "all") return requests;
    return requests.filter((r) => r.status === activeTab);
  }, [requests, activeTab]);

  /* 批量通過／拒絕：只勾得到畫面上待審的申請；換分頁或刷新後看不到的自動取消勾選 */
  const selectableIds = filtered.filter((r) => r.status === "pending").map((r) => r.id);
  const selection = useRowSelection(selectableIds);
  const selectedRequests = filtered.filter((r) => selection.isSelected(r.id));
  /* 對話框關閉動畫期間還要知道是哪一種，所以動作與開關分開記 */
  const [batchAction, setBatchAction] = useState("rejected");
  const [batchOpen, setBatchOpen] = useState(false);
  const batchDialog = useDialogPresence(batchOpen);
  const [batchProgress, setBatchProgress] = useState(null); // { action, done, total }
  /* 上一次批量沒成功的那幾筆：原因標在各自的列上（id → { action, reason }），下一次批量或換分頁時清掉 */
  const [batchErrors, setBatchErrors] = useState({});

  function changeTab(tab) {
    setActiveTab(tab);
    setBatchErrors({});
  }

  function openBatchDialog(action) {
    setBatchAction(action);
    setBatchOpen(true);
  }

  /* 沒有後端批量 API：逐筆呼叫單筆審核，一筆失敗不影響其他筆 */
  async function batchReview(reviewComment) {
    const action = batchAction;
    const targets = selectedRequests;
    setBatchOpen(false);
    if (!targets.length || batchProgress) return;
    const approving = action === "approved";
    setBatchErrors({});
    setBatchProgress({ action, done: 0, total: targets.length });
    const body = { status: action, review_comment: reviewComment };
    const res = await runBatch(targets, (item) => AiApiService.reviewRequest(item.id, body), {
      concurrency: 3,
      onProgress: ({ done, total }) => setBatchProgress({ action, done, total }),
    });
    const failed = res.results.filter((r) => !r.ok);
    if (failed.length === 0) {
      toast.success(t(approving ? "AiApiReviewPage.batchApprovedToast" : "AiApiReviewPage.batchRejectedToast", { count: res.succeeded }));
    } else {
      toast.error(t(approving ? "AiApiReviewPage.batchApproveFailedKeptToast" : "AiApiReviewPage.batchRejectFailedKeptToast", { succeeded: res.succeeded, failed: res.failed }));
    }
    /* 失敗的原因標在各自的列上，不用一筆筆點開猜 */
    setBatchErrors(Object.fromEntries(failed.map((r) => [
      r.item.id,
      { action, reason: r.error?.message ?? t("AiApiReviewPage.actionError") },
    ])));
    /* 成功的取消勾選，失敗的留著可以直接再試；靜默刷新，清單不閃載入畫面 */
    selection.replace(failed.map((r) => r.item.id));
    setBatchProgress(null);
    refreshAfterReview();
  }

  const selectable = selectableIds.length > 0;
  const table = useTable({
    features: baseFeatures,
    columns: selectable ? selectableColumns : requestColumns,
    data: filtered,
    getRowId: (r) => String(r.id),
    meta: {
      onReviewed: refreshAfterReview,
      selectAll: {
        checked: selection.allSelected,
        indeterminate: selection.someSelected,
        onToggle: selection.toggleAll,
      },
      isSelected: selection.isSelected,
      onToggleSelect: selection.toggle,
      batchErrors,
    },
  });
  /* 欄位表跟著有沒有勾選欄換（兩組都是模組層級常數，換分頁才會重新量） */
  const fit = useTableFit(selectable ? SELECTABLE_FIT_COLUMNS : REQUEST_FIT_COLUMNS);

  /* 勾選狀態下（已勾了至少一筆）點待審的整列也是勾選；列內的通過／拒絕鈕照舊 */
  const requestRowClassName = (row) => {
    const selectable = row.original.status === "pending";
    return `${styles.tr}${selection.isSelected(row.original.id) ? ` ${styles.trSelected}` : ""}${selection.selecting && selectable ? ` ${styles.trClickable}` : ""}`;
  };
  const requestRowProps = (row) => ({
    onClick: (event) => { selection.rowClick(row.original.id, event); },
  });

  return (
    <div className={styles.page}>
      <PageHeader title={t("AiApiReviewPage.pageTitle")} />

      {/* 平常是狀態分頁；勾選待審申請後原地換成批量通過／拒絕（同一個高度，表格不會跳） */}
      <DataToolbar
        data-guide="ai-review-tabs"
        selecting={selectedRequests.length > 0}
        batch={(
          <BatchBar
            countLabel={t("AiApiReviewPage.selectedCount", { count: selectedRequests.length })}
            onClear={selection.clear}
            progress={batchProgress && {
              text: t(batchProgress.action === "approved" ? "AiApiReviewPage.batchApproving" : "AiApiReviewPage.batchRejecting", batchProgress),
              done: batchProgress.done,
              total: batchProgress.total,
            }}
          >
            <BatchAction icon="check" label={t("AiApiReviewPage.actionApprove")} onClick={() => openBatchDialog("approved")} />
            <BatchDivider />
            <BatchAction icon="block" label={t("AiApiReviewPage.actionReject")} danger onClick={() => openBatchDialog("rejected")} />
          </BatchBar>
        )}
      >
        <SegmentedControl
          className={styles.tabsControl}
          options={TABS.map(({ key, label }) => ({
            value: key,
            label,
            badge: counts[key] ?? 0,
          }))}
          value={activeTab}
          onChange={changeTab}
          ariaLabel={t("AiApiReviewPage.tabsAriaLabel")}
        />
      </DataToolbar>

      <div className={styles.content}>
        {loading ? (
          <LoadingState fullPage />
        ) : loadError ? (
          <ErrorState onRetry={retryLoad} />
        ) : filtered.length === 0 ? (
          <EmptyState />
        ) : (
          <div ref={fit.ref} className={styles.tableWrap} data-guide="ai-review-table">
            <DataTable
              table={table}
              fit={fit}
              className={styles.table}
              rowClassName={requestRowClassName}
              rowProps={requestRowProps}
            />
          </div>
        )}
      </div>

      {batchDialog.open && (
        <BatchReviewDialog
          tone={batchAction === "approved" ? "approve" : "reject"}
          title={t(batchAction === "approved" ? "AiApiReviewPage.batchApproveTitle" : "AiApiReviewPage.batchRejectTitle", { count: selectedRequests.length })}
          description={t(batchAction === "approved" ? "AiApiReviewPage.batchApproveDesc" : "AiApiReviewPage.batchRejectDesc")}
          items={selectedRequests.map((r) => ({ id: r.id, icon: "key", name: r.api_key_name, sub: r.user_full_name || r.user_email }))}
          moreLabel={(count) => t("AiApiReviewPage.batchNamesMore", { count })}
          commentLabel={t("AiApiReviewPage.batchCommentLabel")}
          commentPlaceholder={t("AiApiReviewPage.batchCommentPlaceholder")}
          confirmLabel={t(batchAction === "approved" ? "AiApiReviewPage.batchApproveConfirm" : "AiApiReviewPage.batchRejectConfirm", { count: selectedRequests.length })}
          cancelLabel={t("AiApiReviewPage.cancel")}
          closing={batchDialog.closing}
          onClose={() => setBatchOpen(false)}
          onSubmit={batchReview}
        />
      )}
    </div>
  );
}
