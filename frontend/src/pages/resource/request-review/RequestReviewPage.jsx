import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./RequestReviewPage.module.scss";
import MIcon from "../../../components/MIcon";
import SharedEmptyState from "../../../components/EmptyState/EmptyState";
import { useToast } from "../../../hooks/useToast";
import useAutoRefresh from "../../../hooks/useAutoRefresh";
import LoadingState from "../../../components/LoadingState/LoadingState";
import { DeletionRequestsService } from "../../../services/deletionRequests";
import { SpecChangeRequestsService } from "../../../services/specChangeRequests";
import { VmRequestsService } from "../../../services/vmRequests";
import { CONSUMED_REQUEST_MARKERS } from "../../../services/pendingResources";
import PageHeader from "../../../components/PageHeader/PageHeader";

function useTabs() {
  const { t } = useTranslation("resource");
  return useMemo(() => [
    { key: "pending", label: t("RequestReviewPage.tabPending"), icon: "pending_actions" },
    { key: "approved", label: t("RequestReviewPage.tabApproved"), icon: "task_alt" },
    { key: "rejected", label: t("RequestReviewPage.tabRejected"), icon: "block" },
    { key: "expired", label: t("RequestReviewPage.tabExpired"), icon: "hourglass_empty" },
    { key: "all", label: t("RequestReviewPage.tabAll"), icon: "view_list" },
  ], [t]);
}

function useStatusMeta() {
  const { t } = useTranslation("resource");
  return useMemo(() => ({
    pending: { label: t("RequestReviewPage.statusPending"), tone: "info" },
    approved: { label: t("RequestReviewPage.statusApproved"), tone: "success" },
    rejected: { label: t("RequestReviewPage.statusRejected"), tone: "danger" },
    cancelled: { label: t("RequestReviewPage.statusCancelled"), tone: "muted" },
    expired: { label: t("RequestReviewPage.statusExpired"), tone: "muted" },
    running: { label: t("RequestReviewPage.statusRunning"), tone: "info" },
    completed: { label: t("RequestReviewPage.statusCompleted"), tone: "muted" },
    failed: { label: t("RequestReviewPage.statusFailed"), tone: "danger" },
    /* 規格調整：核准後由申請人自己按「套用」，所以 approved 再依套用進度細分 */
    approved_awaiting_apply: { label: t("RequestReviewPage.statusAwaitingApply"), tone: "success" },
    applying: { label: t("RequestReviewPage.statusApplying"), tone: "info" },
    applied: { label: t("RequestReviewPage.statusApplied"), tone: "success" },
    apply_failed: { label: t("RequestReviewPage.statusApplyFailed"), tone: "danger" },
  }), [t]);
}

function specReviewStatus(request) {
  if (request.status !== "approved") return request.status;
  switch (request.apply_status) {
    case "applied":
      return "applied";
    case "applying":
      return "applying";
    case "failed":
    case "interrupted":
      return "apply_failed";
    default:
      return "approved_awaiting_apply";
  }
}


function formatDateTime(value, t) {
  if (!value) return t("RequestReviewPage.notSet");
  return new Date(value).toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function formatRange(startAt, endAt, t) {
  if (!startAt && !endAt) return t("RequestReviewPage.notSet");
  if (!endAt) return t("RequestReviewPage.startingFrom", { time: formatDateTime(startAt, t) });
  return `${formatDateTime(startAt, t)} - ${formatDateTime(endAt, t)}`;
}

function vmSpecLabel(request, t) {
  if (!request) return "-";
  const disk =
    request.resource_type === "vm"
      ? t("RequestReviewPage.diskLabel", { size: request.disk_size ?? 0 })
      : t("RequestReviewPage.rootfsLabel", { size: request.rootfs_size ?? 0 });
  return t("RequestReviewPage.specVm", {
    cores: request.cores,
    memory: (request.memory / 1024).toFixed(1),
    disk,
  });
}

function specChangeLabel(request, t) {
  const parts = [
    request.requested_cpu
      ? t("RequestReviewPage.specChangeCpu", { from: request.current_cpu ?? "-", to: request.requested_cpu })
      : "",
    request.requested_memory
      ? t("RequestReviewPage.specChangeRam", { from: request.current_memory ?? "-", to: request.requested_memory })
      : "",
    request.requested_disk
      ? t("RequestReviewPage.specChangeDisk", { from: request.current_disk ?? "-", to: request.requested_disk })
      : "",
  ].filter(Boolean);
  return parts.join(" / ") || request.change_type || "-";
}

/* AI API 金鑰申請有專屬的 /ai-api-review 頁，這裡不重複列出 */
function sourceLabel(source, t) {
  if (source === "vm") return t("RequestReviewPage.sourceCreate");
  if (source === "spec") return t("RequestReviewPage.sourceSpec");
  return t("RequestReviewPage.sourceDeletion");
}

function sourceIcon(item) {
  if (item.source === "spec") return "tune";
  if (item.source === "deletion") return "delete_outline";
  return item.raw?.resource_type === "vm" ? "computer" : "terminal";
}

/* 審核頁只反映申請本身的狀態；機器後來被刪掉是資源的事，不在這裡呈現 */
function normalizeVmRequest(request, t) {
  const reviewStatus = ["pending", "approved", "rejected", "expired"].includes(request.status)
    ? request.status
    : "other";

  return {
    id: `vm:${request.id}`,
    rawId: request.id,
    source: "vm",
    raw: request,
    reviewStatus,
    status: request.status,
    title: request.hostname || request.name || t("RequestReviewPage.unnamedRequest"),
    user: request.user_full_name || request.user_email || t("RequestReviewPage.unknownUser"),
    userSubtext: request.user_email || request.user_id || "-",
    timeText: formatRange(request.start_at, request.end_at, t),
    specText: vmSpecLabel(request, t),
    reason: request.reason,
    paramLabel: t("RequestReviewPage.paramLabelOs"),
    paramText:
      request.os_info ||
      request.ostemplate ||
      (request.template_id ? `Template #${request.template_id}` : t("RequestReviewPage.notSet")),
    gpuText: request.gpu_mapping_id || t("RequestReviewPage.gpuNotRequested"),
    nodeText: request.assigned_node || request.desired_node || t("RequestReviewPage.nodeNotEvaluated"),
    createdAt: request.created_at,
    reviewedAt: request.reviewed_at,
  };
}

function normalizeSpecRequest(request, t) {
  return {
    id: `spec:${request.id}`,
    rawId: request.id,
    source: "spec",
    raw: request,
    reviewStatus: request.status,
    status: specReviewStatus(request),
    title: request.resource_name
      ? t("RequestReviewPage.specChangeTitleNamed", { name: request.resource_name, vmid: request.vmid })
      : t("RequestReviewPage.specChangeTitle", { vmid: request.vmid }),
    user: request.user_full_name || request.user_email || t("RequestReviewPage.unknownUser"),
    userSubtext: request.user_email || request.user_id || "-",
    timeText: formatDateTime(request.created_at, t),
    specText: specChangeLabel(request, t),
    reason: request.reason,
    paramLabel: t("RequestReviewPage.paramLabelChangeType"),
    paramText: request.change_type || "-",
    gpuText: "-",
    nodeText: `VMID ${request.vmid}`,
    createdAt: request.created_at,
    reviewedAt: request.reviewed_at,
  };
}

function normalizeDeletionRequest(request, t) {
  return {
    id: `deletion:${request.id}`,
    rawId: request.id,
    source: "deletion",
    raw: request,
    reviewStatus: "other",
    status: request.status,
    title: `${request.name || "Resource"} / VMID ${request.vmid}`,
    user: request.user_full_name || request.user_email || t("RequestReviewPage.unknownUser"),
    userSubtext: request.user_email || request.user_id || "-",
    timeText: formatDateTime(request.created_at, t),
    specText: `${request.resource_type || "resource"} / ${request.node || "unknown node"}`,
    reason: request.error_message || t("RequestReviewPage.deletionReasonDefault"),
    paramLabel: t("RequestReviewPage.paramLabelDeleteParams"),
    paramText: `purge=${request.purge ? "yes" : "no"} / force=${request.force ? "yes" : "no"}`,
    gpuText: "-",
    nodeText: request.node || "unknown node",
    createdAt: request.created_at,
    reviewedAt: request.completed_at,
  };
}

function StatusBadge({ status }) {
  const statusMeta = useStatusMeta();
  const meta = statusMeta[status] ?? { label: status, tone: "muted" };
  return (
    <span className={`${styles.badge} ${styles[`badge_${meta.tone}`]}`}>
      {meta.label}
    </span>
  );
}

function EmptyState() {
  const { t } = useTranslation("resource");
  return <SharedEmptyState icon="assignment_turned_in" title={t("RequestReviewPage.emptyTitle")} />;
}

function InfoRow({ label, value }) {
  return (
    <div className={styles.infoRow}>
      <span>{label}</span>
      <strong>{value || "-"}</strong>
    </div>
  );
}

function filterByTab(items, tab) {
  if (tab === "all") return items;
  return items.filter((item) => item.reviewStatus === tab);
}

export default function RequestReviewPage() {
  const { t } = useTranslation("resource");
  const tabs = useTabs();
  const toast = useToast();
  const [activeTab, setActiveTab] = useState("pending");
  const [requests, setRequests] = useState([]);
  const [allRequests, setAllRequests] = useState([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [context, setContext] = useState(null);
  const [contextLoading, setContextLoading] = useState(false);
  const [contextError, setContextError] = useState("");
  const [comment, setComment] = useState("");
  const [reviewing, setReviewing] = useState(false);

  const selected = useMemo(
    () => requests.find((request) => request.id === selectedId) ?? requests[0] ?? null,
    [requests, selectedId],
  );

  /** silent = true 時不觸發 loading 與錯誤提示，供背景自動刷新使用 */
  const fetchRequests = useCallback(async (tab = activeTab, silent = false) => {
    if (!silent) {
      setLoading(true);
      setError("");
    }
    try {
      const [vmRes, specRes, deletionRes] = await Promise.all([
        VmRequestsService.listAll(undefined),
        SpecChangeRequestsService.listAll(),
        DeletionRequestsService.listAll(),
      ]);
      const items = [
        ...(vmRes.data ?? []).map((r) => normalizeVmRequest(r, t)),
        ...(specRes.data ?? []).map((r) => normalizeSpecRequest(r, t)),
        ...(deletionRes.data ?? []).map((r) => normalizeDeletionRequest(r, t)),
      ].sort(
        (a, b) =>
          new Date(b.createdAt || 0).getTime() - new Date(a.createdAt || 0).getTime(),
      );
      const filtered = filterByTab(items, tab);
      setAllRequests(items);
      setRequests(filtered);
      setSelectedId((current) =>
        current && filtered.some((item) => item.id === current)
          ? current
          : filtered[0]?.id ?? null,
      );
    } catch (err) {
      if (!silent) {
        setRequests([]);
        setAllRequests([]);
        setSelectedId(null);
        setError(err?.message ?? t("RequestReviewPage.loadRequestsFailed"));
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, [activeTab, t]);

  useEffect(() => {
    fetchRequests(activeTab);
    setComment("");
  }, [activeTab, fetchRequests]);

  useAutoRefresh(() => fetchRequests(activeTab, true));

  useEffect(() => {
    if (
      !selected?.rawId ||
      selected.source !== "vm" ||
      selected.reviewStatus !== "pending"
    ) {
      setContext(null);
      setContextError("");
      setContextLoading(false);
      return;
    }

    let cancelled = false;
    setContextLoading(true);
    setContextError("");
    setContext(null);
    VmRequestsService.getReviewContext(selected.rawId)
      .then((res) => {
        if (!cancelled) setContext(res);
      })
      .catch((err) => {
        if (!cancelled) setContextError(err?.message ?? t("RequestReviewPage.loadContextFailed"));
      })
      .finally(() => {
        if (!cancelled) setContextLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected?.rawId, selected?.source, selected?.reviewStatus]);

  async function submitReview(status) {
    if (!selected?.rawId || reviewing || selected.reviewStatus !== "pending") return;
    setReviewing(true);
    try {
      const body = {
        status,
        review_comment: comment.trim() || null,
      };
      if (selected.source === "vm") {
        await VmRequestsService.review(selected.rawId, body);
      } else if (selected.source === "spec") {
        await SpecChangeRequestsService.review(selected.rawId, body);
      } else {
        return;
      }
      toast.success(status === "approved" ? t("RequestReviewPage.approvedToast") : t("RequestReviewPage.rejectedToast"));
      setComment("");
      await fetchRequests(activeTab);
    } catch (err) {
      toast.error(err?.message ?? t("RequestReviewPage.reviewFailed"));
    } finally {
      setReviewing(false);
    }
  }

  const isPending = selected?.reviewStatus === "pending";
  /* 規格調整：機器已刪除（resource_vmid 已清空）就不能核准，後端也會擋 */
  const specResourceGone =
    selected?.source === "spec" && selected?.raw?.resource_exists === false;
  /* 系統寫入的刪除標記（CONSUMED_REQUEST_MARKERS）不是審核人留的備註，不顯示 */
  const rawReviewComment = selected?.raw?.review_comment;
  const reviewNote =
    rawReviewComment && !CONSUMED_REQUEST_MARKERS.includes(rawReviewComment)
      ? rawReviewComment
      : null;
  const stats = useMemo(() => {
    const source = allRequests.length ? allRequests : requests;
    const pending = source.filter((request) => request.reviewStatus === "pending").length;
    const approved = source.filter((request) => request.reviewStatus === "approved").length;
    const rejected = source.filter((request) => request.reviewStatus === "rejected").length;
    return { total: source.length, pending, approved, rejected };
  }, [allRequests, requests]);

  const visibleRequests = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return requests;
    return requests.filter((request) => {
      const searchable = [
        sourceLabel(request.source, t),
        request.title,
        request.user,
        request.userSubtext,
        request.status,
        request.specText,
        request.timeText,
        request.gpuText,
      ]
        .join(" ")
        .toLowerCase();
      return searchable.includes(q);
    });
  }, [query, requests]);

  return (
    <div className={styles.page}>
      <PageHeader title={t("RequestReviewPage.pageTitle")} subtitle={t("RequestReviewPage.pageSubtitle")} />

      <div className={styles.statRow}>
        <div className={styles.statCard}>
          <div className={styles.statIcon}>
            <MIcon name="assignment" size={20} />
          </div>
          <div className={styles.statInfo}>
            <span className={styles.statLabel}>{t("RequestReviewPage.statTotal")}</span>
            <span className={styles.statValue}>{stats.total}</span>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={`${styles.statIcon} ${styles.statIconBusy}`}>
            <MIcon name="pending_actions" size={20} />
          </div>
          <div className={styles.statInfo}>
            <span className={styles.statLabel}>{t("RequestReviewPage.statPending")}</span>
            <span className={styles.statValue}>{stats.pending}</span>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={`${styles.statIcon} ${styles.statIconOk}`}>
            <MIcon name="task_alt" size={20} />
          </div>
          <div className={styles.statInfo}>
            <span className={styles.statLabel}>{t("RequestReviewPage.statApproved")}</span>
            <span className={styles.statValue}>{stats.approved}</span>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={`${styles.statIcon} ${styles.statIconDanger}`}>
            <MIcon name="block" size={20} />
          </div>
          <div className={styles.statInfo}>
            <span className={styles.statLabel}>{t("RequestReviewPage.statRejected")}</span>
            <span className={styles.statValue}>{stats.rejected}</span>
          </div>
        </div>
      </div>

      <div className={styles.tabsRow}>
        <div className={styles.tabs}>
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`${styles.tab} ${activeTab === tab.key ? styles.tabActive : ""}`}
              onClick={() => setActiveTab(tab.key)}
            >
              <MIcon name={tab.icon} size={16} />
              {tab.label}
            </button>
          ))}
        </div>

        <div className={styles.search}>
          <MIcon name="search" size={16} />
          <input
            type="text"
            className={styles.searchInput}
            placeholder={t("RequestReviewPage.searchPlaceholder")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      </div>

      <div className={styles.content}>
        <div className={styles.reviewGrid}>
          <section className={styles.listPane}>
            {loading ? (
              <LoadingState text={t("RequestReviewPage.loadingRequests")} />
            ) : error ? (
              <div className={styles.stateBox}>
                <span>{error}</span>
                <button type="button" className={styles.btnSecondary} onClick={() => fetchRequests(activeTab)}>
                  {t("RequestReviewPage.retry")}
                </button>
              </div>
            ) : visibleRequests.length === 0 ? (
              <EmptyState tab={activeTab} />
            ) : (
              <div className={styles.list}>
                {visibleRequests.map((request) => (
                  <button
                    key={request.id}
                    type="button"
                    className={`${styles.row} ${selected?.id === request.id ? styles.rowActive : ""}`}
                    onClick={() => { setSelectedId(request.id); setComment(""); }}
                  >
                    <div className={styles.rowIcon}>
                      <MIcon name={sourceIcon(request)} size={20} />
                    </div>
                    <div className={styles.rowMain}>
                      <span className={styles.rowName}>{request.title}</span>
                      <span className={styles.rowMeta}>
                        {sourceLabel(request.source, t)}・{request.user}
                      </span>
                    </div>
                    <div className={styles.rowSide}>
                      <StatusBadge status={request.status} />
                      <span className={styles.rowTime}>{request.timeText}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className={styles.detailPane}>
            {!selected ? (
              <div className={styles.stateBox}>{t("RequestReviewPage.selectARequest")}</div>
            ) : (
              <>
                <div className={styles.detailHeader}>
                  <h2>{selected.title}</h2>
                  <p>{selected.user}</p>
                </div>

                <div className={styles.infoGrid}>
                  <InfoRow label={t("RequestReviewPage.infoLabelType")} value={sourceLabel(selected.source, t)} />
                  <InfoRow label={t("RequestReviewPage.infoLabelSpec")} value={selected.specText} />
                  <InfoRow label={t("RequestReviewPage.infoLabelTime")} value={selected.timeText} />
                  <InfoRow label={selected.paramLabel} value={selected.paramText} />
                  <InfoRow label={t("RequestReviewPage.infoLabelGpu")} value={selected.gpuText} />
                  <InfoRow label={t("RequestReviewPage.infoLabelNode")} value={context?.projected_node || selected.nodeText} />
                </div>

                <div className={styles.reasonBox}>
                  <span>{t("RequestReviewPage.reasonLabel")}</span>
                  <p>{selected.reason}</p>
                </div>

                {contextLoading && <LoadingState text={t("RequestReviewPage.loadingContext")} />}
                {contextError && selected.source === "vm" && (
                  <div className={`${styles.stateBox} ${styles.stateError}`}>
                    {contextError}
                  </div>
                )}
                {context && selected.source === "vm" && (
                  <div className={styles.contextBox}>
                    <div className={styles.contextTitle}>
                      <MIcon name={context.feasible ? "check_circle" : "warning"} size={18} />
                      <span>{context.feasible ? t("RequestReviewPage.feasibleYes") : t("RequestReviewPage.feasibleNo")}</span>
                    </div>
                    <p>{context.summary}</p>
                    {context.warnings?.length > 0 && (
                      <div className={styles.warningList}>
                        {context.warnings.map((warning) => (
                          <span key={warning}>{warning}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {isPending && selected.source !== "deletion" ? (
                  <div className={styles.reviewBar}>
                    {selected.source === "spec" && (
                      <div className={styles.rowActions}>
                        <span className={styles.doneText}>
                          {specResourceGone
                            ? t("RequestReviewPage.specResourceGoneHint")
                            : t("RequestReviewPage.specApplyHint")}
                        </span>
                      </div>
                    )}
                    <label className={styles.commentField}>
                      <span>{t("RequestReviewPage.commentLabel")}</span>
                      <textarea
                        value={comment}
                        onChange={(event) => setComment(event.target.value)}
                        disabled={reviewing}
                        placeholder={t("RequestReviewPage.commentPlaceholder")}
                      />
                    </label>
                    <div className={styles.rowActions}>
                      <button
                        type="button"
                        className={styles.btnApprove}
                        disabled={reviewing || (selected.source === "vm" && context && !context.feasible) || specResourceGone}
                        onClick={() => submitReview("approved")}
                      >
                        {t("RequestReviewPage.approve")}
                      </button>
                      <button
                        type="button"
                        className={styles.btnReject}
                        disabled={reviewing}
                        onClick={() => submitReview("rejected")}
                      >
                        {t("RequestReviewPage.reject")}
                      </button>
                    </div>
                  </div>
                ) : selected.source === "deletion" ? (
                  <div className={styles.rowActions}>
                    <span className={styles.doneText}>{t("RequestReviewPage.deletionOnlyNote")}</span>
                  </div>
                ) : (
                  <>
                    {(reviewNote || selected.reviewedAt) && (
                      <div className={styles.reasonBox}>
                        <span>
                          {t("RequestReviewPage.commentLabel")}
                          {selected.reviewedAt ? t("RequestReviewPage.reviewedAtSuffix", { time: formatDateTime(selected.reviewedAt, t) }) : ""}
                        </span>
                        <p>{reviewNote || t("RequestReviewPage.noReviewNote")}</p>
                      </div>
                    )}
                    {selected.source === "spec" && selected.raw?.status === "approved" && (
                      <div className={styles.reasonBox}>
                        <span>
                          {t("RequestReviewPage.applyResultLabel")}
                          {selected.raw.applied_at ? t("RequestReviewPage.applyResultAppliedAt", { time: formatDateTime(selected.raw.applied_at, t) }) : ""}
                        </span>
                        <p>
                          {selected.raw.apply_error
                            || (selected.raw.apply_status === "applied"
                              ? t("RequestReviewPage.applyResultApplied")
                              : selected.raw.apply_status === "applying"
                                ? t("RequestReviewPage.applyResultApplying")
                                : t("RequestReviewPage.applyResultAwaiting"))}
                        </p>
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
