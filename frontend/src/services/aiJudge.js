import {
  apiDelete,
  apiGet,
  apiGetBlob,
  apiPatch,
  apiPost,
  apiPostBlob,
  apiPostMultipart,
} from "./api";
import i18n from "../i18n";

// 腳本產生會依序執行 generation、policy/quality 修正與 AI reviewer，
// 不能沿用一般 API 的 15 秒 request budget。後端每次 vLLM 呼叫仍有自己的 timeout。
const SCRIPT_GENERATION_TIMEOUT_MS = 7 * 60 * 1000;
// Teacher Judge 的 AI 分析／對話以 backend/config/system-ai.json 的 60 秒為準。
export const TEACHER_JUDGE_REQUEST_TIMEOUT_MS = 60 * 1000;

/** 評分環境模板選項 */
export const TEMPLATE_OPTIONS = [
  { key: "n8n", label: "n8n" },
  { key: "python", label: "Python" },
  { key: "postgresql", label: "PostgreSQL" },
  { key: "linux", label: i18n.t("aiJudge.linuxTemplateLabel", { ns: "services" }) },
];

/** 正式工作區與獨立編輯頁共用的整表潤飾動作。 */
export const RUBRIC_POLISH_PROMPT =
  "請在不改變原始評分目標的前提下潤飾目前評分表：檢查每個項目的描述與成功條件，判斷後續自動檢測支援程度為 auto、partial 或 manual，並補充偵測方式、fallback 與 check_steps，讓下一層檢查 AI 能理解。即使內容不需修改，也請回傳完整評分項目列表，以完成這次可偵測性評估。將目前評分環境視為主要情境而非硬性範圍，逐項查找平台所有已啟用的受控檢查能力；若缺少工作目錄、執行命令或成功條件，請明確向我詢問，不要改成較容易但不同的檢查目標，也不要只因單一項目跨環境就要求切換整份評分表環境";

/** 評分項目異動後，重新判斷目前環境能自動檢查到什麼程度。 */
export const RUBRIC_REASSESS_PROMPT =
  "請在不改變原始評分目標的前提下重新評估各項目的可自動偵測程度，更新偵測分類、偵測方式、替代建議與評分計劃書。將目前評分環境視為主要情境，個別項目可使用平台其他已啟用的受控能力；若缺少工作目錄、執行命令或成功條件，請明確向我詢問，不要改成不同的檢查目標，也不要只因單一項目跨環境就要求切換整份評分表環境";

export function getTemplateLabel(templateKey) {
  return (
    TEMPLATE_OPTIONS.find((option) => option.key === templateKey)?.label ??
    i18n.t("aiJudge.linuxTemplateLabel", { ns: "services" })
  );
}

/** 把 rubric 分析結果轉成 AI 對話用的 context 字串 */
export function rubricToContext(analysis) {
  return JSON.stringify({
    items: analysis.items,
    total_items: analysis.total_items,
    checked_count: analysis.checked_count,
    summary: analysis.summary,
  });
}

/** refine action 的內部指令仍保留在 session 歷史，但不在教師聊天室呈現。 */
export function shouldDisplayChatMessage(message) {
  const isKnownInternalPrompt = [RUBRIC_POLISH_PROMPT, RUBRIC_REASSESS_PROMPT].includes(
    message?.content,
  );
  return !message?.hidden && !message?.metadata_json?.ui_hidden && !isKnownInternalPrompt;
}

export const AiJudgeService = {
  /* ── 持久化檢查 Session ── */

  listSessions(classId) {
    return apiGet(`/api/v1/teaching-classes/${classId}/judge/sessions/`);
  },

  createSession(classId, {
    title,
    teachingClassWeekId = null,
    selectedFileId = null,
    creationMode,
    rubricName,
    environmentKeys,
  }) {
    const payload = {
      title,
      selected_file_id: selectedFileId,
    };
    if (teachingClassWeekId) payload.teaching_class_week_id = teachingClassWeekId;
    if (creationMode) payload.creation_mode = creationMode;
    if (rubricName !== undefined) payload.rubric_name = rubricName;
    if (environmentKeys !== undefined) payload.environment_keys = environmentKeys;
    return apiPost(`/api/v1/teaching-classes/${classId}/judge/sessions/`, payload);
  },

  createBlankSession(classId, {
    title = i18n.t("aiJudge.defaultBlankSessionTitle", { ns: "services" }),
    rubricName = i18n.t("aiJudge.defaultBlankRubricName", { ns: "services" }),
    environmentKeys = ["n8n"],
  } = {}) {
    return this.createSession(classId, {
      title,
      selectedFileId: null,
      creationMode: "blank",
      rubricName,
      environmentKeys,
    });
  },

  getSession(classId, sessionId) {
    return apiGet(`/api/v1/teaching-classes/${classId}/judge/sessions/${sessionId}`);
  },

  updateSession(classId, sessionId, changes) {
    return apiPatch(
      `/api/v1/teaching-classes/${classId}/judge/sessions/${sessionId}`,
      changes,
    );
  },

  forkSession(classId, sessionId, title = null) {
    return apiPost(
      `/api/v1/teaching-classes/${classId}/judge/sessions/${sessionId}/fork`,
      title ? { title } : {},
    );
  },

  deleteSession(classId, sessionId) {
    return apiDelete(
      `/api/v1/teaching-classes/${classId}/judge/sessions/${sessionId}`,
    );
  },

  listSessionMessages(classId, sessionId, before = null) {
    const query = before ? `?before=${encodeURIComponent(before)}` : "";
    return apiGet(
      `/api/v1/teaching-classes/${classId}/judge/sessions/${sessionId}/messages${query}`,
    );
  },

  clearSessionMessages(classId, sessionId) {
    return apiDelete(
      `/api/v1/teaching-classes/${classId}/judge/sessions/${sessionId}/messages`,
    );
  },

  sendSessionMessage(
    classId,
    sessionId,
    content,
    analysisRevision = null,
    { isRefine = false, attachmentIds = [] } = {},
  ) {
    const payload = { content };
    if (analysisRevision !== null && analysisRevision !== undefined) {
      payload.analysis_revision = analysisRevision;
    }
    if (isRefine) payload.is_refine = true;
    if (attachmentIds.length) payload.attachment_ids = attachmentIds;
    return apiPost(
      `/api/v1/teaching-classes/${classId}/judge/sessions/${sessionId}/messages`,
      payload,
      { timeoutMs: TEACHER_JUDGE_REQUEST_TIMEOUT_MS },
    );
  },

  uploadSessionAttachment(classId, sessionId, file) {
    const formData = new FormData();
    formData.append("file", file);
    return apiPostMultipart(
      `/api/v1/teaching-classes/${classId}/judge/sessions/${sessionId}/attachments`,
      formData,
      { timeoutMs: TEACHER_JUDGE_REQUEST_TIMEOUT_MS },
    );
  },

  deleteSessionAttachment(classId, sessionId, attachmentId) {
    return apiDelete(
      `/api/v1/teaching-classes/${classId}/judge/sessions/${sessionId}/attachments/${attachmentId}`,
    );
  },

  createSessionScript(classId, sessionId, analysisRevision = null) {
    const payload = {};
    if (analysisRevision !== null && analysisRevision !== undefined) {
      payload.analysis_revision = analysisRevision;
    }
    return apiPost(
      `/api/v1/teaching-classes/${classId}/judge/sessions/${sessionId}/scripts`,
      payload,
      { timeoutMs: SCRIPT_GENERATION_TIMEOUT_MS },
    );
  },

  listSessionRuns(classId, sessionId) {
    return apiGet(
      `/api/v1/teaching-classes/${classId}/judge/sessions/${sessionId}/runs`,
    );
  },

  getSessionRun(classId, sessionId, runId) {
    return apiGet(
      `/api/v1/teaching-classes/${classId}/judge/sessions/${sessionId}/runs/${runId}`,
    );
  },

  createSessionRun(classId, sessionId, scriptId, targetVmids) {
    return apiPost(
      `/api/v1/teaching-classes/${classId}/judge/sessions/${sessionId}/scripts/${scriptId}/runs`,
      { target_scope: "manual", target_vmids: targetVmids },
    );
  },

  /* ── 評分表文件 ── */

  /** 列出班級已保存的評分表 */
  listFiles(classId) {
    return apiGet(`/api/v1/teaching-classes/${classId}/judge/files/`);
  },

  /**
   * 上傳評分表文件並觸發 AI 分析；environmentKeys 的第一項為主要情境。
   * 同名檔案已存在時後端回 409，可帶 conflictStrategy（"overwrite" | "copy"）重送。
   */
  uploadFile(classId, file, templateKey, conflictStrategy, environmentKeys = null) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("template_key", templateKey);
    const selectedEnvironments = Array.isArray(environmentKeys) && environmentKeys.length
      ? environmentKeys
      : [templateKey];
    selectedEnvironments.forEach((key) => formData.append("environment_keys", key));
    if (conflictStrategy) formData.append("conflict_strategy", conflictStrategy);
    return apiPostMultipart(
      `/api/v1/teaching-classes/${classId}/judge/files/`,
      formData,
      { timeoutMs: TEACHER_JUDGE_REQUEST_TIMEOUT_MS },
    );
  },

  /** 更新已保存評分表的分析結果（項目編輯後持久化） */
  updateFileAnalysis(classId, fileId, analysis, expectedRevision = null) {
    const payload = { analysis };
    if (expectedRevision !== null && expectedRevision !== undefined) {
      payload.expected_revision = expectedRevision;
    }
    return apiPatch(
      `/api/v1/teaching-classes/${classId}/judge/files/${fileId}/analysis`,
      payload,
    );
  },

  updateFileMetadata(classId, fileId, metadata) {
    return apiPatch(
      `/api/v1/teaching-classes/${classId}/judge/files/${fileId}`,
      metadata,
    );
  },

  createBlankFile(classId, { displayName, environmentKeys }) {
    return apiPost(`/api/v1/teaching-classes/${classId}/judge/files/blank`, {
      display_name: displayName,
      environment_keys: environmentKeys,
    });
  },

  /** 下載評分表原始檔 */
  downloadFile(classId, fileId) {
    return apiGetBlob(`/api/v1/teaching-classes/${classId}/judge/files/${fileId}/download`);
  },

  /** 刪除評分表（原始檔＋分析結果） */
  deleteFile(classId, fileId) {
    return apiDelete(`/api/v1/teaching-classes/${classId}/judge/files/${fileId}`);
  },

  /* ── AI 對話與匯出 ── */

  /** 與 AI 對話精煉評分表；isRefine 為全表潤飾 */
  chat({ messages, rubricContext, isRefine = false, templateKey = "linux" }) {
    return apiPost(
      "/api/v1/rubric/chat",
      {
        messages,
        rubric_context: rubricContext,
        is_refine: isRefine,
        template_key: templateKey,
      },
      { timeoutMs: TEACHER_JUDGE_REQUEST_TIMEOUT_MS },
    );
  },

  /** 將評分項目匯出成 Excel（回傳 Blob） */
  downloadExcel(items, summary) {
    return apiPostBlob("/api/v1/rubric/download-excel", { items, summary });
  },

  /* ── 收集腳本 ── */

  /** 列出班級收集腳本 */
  listScripts(classId, sessionId = null) {
    const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
    return apiGet(`/api/v1/teaching-classes/${classId}/judge/scripts/${query}`);
  },

  /** 由評分表快照產生受管收集腳本（後端會接著跑 policy 與 AI 審查） */
  createScript(classId, { name, templateKey, rubricSnapshot, sourceFileId = null }) {
    return apiPost(
      `/api/v1/teaching-classes/${classId}/judge/scripts/`,
      {
        name,
        template_key: templateKey,
        rubric_snapshot: rubricSnapshot,
        source_file_id: sourceFileId,
      },
      { timeoutMs: SCRIPT_GENERATION_TIMEOUT_MS },
    );
  },

  /** 重新生成腳本（可帶新的 rubric 快照） */
  regenerateScript(classId, scriptId, rubricSnapshot = null) {
    return apiPost(
      `/api/v1/teaching-classes/${classId}/judge/scripts/${scriptId}/regenerate`,
      { rubric_snapshot: rubricSnapshot },
      { timeoutMs: SCRIPT_GENERATION_TIMEOUT_MS },
    );
  },

  /** 相容舊版待老師核准腳本；新流程通過靜態與 AI 檢查後會直接 approved。 */
  approveScript(classId, scriptId) {
    return apiPost(`/api/v1/teaching-classes/${classId}/judge/scripts/${scriptId}/approve`, {});
  },

  /** 刪除腳本 */
  deleteScript(classId, scriptId) {
    return apiDelete(`/api/v1/teaching-classes/${classId}/judge/scripts/${scriptId}`);
  },

  /** 重新命名腳本 */
  renameScript(classId, scriptId, name) {
    return apiPatch(`/api/v1/teaching-classes/${classId}/judge/scripts/${scriptId}`, {
      name,
    });
  },

  /* ── 腳本執行 ── */

  /** 對指定 VMID 建立腳本執行任務 */
  createScriptRun(classId, scriptId, targetVmids) {
    return apiPost(`/api/v1/teaching-classes/${classId}/judge/scripts/${scriptId}/runs`, {
      target_scope: "manual",
      target_vmids: targetVmids,
    });
  },

  /** 查詢執行任務進度與結果（前端輪詢用） */
  getScriptRun(classId, scriptId, runId) {
    return apiGet(
      `/api/v1/teaching-classes/${classId}/judge/scripts/${scriptId}/runs/${runId}`,
    );
  },
};
