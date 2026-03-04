import type { ColumnDef, TFunction } from "@tanstack/react-table"

import type { VMRequestPublic } from "@/client"
import { Badge } from "@/components/ui/badge"
import { ReviewActions } from "./ReviewActions"

export const createAdminRequestColumns = (
  t: TFunction<string, string>,
): ColumnDef<VMRequestPublic>[] => [
  {
    accessorKey: "user_full_name",
    header: t("approvals:review.applicant"),
    cell: ({ row }) => (
      <div className="flex flex-col">
        <span className="font-medium">
          {row.original.user_full_name || "N/A"}
        </span>
        <span className="text-xs text-muted-foreground">
          {row.original.user_email}
        </span>
      </div>
    ),
  },
  {
    accessorKey: "hostname",
    header: t("approvals:review.hostname"),
    cell: ({ row }) => (
      <span className="font-medium">{row.original.hostname}</span>
    ),
  },
  {
    accessorKey: "resource_type",
    header: t("approvals:review.type"),
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
    header: t("approvals:review.reason"),
    cell: ({ row }) => (
      <span className="text-muted-foreground line-clamp-2 max-w-[250px]">
        {row.original.reason}
      </span>
    ),
  },
  {
    accessorKey: "cores",
    header: t("approvals:review.specs"),
    cell: ({ row }) => (
      <span className="text-sm text-muted-foreground">
        {row.original.cores} Core / {(row.original.memory / 1024).toFixed(1)} GB
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
  {
    id: "actions",
    header: t("approvals:review.approve"),
    cell: ({ row }) => <ReviewActions request={row.original} />,
  },
]

export const adminRequestColumns: ColumnDef<VMRequestPublic>[] =
  createAdminRequestColumns(() => "")
