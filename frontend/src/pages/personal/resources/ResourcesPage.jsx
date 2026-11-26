import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { createColumnHelper, useTable } from "@tanstack/react-table";
import { useAuth } from "../../../contexts/AuthContext";
import styles from "./ResourcesPage.module.scss";
import MIcon from "../../../components/MIcon";
import DataTable, { DataTableCells } from "../../../components/DataTable/DataTable";
import { baseFeatures } from "../../../components/DataTable/features";
import { useTableFitContext } from "../../../components/DataTable/TableFitContext";
import useTableFit from "../../../hooks/useTableFit";
import MachineKindBadge from "../../../components/MachineKindBadge/MachineKindBadge";
import PowerMenu from "../../../components/PowerMenu/PowerMenu";
import TemplateFormDialog from "../../resource/templates/TemplateFormDialog";
import useDialogPresence from "../../../hooks/useDialogPresence";
import usePersistedGroupExpansion from "../../../hooks/usePersistedGroupExpansion";
import SharedEmptyState from "../../../components/EmptyState/EmptyState";
import ErrorState from "../../../components/ErrorState/ErrorState";
import LoadingState from "../../../components/LoadingState/LoadingState";
import { ResourcesService } from "../../../services/resources";
import { VmRequestsService } from "../../../services/vmRequests";
import { cancelVmRequest, pendingSignature } from "../../../services/pendingResources";
import { resourceKeys, useMyResourcesQuery, useResourceCacheUpdater } from "../../../queries/resources";
import { usePendingVmRequestsQuery, useVmRequestCacheUpdater } from "../../../queries/vmRequests";
import { useToast } from "../../../hooks/useToast";
import { useQueryView } from "../../../hooks/useQueryLoadState";
import TerminalDialog from "./TerminalDialog";
import VncDialog from "./VncDialog";
import { LIVE_STATUSES, isRowBackgroundClick, machineSpecLabel, resourceRowKey, statusAfterAction } from "./resourceRows";
import { isExpiryFromWindow } from "./detail/lifecycleFormat";
import QuotaUsageBar from "../../../components/QuotaUsageBar/QuotaUsageBar";
import PageHeader from "../../../components/PageHeader/PageHeader";
import { useConfirm } from "../../../components/ConfirmDialog/ConfirmProvider";
import { QuickPracticeService } from "../../../services/quickPractice";
import { buildEnvironmentGroups, groupedResourceKeys } from "../../../utils/environmentGroups";
import * as fmt from "../../../utils/formatDate";
import { canTeachUser } from "../../../utils/roles";
import { getDesktopClientDownloadUrl, getDesktopClientPlatform } from "../../../services/desktopClient";

/* ── Constants ── */
const STATUS_MAP = {
  scheduled:    { labelKey: "ResourcesPage.statusScheduled",     color: "info",    icon: "event"          },
  provisioning: { labelKey: "ResourcesPage.statusProvisioning",  color: "info",    icon: "settings"       },
  starting:     { labelKey: "ResourcesPage.statusStarting",      color: "info",    icon: "hourglass_top"  },
  partial_failed:{ labelKey: "ResourcesPage.statusPartialFailed",color: "danger",  icon: "error_outline"  },
  running:      { labelKey: "ResourcesPage.statusRunning",       color: "success", icon: "play_circle"    },
  stopping:     { labelKey: "ResourcesPage.statusStopping",      color: "muted",   icon: "power_settings_new" },
  reclaiming:   { labelKey: "ResourcesPage.statusReclaiming",    color: "danger",  icon: "delete_sweep"   },
  stopped:      { labelKey: "ResourcesPage.statusStopped",       color: "muted",   icon: "stop_circle"    },
  paused:       { labelKey: "ResourcesPage.statusPaused",        color: "muted",   icon: "pause_circle"   },
  deleting:     { labelKey: "ResourcesPage.statusDeleting",      color: "danger",  icon: "hourglass_empty"},
  failed:       { labelKey: "ResourcesPage.statusFailed",        color: "danger",  icon: "error_outline"  },
  /* 前端衍生：failed 佔位列已有 vmid ＝ 機器建好了、是之後開機失敗 */
  start_failed: { labelKey: "ResourcesPage.statusStartFailed",   color: "danger",  icon: "error_outline"  },
  deleted:      { labelKey: "ResourcesPage.statusDeleted",       color: "danger",  icon: "delete_forever" },
  unknown:      { labelKey: "ResourcesPage.statusUnknown",       color: "muted",   icon: "help_outline"   },
};

/* 群組進入這些狀態後，環境內每台機器的狀態都跟著群組顯示（見 EnvironmentMachineRow） */
const MACHINE_FOLLOWS_GROUP = new Set(["stopping", "reclaiming", "reclaimed"]);

const TYPE_MAP = {
  lxc:   { labelKey: "ResourcesPage.typeLxc", icon: "terminal" },
  qemu:  { labelKey: "ResourcesPage.typeQemu", icon: "computer" },
};

const detectedDesktopPlatform = getDesktopClientPlatform();
const desktopDownloads = (detectedDesktopPlatform ? [detectedDesktopPlatform] : ["windows", "macos"])
  .map((platform) => ({
    platform,
    label: platform === "macos" ? "macOS" : "Windows",
    url: getDesktopClientDownloadUrl(platform),
  }));

/* ── Helpers ── */
function formatDate(isoStr) {
  return fmt.formatDate(isoStr, null);
}

/* 到期日照字面顯示，小字附本地時間的實際截止時刻（後端以到期日 00:00 UTC 為界）。
   compact：收進狀態欄的那一行只放日期，截止時刻留在 title */
function ExpiryDateValue({ value, compact = false }) {
  const expiry = fmt.formatExpiryDate(value);
  if (!expiry) return null;
  if (compact) return <span title={expiry.title}>{expiry.date}</span>;
  return (
    <>
      {expiry.date}
      {expiry.cutoff && <div className={styles.envSub} title={expiry.title}>{expiry.cutoff}</div>}
    </>
  );
}

/* ── 窄版收欄（useTableFit） ──
   表格區不夠寬時依序收起節點、到期日、環境、來源、IP，名稱、狀態、操作永遠在；
   收起的內容改畫在名稱欄（節點、環境、來源）與狀態欄（IP、到期日）裡的小字行。
   欄寬只寫在這裡：英文的建立中狀態（Pending Review、Overdue (25 min)）要 150px，
   操作欄的 Console／Terminal 加 ⋮ 與右側留白要約 175px。
   收到只剩三欄合計 560px，1440 寬開著 AI 助手（表格區約 567px）也放得下；再窄才橫捲並固定首尾欄 */
const RESOURCE_FIT_COLUMNS = Object.freeze([
  { id: "name", width: 230 },
  { id: "kind", width: 190, fold: 4 },
  { id: "env", width: 160, fold: 3 },
  { id: "status", width: 150 },
  { id: "ip", width: 150, fold: 5 },
  { id: "expiry", width: 150, fold: 2 },
  { id: "node", width: 85, fold: 1 },
  { id: "actions", width: 180 },
]);

/* 收起的欄在主欄裡的一行小字；label 給「光看值看不出是什麼」的欄（到期日） */
function FoldedLine({ label, children }) {
  return (
    <div className={styles.foldedLine}>
      {label && <span className={styles.foldedLabel}>{label}</span>}
      {children}
    </div>
  );
}

/* 收起來源欄時，來源徽章接在名稱後面同一行（名稱放不下就截斷），不另起一行把名稱欄疊高；沒收起就只有名稱 */
function NameLine({ badge, children }) {
  if (!badge) return children;
  return <div className={styles.nameLine}>{children}{badge}</div>;
}

/* 名稱欄第二行：類型等原本的說明，後面接收起的節點 */
function joinMeta(...parts) {
  return parts.filter(Boolean).join(" · ");
}

/* ── Primitive sub-components ── */
function StatusBadge({ status }) {
  const { t } = useTranslation("personal");
  const s = STATUS_MAP[status] ?? { label: status, color: "muted", icon: "help_outline" };
  return (
    <span className={`${styles.badge} ${styles[`badge_${s.color}`]}`}>
      {s.labelKey ? t(s.labelKey) : s.label}
    </span>
  );
}

/* ── Creating placeholder row ── */

/* 開始時間剛過還沒開始建立是正常的：排程器每 60 秒才掃一次，立即模式的 start_at
   就是送出當下、要等 worker 接手才變 running。超過這段寬限才算超時 */
const OVERDUE_GRACE_MS = 5 * 60_000;

/** 依申請階段決定 placeholder 的狀態顯示（開通中 / 超時 / 失敗…） */
function getCreatingDisplay(req, t) {
  if (req.status === "pending") {
    return { label: t("CreatingRow.statusPendingReview"), color: "info", spin: true };
  }
  if (req.provisioning_status === "failed") {
    return { label: t("CreatingRow.statusProvisionFailed"), color: "danger", spin: false };
  }
  if (req.provisioning_status === "running") {
    return { label: t("CreatingRow.statusProvisioning"), color: "info", spin: true };
  }
  // approved 等待排程開機：start_at 已過寬限仍未開始建立 → 超時
  const lateMs = req.start_at ? Date.now() - new Date(req.start_at).getTime() : 0;
  if (lateMs > OVERDUE_GRACE_MS) {
    const overdueMin = Math.floor(lateMs / 60_000);
    const overdueLabel = overdueMin >= 60
      ? t("CreatingRow.overdueHoursLabel", { count: Math.floor(overdueMin / 60) })
      : t("CreatingRow.overdueMinutesLabel", { count: overdueMin });
    return { label: t("CreatingRow.statusOverdue", { label: overdueLabel }), color: "danger", spin: false };
  }
  return { label: t("CreatingRow.statusScheduling"), color: "info", spin: true };
}

function formatMemory(memoryMb) {
  if (memoryMb == null) return null;
  return memoryMb >= 1024 ? `${memoryMb / 1024} GB` : `${memoryMb} MB`;
}

/* 到期日欄跟機器開出來後一致（到期日 → 核准時段結束 → 無期限），不放開始時間 */
function CreatingExpiryValue({ request, compact = false }) {
  const { t } = useTranslation("personal");
  if (request.expiry_date) return <ExpiryDateValue value={request.expiry_date} compact={compact} />;
  if (request.end_at) return formatDate(request.end_at);
  return <span className={styles.cardPeriodUnlimited}>{t("ResourceRow.unlimited")}</span>;
}

function CreatingRow({ request, onCancelled }) {
  const { t } = useTranslation("personal");
  const toast = useToast();
  const confirm = useConfirm();
  const fit = useTableFitContext();
  const [cancelling, setCancelling]       = useState(false);

  const type    = TYPE_MAP[request.resource_type === "lxc" ? "lxc" : "qemu"];
  const display = getCreatingDisplay(request, t);
  // 能不能取消交給後端判斷（clone 真的在跑時會回明確錯誤）。前端不能只看
  // provisioning_status：後端重啟後 worker 沒了，狀態會永遠停在 running，
  // 在這裡擋掉的話那筆申請就再也取消不了。與「我的申請」頁的規則一致。

  async function handleCancel() {
    const ok = await confirm({
      title: t("CreatingRow.confirmCancelTitle"),
      message: t("CreatingRow.confirmCancelDesc", { hostname: request.hostname }),
      confirmText: t("CreatingRow.confirmCancelLabel"),
      danger: true,
    });
    if (!ok) return;
    setCancelling(true);
    try {
      await cancelVmRequest(request.id);
      toast.success(t("CreatingRow.cancelRequestSuccess", { hostname: request.hostname }));
      onCancelled();
    } catch (err) {
      toast.error(err?.message ?? t("CreatingRow.cancelRequestFailed"));
    } finally {
      setCancelling(false);
    }
  }

  const specs = [
    request.cores != null ? t("CreatingRow.coresLabel", { count: request.cores }) : null,
    formatMemory(request.memory),
  ].filter(Boolean).join(" / ");
  const node = request.assigned_node ?? request.desired_node ?? t("CreatingRow.notAssigned");

  /* 窄版收欄：來源、環境、IP 這三欄在建立中的列本來就沒內容，收起就不畫；節點、到期日收進名稱與狀態欄 */
  return <>
    <tr className={`${styles.tr} ${styles.pendingRow}`}>
      <td className={styles.td}>
        <div className={styles.nameCell}>
          <span className={styles.nameIcon}><MIcon name={type.icon} size={18} /></span>
          <div><strong>{request.hostname}</strong><small>{joinMeta(t(type.labelKey), specs || t("CreatingRow.specsPending"), fit.isFolded("node") && node)}</small></div>
        </div>
      </td>
      {!fit.isFolded("kind") && <td className={styles.td}><span className={styles.muted}>—</span></td>}
      {!fit.isFolded("env") && <td className={styles.td}>
        <div className={styles.envPrimary}>{t("CreatingRow.resourceRequestLabel")}</div>
        {/* 還在審核的申請還沒開始開通：旁邊的狀態是「審核中」，這裡不寫「開通中」 */}
        {request.status !== "pending" && <div className={styles.envSub}>{t("CreatingRow.creating")}</div>}
      </td>}
      <td className={styles.td}>
        <span className={`${styles.badge} ${styles[`badge_${display.color}`]} ${styles.creatingBadge}`}>
          <span className={styles.badgeIcon}><MIcon name={display.spin ? "autorenew" : "error_outline"} size={12} spin={display.spin} /></span>{display.label}
        </span>
        {fit.isFolded("expiry") && <FoldedLine label={t("ResourcesPage.colExpiry")}><CreatingExpiryValue request={request} compact /></FoldedLine>}
      </td>
      {!fit.isFolded("ip") && <td className={styles.td}><span className={styles.muted}>N/A</span></td>}
      {!fit.isFolded("expiry") && <td className={styles.td}><CreatingExpiryValue request={request} /></td>}
      {!fit.isFolded("node") && <td className={styles.td}>{node}</td>}
      <td className={styles.td}>
        <button type="button" className={styles.cancelBtn} disabled={cancelling} onClick={handleCancel}>
          <MIcon name="cancel" size={14} />{t("CreatingRow.cancelRequest")}
        </button>
      </td>
    </tr>
  </>;
}

/* ── Resource row ──
   機器列是 TanStack 的資料列：列元件擁有選單、操作中、主控台、轉範本的狀態並自己畫 <tr>，
   儲存格由 RESOURCE_COLUMNS 的 cell 畫，狀態與處理函式經 rowState 交給它們 */
function ResourceRow({ row, resource, onUpdated, onDeleted, onRefresh }) {
  const { t } = useTranslation("personal");
  const navigate = useNavigate();
  const { user } = useAuth();
  /* VMID 是系統內部編號，僅管理員／老師看得到 */
  const showVmid = canTeachUser(user);
  /* 轉成範本只給老師／管理員，且只有自己能管理的個人機器 */
  const canConvertTemplate = showVmid
    && resource.can_manage !== false
    && resource.allocation_scope !== "teaching_class"
    && !resource.is_placeholder
    && resource.vmid > 0;
  const confirm = useConfirm();
  const toast = useToast();
  const [actionLoading, setActionLoading] = useState(null);
  const [deleting, setDeleting]            = useState(false);
  const [menuOpen, setMenuOpen]            = useState(false);
  /* 選單先播 130ms 離場動畫再卸載 */
  const menu = useDialogPresence(menuOpen, 130);
  const [consoleOpen, setConsoleOpen]      = useState(false);
  const [convertOpen, setConvertOpen]      = useState(false);
  const convertDialog = useDialogPresence(convertOpen);
  const closeMenu = () => setMenuOpen(false);

  const isLxc   = resource.type === "lxc";
  const canControl = resource.can_control !== false && resource.vmid != null && resource.vmid > 0;
  const isLive  = canControl && LIVE_STATUSES.has(resource.status);

  async function handleControl(action) {
    setActionLoading(action);
    try {
      await ResourcesService[action](resource.vmid);
      onUpdated({ ...resource, status: statusAfterAction(action) });
    } catch (err) {
      toast.error(err?.message ?? t("ResourceRow.controlFailed"));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleDelete() {
    if (deleting) return;
    const ok = await confirm({
      title: t("ResourceRow.confirmDeleteTitle"),
      message: showVmid
        ? t("ResourceRow.confirmDeleteDescWithVmid", { name: resource.name, vmid: resource.vmid })
        : t("ResourceRow.confirmDeleteDescNoVmid", { name: resource.name }),
      confirmText: t("ResourceRow.confirmDeleteLabel"),
      danger: true,
    });
    if (!ok) return;
    setDeleting(true);
    try {
      await ResourcesService.delete(resource.vmid);
      toast.success(t("ResourceRow.deleteQueued"));
      onDeleted(resource.vmid);
    } catch (err) {
      toast.error(err?.message ?? t("ResourceRow.deleteFailed"));
    } finally {
      setDeleting(false);
    }
  }

  /* 失敗的佔位列（已核准但 Proxmox 上看不到機器）：可重試或刪除。
     沒有 vmid＝clone 失敗，重試會重新建立；有 vmid＝機器建好了、之後開機失敗，重試只會重新開機。
     操作完重新抓列表，不能用 vmid 比對更新（會連帶命中其他 vmid 為 null 的列） */
  const isFailedPlaceholder = Boolean(
    resource.is_placeholder && resource.status === "failed" && resource.request_id,
  );
  const isStartFailure = isFailedPlaceholder && Boolean(resource.vmid);
  const displayStatus = isStartFailure ? "start_failed" : resource.status;
  const [failedAction, setFailedAction] = useState(null);

  async function handleRebuild() {
    setFailedAction("rebuild");
    try {
      await VmRequestsService.retry(resource.request_id);
      toast.success(t(isStartFailure ? "ResourceRow.restartQueued" : "ResourceRow.rebuildQueued", { name: resource.name }));
      onRefresh();
    } catch (err) {
      toast.error(err?.message ?? t("Error.generic", { ns: "common" }));
    } finally {
      setFailedAction(null);
    }
  }

  async function handleDiscardFailed() {
    const ok = await confirm({
      title: t("ResourceRow.confirmDeleteTitle"),
      message: t("ResourceRow.confirmDeleteFailedDesc", { name: resource.name }),
      confirmText: t("ResourceRow.confirmDeleteLabel"),
      danger: true,
    });
    if (!ok) return;
    setFailedAction("delete");
    try {
      /* 沒有 vmid：取消這張申請即可；少數已分到 vmid 的走資源刪除（後端會清掉 Proxmox 上不存在的孤兒紀錄） */
      if (resource.vmid) await ResourcesService.delete(resource.vmid);
      else await cancelVmRequest(resource.request_id);
      toast.success(t("ResourceRow.failedDeleted", { name: resource.name }));
      onRefresh();
    } catch (err) {
      toast.error(err?.message ?? t("ResourceRow.deleteFailed"));
    } finally {
      setFailedAction(null);
    }
  }

  const canOpenDetail = resource.vmid > 0;
  /* 整列可點進詳情；列內按鈕／連結／選單的點擊不觸發導頁 */
  const openDetail = (event) => {
    if (!isRowBackgroundClick(event)) return;
    navigate(`/my-resources/${resource.vmid}`);
  };

  /* 儲存格要的狀態與處理函式；resource 一併放進來，列資料換了儲存格才會跟著重繪 */
  const rowState = {
    resource,
    showVmid,
    displayStatus,
    isLive,
    isLxc,
    isFailedPlaceholder,
    isStartFailure,
    actionLoading,
    failedAction,
    menuOpen: menu.open,
    menuClosing: menu.closing,
    onToggleMenu: () => setMenuOpen((value) => !value),
    onCloseMenu: closeMenu,
    onOpenConsole: () => setConsoleOpen(true),
    onControl: handleControl,
    onDeleteClick: resource.can_delete === false ? undefined : () => { closeMenu(); handleDelete(); },
    onConvertTemplate: canConvertTemplate ? () => { closeMenu(); setConvertOpen(true); } : undefined,
    onRebuild: handleRebuild,
    onDiscardClick: resource.can_delete === false ? undefined : () => { closeMenu(); handleDiscardFailed(); },
  };

  return <>
    <tr
      className={`${styles.tr} ${canOpenDetail ? styles.trClickable : ""}`}
      onClick={canOpenDetail ? openDetail : undefined}
      data-guide="resource-card"
    >
      <DataTableCells row={row} rowState={rowState} />
    </tr>
    {consoleOpen && isLxc && createPortal(<TerminalDialog resource={resource} onClose={() => setConsoleOpen(false)} />, document.body)}
    {consoleOpen && !isLxc && createPortal(<VncDialog resource={resource} onClose={() => setConsoleOpen(false)} />, document.body)}
    {convertDialog.open && createPortal(<TemplateFormDialog sourceResource={resource} closing={convertDialog.closing} onClose={() => setConvertOpen(false)} onSaved={() => { onDeleted(resource.vmid); navigate("/templates"); }} />, document.body)}
  </>;
}

/* 環境內機器的連線資訊：IP、對外網址、對外 port（IP 欄，窄版時收進狀態欄） */
function MachineIpValue({ machine }) {
  const { t } = useTranslation("personal");
  return <>
    <span className={styles.mono}>{machine.ip}</span>
    {machine.publicUrl && <a className={styles.publicUrlLink} href={machine.publicUrl} target="_blank" rel="noreferrer" title={machine.publicUrl}><MIcon name="open_in_new" size={13} /><span className={styles.publicUrlText}>{machine.publicUrl.replace(/^https?:\/\//, "")}</span></a>}
    {/* 對外 port：與課程頁同一份資料，SSH / 資料庫這類服務靠它連 */}
    {(machine.forwardEndpoints ?? []).map((endpoint) => <code key={`${endpoint.protocol}-${endpoint.external_port}`} className={styles.mono} title={t("EnvironmentMachineRow.forwardEndpointTitle", { port: endpoint.internal_port, protocol: endpoint.protocol })}> {endpoint.host ? `${endpoint.host}:${endpoint.external_port}` : t("EnvironmentMachineRow.forwardPortOnly", { port: endpoint.external_port })}</code>)}
  </>;
}

function EnvironmentMachineRow({ machine, groupStatus, onUpdated }) {
  const { t } = useTranslation("personal");
  const toast = useToast();
  const navigate = useNavigate();
  const fit = useTableFitContext();
  const type = TYPE_MAP[machine.type] ?? { label: machine.type, icon: "computer" };
  const [consoleOpen, setConsoleOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menu = useDialogPresence(menuOpen, 130);
  const menuBtnRef = useRef(null);
  const resource = machine.resource;
  const isLxc = machine.type === "lxc";
  const environmentReady = ["running", "active"].includes(groupStatus);
  /* 群組在收尾（準備回收／回收中／已回收）時，機器列跟著群組顯示：後端的機器狀態只看各自的建立進度，
     還沒建好或還在 clone 的機器會一直回 provisioning，畫面就變成群組「回收中」、底下卻寫「開通中」 */
  const groupTearingDown = MACHINE_FOLLOWS_GROUP.has(groupStatus);
  const displayStatus = groupTearingDown ? (groupStatus === "reclaimed" ? "deleted" : groupStatus) : machine.status;
  const canControl = Boolean(
    environmentReady && resource?.vmid && resource.can_control !== false,
  );
  const canOpen = canControl && resource.status === "running" && !resource.start_blocked_reason;
  const specLabel = machineSpecLabel(machine);

  // 與單機列同一組電源控制；環境內的機器差別只在不能單台刪除。
  async function handleControl(action) {
    if (!canControl || actionLoading) return;
    setActionLoading(action);
    try {
      await ResourcesService[action](resource.vmid);
      onUpdated({ ...resource, status: statusAfterAction(action) });
      toast.success(t("EnvironmentMachineRow.commandSent"));
    } catch (error) {
      toast.error(error?.message ?? t("EnvironmentMachineRow.controlFailed"));
    } finally {
      setActionLoading(null);
    }
  }

  const canOpenDetail = resource?.vmid > 0;
  /* 整列可點進詳情；列內按鈕／連結／選單的點擊不觸發導頁 */
  const openDetail = (event) => {
    if (!isRowBackgroundClick(event)) return;
    navigate(`/my-resources/${resource.vmid}`);
  };

  /* 窄版收欄：來源（佔位）與到期日（由環境管理）收起就不畫；節點、環境收進名稱欄，IP 收進狀態欄 */
  return <>
    <tr
      className={`${styles.tr} ${styles.environmentMachineRow} ${canOpenDetail ? styles.trClickable : ""}`}
      onClick={canOpenDetail ? openDetail : undefined}
    >
    <td className={styles.td}><div className={`${styles.nameCell} ${styles.environmentMachineName}`}><span className={styles.machineBranch}>└</span><div><strong>{machine.name}</strong><small>{machine.ownerName ? <><span className={styles.machineOwner}><MIcon name="person" size={11} />{machine.ownerName}</span> · </> : null}{joinMeta(machine.role, t(type.labelKey ?? type.label), specLabel, fit.isFolded("node") && machine.node)}</small>
      {/* 課程機器的名稱本來就取自 os 欄（老師取的機器名），跟名稱一樣就不再寫一行 */}
      {fit.isFolded("env") && machine.os && machine.os !== machine.name && <small>{machine.os}</small>}</div></div></td>
    {/* 「來源」欄佔位：群組標題列已標示來源，環境內機器不重複 */}
    {!fit.isFolded("kind") && <td className={styles.td}><span className={styles.muted}>—</span></td>}
    {!fit.isFolded("env") && <td className={styles.td}><div className={styles.envPrimary}>{machine.os}</div>{machine.resource ? <div className={styles.envSub}>{t("EnvironmentMachineRow.resourceConnected")}</div> : !groupTearingDown && <div className={styles.envSub}>{t("EnvironmentMachineRow.creating")}</div>}</td>}
    <td className={styles.td}><StatusBadge status={displayStatus} />
      {fit.isFolded("ip") && machine.ip && <FoldedLine><MachineIpValue machine={machine} /></FoldedLine>}</td>
    {!fit.isFolded("ip") && <td className={styles.td}><MachineIpValue machine={machine} /></td>}
    {!fit.isFolded("expiry") && <td className={styles.td}><span className={styles.muted}>{t("EnvironmentMachineRow.managedByEnvironment")}</span></td>}
    {!fit.isFolded("node") && <td className={styles.td}>{machine.node}</td>}
    <td className={styles.td}><div className={styles.rowActions}>
      <button type="button" data-bombadil="danger" className={styles.terminalBtn} disabled={!canOpen} title={canOpen ? (isLxc ? t("EnvironmentMachineRow.terminal") : t("EnvironmentMachineRow.console")) : resource?.status === "starting" ? t("ResourceRow.consoleBootingTitle") : t("EnvironmentMachineRow.notReadyTitle")} onClick={() => setConsoleOpen(true)} data-guide="resource-console"><MIcon name={isLxc ? "terminal" : "desktop_windows"} size={14} />{isLxc ? t("EnvironmentMachineRow.terminal") : t("EnvironmentMachineRow.console")}</button>
      {actionLoading && <MIcon name="hourglass_empty" size={16} spin />}
      {canControl && <div className={styles.menuWrap}>
        {menu.open && <PowerMenu resource={resource} actionLoading={actionLoading} onControl={handleControl} onClose={() => setMenuOpen(false)} anchorRef={menuBtnRef} closing={menu.closing} />}
        <button ref={menuBtnRef} type="button" className={`${styles.menuBtn} ${menu.open ? styles.menuBtnActive : ""}`} onClick={() => setMenuOpen((value) => !value)} title={t("ResourceRow.moreActions")} aria-label={t("ResourceRow.moreActions")} data-guide="resource-more-actions" aria-haspopup="menu" aria-expanded={menuOpen}><MIcon name="more_vert" size={18} /></button>
      </div>}
    </div></td>
    </tr>
    {consoleOpen && isLxc && createPortal(<TerminalDialog resource={resource} onClose={() => setConsoleOpen(false)} />, document.body)}
    {consoleOpen && !isLxc && createPortal(<VncDialog resource={resource} onClose={() => setConsoleOpen(false)} />, document.body)}
  </>;
}

function EnvironmentGroupRows({ group, onUpdated, onEnded }) {
  const { t } = useTranslation("personal");
  const confirm = useConfirm();
  /* 開合記在本機：上次收起的群組回到頁面仍是收起的 */
  const [expanded, toggleExpanded] = usePersistedGroupExpansion("my-resources", group.id);
  const [ending, setEnding] = useState(false);
  const [groupAction, setGroupAction] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menu = useDialogPresence(menuOpen, 130);
  const menuBtnRef = useRef(null);
  const toast = useToast();
  const fit = useTableFitContext();

  const canEnd = group.kind === "quick_practice" && !["reclaiming", "reclaimed"].includes(group.status);
  const controllableVmids = group.machines
    .filter((machine) => machine.resource?.vmid && machine.resource.can_control !== false)
    .map((machine) => machine.resource.vmid);
  const runningCount = group.machines.filter((machine) => machine.status === "running").length;
  /* 窄版收欄時這幾樣改畫在名稱欄（環境、來源、節點）與狀態欄（執行中台數、時限），兩處共用同一份 */
  const runningLabel = t("EnvironmentGroupRows.runningCount", { running: runningCount, total: group.machines.length });
  const envLabel = group.kind === "course" ? t("EnvironmentGroupRows.courseEnv") : t("EnvironmentGroupRows.quickPracticeEnv");
  const kindBadge = <MachineKindBadge kind={group.kind === "quick_practice" ? "quick_practice" : "teaching_class"} classRelation={group.classRelation} teachingClassName={group.title} />;

  async function runGroupAction(action) {
    if (!controllableVmids.length || groupAction) return;
    setGroupAction(action);
    try {
      const result = await ResourcesService.batchActionInChunks(controllableVmids, action);
      if (result.failed) {
        toast.error(t("EnvironmentGroupRows.groupCommandPartial", { succeeded: result.succeeded, failed: result.failed }));
      } else {
        toast.success(t("EnvironmentGroupRows.groupCommandSent"));
      }
      onEnded?.();
    } catch (error) {
      toast.error(error?.message ?? t("EnvironmentGroupRows.groupCommandFailed"));
    } finally {
      setGroupAction(null);
    }
  }

  async function endPractice() {
    const ok = await confirm({
      title: t("EnvironmentGroupRows.confirmEndTitle"),
      message: t("EnvironmentGroupRows.confirmEndDesc"),
      confirmText: t("EnvironmentGroupRows.endPractice"),
      danger: true,
    });
    if (!ok) return;
    setEnding(true);
    try {
      await QuickPracticeService.endSession(group.id);
      toast.success(t("EnvironmentGroupRows.endPracticeSuccess"));
      onEnded?.();
    } catch (error) {
      toast.error(error?.message ?? t("EnvironmentGroupRows.endPracticeFailed"));
    } finally {
      setEnding(false);
    }
  }

  return <>
    <tr
      className={`${styles.tr} ${styles.environmentGroupRow}`}
      onClick={(event) => {
        /* 整列都可以開合，但列內的按鈕（結束練習、名稱區的 toggle）各自處理自己的點擊 */
        if (!isRowBackgroundClick(event, "button")) return;
        toggleExpanded();
      }}
    >
      <td className={styles.td}>
        <div className={styles.nameCell}>
          <button type="button" className={styles.environmentToggle} aria-expanded={expanded} aria-label={t("EnvironmentGroupRows.toggleAria", { name: group.title })} onClick={toggleExpanded}><MIcon name={expanded ? "expand_more" : "chevron_right"} size={20} /></button>
          <div><NameLine badge={fit.isFolded("kind") && kindBadge}><strong>{group.title}</strong></NameLine><small>{joinMeta(t("EnvironmentGroupRows.machineCount", { count: group.machines.length }), fit.isFolded("env") && envLabel, fit.isFolded("node") && group.nodeLabel)}</small>
            {group.publicationPending && <small className={styles.publicationPending}><MIcon name="schedule" size={12} />{t("EnvironmentGroupRows.publicationPending")}</small>}</div>
        </div>
      </td>
      {!fit.isFolded("kind") && <td className={styles.td}>{kindBadge}</td>}
      {!fit.isFolded("env") && <td className={styles.td}><div className={styles.envPrimary}>{envLabel}</div><div className={styles.envSub}>{t("EnvironmentGroupRows.groupOverview")}</div></td>}
      <td className={styles.td}><StatusBadge status={group.status} />
        {fit.isFolded("ip") && <FoldedLine>{runningLabel}</FoldedLine>}
        {fit.isFolded("expiry") && group.timingLabel && <FoldedLine><strong className={styles.environmentTiming}>{group.timingLabel}</strong></FoldedLine>}</td>
      {!fit.isFolded("ip") && <td className={styles.td}><span className={styles.muted}>{runningLabel}</span></td>}
      {!fit.isFolded("expiry") && <td className={styles.td}><strong className={styles.environmentTiming}>{group.timingLabel}</strong></td>}
      {!fit.isFolded("node") && <td className={styles.td}>{group.nodeLabel}</td>}
      <td className={styles.td}><div className={styles.rowActions}>
        {(groupAction || ending) && <MIcon name="hourglass_empty" size={16} spin />}
        {(controllableVmids.length > 0 || canEnd) && <div className={styles.menuWrap}>
          {menu.open && <PowerMenu
            title={t("EnvironmentGroupRows.groupPowerTitle")}
            items={[
              ...(controllableVmids.length > 0 ? [
                { action: "start", label: t("EnvironmentGroupRows.startAll"), icon: "play_arrow", tone: "ok", disabled: runningCount === group.machines.length },
                { action: "shutdown", label: t("EnvironmentGroupRows.shutdownAll"), icon: "power_settings_new", disabled: runningCount === 0 },
              ] : []),
              ...(canEnd ? [{ action: "end", label: t("EnvironmentGroupRows.endPractice"), icon: "stop_circle", tone: "danger" }] : []),
            ]}
            actionLoading={groupAction || (ending ? "end" : null)}
            onControl={(action) => action === "end" ? endPractice() : runGroupAction(action)}
            onClose={() => setMenuOpen(false)}
            anchorRef={menuBtnRef}
            closing={menu.closing}
          />}
          <button ref={menuBtnRef} type="button" className={`${styles.menuBtn} ${menu.open ? styles.menuBtnActive : ""}`} onClick={() => setMenuOpen((value) => !value)} title={t("EnvironmentGroupRows.groupPowerTitle")} aria-label={t("EnvironmentGroupRows.groupPowerTitle")} aria-haspopup="menu" aria-expanded={menuOpen}><MIcon name="more_vert" size={18} /></button>
        </div>}
      </div></td>
    </tr>
    {expanded && group.machines.map((machine) => <EnvironmentMachineRow key={machine.id} machine={machine} groupStatus={group.status} onUpdated={onUpdated} />)}
  </>;
}

/* ── 機器列的儲存格（ResourceRow 的 rowState 帶狀態與處理函式進來） ── */
/* 窄版收欄時名稱欄多畫：節點接在第二行後面、環境另起一行、來源徽章放最下面 */
function ResourceNameCell({ rowState }) {
  const { t } = useTranslation("personal");
  const fit = useTableFitContext();
  const { resource, showVmid } = rowState;
  const type = TYPE_MAP[resource.type] ?? { label: resource.type, icon: "computer" };
  const typeLabel = `${t(type.labelKey)}${showVmid && resource.vmid > 0 ? t("ResourceRow.vmidSuffix", { vmid: resource.vmid }) : ""}`;
  return (
    <div className={styles.nameCell}>
      <span className={styles.nameIcon}><MIcon name={type.icon} size={18} /></span>
      <div>
        {/* 導覽的 performSelector 會點這裡；點擊沿用整列點擊的 openDetail */}
        <NameLine badge={fit.isFolded("kind") && <ResourceKindCell rowState={rowState} />}>
          <strong data-guide="resource-open-detail">{resource.name}</strong>
        </NameLine>
        <small>{joinMeta(typeLabel, fit.isFolded("node") && resource.node)}</small>
        {fit.isFolded("env") && <small>{joinMeta(resource.environment_type || "Custom", resource.os_info)}</small>}
      </div>
    </div>
  );
}

/* 來源：個人申請／共享／班級／快速練習／課程 */
function ResourceKindCell({ rowState }) {
  const { resource } = rowState;
  return (
    <MachineKindBadge
      kind={resource.machine_kind}
      classRelation={resource.class_relation}
      ownerName={resource.owner_name ?? resource.owner_email}
      teachingClassName={resource.teaching_class_name}
    />
  );
}

function ResourceEnvCell({ rowState }) {
  const { resource } = rowState;
  return <><div className={styles.envPrimary}>{resource.environment_type || "Custom"}</div><div className={styles.envSub}>{resource.os_info || "—"}</div></>;
}

/* 窄版收欄時狀態欄多畫：IP（連線用，沒有就不放）、到期日 */
function ResourceStatusCell({ rowState }) {
  const { t } = useTranslation("personal");
  const fit = useTableFitContext();
  const { resource } = rowState;
  const hasConnection = resource.ip_address || (resource.public_urls ?? []).length > 0;
  return <>
    <StatusBadge status={rowState.displayStatus} />
    {fit.isFolded("ip") && hasConnection && <FoldedLine><ResourceIpCell rowState={rowState} /></FoldedLine>}
    {fit.isFolded("expiry") && <FoldedLine label={t("ResourcesPage.colExpiry")}><ResourceExpiryCell rowState={rowState} compact /></FoldedLine>}
  </>;
}

function ResourceIpCell({ rowState }) {
  const { resource } = rowState;
  return <>
    <span className={styles.mono}>{resource.ip_address ?? "N/A"}</span>
    {/* 反向代理發布的對外網址：和環境機器列一樣直接可點，不必進詳情頁 */}
    {(resource.public_urls ?? []).length > 0 && (
      <div className={styles.publicUrlList}>
        {resource.public_urls.map((url) => (
          <a key={url} className={styles.publicUrlLink} href={url} target="_blank" rel="noreferrer" title={url}>
            <MIcon name="open_in_new" size={13} /><span className={styles.publicUrlText}>{url.replace(/^https?:\/\//, "")}</span>
          </a>
        ))}
      </div>
    )}
  </>;
}

/* 期限：有到期日照舊；沒有到期日但有申請的使用時段，顯示時段結束日（已結束標紅），不再誤寫「無期限」 */
function ResourceExpiryCell({ rowState, compact = false }) {
  const { t } = useTranslation("personal");
  const { resource } = rowState;
  /* 到期日與核准時段取較早者：時段先結束就顯示時段迄日 */
  return isExpiryFromWindow(resource) ? (
      <span className={resource.start_blocked_reason === "window_ended" ? styles.periodEnded : undefined}>
        {formatDate(resource.window_end_at)}
        {resource.start_blocked_reason === "window_ended" && <small>{t("ResourceRow.windowEnded")}</small>}
      </span>
    ) : resource.expiry_date ? <ExpiryDateValue value={resource.expiry_date} compact={compact} />
    : <span className={styles.cardPeriodUnlimited}>{t("ResourceRow.unlimited")}</span>;
}

function ResourceNodeCell({ rowState }) {
  return rowState.resource.node ?? "—";
}

/* 選單開關與操作中狀態在 ResourceRow；⋮ 鈕與選單都畫在這一格，錨點 ref 就放這裡 */
function ResourceActionsCell({ rowState }) {
  const { t } = useTranslation("personal");
  const menuBtnRef = useRef(null);
  const {
    resource, isLive, isLxc, isFailedPlaceholder, isStartFailure, actionLoading, failedAction,
    menuOpen, menuClosing, onToggleMenu, onCloseMenu, onOpenConsole, onControl, onDeleteClick,
    onConvertTemplate, onRebuild, onDiscardClick,
  } = rowState;
  return isLive ? <div className={styles.rowActions}>
    <button type="button" data-bombadil="danger" className={styles.terminalBtn} disabled={resource.status !== "running" || Boolean(resource.start_blocked_reason)} title={resource.start_blocked_reason === "window_ended" ? t("ResourceRow.windowEnded") : resource.status === "starting" ? t("ResourceRow.consoleBootingTitle") : undefined} onClick={onOpenConsole} data-guide="resource-console">
      <MIcon name={isLxc ? "terminal" : "desktop_windows"} size={14} />{isLxc ? t("ResourceRow.terminal") : t("ResourceRow.console")}
    </button>
    {actionLoading && <MIcon name="hourglass_empty" size={16} spin />}
    <div className={styles.menuWrap}>
      {menuOpen && <PowerMenu resource={resource} actionLoading={actionLoading} onControl={onControl} onDeleteClick={onDeleteClick} onConvertTemplate={onConvertTemplate} onClose={onCloseMenu} anchorRef={menuBtnRef} closing={menuClosing} />}
      <button ref={menuBtnRef} type="button" className={`${styles.menuBtn} ${menuOpen ? styles.menuBtnActive : ""}`} onClick={onToggleMenu} title={t("ResourceRow.moreActions")} aria-label={t("ResourceRow.moreActions")} data-guide="resource-more-actions" aria-haspopup="menu" aria-expanded={menuOpen}><MIcon name="more_vert" size={18} /></button>
    </div>
  </div> : isFailedPlaceholder ? <div className={styles.rowActions}>
    {/* 動作欄只有 160px，兩顆文字按鈕會擠出欄外：收進與一般列同位置的 ⋮ 選單 */}
    {failedAction && <MIcon name="hourglass_empty" size={16} spin />}
    <div className={styles.menuWrap}>
      {menuOpen && <PowerMenu
        title={t("ResourceRow.moreActions")}
        items={[{
          action: "retry",
          label: t(isStartFailure ? "ResourceRow.restart" : "ResourceRow.rebuild"),
          icon: isStartFailure ? "power_settings_new" : "autorenew",
          tone: "ok",
        }]}
        actionLoading={failedAction}
        onControl={onRebuild}
        onDeleteClick={onDiscardClick}
        onClose={onCloseMenu}
        anchorRef={menuBtnRef}
        closing={menuClosing}
      />}
      <button ref={menuBtnRef} type="button" className={`${styles.menuBtn} ${menuOpen ? styles.menuBtnActive : ""}`} disabled={failedAction !== null} onClick={onToggleMenu} title={t("ResourceRow.moreActions")} aria-label={t("ResourceRow.moreActions")} aria-haspopup="menu" aria-expanded={menuOpen}><MIcon name="more_vert" size={18} /></button>
    </div>
  </div> : <span className={styles.deletedNote}>{STATUS_MAP[resource.status]?.labelKey ? t(STATUS_MAP[resource.status].labelKey) : resource.status}</span>;
}

/* ── 導覽示範列的儲存格（示範資料是常數，只有 ⋮ 選單的開關是列狀態） ── */
function GuideDemoNameCell({ row }) {
  const { t } = useTranslation("personal");
  const navigate = useNavigate();
  const fit = useTableFitContext();
  const demo = row.original;
  return (
    <div className={styles.nameCell}>
      <span className={styles.nameIcon}><MIcon name="terminal" size={18} /></span>
      <div>
        <button type="button" className={styles.nameLink} onClick={() => navigate("/my-resources/demo")} data-guide="resource-open-detail">{demo.name}</button>
        <small>{joinMeta(t("ResourcesPage.guideDemoMachineType"), fit.isFolded("node") && demo.node)}</small>
        {fit.isFolded("env") && <small>{joinMeta(demo.os, demo.stack)}</small>}
      </div>
    </div>
  );
}

function GuideDemoEnvCell({ row }) {
  const demo = row.original;
  return <><div className={styles.envPrimary}>{demo.os}</div><div className={styles.envSub}>{demo.stack}</div></>;
}

function GuideDemoStatusCell({ row }) {
  const { t } = useTranslation("personal");
  const fit = useTableFitContext();
  const demo = row.original;
  return <>
    <StatusBadge status="running" />
    {fit.isFolded("ip") && <FoldedLine><span className={styles.mono}>{demo.ip}</span></FoldedLine>}
    {fit.isFolded("expiry") && <FoldedLine label={t("ResourcesPage.colExpiry")}>{demo.expiry}</FoldedLine>}
  </>;
}

function GuideDemoActionsCell({ rowState }) {
  const { t } = useTranslation("personal");
  const { menuOpen, onToggleMenu } = rowState;
  return (
    <div className={styles.rowActions}>
      <button type="button" className={styles.terminalBtn} data-guide="resource-console">
        <MIcon name="terminal" size={14} />{t("ResourceRow.terminal")}
      </button>
      <div className={styles.menuWrap}>
        <button type="button" className={`${styles.menuBtn} ${menuOpen ? styles.menuBtnActive : ""}`} onClick={onToggleMenu} data-guide="resource-more-actions" title={t("ResourceRow.moreActions")} aria-label={t("ResourceRow.moreActions")}>
          <MIcon name="more_vert" size={18} />
        </button>
        {menuOpen && (
          <div className={styles.guideDemoMenu} data-guide="resource-power-menu">
            <span>{t("ResourcesPage.guideDemoPowerMenu")}</span>
            <button type="button"><MIcon name="replay" size={14} />{t("ResourcesPage.guideDemoRestart")}</button>
            <button type="button"><MIcon name="power_settings_new" size={14} />{t("ResourcesPage.guideDemoShutdown")}</button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── 欄位定義 ──
   導覽示範表與真正的資源表共用同一組欄位（id、標題；欄寬與收合順序在 RESOURCE_FIT_COLUMNS），
   兩張表的欄寬與標題才不會各改各的；兩張表只有儲存格各畫各的（示範列是靜態內容）。
   放模組層級：cell／header 會被當成元件掛載，render 裡新建會整格重掛（選單、焦點都會掉） */
const columnHelper = createColumnHelper();

const RESOURCE_COLUMN_SPECS = [
  { id: "name", labelKey: "ResourcesPage.colName" },
  { id: "kind", labelKey: "ResourcesPage.colKind" },
  { id: "env", labelKey: "ResourcesPage.colEnvironment" },
  { id: "status", labelKey: "ResourcesPage.colStatus" },
  { id: "ip", labelKey: "ResourcesPage.colIp" },
  { id: "expiry", labelKey: "ResourcesPage.colExpiry" },
  { id: "node", labelKey: "ResourcesPage.colNode" },
  { id: "actions", labelKey: "ResourcesPage.colActions" },
];

function ResourceHeader({ column }) {
  const { t } = useTranslation("personal");
  return t(column.columnDef.meta.labelKey);
}

function buildResourceColumns(cells) {
  return columnHelper.columns(RESOURCE_COLUMN_SPECS.map(({ id, labelKey }) => columnHelper.display({
    id,
    header: ResourceHeader,
    cell: cells[id],
    meta: { labelKey, thClassName: styles.th, tdClassName: styles.td },
  })));
}

const RESOURCE_COLUMNS = buildResourceColumns({
  name: ResourceNameCell,
  kind: ResourceKindCell,
  env: ResourceEnvCell,
  status: ResourceStatusCell,
  ip: ResourceIpCell,
  expiry: ResourceExpiryCell,
  node: ResourceNodeCell,
  actions: ResourceActionsCell,
});

const GUIDE_DEMO_COLUMNS = buildResourceColumns({
  name: GuideDemoNameCell,
  kind: () => <span className={styles.muted}>—</span>,
  env: GuideDemoEnvCell,
  status: GuideDemoStatusCell,
  ip: ({ row }) => <span className={styles.mono}>{row.original.ip}</span>,
  expiry: ({ row }) => row.original.expiry,
  node: ({ row }) => row.original.node,
  actions: GuideDemoActionsCell,
});

const GUIDE_DEMO_ROWS = Object.freeze([
  { name: "demo-web-01", os: "Ubuntu 24.04", stack: "Docker / Nginx", ip: "10.20.0.24", expiry: "2026/12/31", node: "pve-01" },
]);

const getResourceRowId = (resource, index) => resourceRowKey(resource, index);
const getGuideDemoRowId = (demo) => demo.name;

/* ── Empty / Error states ── */
function EmptyState() {
  const { t } = useTranslation("personal");
  const navigate = useNavigate();
  return <SharedEmptyState icon="dns" title={t("ResourcesPage.emptyTitle")}
    action={<button type="button" className={styles.btnPrimary} onClick={() => navigate("/my-requests", { state: { create: true } })} data-guide="resource-request"><MIcon name="add" size={16} />{t("ResourcesPage.requestResource")}</button>} />;
}

/* 導覽示範列：示範資料是常數、列物件不會變，⋮ 選單的開關要經 rowState 交給儲存格才會重繪 */
function ResourceGuideDemoRow({ row }) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <tr className={`${styles.tr} ${styles.guideDemoRow}`} data-guide="resource-card">
      <DataTableCells row={row} rowState={{ menuOpen, onToggleMenu: () => setMenuOpen((value) => !value) }} />
    </tr>
  );
}

/* 導覽示範表：沒有機器可看時給導覽指的一列，欄位與窄版收欄都跟真正的資源表同一組 */
function ResourceGuideDemoTable() {
  const fit = useTableFit(RESOURCE_FIT_COLUMNS);
  const table = useTable({
    features: baseFeatures,
    columns: GUIDE_DEMO_COLUMNS,
    data: GUIDE_DEMO_ROWS,
    getRowId: getGuideDemoRowId,
  });
  return (
    <div ref={fit.ref} className={styles.tableWrap}>
      <DataTable
        table={table}
        className={styles.table}
        fit={fit}
        renderRow={(row) => <ResourceGuideDemoRow key={row.id} row={row} />}
      />
    </div>
  );
}

/* ── Page ── */
const EMPTY = Object.freeze([]);

export default function ResourcesPage() {
  const { t } = useTranslation("personal");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [guideDemo, setGuideDemo] = useState(false);

  /* 清單與建立中的申請都走 TanStack Query：背景 30 秒刷新（開機中 5 秒、有建立中申請 5 秒）、
     分頁隱藏時暫停、切回來超過 5 秒才重抓，換頁回來先顯示快取再背景更新 */
  const resourcesQuery = useMyResourcesQuery();
  const pendingQuery = usePendingVmRequestsQuery();
  const resourceCache = useResourceCacheUpdater();
  const requestCache = useVmRequestCacheUpdater();
  const resources = resourcesQuery.data?.resources ?? EMPTY;
  const quickSessions = resourcesQuery.data?.sessions ?? EMPTY;
  const pending = pendingQuery.data ?? EMPTY;
  /* 只有「還沒有任何資料」時才顯示 skeleton／錯誤畫面；背景刷新失敗沿用上一筆資料（原本就是靜默）。
     錯誤畫面在背景重試期間不閃回 skeleton，按重試才回到 skeleton，背景刷新成功也會自動離開錯誤畫面 */
  const { loading, error, retry: retryResources } = useQueryView(resourcesQuery);

  /** 建立中的申請階段變化（審核通過、開通完成／失敗、取消）時靜默刷新資源列表 */
  const pendingSigRef = useRef(null);
  useEffect(() => {
    if (pendingQuery.data === undefined) return;
    const sig = pendingSignature(pendingQuery.data);
    if (pendingSigRef.current !== null && sig !== pendingSigRef.current) {
      queryClient.invalidateQueries({ queryKey: resourceKeys.mine });
    }
    pendingSigRef.current = sig;
  }, [pendingQuery.data, queryClient]);

  useEffect(() => {
    const handleGuideState = (event) => {
      setGuideDemo(Boolean(event.detail?.open && event.detail?.id === "my-resources"));
    };
    window.addEventListener("skylab:user-guide-state", handleGuideState);
    return () => window.removeEventListener("skylab:user-guide-state", handleGuideState);
  }, []);

  function handleUpdated(updated) {
    resourceCache.update(updated);
  }

  function handleDeleted(vmid) {
    resourceCache.remove(vmid);
  }

  function refreshResources() {
    resourceCache.invalidate();
  }

  function refreshPending() {
    requestCache.invalidate();
  }

  /* 建立失敗的列重建／刪除後：兩份清單都可能變（重建會回到建立中），直接重抓 */
  function refreshAfterFailedAction() {
    refreshResources();
    refreshPending();
  }

  // 建立中申請會同時出現在 pending 與資源 API；先移除 placeholder，避免重複列。
  const pendingRequestIds = new Set(pending.map((request) => String(request.id)));
  const resourcesForDisplay = resources.filter((resource) => !(
    resource.is_placeholder
    && resource.request_id != null
    && pendingRequestIds.has(String(resource.request_id))
  ));
  const environmentGroups = buildEnvironmentGroups(resourcesForDisplay, quickSessions);
  const grouped = groupedResourceKeys(environmentGroups);
  const visibleResources = resourcesForDisplay.filter((resource) => (
    !grouped.vmids.has(resource.vmid)
    && !grouped.requestIds.has(String(resource.request_id))
  ));
  const visiblePending = pending.filter((request) => !grouped.requestIds.has(String(request.id)));
  const resourceListEmpty = visibleResources.length === 0 && visiblePending.length === 0 && environmentGroups.length === 0;
  /* 機器列是表格的資料列；環境群組列與建立中佔位列不是同一份資料，照原順序排在 tbody 最前面 */
  const resourceTable = useTable({
    features: baseFeatures,
    columns: RESOURCE_COLUMNS,
    data: visibleResources,
    getRowId: getResourceRowId,
  });
  const resourceFit = useTableFit(RESOURCE_FIT_COLUMNS);
  /* 頁首的「申請資源」等清單有東西才出現：空狀態那顆就是唯一入口，不要上下兩顆一樣的鈕。
     導覽示範列顯示時照常放（導覽要指它）；載入中也先不放，免得空清單的人看到它閃一下 */
  const showEmptyState = !error && !loading && resourceListEmpty && !guideDemo;
  const showHeaderRequest = !loading && !showEmptyState;

  return (
    <div className={styles.page}>
      <PageHeader title={t("ResourcesPage.title")}>
        <div className={styles.pageActions}>
          {desktopDownloads.map((download) => (
            <a
              key={download.platform}
              className={styles.btnSecondary}
              data-bombadil="danger"
              href={download.url}
            >
              <MIcon name="download" size={16} />
              {t("ResourcesPage.downloadDesktopClient")} ({download.label})
            </a>
          ))}
          {showHeaderRequest && (
            <button
              type="button"
              className={styles.btnPrimary}
              onClick={() => navigate("/my-requests", { state: { create: true } })}
              data-guide="resource-request"
            >
              <MIcon name="add" size={16} />
              {t("ResourcesPage.requestResource")}
            </button>
          )}
        </div>
      </PageHeader>

      {/* 我的配額用量（模組 E）。清單整頁出錯時不放：兩支 API 通常一起失敗，下方已有錯誤畫面＋重試，
          配額卡再寫一次同樣的錯誤只是重複；只有配額抓不到時，卡片照常顯示自己的佔位 */}
      {!error && <QuotaUsageBar />}

      <div className={styles.content}>
        {error ? (
          <ErrorState onRetry={retryResources} />
        ) : loading ? (
          <LoadingState fullPage />
        ) : resourceListEmpty ? (
          guideDemo ? (
            <div className={styles.guideDemo}>
              <div className={styles.guideDemoNotice}>
                <MIcon name="visibility" size={17} />
                <span><strong>{t("ResourcesPage.guideDemoTitle")}</strong>{t("ResourcesPage.guideDemoDesc")}</span>
              </div>
              <ResourceGuideDemoTable />
            </div>
          ) : <EmptyState />
        ) : (
          <div ref={resourceFit.ref} className={styles.tableWrap}>
            <DataTable
              table={resourceTable}
              className={styles.table}
              fit={resourceFit}
              renderRow={(row) => (
                <ResourceRow
                  key={row.id}
                  row={row}
                  resource={row.original}
                  onUpdated={handleUpdated}
                  onDeleted={handleDeleted}
                  onRefresh={refreshAfterFailedAction}
                />
              )}
            >
              {environmentGroups.map((group) => <EnvironmentGroupRows key={group.id} group={group} onUpdated={handleUpdated} onEnded={refreshResources} />)}
              {visiblePending.map((req) => <CreatingRow key={`creating:${req.id}`} request={req} onCancelled={refreshPending} />)}
            </DataTable>
          </div>
        )}
      </div>

    </div>
  );
}
