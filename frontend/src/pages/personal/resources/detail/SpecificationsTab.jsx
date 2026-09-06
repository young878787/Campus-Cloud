import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./ResourceDetailPage.module.scss";
import LoadingState from "../../../../components/LoadingState/LoadingState";
import MIcon from "../../../../components/MIcon";
import { useConfirm } from "../../../../components/ConfirmDialog/ConfirmProvider";
import { useAuth } from "../../../../contexts/AuthContext";
import { ResourcesService } from "../../../../services/resources";
import {
  SpecChangeRequestsService,
  canApplySpecRequest,
  canCancelSpecRequest,
  isOpenSpecRequest,
  specRequestChangeLabel,
  specRequestDisplayStatus,
} from "../../../../services/specChangeRequests";
import { useToast } from "../../../../hooks/useToast";
import { focusInvalidField } from "../../../../utils/focusField";

/* 套用中（關機 → 改規格 → 開機）約 1～3 分鐘，期間每 5 秒跟一次進度 */
const APPLY_POLL_MS = 5000;

/** 這台機器目前還在流程中的申請（最多一張：後端擋重複送單） */
function findOpenRequest(list, vmid) {
  return (list ?? [])
    .filter((r) => r.vmid === vmid && isOpenSpecRequest(r))
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0] ?? null;
}

/** 最近一張已套用但自動開機失敗的申請：規格已改，但機器還關著要提醒 */
function findAppliedWithWarning(list, vmid) {
  return (list ?? []).find(
    (r) => r.vmid === vmid && r.status === "approved" && r.apply_status === "applied" && r.apply_error,
  ) ?? null;
}

function OpenRequestNotice({ request, busy, onApply, onCancel }) {
  const { t } = useTranslation("personal");
  const display = specRequestDisplayStatus(request);
  const statusLabel = display.labelKey ? t(display.labelKey) : display.key;
  const showApply = canApplySpecRequest(request);
  const showCancel = canCancelSpecRequest(request);

  let line;
  switch (display.key) {
    case "pending":
      line = t("SpecificationsTab.noticePending");
      break;
    case "ready":
      line = t("SpecificationsTab.noticeReady");
      break;
    case "applying":
      line = t("SpecificationsTab.noticeApplying");
      break;
    case "apply_failed":
      line = t("SpecificationsTab.noticeApplyFailed", {
        error: request.apply_error ?? t("SpecificationsTab.unknownError"),
      });
      break;
    case "apply_interrupted":
      line = t("SpecificationsTab.noticeInterrupted");
      break;
    default:
      line = statusLabel;
  }

  return (
    <div className={styles.noteBox}>
      <span className={styles.noteBoxTitle}>
        <MIcon name={display.key === "applying" ? "hourglass_top" : "tune"} size={14} />
        {t("SpecificationsTab.noticeTitle", { status: statusLabel })}
      </span>
      <span className={styles.noteBoxLine}>{specRequestChangeLabel(request, t)}</span>
      <span className={styles.noteBoxLine}>{line}</span>
      {(showApply || showCancel) && (
        <div className={styles.noteActions}>
          {showApply && (
            <button type="button" className={styles.btnPrimary} disabled={busy} onClick={onApply}>
              <MIcon name="play_arrow" size={16} />
              {display.key === "ready" ? t("SpecificationsTab.applyNewSpec") : t("SpecificationsTab.reapply")}
            </button>
          )}
          {showCancel && (
            <button type="button" className={styles.btnDangerOutline} disabled={busy} onClick={onCancel}>
              {t("SpecificationsTab.cancelRequest")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function SpecificationsTab({ vmid }) {
  const { t } = useTranslation("personal");
  const toast = useToast();
  const confirm = useConfirm();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin" || user?.is_superuser || false;

  const [config, setConfig] = useState(null);
  // 課堂與快速練習的機器照課程環境版本建立，規格不接受個別調整；
  // 後端一直有算 can_request_spec_change，只是沒有人讀。
  const [specFixed, setSpecFixed] = useState(false);
  const [cores, setCores] = useState(1);
  const [memory, setMemory] = useState(512);
  const [reason, setReason] = useState("");
  const [reasonInvalid, setReasonInvalid] = useState(false);
  const reasonRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const [openRequest, setOpenRequest] = useState(null);
  const [appliedWarning, setAppliedWarning] = useState(null);

  const loadConfig = useCallback(async () => {
    try {
      const c = await ResourcesService.getConfig(vmid);
      setConfig(c);
      setCores(c.cpu_cores || 1);
      setMemory(c.memory_mb || 512);
    } catch {
      setError(true);
      return;
    }
    try {
      const resource = await ResourcesService.get(vmid);
      setSpecFixed(resource?.can_request_spec_change === false);
    } catch {
      setSpecFixed(false);
    }
  }, [vmid]);

  /* 管理員直接套用，不走申請；只有一般使用者需要看自己的申請進度 */
  const loadRequests = useCallback(async () => {
    if (isAdmin) return;
    try {
      const res = await SpecChangeRequestsService.listMy();
      setOpenRequest(findOpenRequest(res.data, vmid));
      setAppliedWarning(findAppliedWithWarning(res.data, vmid));
    } catch {
      /* 申請進度載入失敗不影響表單本身 */
    }
  }, [isAdmin, vmid]);

  useEffect(() => {
    loadConfig();
    loadRequests();
  }, [loadConfig, loadRequests]);

  const applying = openRequest?.apply_status === "applying";
  useEffect(() => {
    if (!applying) return undefined;
    const timer = setInterval(async () => {
      const before = openRequest?.id;
      await loadRequests();
      /* 套用完成後 openRequest 會消失；重新載入規格讓「目前」數字更新 */
      if (before) loadConfig();
    }, APPLY_POLL_MS);
    return () => clearInterval(timer);
  }, [applying, openRequest?.id, loadRequests, loadConfig]);

  const handleApply = async () => {
    if (!openRequest) return;
    const ok = await confirm({
      title: t("SpecificationsTab.confirmApplyTitle"),
      message: t("SpecificationsTab.confirmApplyMessage"),
      confirmText: t("SpecificationsTab.confirmApplyLabel"),
    });
    if (!ok) return;
    setBusy(true);
    try {
      const res = await SpecChangeRequestsService.apply(openRequest.id);
      setOpenRequest(res.request);
      toast.success(t("SpecificationsTab.applyStarted"));
    } catch (e) {
      toast.error(e?.message ?? t("SpecificationsTab.applyFailed"));
      await loadRequests();
    } finally {
      setBusy(false);
    }
  };

  const handleCancel = async () => {
    if (!openRequest) return;
    const ok = await confirm({
      title: t("SpecificationsTab.confirmCancelTitle"),
      message: t("SpecificationsTab.confirmCancelMessage"),
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await SpecChangeRequestsService.cancel(openRequest.id);
      setOpenRequest(null);
      toast.success(t("SpecificationsTab.cancelSuccess"));
    } catch (e) {
      toast.error(e?.message ?? t("SpecificationsTab.cancelFailed"));
      await loadRequests();
    } finally {
      setBusy(false);
    }
  };

  const handleSubmit = async () => {
    const hasChanges = cores !== config.cpu_cores || memory !== config.memory_mb;

    if (isAdmin) {
      setBusy(true);
      try {
        await ResourcesService.updateSpecDirect(vmid, {
          cores: cores !== config.cpu_cores ? cores : undefined,
          memory: memory !== config.memory_mb ? memory : undefined,
        });
        toast.success(t("SpecificationsTab.updateSuccess"));
        await loadConfig();
      } catch (e) {
        toast.error(e?.message ?? t("SpecificationsTab.updateFailed"));
      } finally {
        setBusy(false);
      }
      return;
    }

    if (reason.trim().length < 10) {
      setReasonInvalid(true);
      focusInvalidField(reasonRef.current);
      return;
    }
    if (!hasChanges) {
      toast.error(t("SpecificationsTab.noChanges"));
      return;
    }

    setBusy(true);
    try {
      const created = await SpecChangeRequestsService.create({
        vmid,
        change_type: "combined",
        reason,
        requested_cpu: cores !== config.cpu_cores ? cores : undefined,
        requested_memory: memory !== config.memory_mb ? memory : undefined,
      });
      setOpenRequest(created);
      toast.success(t("SpecificationsTab.requestSubmitted"));
      setReason("");
    } catch (e) {
      toast.error(e?.message ?? t("SpecificationsTab.submitFailed"));
    } finally {
      setBusy(false);
    }
  };

  if (error) return <p className={styles.stateText}>{t("SpecificationsTab.loadFailed")}</p>;
  if (!config) return <LoadingState />;

  /* 一張處理中就不能再送（後端也擋），表單只留給管理員或沒有申請時 */
  const formLocked = !isAdmin && Boolean(openRequest);
  const inputsDisabled = specFixed || formLocked;

  let desc;
  if (specFixed) desc = t("SpecificationsTab.descFixed");
  else if (isAdmin) desc = t("SpecificationsTab.descAdmin");
  else if (formLocked) desc = t("SpecificationsTab.descLocked");
  else desc = t("SpecificationsTab.descUser");

  return (
    <div className={styles.tabStack}>
      {!isAdmin && appliedWarning && !openRequest && (
        <div className={styles.noteBox}>
          <span className={styles.noteBoxTitle}>
            <MIcon name="warning" size={14} />
            {t("SpecificationsTab.appliedWarningTitle")}
          </span>
          <span className={styles.noteBoxLine}>{appliedWarning.apply_error}</span>
        </div>
      )}

      {openRequest && (
        <OpenRequestNotice
          request={openRequest}
          busy={busy}
          onApply={handleApply}
          onCancel={handleCancel}
        />
      )}

      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <h2 className={styles.cardTitle}>{t("SpecificationsTab.title")}</h2>
            <p className={styles.cardDesc}>{desc}</p>
          </div>
        </div>
        <div className={styles.cardBody}>
          <div className={styles.formGrid}>
            <div className={styles.field}>
              <label htmlFor="spec-cores">{t("SpecificationsTab.cpuCoresLabel")}</label>
              <input
                id="spec-cores"
                type="number"
                min={1}
                max={32}
                value={cores}
                disabled={inputsDisabled}
                onChange={(e) => setCores(Number.parseInt(e.target.value, 10) || 1)}
              />
              <span className={styles.fieldHint}>{t("SpecificationsTab.currentLabel", { value: config.cpu_cores })}</span>
            </div>
            <div className={styles.field}>
              <label htmlFor="spec-memory">{t("SpecificationsTab.memoryLabel")}</label>
              <input
                id="spec-memory"
                type="number"
                min={512}
                max={65536}
                step={512}
                value={memory}
                disabled={inputsDisabled}
                onChange={(e) => setMemory(Number.parseInt(e.target.value, 10) || 512)}
              />
              <span className={styles.fieldHint}>{t("SpecificationsTab.currentMemoryLabel", { value: config.memory_mb })}</span>
            </div>
          </div>

          {!isAdmin && !specFixed && (
            <div className={`${styles.field} ${reasonInvalid ? styles.fieldInvalid : ""}`}>
              <label htmlFor="spec-reason">{t("SpecificationsTab.reasonLabel")}</label>
              <textarea
                id="spec-reason"
                ref={reasonRef}
                rows={4}
                placeholder={t("SpecificationsTab.reasonPlaceholder")}
                aria-invalid={reasonInvalid}
                value={reason}
                disabled={formLocked}
                onChange={(e) => { setReason(e.target.value); setReasonInvalid(false); }}
              />
              <span className={styles.fieldHint}>{t("SpecificationsTab.reasonHint")}</span>
            </div>
          )}

          {!specFixed && (
            <button
              type="button"
              className={styles.btnPrimary}
              disabled={busy || formLocked}
              onClick={handleSubmit}
            >
              {busy ? t("SpecificationsTab.processing") : isAdmin ? t("SpecificationsTab.applyChanges") : t("SpecificationsTab.submitRequest")}
            </button>
          )}
        </div>
      </div>

      {!isAdmin && !specFixed && (
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>{t("SpecificationsTab.reviewProcessTitle")}</h2>
          </div>
          <div className={styles.cardBody}>
            <ol className={styles.stepList}>
              <li>{t("SpecificationsTab.step1")}</li>
              <li>{t("SpecificationsTab.step2")}</li>
              <li>{t("SpecificationsTab.step3")}</li>
              <li>{t("SpecificationsTab.step4")}</li>
            </ol>
          </div>
        </div>
      )}
    </div>
  );
}
