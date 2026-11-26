import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { createColumnHelper, useTable } from "@tanstack/react-table";
import styles from "./MonitoringPage.module.scss";
import MIcon from "../../../components/MIcon";
import Modal from "../../../components/Modal/Modal";
import DataTable, { DataTableCells } from "../../../components/DataTable/DataTable";
import { baseFeatures } from "../../../components/DataTable/features";
import { useTableFitContext } from "../../../components/DataTable/TableFitContext";
import useTableFit from "../../../hooks/useTableFit";
import LoadingState from "../../../components/LoadingState/LoadingState";
import EmptyState from "../../../components/EmptyState/EmptyState";
import { MiningIncidentsService } from "../../../services/miningIncidents";
import { useMiningIncidentCacheUpdater, useMiningIncidentsQuery } from "../../../queries/miningIncidents";
import { useToast } from "../../../hooks/useToast";
import { useLoadError } from "../../../hooks/useQueryLoadState";
import { useConfirm } from "../../../components/ConfirmDialog/ConfirmProvider";
import useDialogPresence from "../../../hooks/useDialogPresence";
import { formatDate, formatDateTime } from "../../../utils/formatDate";
import { joinClauses } from "../../../utils/joinList";

/** 待處理＝detected／suspended（與後端 open 定義相同）；banned／dismissed 為已結案 */
const isOpenIncident = (status) => status === "detected" || status === "suspended";

const EMPTY = Object.freeze([]);

/** 待處理顯示紅色，已結案中性 */
function statusBadgeClass(status) {
  return isOpenIncident(status) ? "badge_danger" : "badge_muted";
}

/**
 * 誤判解除後要顯示的提示。
 * 後端恢復 VM／刪存證快照失敗時仍會結案，只把失敗原因附進 review_note，
 * 所以不能只看 status（永遠是 dismissed）就報成功。
 * 優先用回應的 warnings 陣列；舊版後端沒有這個欄位時，review_note 與送出的備註不同
 * 就代表後端附加了失敗原因（沒有失敗時後端會原樣存入送出的備註）。
 */
export function dismissOutcome(incident, result, submittedNote) {
  let warnings;
  if (Array.isArray(result?.warnings)) {
    warnings = result.warnings.filter(Boolean);
  } else {
    const stored = result?.review_note ?? null;
    warnings = stored !== (submittedNote ?? null) && stored ? [stored] : [];
  }
  if (warnings.length > 0) {
    return { level: "warning", key: "MiningIncidentsPanel.toastDismissedWithWarnings", message: joinClauses(warnings) };
  }
  return {
    level: "success",
    key: incident?.status === "suspended"
      ? "MiningIncidentsPanel.toastDismissedAndRecovered"
      : "MiningIncidentsPanel.toastDismissed",
  };
}

/** 表頭文字（header 是元件，可以直接用 hook） */
function ColTitle({ name }) {
  const { t } = useTranslation("system");
  return t(`MiningIncidentsPanel.${name}`);
}

/* ── 挖礦事件表窄版收欄（useTableFit） ──
   表格區不夠寬時依序收起觀察視窗、存證快照、平均 CPU、偵測時間、擁有者；VMID、狀態、操作永遠在。
   觀察視窗是平均 CPU 的統計區間，只收它時接在平均 CPU 底下；偵測證據（平均 CPU、存證快照）與偵測時間
   收到狀態徽章底下；擁有者收到 VMID 底下（欄窄，只寫姓名一行，email 在 title）。
   欄寬只寫在這裡：觀察視窗 140px 是為了英文表頭 Observation Window；操作欄放得下中文「停權＋誤判解除」，
   英文／日文放不下時兩顆換行。原本表格直接放在卡片裡（卡片 overflow: hidden），放不下的欄被裁掉也捲不到，
   現在包一層 .tableScroll。全部欄 1230px：1440（約 1003px）、1366 筆電（約 929px）收掉觀察視窗與存證快照（920px），
   1100 寬視窗（約 678px）收到偵測時間（660px），1440 開著 AI 助手（約 567px）收到擁有者（490px）；
   再窄才橫捲並固定 VMID 欄 */
const INCIDENT_FIT_COLUMNS = Object.freeze([
  { id: "vmid", width: 90 },
  { id: "owner", width: 170, fold: 5 },
  { id: "avg_cpu", width: 90, fold: 3 },
  { id: "window_hours", width: 140, fold: 1 },
  { id: "snapshot_name", width: 170, fold: 2 },
  { id: "status", width: 160 },
  { id: "detected_at", width: 170, fold: 4 },
  { id: "actions", width: 240 },
]);

/* 收起的欄在主欄裡的一行小字；label 給「光看值看不出是什麼」的欄（平均 CPU、偵測時間） */
function FoldedLine({ label, title, truncate = false, children }) {
  return (
    <div className={`${styles.foldedLine} ${truncate ? styles.foldedLineTruncate : ""}`} title={title}>
      {label && <span className={styles.foldedLabel}>{label}</span>}
      {children}
    </div>
  );
}

/* 窄版收起擁有者時，姓名接在 VMID 底下 */
function VmidCell({ incident }) {
  const { t } = useTranslation("system");
  const fit = useTableFitContext();
  const { vmid } = incident;
  /* 判斷誤判要看機器用途、CPU 曲線與存證快照，直接連到資源詳情 */
  return (
    <>
      <Link
        to={`/resource-mgmt/${vmid}`}
        className={styles.vmLink}
        title={t("MiningIncidentsPanel.openResourceDetail", { vmid })}
      >
        {vmid}
        <MIcon name="open_in_new" size={12} />
      </Link>
      {fit.isFolded("owner") && (
        <FoldedLine title={incident.owner_email || undefined} truncate>
          {incident.owner_full_name || incident.owner_email || t("MiningIncidentsPanel.ownerUnknown")}
        </FoldedLine>
      )}
    </>
  );
}

function OwnerCell({ incident }) {
  const { t } = useTranslation("system");
  return incident.owner_email ? (
    <div className={styles.ownerCell}>
      <span>{incident.owner_full_name || incident.owner_email}</span>
      {incident.owner_full_name && (
        <span className={styles.mutedCell}>{incident.owner_email}</span>
      )}
    </div>
  ) : (
    <span className={styles.mutedCell}>{t("MiningIncidentsPanel.ownerUnknown")}</span>
  );
}

function WindowCell({ hours }) {
  const { t } = useTranslation("system");
  return t("MiningIncidentsPanel.hoursValue", { hours });
}

function avgCpuText(incident) {
  return `${incident.avg_cpu.toFixed(1)}%`;
}

/* 只收起觀察視窗時，統計區間接在平均 CPU 底下（「98.5%／6 小時」看得出是幾小時的平均） */
function AvgCpuCell({ incident }) {
  const fit = useTableFitContext();
  return (
    <>
      {avgCpuText(incident)}
      {fit.isFolded("window_hours") && <FoldedLine><WindowCell hours={incident.window_hours} /></FoldedLine>}
    </>
  );
}

function SnapshotCell({ name }) {
  const { t } = useTranslation("system");
  return name ? (
    <span className={`${styles.monoCell} ${styles.snapCell}`}>
      <MIcon name="photo_camera" size={12} />
      {name}
    </span>
  ) : (
    <span className={styles.mutedCell}>{t("MiningIncidentsPanel.snapshotFailed")}</span>
  );
}

/* 窄版收欄時狀態欄多畫：平均 CPU（觀察視窗也收了就接在後面）、存證快照、偵測時間 */
function StatusCell({ incident }) {
  const { t } = useTranslation("system");
  const fit = useTableFitContext();
  const STATUS_LABELS = {
    detected: t("MiningIncidentsPanel.statusDetected"),
    suspended: t("MiningIncidentsPanel.statusSuspended"),
    banned: t("MiningIncidentsPanel.statusBanned"),
    dismissed: t("MiningIncidentsPanel.statusDismissed"),
  };
  return (
    <>
      <span className={`${styles.badge} ${styles[statusBadgeClass(incident.status)]}`}>
        {STATUS_LABELS[incident.status] ?? incident.status}
      </span>
      {/* 結案備註含後端附加的失敗原因（例如 VM 恢復失敗要手動開機），重新整理後仍要看得到 */}
      {!isOpenIncident(incident.status) && incident.review_note && (
        <div className={`${styles.mutedCell} ${styles.reviewNote}`} title={incident.review_note}>
          {incident.review_note}
        </div>
      )}
      {fit.isFolded("avg_cpu") && (
        <FoldedLine label={t("MiningIncidentsPanel.colAvgCpu")}>
          {avgCpuText(incident)}
          {fit.isFolded("window_hours") && <> · <WindowCell hours={incident.window_hours} /></>}
        </FoldedLine>
      )}
      {/* 快照有相機圖示、失敗時寫「存證失敗」，不另加欄名 */}
      {fit.isFolded("snapshot_name") && <FoldedLine><SnapshotCell name={incident.snapshot_name} /></FoldedLine>}
      {fit.isFolded("detected_at") && (
        <FoldedLine label={t("MiningIncidentsPanel.colDetectedAt")} title={formatDateTime(incident.detected_at)}>
          {formatDate(incident.detected_at)}
        </FoldedLine>
      )}
    </>
  );
}

/** 停權／誤判解除；處理函式在點擊當下才從 table meta 取，拿到的一定是面板最新的那一份 */
function IncidentActions({ incident, busy, table }) {
  const { t } = useTranslation("system");
  if (!isOpenIncident(incident.status)) return null;
  return (
    <div className={styles.incidentActions}>
      <button
        type="button"
        className={styles.btnDangerOutline}
        disabled={busy}
        onClick={() => table.options.meta.onBan(incident)}
      >
        <MIcon name="block" size={14} />
        {t("MiningIncidentsPanel.ban")}
      </button>
      <button
        type="button"
        className={styles.btnSecondary}
        disabled={busy}
        onClick={() => table.options.meta.onDismiss(incident)}
      >
        <MIcon name="undo" size={14} />
        {t("MiningIncidentsPanel.dismissMisjudged")}
      </button>
    </div>
  );
}

const columnHelper = createColumnHelper();

/* 欄位定義放模組層級：FlexRender 把函式型的 header／cell 當元件掛載，render 裡新建會整格重新掛載 */
const incidentColumns = columnHelper.columns([
  columnHelper.accessor("vmid", {
    header: "VMID",
    cell: ({ row }) => <VmidCell incident={row.original} />,
    meta: { thClassName: styles.th, tdClassName: `${styles.td} ${styles.monoCell}` },
  }),
  columnHelper.display({
    id: "owner",
    header: () => <ColTitle name="colOwner" />,
    cell: ({ row }) => <OwnerCell incident={row.original} />,
    meta: { thClassName: styles.th, tdClassName: styles.td },
  }),
  columnHelper.accessor("avg_cpu", {
    header: () => <ColTitle name="colAvgCpu" />,
    cell: ({ row }) => <AvgCpuCell incident={row.original} />,
    meta: { thClassName: styles.th, tdClassName: `${styles.td} ${styles.monoCell}` },
  }),
  columnHelper.accessor("window_hours", {
    header: () => <ColTitle name="colWindow" />,
    cell: ({ row }) => <WindowCell hours={row.original.window_hours} />,
    meta: { thClassName: styles.th, tdClassName: `${styles.td} ${styles.mutedCell}` },
  }),
  columnHelper.accessor("snapshot_name", {
    header: () => <ColTitle name="colSnapshot" />,
    cell: ({ row }) => <SnapshotCell name={row.original.snapshot_name} />,
    meta: { thClassName: styles.th, tdClassName: styles.td },
  }),
  columnHelper.accessor("status", {
    header: () => <ColTitle name="colStatus" />,
    cell: ({ row }) => <StatusCell incident={row.original} />,
    meta: { thClassName: styles.th, tdClassName: styles.td },
  }),
  columnHelper.accessor("detected_at", {
    header: () => <ColTitle name="colDetectedAt" />,
    cell: ({ row }) => formatDateTime(row.original.detected_at),
    meta: { thClassName: styles.th, tdClassName: `${styles.td} ${styles.mutedCell}` },
  }),
  columnHelper.display({
    id: "actions",
    header: () => <ColTitle name="colActions" />,
    /* busy 是面板的狀態：經 rowState 傳進來（只改 table meta 不會讓儲存格重繪） */
    cell: ({ row, table, rowState }) => <IncidentActions incident={row.original} busy={rowState.busy} table={table} />,
    meta: { thClassName: styles.th, tdClassName: styles.td },
  }),
]);

export default function MiningIncidentsPanel({ onCountChange }) {
  const { t } = useTranslation("system");
  const toast = useToast();
  const confirm = useConfirm();
  const [dismissTarget, setDismissTarget] = useState(null);
  const [dismissExempt, setDismissExempt] = useState(false);
  const [dismissNote, setDismissNote] = useState("");
  const [busy, setBusy] = useState(false);
  const dismissDialog = useDialogPresence(dismissTarget);
  /* 30 秒背景刷新、分頁隱藏時暫停。首次就抓不到時當作沒有事件（同原本，不擋住面板）；
     背景刷新失敗沿用上一份清單 */
  const incidentsQuery = useMiningIncidentsQuery();
  const incidentCache = useMiningIncidentCacheUpdater();
  /* 首載失敗看 useLoadError（沒資料時 v5 每次重抓都把 status 改回 pending、清掉 error，看 isError 會在背景重試時閃回載入中） */
  const incidentsLoadError = useLoadError(incidentsQuery).error;
  const incidents = incidentsQuery.data !== undefined
    ? incidentsQuery.data ?? EMPTY
    : incidentsLoadError ? EMPTY : null;

  const open = (incidents ?? []).filter((i) => isOpenIncident(i.status));
  const closed = (incidents ?? []).filter((i) => !isOpenIncident(i.status));

  /* 分頁角標顯示「待處理」筆數，載入後回報給監控頁 */
  useEffect(() => {
    if (incidents !== null) onCountChange?.(open.length);
  }, [incidents, open.length, onCountChange]);

  /* 停權不需要填理由，直接用共用確認框；送出期間 busy 擋住重複點擊 */
  const handleBan = async (incident) => {
    if (busy) return;
    const ok = await confirm({
      title: t("MiningIncidentsPanel.banConfirmTitle"),
      message: t("MiningIncidentsPanel.banConfirmMessage", { vmid: incident.vmid }),
      confirmText: t("MiningIncidentsPanel.confirmBan"),
      cancelText: t("MiningIncidentsPanel.cancel"),
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await MiningIncidentsService.ban(incident.id);
      toast.success(t("MiningIncidentsPanel.toastBanSuccess"));
      /* 重抓完才解除 busy（同原本 await load()）；管理首頁的待處理數也一起過期 */
      await incidentCache.invalidate();
    } catch (e) {
      toast.error(t("MiningIncidentsPanel.toastBanFailed", { message: e?.message ?? t("MiningIncidentsPanel.unknownError") }));
    } finally {
      setBusy(false);
    }
  };

  const closeDismiss = () => {
    setDismissTarget(null);
    setDismissExempt(false);
    setDismissNote("");
  };

  const handleDismiss = async () => {
    setBusy(true);
    try {
      const note = dismissNote || null;
      const result = await MiningIncidentsService.dismiss(dismissTarget.id, {
        exempt: dismissExempt,
        note,
      });
      const outcome = dismissOutcome(dismissTarget, result, note);
      if (outcome.level === "warning") {
        toast.warning(t(outcome.key, { message: outcome.message }));
      } else {
        toast.success(t(outcome.key));
      }
      closeDismiss();
      await incidentCache.invalidate();
    } catch (e) {
      toast.error(t("MiningIncidentsPanel.toastDismissFailed", { message: e?.message ?? t("MiningIncidentsPanel.unknownError") }));
    } finally {
      setBusy(false);
    }
  };

  /* 待處理排前面、已結案在後 */
  const table = useTable({
    features: baseFeatures,
    columns: incidentColumns,
    data: [...open, ...closed],
    getRowId: (incident) => String(incident.id),
    meta: { onBan: handleBan, onDismiss: setDismissTarget },
  });
  /* 面板在監控頁的分頁裡：沒選中時 display: none 量不到寬度（不收欄），切過來時 ResizeObserver 會重量 */
  const fit = useTableFit(INCIDENT_FIT_COLUMNS);

  return (
    <div className={styles.card}>
      {/* 標題由外層頁籤承擔，卡內只留說明 */}
      <div className={styles.cardHeader}>
        <p className={styles.cardDesc}>{t("MiningIncidentsPanel.desc")}</p>
        {open.length > 0 && <span className={styles.alertCount}>{t("MiningIncidentsPanel.pendingCount", { count: open.length })}</span>}
      </div>

      {incidents === null ? (
        <LoadingState />
      ) : incidents.length === 0 ? (
        <EmptyState icon="verified_user" title={t("MiningIncidentsPanel.emptyNone")} />
      ) : (
        <div ref={fit.ref} className={styles.tableScroll}>
          <DataTable
            table={table}
            className={styles.table}
            fit={fit}
            renderRow={(row) => (
              <tr key={row.id} className={styles.tr}>
                <DataTableCells row={row} rowState={{ busy }} />
              </tr>
            )}
          />
        </div>
      )}

      {/* 誤判解除：要勾選豁免與填備註，不能用 useConfirm；送出中 Esc／點遮罩都不關 */}
      {dismissDialog.open && (
        <Modal
          closing={dismissDialog.closing}
          onClose={closeDismiss}
          busy={busy}
          title={t("MiningIncidentsPanel.dismissTitle")}
          description={t("MiningIncidentsPanel.dismissMessage", { vmid: dismissDialog.item.vmid })}
          actions={
            <>
              <button type="button" className={styles.btnSecondary} disabled={busy} onClick={closeDismiss}>
                {t("MiningIncidentsPanel.cancel")}
              </button>
              <button
                data-bombadil="danger"
                type="button"
                className={styles.btnPrimary}
                disabled={busy}
                onClick={handleDismiss}
              >
                {busy ? t("MiningIncidentsPanel.processing") : t("MiningIncidentsPanel.confirmDismiss")}
              </button>
            </>
          }
        >
          <label className={styles.checkLine}>
            <input
              type="checkbox"
              checked={dismissExempt}
              onChange={(e) => setDismissExempt(e.target.checked)}
            />
            {t("MiningIncidentsPanel.exemptLabel")}
          </label>
          <div className={styles.field}>
            <label htmlFor="mining-note">{t("MiningIncidentsPanel.noteLabel")}</label>
            <textarea
              id="mining-note"
              rows={3}
              placeholder={t("MiningIncidentsPanel.notePlaceholder")}
              value={dismissNote}
              onChange={(e) => setDismissNote(e.target.value)}
            />
          </div>
        </Modal>
      )}
    </div>
  );
}
