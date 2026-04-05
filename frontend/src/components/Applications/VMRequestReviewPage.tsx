import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query"
import { Link, useNavigate } from "@tanstack/react-router"
import { ArrowLeft, Check, X } from "lucide-react"
import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import { VmRequestsService } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { LoadingButton } from "@/components/ui/loading-button"
import { Textarea } from "@/components/ui/textarea"
import useCustomToast from "@/hooks/useCustomToast"
import { cn } from "@/lib/utils"
import {
  type VmRequestAvailabilityNodeSnapshot,
  type VmRequestAvailabilityResponse,
  type VmRequestAvailabilitySlot,
  VmRequestAvailabilityService,
} from "@/services/vmRequestAvailability"
import { handleError } from "@/utils"

function formatScheduledRange(startAt?: string | null, endAt?: string | null) {
  if (!startAt || !endAt) return "未設定時段"

  const formatter = new Intl.DateTimeFormat("zh-TW", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    timeZone: "Asia/Taipei",
  })

  return `${formatter.format(new Date(startAt))} - ${formatter.format(new Date(endAt))}`
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

function getSelectedSlots(
  data: VmRequestAvailabilityResponse | undefined,
  startAt?: string | null,
  endAt?: string | null,
) {
  if (!data || !startAt || !endAt) return []

  const startMs = new Date(startAt).getTime()
  const endMs = new Date(endAt).getTime()

  return data.days
    .flatMap((day) => day.slots)
    .filter((slot) => {
      const slotStart = new Date(slot.start_at).getTime()
      return slotStart >= startMs && slotStart < endMs
    })
}

function summarizeSelectedSlots(selectedSlots: VmRequestAvailabilitySlot[]) {
  const feasible =
    selectedSlots.length > 0 &&
    selectedSlots.every(
      (slot) => slot.status === "available" || slot.status === "limited",
    )

  const nodes = Array.from(
    selectedSlots.reduce((acc, slot) => {
      for (const node of slot.recommended_nodes) {
        acc.set(node, (acc.get(node) ?? 0) + 1)
      }
      return acc
    }, new Map<string, number>()),
  )
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([node]) => node)

  const reasons = Array.from(
    new Set(selectedSlots.flatMap((slot) => slot.reasons)),
  ).slice(0, 4)

  const snapshots = new Map<string, VmRequestAvailabilityNodeSnapshot>()
  for (const slot of selectedSlots) {
    for (const snapshot of slot.node_snapshots ?? []) {
      const current = snapshots.get(snapshot.node)
      if (
        !current ||
        (!current.is_target && snapshot.is_target) ||
        (current.is_target === snapshot.is_target &&
          snapshot.dominant_share > current.dominant_share)
      ) {
        snapshots.set(snapshot.node, snapshot)
      }
    }
  }

  return {
    feasible,
    nodes,
    reasons,
    nodeSnapshots: Array.from(snapshots.values()).sort(
      (a, b) =>
        Number(b.is_target) - Number(a.is_target) ||
        a.priority - b.priority ||
        a.dominant_share - b.dominant_share ||
        a.node.localeCompare(b.node),
    ),
    strategy: selectedSlots[0]?.placement_strategy ?? null,
  }
}

function summarizeSlotStatus(selectedSlots: VmRequestAvailabilitySlot[]) {
  const counts = selectedSlots.reduce(
    (acc, slot) => {
      acc[slot.status] += 1
      return acc
    },
    {
      available: 0,
      limited: 0,
      unavailable: 0,
      policy_blocked: 0,
    },
  )

  const blockedReasons = Array.from(
    new Set(
      selectedSlots
        .filter((slot) => slot.status !== "available" && slot.status !== "limited")
        .flatMap((slot) => slot.reasons),
    ),
  ).slice(0, 4)

  return {
    counts,
    blockedReasons,
    total: selectedSlots.length,
  }
}

function formatSlotRange(slot: VmRequestAvailabilitySlot) {
  const formatter = new Intl.DateTimeFormat("zh-TW", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    timeZone: "Asia/Taipei",
  })

  return `${formatter.format(new Date(slot.start_at))} - ${formatter.format(new Date(slot.end_at))}`
}

function statusMeta(status: string, t: (key: string) => string) {
  if (status === "approved") {
    return { label: t("approvals:filters.approved"), variant: "default" as const }
  }
  if (status === "rejected") {
    return { label: t("approvals:filters.rejected"), variant: "destructive" as const }
  }
  return { label: t("approvals:filters.pending"), variant: "outline" as const }
}

function PlacementStateBadge({
  hasSchedule,
  loading,
  error,
  feasible,
}: {
  hasSchedule: boolean
  loading: boolean
  error: boolean
  feasible: boolean
}) {
  const variant =
    !hasSchedule || loading ? "outline" : error ? "destructive" : feasible ? "default" : "destructive"

  return (
    <Badge variant={variant}>
      {!hasSchedule
        ? "未設定時段"
        : loading
          ? "模擬中"
          : error
            ? "模擬失敗"
            : feasible
              ? "目前可放入"
              : "目前放不下"}
    </Badge>
  )
}

function InfoRow({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border/70 py-2 last:border-b-0">
      <span className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </span>
      <span className="max-w-[76%] text-right text-sm leading-snug">{value}</span>
    </div>
  )
}

function formatResourceTypeLabel(resourceType: string) {
  return resourceType === "lxc" ? "LXC 容器" : "QEMU 虛擬機"
}

function formatTemplateLabel(request: {
  resource_type: string
  ostemplate?: string | null
  template_id?: number | null
}) {
  if (request.resource_type === "lxc") {
    if (!request.ostemplate) return "未設定"
    return (
      request.ostemplate
        .split("/")
        .pop()
        ?.replace(/\.tar\..+$/i, "")
        .replace(/\.img$/i, "") || request.ostemplate
    )
  }

  if (request.template_id) return `Template #${request.template_id}`
  return "未設定"
}

function formatSpecLabel(request: {
  resource_type: string
  cores: number
  memory: number
  disk_size?: number | null
  rootfs_size?: number | null
}) {
  const base = `${request.cores} Core / ${(request.memory / 1024).toFixed(1)} GB RAM`

  if (request.resource_type === "vm") {
    return `${base} / ${(request.disk_size ?? 0).toFixed(0)} GB Disk`
  }

  return `${base} / ${(request.rootfs_size ?? 0).toFixed(0)} GB Rootfs`
}

function MetricPill({
  label,
  value,
  share,
}: {
  label: string
  value: string
  share: number
}) {
  return (
    <div className="rounded-md border border-border/70 bg-background/70 px-2 py-1.5 text-[11px]">
      <div className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 font-medium">{value}</div>
      <div className="text-muted-foreground">{formatPercent(share)}</div>
    </div>
  )
}

function StackServerColumn({
  snapshot,
}: {
  snapshot: VmRequestAvailabilityNodeSnapshot
}) {
  return (
    <article className="grid gap-2.5">
      <div
        className={cn(
          "rounded-b-[18px] border-x-4 border-b-4 border-t-0 border-slate-500/80 px-2.5 pb-0 pt-2.5",
          snapshot.is_target && "border-teal-500",
        )}
      >
        <div className="flex items-center gap-1.5 border-b-[3px] border-slate-500/80 pb-1.5 text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          <span>{snapshot.node}</span>
          <span className="rounded bg-accent px-1.5 py-0.5 text-[9px] font-semibold text-accent-foreground">
            P{snapshot.priority}
          </span>
          {snapshot.is_target && (
            <span className="rounded bg-teal-500 px-1.5 py-0.5 text-[9px] font-semibold text-black">
              目標
            </span>
          )}
        </div>
        <div className="flex h-[280px] flex-col-reverse gap-1.5 overflow-y-auto py-2 pr-1">
          {snapshot.vm_stack.length === 0 ? (
            <div className="grid min-h-[64px] place-items-end-center text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
              empty
            </div>
          ) : (
            snapshot.vm_stack.map((item) => (
              <div
                key={`${snapshot.node}-${item.name}`}
                className={cn(
                  "flex min-h-[42px] items-center justify-between gap-2 rounded-b-[12px] border-[2px] border-rose-400 bg-background/90 px-2.5 py-1.5 text-xs font-medium",
                  item.pending &&
                    "border-teal-500 bg-teal-500/10 text-teal-300",
                )}
              >
                <span className="truncate">{item.name}</span>
                <span className="shrink-0 text-xs">x{item.count}</span>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="text-center">
        <h3 className="text-lg font-semibold tracking-tight">{snapshot.node}</h3>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          {snapshot.status} · DS {formatPercent(snapshot.dominant_share)} ·{" "}
          {snapshot.candidate ? "可候選" : "非候選"}
        </p>
      </div>

      <div className="grid grid-cols-3 gap-1.5">
        <MetricPill
          label="CPU 剩餘"
          value={snapshot.remaining_cpu_cores.toFixed(2)}
          share={snapshot.cpu_share}
        />
        <MetricPill
          label="RAM 剩餘"
          value={`${snapshot.remaining_memory_gb.toFixed(1)} GB`}
          share={snapshot.memory_share}
        />
        <MetricPill
          label="Disk 剩餘"
          value={`${snapshot.remaining_disk_gb.toFixed(1)} GB`}
          share={snapshot.disk_share}
        />
      </div>
    </article>
  )
}

export function VMRequestReviewPage({ requestId }: { requestId: string }) {
  const { t } = useTranslation(["approvals", "messages"])
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [comment, setComment] = useState("")

  const requestQuery = useSuspenseQuery({
    queryKey: ["vm-request", requestId],
    queryFn: () => VmRequestsService.getVmRequest({ requestId }),
  })

  const request = requestQuery.data
  const scheduledStartAt = request.start_at ?? null
  const scheduledEndAt = request.end_at ?? null

  const availabilityQuery = useQuery({
    queryKey: ["vm-request-availability-review", request.id],
    queryFn: () =>
      VmRequestAvailabilityService.getByRequestId({
        requestId: request.id,
        days: 7,
        timezone: "Asia/Taipei",
      }),
    enabled: Boolean(request.start_at && request.end_at),
    staleTime: 30_000,
  })

  const selectedSlots = useMemo(
    () =>
      getSelectedSlots(
        availabilityQuery.data,
        scheduledStartAt,
        scheduledEndAt,
      ),
    [availabilityQuery.data, scheduledEndAt, scheduledStartAt],
  )

  const previewSummary = useMemo(
    () => summarizeSelectedSlots(selectedSlots),
    [selectedSlots],
  )

  const slotSummary = useMemo(
    () => summarizeSlotStatus(selectedSlots),
    [selectedSlots],
  )

  const reviewMutation = useMutation({
    mutationFn: (status: "approved" | "rejected") =>
      VmRequestsService.reviewVmRequest({
        requestId: request.id,
        requestBody: {
          status,
          review_comment: comment || null,
        },
      }),
    onSuccess: (_data, status) => {
      showSuccessToast(
        status === "approved"
          ? t("messages:success.applicationApproved")
          : t("messages:success.applicationRejected"),
      )
      queryClient.invalidateQueries({ queryKey: ["vm-requests-admin"] })
      queryClient.invalidateQueries({ queryKey: ["vm-request", request.id] })
      navigate({ to: "/approvals" })
    },
    onError: handleError.bind(showErrorToast),
  })

  const currentStatus = statusMeta(request.status, t)
  const hasSchedule = Boolean(scheduledStartAt && scheduledEndAt)
  const isPending = request.status === "pending"

  return (
    <div className="space-y-5">
      <header className="border-b border-border/70 pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <Button asChild variant="outline" size="sm">
              <Link to="/approvals">
                <ArrowLeft className="mr-2 h-4 w-4" />
                返回審核列表
              </Link>
            </Button>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">{request.hostname}</h1>
              <p className="text-sm text-muted-foreground">
                先確認申請資訊與放置模擬，再決定是否通過這筆申請。
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={currentStatus.variant}>{currentStatus.label}</Badge>
            <PlacementStateBadge
              hasSchedule={hasSchedule}
              loading={availabilityQuery.isLoading}
              error={availabilityQuery.isError}
              feasible={previewSummary.feasible}
            />
            {request.assigned_node && <Badge variant="secondary">Node {request.assigned_node}</Badge>}
            {request.vmid && <Badge variant="outline">VMID {request.vmid}</Badge>}
          </div>
        </div>
      </header>

      <section className="grid gap-5 xl:grid-cols-[400px_minmax(0,1fr)] 2xl:grid-cols-[440px_minmax(0,1fr)]">
        <div className="rounded-2xl border border-border/80 bg-card/40 p-4">
          <h2 className="text-lg font-semibold">申請內容</h2>
          <div className="mt-3">
            <InfoRow
              label="申請者"
              value={request.user_full_name || request.user_email || "Unknown"}
            />
            <InfoRow
              label="類型"
              value={formatResourceTypeLabel(request.resource_type)}
            />
            <InfoRow
              label="作業系統 / 模板"
              value={formatTemplateLabel(request)}
            />
            <InfoRow
              label="作業系統資訊"
              value={request.os_info?.trim() || "未填寫"}
            />
            <InfoRow
              label="環境類型"
              value={request.environment_type || "未設定"}
            />
            <InfoRow
              label="規格"
              value={formatSpecLabel(request)}
            />
            <InfoRow
              label="儲存"
              value={request.storage || "未設定"}
            />
            {request.resource_type === "vm" && (
              <InfoRow
                label="使用者名稱"
                value={request.username || "未填寫"}
              />
            )}
            <InfoRow
              label="時段"
              value={formatScheduledRange(scheduledStartAt, scheduledEndAt)}
            />
            <InfoRow label="狀態" value={currentStatus.label} />
          </div>
          <div className="mt-4 border-t border-border/70 pt-3 text-sm">
            <div className="mb-1 text-xs uppercase tracking-[0.18em] text-muted-foreground">
              申請原因
            </div>
            <p>{request.reason}</p>
          </div>
        </div>

        <div className="rounded-2xl border border-border/80 bg-card/40 p-4">
          <h2 className="text-lg font-semibold">審核動作</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            放置模擬固定依申請者送出的時段計算，並反映目前 PVE 叢集狀態。
          </p>

          <div className="mt-4">
            <label htmlFor="review-note" className="text-sm font-medium">
              {t("approvals:review.reviewNote")}
            </label>
            <Textarea
              id="review-note"
              placeholder={t("approvals:review.reviewNotePlaceholder")}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="mt-1"
              disabled={!isPending || reviewMutation.isPending}
            />
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            {isPending ? (
              <>
                <LoadingButton
                  type="button"
                  onClick={() => reviewMutation.mutate("approved")}
                  loading={reviewMutation.isPending}
                >
                  <Check className="mr-2 h-4 w-4" />
                  {t("approvals:review.confirmApprove")}
                </LoadingButton>
                <LoadingButton
                  type="button"
                  variant="destructive"
                  onClick={() => reviewMutation.mutate("rejected")}
                  loading={reviewMutation.isPending}
                >
                  <X className="mr-2 h-4 w-4" />
                  {t("approvals:review.confirmReject")}
                </LoadingButton>
              </>
            ) : (
              <div className="rounded-lg border border-dashed px-3 py-3 text-sm text-muted-foreground">
                這筆申請已完成審核。
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-border/80 bg-card/40 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 pb-3">
          <div>
            <h2 className="text-lg font-semibold">放置模擬</h2>
            <p className="text-sm text-muted-foreground">
              顯示這筆申請在目前叢集狀態下，會優先落在哪些節點以及對應的 PVE stack。
            </p>
          </div>
          <div className="flex flex-wrap gap-3 text-sm text-muted-foreground">
            <span>
              策略：{" "}
              Priority 排程，未設定節點權重時平均分配
            </span>
            <span>
              建議節點：{" "}
              {previewSummary.nodes.length > 0 ? previewSummary.nodes.join(", ") : "無"}
            </span>
          </div>
        </div>

        {!availabilityQuery.isLoading && !availabilityQuery.isError && (
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border border-border/70 bg-background/60 p-3">
              <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                時段總數
              </div>
              <div className="mt-2 text-2xl font-semibold">{slotSummary.total}</div>
              <div className="mt-1 text-sm text-muted-foreground">
                已納入這筆申請的整段時窗模擬
              </div>
            </div>
            <div className="rounded-xl border border-border/70 bg-background/60 p-3">
              <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                可放入
              </div>
              <div className="mt-2 text-2xl font-semibold text-emerald-500">
                {slotSummary.counts.available + slotSummary.counts.limited}
              </div>
              <div className="mt-1 text-sm text-muted-foreground">
                這些時段會保留可正常開機
              </div>
            </div>
            <div className="rounded-xl border border-border/70 bg-background/60 p-3">
              <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                被占用 / 不可用
              </div>
              <div className="mt-2 text-2xl font-semibold text-rose-500">
                {slotSummary.counts.unavailable + slotSummary.counts.policy_blocked}
              </div>
              <div className="mt-1 text-sm text-muted-foreground">
                這些時段會被排除或顯示為不可選
              </div>
            </div>
            <div className="rounded-xl border border-border/70 bg-background/60 p-3">
              <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                最終節點
              </div>
              <div className="mt-2 text-2xl font-semibold">
                {previewSummary.nodes[0] ?? request.assigned_node ?? "未定"}
              </div>
              <div className="mt-1 text-sm text-muted-foreground">
                依目前模擬結果保留的主要落點
              </div>
            </div>
          </div>
        )}

        {!availabilityQuery.isLoading &&
          !availabilityQuery.isError &&
          slotSummary.blockedReasons.length > 0 && (
            <div className="mt-4 rounded-xl border border-dashed border-border/70 bg-background/40 p-3">
              <div className="text-sm font-medium">時段衝突原因</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {slotSummary.blockedReasons.map((reason) => (
                  <Badge key={reason} variant="outline" className="max-w-full">
                    {reason}
                  </Badge>
                ))}
              </div>
            </div>
          )}

        {availabilityQuery.isError && (
          <div className="mt-4 rounded-lg border border-dashed px-3 py-3 text-sm text-muted-foreground">
            目前無法載入這筆申請的放置模擬結果。
          </div>
        )}

        {!availabilityQuery.isLoading &&
          !availabilityQuery.isError &&
          previewSummary.reasons.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {previewSummary.reasons.map((reason) => (
                <Badge key={reason} variant="outline" className="max-w-full">
                  {reason}
                </Badge>
              ))}
            </div>
          )}

        <div className="mt-5 grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
          {!availabilityQuery.isLoading &&
            !availabilityQuery.isError &&
            previewSummary.nodeSnapshots.map((snapshot) => (
              <StackServerColumn key={snapshot.node} snapshot={snapshot} />
            ))}
        </div>
      </section>
    </div>
  )
}

export default VMRequestReviewPage
