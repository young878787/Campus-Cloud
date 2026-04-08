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
  { value: "all", label: "全部狀態" },
  { value: "pending", label: "等待中" },
  { value: "running", label: "執行中" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失敗" },
  { value: "blocked", label: "受阻" },
  { value: "cancelled", label: "已取消" },
]

function statusMeta(status: MigrationJobStatus) {
  const map: Record<
    MigrationJobStatus,
    {
      label: string
      variant: "default" | "secondary" | "destructive" | "outline"
    }
  > = {
    pending: { label: "等待中", variant: "secondary" },
    running: { label: "執行中", variant: "default" },
    completed: { label: "已完成", variant: "default" },
    failed: { label: "失敗", variant: "destructive" },
    blocked: { label: "受阻", variant: "destructive" },
    cancelled: { label: "已取消", variant: "outline" },
  }
  return map[status] ?? { label: status, variant: "outline" as const }
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
        <div className="text-xs text-muted-foreground">總 Jobs</div>
      </div>
      <div className="rounded-lg glass-panel p-3">
        <div className="text-2xl font-bold text-green-500">
          {stats.success_rate}%
        </div>
        <div className="text-xs text-muted-foreground">成功率</div>
      </div>
      <div className="rounded-lg glass-panel p-3">
        <div className="text-2xl font-bold">
          {stats.avg_duration_seconds > 0
            ? `${stats.avg_duration_seconds.toFixed(0)}s`
            : "-"}
        </div>
        <div className="text-xs text-muted-foreground">平均耗時</div>
      </div>
      <div className="rounded-lg glass-panel p-3">
        <div className="flex flex-wrap gap-1.5">
          {stats.by_status.pending ? (
            <Badge variant="secondary">{stats.by_status.pending} 等待</Badge>
          ) : null}
          {stats.by_status.running ? (
            <Badge variant="default">{stats.by_status.running} 執行</Badge>
          ) : null}
          {stats.by_status.failed ? (
            <Badge variant="destructive">{stats.by_status.failed} 失敗</Badge>
          ) : null}
          {stats.by_status.blocked ? (
            <Badge variant="destructive">{stats.by_status.blocked} 受阻</Badge>
          ) : null}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">狀態分佈</div>
      </div>
    </div>
  )
}

function JobRow({ job }: { job: MigrationJob }) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const status = statusMeta(job.status)

  const retryMutation = useMutation({
    mutationFn: () => MigrationJobsService.retry({ jobId: job.id }),
    onSuccess: () => {
      showSuccessToast("已重新排入佇列")
      queryClient.invalidateQueries({ queryKey: ["migration-jobs"] })
    },
    onError: handleError.bind(showErrorToast),
  })

  const cancelMutation = useMutation({
    mutationFn: () => MigrationJobsService.cancel({ jobId: job.id }),
    onSuccess: () => {
      showSuccessToast("已取消")
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
        <Badge variant={status.variant}>{status.label}</Badge>
      </td>
      <td className="px-3 py-2.5 text-xs">
        {job.source_node ?? "-"} → {job.target_node}
      </td>
      <td className="px-3 py-2.5 text-xs">{job.attempt_count}</td>
      <td className="px-3 py-2.5">
        {job.last_error ? (
          <div
            className="max-w-[200px] truncate text-xs text-destructive"
            title={job.last_error}
          >
            {job.last_error}
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">-</span>
        )}
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
              title="重試"
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
              title="取消"
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
          重新整理
        </Button>
      </div>

      <StatsPanel />

      <div className="flex items-center gap-3">
        <Select
          value={statusFilter}
          onValueChange={(v) => {
            setStatusFilter(v)
            setPage(0)
          }}
        >
          <SelectTrigger className="w-[160px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-sm text-muted-foreground">
          共 {data?.count ?? 0} 筆
        </span>
      </div>

      <div className="glass-panel overflow-x-auto rounded-lg">
        <table className="w-full">
          <thead>
            <tr className="border-b bg-white/15 dark:bg-white/5 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
              <th className="px-3 py-2">Job</th>
              <th className="px-3 py-2">狀態</th>
              <th className="px-3 py-2">搬移路徑</th>
              <th className="px-3 py-2">嘗試</th>
              <th className="px-3 py-2">錯誤</th>
              <th className="px-3 py-2">建立時間</th>
              <th className="px-3 py-2">完成時間</th>
              <th className="px-3 py-2">操作</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td
                  colSpan={8}
                  className="px-3 py-8 text-center text-muted-foreground"
                >
                  載入中...
                </td>
              </tr>
            ) : !data?.data.length ? (
              <tr>
                <td
                  colSpan={8}
                  className="px-3 py-8 text-center text-muted-foreground"
                >
                  沒有 migration jobs
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
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          >
            上一頁
          </Button>
          <span className="text-sm text-muted-foreground">
            {page + 1} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            下一頁
          </Button>
        </div>
      )}
    </div>
  )
}
