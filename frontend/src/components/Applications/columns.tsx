import type { ColumnDef } from "@tanstack/react-table"
import type { TFunction } from "i18next"

import type { VMRequestPublic } from "@/client"
import { Badge } from "@/components/ui/badge"

function formatTemplateLabel(request: VMRequestPublic) {
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

function formatSpecLabel(request: VMRequestPublic) {
  const base = `${request.cores} Core / ${(request.memory / 1024).toFixed(1)} GB RAM`

  if (request.resource_type === "vm") {
    return `${base} / ${(request.disk_size ?? 0).toFixed(0)} GB Disk`
  }

  return `${base} / ${(request.rootfs_size ?? 0).toFixed(0)} GB Rootfs`
}

function formatScheduledRange(startAt?: string | null, endAt?: string | null) {
  if (!startAt || !endAt) return "未設定"

  const formatter = new Intl.DateTimeFormat("zh-TW", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    timeZone: "Asia/Taipei",
  })

  return `${formatter.format(new Date(startAt))} - ${formatter.format(new Date(endAt))}`
}

export const createMyRequestColumns = (
  t: TFunction<string, string>,
): ColumnDef<VMRequestPublic>[] => {
  const statusMap: Record<
    string,
    {
      label: string
      variant: "default" | "secondary" | "destructive" | "outline"
    }
  > = {
    pending: { label: t("applications:status.pending"), variant: "outline" },
    approved: { label: t("applications:status.approved"), variant: "default" },
    rejected: {
      label: t("applications:status.rejected"),
      variant: "destructive",
    },
  }

  return [
    {
      accessorKey: "hostname",
      header: t("applications:table.hostname"),
      cell: ({ row }) => (
        <span className="font-medium">{row.original.hostname}</span>
      ),
    },
    {
      accessorKey: "resource_type",
      header: t("applications:table.type"),
      cell: ({ row }) => (
        <Badge variant="secondary">
          {row.original.resource_type === "lxc"
            ? t("applications:types.lxc")
            : t("applications:types.qemu")}
        </Badge>
      ),
    },
    {
      id: "template",
      header: "作業系統 / 模板",
      cell: ({ row }) => (
        <div className="min-w-[180px] whitespace-normal">
          <div className="font-medium">{formatTemplateLabel(row.original)}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {row.original.os_info?.trim() || "未填寫作業系統資訊"}
          </div>
        </div>
      ),
    },
    {
      id: "formDetails",
      header: "表單資訊",
      cell: ({ row }) => (
        <div className="min-w-[190px] whitespace-normal text-sm">
          <div>{row.original.environment_type || "未設定環境類型"}</div>
          {row.original.resource_type === "vm" ? (
            <div className="mt-1 text-xs text-muted-foreground">
              使用者名稱：{row.original.username || "未填寫"}
            </div>
          ) : null}
          <div className="mt-1 text-xs text-muted-foreground">
            儲存：{row.original.storage || "未設定"}
          </div>
        </div>
      ),
    },
    {
      accessorKey: "reason",
      header: t("applications:table.reason"),
      cell: ({ row }) => (
        <span className="block max-w-[260px] whitespace-normal text-muted-foreground">
          {row.original.reason}
        </span>
      ),
    },
    {
      id: "specs",
      header: t("applications:table.specs"),
      cell: ({ row }) => (
        <span className="block min-w-[210px] whitespace-normal text-sm text-muted-foreground">
          {formatSpecLabel(row.original)}
        </span>
      ),
    },
    {
      id: "schedule",
      header: "申請時段",
      cell: ({ row }) => (
        <span className="block min-w-[210px] whitespace-normal text-sm text-muted-foreground">
          {formatScheduledRange(row.original.start_at, row.original.end_at)}
        </span>
      ),
    },
    {
      accessorKey: "status",
      header: t("applications:table.status"),
      cell: ({ row }) => {
        const s = statusMap[row.original.status] || statusMap.pending
        return <Badge variant={s.variant}>{s.label}</Badge>
      },
    },
    {
      accessorKey: "vmid",
      header: t("applications:table.vmid"),
      cell: ({ row }) => (
        <span className="text-muted-foreground">
          {row.original.vmid ?? "-"}
        </span>
      ),
    },
    {
      accessorKey: "created_at",
      header: t("applications:table.applicationTime"),
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">
          {new Date(row.original.created_at).toLocaleString("zh-TW")}
        </span>
      ),
    },
  ]
}

const noopT = ((key: string) => key) as TFunction

export const myRequestColumns: ColumnDef<VMRequestPublic>[] =
  createMyRequestColumns(noopT)
