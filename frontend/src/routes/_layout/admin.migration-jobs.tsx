import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { RefreshCw, RotateCcw, XCircle } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import useCustomToast from "@/hooks/useCustomToast"
import {
  type MigrationJob,
  type MigrationJobStatus,
  MigrationJobsService,
} from "@/services/migrationJobs"
import { handleError } from "@/utils"

export const Route = createFileRoute("/_layout/admin/migration-jobs")({
  component: MigrationJobsPage,
  head: () => ({
    meta: [{ title: "Migration Jobs - Campus Cloud" }],
  }),
})

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "blocked", label: "Blocked" },
  { value: "cancelled", label: "Cancelled" },
]

function baseStatusMeta(status: MigrationJobStatus) {
  const map: Record<
    MigrationJobStatus,
    {
      label: string
      variant: "default" | "secondary" | "destructive" | "outline"
    }
  > = {
    pending: { label: "Pending", variant: "secondary" },
    running: { label: "Running", variant: "default" },
    completed: { label: "Completed", variant: "default" },
    failed: { label: "Failed", variant: "destructive" },
    blocked: { label: "Blocked", variant: "destructive" },
    cancelled: { label: "Cancelled", variant: "outline" },
  }
  return map[status] ?? { label: status, variant: "outline" as const }
}

function statusDetail(job: MigrationJob) {
  const summary = summarizeError(job.last_error)
  const lowered = summary.toLowerCase()

  if (job.status === "cancelled") {
    if (
      lowered.includes("already on the target node") ||
      lowered.includes("already aligned")
    ) {
      return {
        label: "已對齊",
        category: "已取消",
        detail: "佇列項目已清除，因為目前不需要進行搬移。",
      }
    }
    if (lowered.includes("no longer has a desired target node")) {
      return {
        label: "無目標節點",
        category: "已取消",
        detail: "佇列項目已清除，因為這筆申請已失去目標節點。",
      }
    }
    if (lowered.includes("no longer has a vmid")) {
      return {
        label: "無 VMID",
        category: "已取消",
        detail: "佇列項目已清除，因為這筆申請已經沒有 VMID。",
      }
    }
    if (lowered.includes("no longer active")) {
      return {
        label: "非啟用時段",
        category: "已取消",
        detail: "佇列項目已清除，因為這筆申請已不在有效時段內。",
      }
    }
    if (lowered.includes("manually cancelled")) {
      return {
        label: "手動取消",
        category: "已取消",
        detail: "佇列項目已由管理員手動取消。",
      }
    }
    if (lowered.includes("no longer exists")) {
      return {
        label: "孤兒工作",
        category: "已取消",
        detail: "佇列項目對應的申請已不存在。",
      }
    }
  }

  if (job.status === "blocked") {
    return {
      label: "受阻",
      category: "受阻",
      detail:
        summary || "搬移受到目前的 VM 或儲存設定限制。",
    }
  }

  if (job.status === "failed") {
    return {
      label: "失敗",
      category: "失敗",
      detail: summary || "搬移過程發生執行錯誤。",
    }
  }

  if (job.status === "running") {
    return {
      label: "執行中",
      category: "執行中",
      detail: "搬移作業目前正在進行中。",
    }
  }

  if (job.status === "completed") {
    return {
      label: "已完成",
      category: "已完成",
      detail: "搬移已成功完成。",
    }
  }

  return {
    label: "等待中",
    category: "等待中",
    detail: "搬移已進入佇列，等待執行。",
  }
}

function formatDateTime(value?: string | null) {
  if (!value) return "-"
  return new Intl.DateTimeFormat("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "Asia/Taipei",
  }).format(new Date(value))
}

function formatDuration(start?: string | null, end?: string | null) {
  if (!start || !end) return "-"
  const startMs = new Date(start).getTime()
  const endMs = new Date(end).getTime()
  if (Number.isNaN(startMs) || Number.isNaN(endMs) || endMs < startMs) return "-"

  const totalSeconds = Math.round((endMs - startMs) / 1000)
  if (totalSeconds < 60) return `${totalSeconds}s`

  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`
}

function summarizeError(error?: string | null) {
  const text = String(error || "").trim()
  if (!text) return ""
  const firstLine = text.split("\n")[0]?.trim() || text
  return firstLine.replace(/\. Task log tail:.*$/s, "").trim()
}

function StatsPanel() {
  const { data: stats } = useQuery({
    queryKey: ["migration-jobs", "stats"],
    queryFn: () => MigrationJobsService.getStats(),
    refetchInterval: 30000,
  })

  if (!stats) return null

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div className="rounded-lg glass-panel p-3">
        <div className="text-2xl font-bold">{stats.total_jobs}</div>
        <div className="text-xs text-muted-foreground">Total jobs</div>
      </div>
      <div className="rounded-lg glass-panel p-3">
        <div className="text-2xl font-bold text-green-500">
          {stats.success_rate}%
        </div>
        <div className="text-xs text-muted-foreground">Success rate</div>
      </div>
      <div className="rounded-lg glass-panel p-3">
        <div className="text-2xl font-bold">
          {stats.avg_duration_seconds > 0
            ? `${stats.avg_duration_seconds.toFixed(0)}s`
            : "-"}
        </div>
        <div className="text-xs text-muted-foreground">Avg duration</div>
      </div>
      <div className="rounded-lg glass-panel p-3">
        <div className="flex flex-wrap gap-1.5">
          {stats.by_status.pending ? (
            <Badge variant="secondary">{stats.by_status.pending} pending</Badge>
          ) : null}
          {stats.by_status.running ? (
            <Badge variant="default">{stats.by_status.running} running</Badge>
          ) : null}
          {stats.by_status.failed ? (
            <Badge variant="destructive">{stats.by_status.failed} failed</Badge>
          ) : null}
          {stats.by_status.blocked ? (
            <Badge variant="destructive">{stats.by_status.blocked} blocked</Badge>
          ) : null}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">Status mix</div>
      </div>
    </div>
  )
}

function JobRow({ job }: { job: MigrationJob }) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const baseStatus = baseStatusMeta(job.status)
  const status = statusDetail(job)

  const retryMutation = useMutation({
    mutationFn: () => MigrationJobsService.retry({ jobId: job.id }),
    onSuccess: () => {
      showSuccessToast("Migration job retried")
      queryClient.invalidateQueries({ queryKey: ["migration-jobs"] })
    },
    onError: handleError.bind(showErrorToast),
  })

  const cancelMutation = useMutation({
    mutationFn: () => MigrationJobsService.cancel({ jobId: job.id }),
    onSuccess: () => {
      showSuccessToast("Migration job cancelled")
      queryClient.invalidateQueries({ queryKey: ["migration-jobs"] })
    },
    onError: handleError.bind(showErrorToast),
  })

  const canRetry = ["failed", "blocked", "cancelled"].includes(job.status)
  const canCancel = ["pending", "blocked", "failed"].includes(job.status)

  return (
    <tr className="border-b border-border/50 text-sm">
        <td className="px-3 py-2.5">
          <div className="font-mono text-xs text-muted-foreground">
            {job.id.slice(0, 8)}
          </div>
          {job.vmid != null && <div className="text-xs">VMID {job.vmid}</div>}
        </td>
        <td className="px-3 py-2.5">
          <div className="space-y-1">
            <Badge variant={baseStatus.variant}>{status.label}</Badge>
            {status.category !== status.label ? (
              <div className="text-[11px] text-muted-foreground">
                {status.category}
              </div>
            ) : null}
          </div>
        </td>
        <td className="px-3 py-2.5 text-xs">
          {`${job.source_node ?? "-"} -> ${job.target_node}`}
        </td>
        <td className="px-3 py-2.5 text-xs">{job.attempt_count}</td>
        <td className="px-3 py-2.5">
          <div className="max-w-[320px] space-y-1">
            <div className="text-xs text-foreground">{status.detail}</div>
            {job.last_error && summarizeError(job.last_error) !== status.detail ? (
              <div
                className="line-clamp-2 text-xs text-muted-foreground"
                title={job.last_error}
              >
                {summarizeError(job.last_error)}
              </div>
            ) : null}
            {job.status === "running" ? (
              <div className="text-xs text-muted-foreground">
                建立於 {formatDateTime(job.requested_at)}
              </div>
            ) : null}
            {job.status === "completed" ? (
              <div className="text-xs text-muted-foreground">
                耗時 {formatDuration(job.started_at, job.finished_at)}
              </div>
            ) : null}
          </div>
        </td>
        <td className="px-3 py-2.5 text-xs text-muted-foreground">
          {formatDateTime(job.requested_at)}
        </td>
        <td className="px-3 py-2.5 text-xs text-muted-foreground">
          {formatDateTime(job.finished_at)}
        </td>
        <td className="px-3 py-2.5">
          <div className="flex gap-1">
            {canRetry && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => retryMutation.mutate()}
                disabled={retryMutation.isPending}
                title="Retry"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            )}
            {canCancel && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-destructive"
                onClick={() => cancelMutation.mutate()}
                disabled={cancelMutation.isPending}
                title="Cancel"
              >
                <XCircle className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </td>
      </tr>
  )
}

function MigrationJobsPage() {
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [page, setPage] = useState(0)
  const limit = 20
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["migration-jobs", "list", statusFilter, page],
    queryFn: () =>
      MigrationJobsService.list({
        status:
          statusFilter === "all" ? null : (statusFilter as MigrationJobStatus),
        skip: page * limit,
        limit,
      }),
    refetchInterval: 15000,
  })

  const totalPages = data ? Math.ceil(data.count / limit) : 0

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 md:p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Migration Jobs</h1>
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            queryClient.invalidateQueries({ queryKey: ["migration-jobs"] })
          }
        >
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>

      <StatsPanel />

      <div className="flex items-center gap-3">
        <Select
          value={statusFilter}
          onValueChange={(value) => {
            setStatusFilter(value)
            setPage(0)
          }}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-sm text-muted-foreground">
          {data?.count ?? 0} jobs
        </span>
      </div>

      <div className="glass-panel overflow-x-auto rounded-lg">
        <table className="w-full">
          <thead>
            <tr className="border-b bg-white/15 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground dark:bg-white/5">
              <th className="px-3 py-2">Job</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Route</th>
              <th className="px-3 py-2">Attempt</th>
              <th className="px-3 py-2">說明</th>
              <th className="px-3 py-2">Requested</th>
              <th className="px-3 py-2">Finished</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td
                  colSpan={8}
                  className="px-3 py-8 text-center text-muted-foreground"
                >
                  Loading migration jobs...
                </td>
              </tr>
            ) : !data?.data.length ? (
              <tr>
                <td
                  colSpan={8}
                  className="px-3 py-8 text-center text-muted-foreground"
                >
                  No migration jobs found.
                </td>
              </tr>
            ) : (
              data.data.map((job) => <JobRow key={job.id} job={job} />)
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page === 0}
            onClick={() => setPage((current) => Math.max(0, current - 1))}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            {page + 1} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((current) => current + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  )
}
