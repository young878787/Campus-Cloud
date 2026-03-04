import type { ColumnDef, TFunction } from "@tanstack/react-table"

import type { VMRequestPublic } from "@/client"
import { Badge } from "@/components/ui/badge"

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
      accessorKey: "reason",
      header: t("applications:table.reason"),
      cell: ({ row }) => (
        <span className="text-muted-foreground line-clamp-2 max-w-[300px]">
          {row.original.reason}
        </span>
      ),
    },
    {
      accessorKey: "cores",
      header: t("applications:table.specs"),
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">
          {row.original.cores} Core / {(row.original.memory / 1024).toFixed(1)}{" "}
          GB
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
        <span className="text-muted-foreground text-sm">
          {new Date(row.original.created_at).toLocaleString("zh-TW")}
        </span>
      ),
    },
  ]
}

export const myRequestColumns: ColumnDef<VMRequestPublic>[] =
  createMyRequestColumns(() => "")
