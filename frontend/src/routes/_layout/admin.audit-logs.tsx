import { createFileRoute } from "@tanstack/react-router"
import { useSuspenseQuery } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { Suspense, useState } from "react"

import { AuditLogsService } from "@/client"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

export const Route = createFileRoute("/_layout/admin/audit-logs")({
  component: AdminAuditLogsPage,
})

function AdminAuditLogsPage() {
  const { t } = useTranslation("settings")
  const [vmidFilter, setVmidFilter] = useState<string>("")
  const [actionFilter, setActionFilter] = useState<string>("all")
  const [page, setPage] = useState(0)
  const limit = 50

  const { data: auditLogs, refetch } = useSuspenseQuery({
    queryKey: ["allAuditLogs", page, vmidFilter, actionFilter],
    queryFn: () =>
      AuditLogsService.getAllAuditLogs({
        skip: page * limit,
        limit,
        vmid: vmidFilter ? Number.parseInt(vmidFilter) : undefined,
        action: actionFilter !== "all" ? actionFilter : undefined,
      }),
  })

  const getActionBadgeColor = (action: string) => {
    if (action.includes("create")) return "bg-green-500"
    if (action.includes("delete")) return "bg-red-500"
    if (action.includes("update") || action.includes("spec_change")) return "bg-blue-500"
    if (action.includes("snapshot")) return "bg-purple-500"
    if (action.includes("request")) return "bg-orange-500"
    return "bg-gray-500"
  }

  const totalPages = Math.ceil(auditLogs.count / limit)

  return (
    <div className="container mx-auto py-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">{t("admin.auditLogs.title")}</h1>
        <p className="text-muted-foreground">
          {t("admin.auditLogs.description")}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("admin.auditLogs.allRecords")}</CardTitle>
          <CardDescription>
            {t("admin.auditLogs.showing")} {auditLogs.count} {t("admin.auditLogs.records")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* Filters */}
          <div className="mb-4 flex gap-4">
            <div className="flex-1">
              <Input
                placeholder={t("admin.auditLogs.filterByVMID")}
                value={vmidFilter}
                onChange={(e) => {
                  setVmidFilter(e.target.value)
                  setPage(0)
                }}
                type="number"
              />
            </div>
            <div className="w-[200px]">
              <Select
                value={actionFilter}
                onValueChange={(value) => {
                  setActionFilter(value)
                  setPage(0)
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t("admin.auditLogs.allActions")}</SelectItem>
                  <SelectItem value="vm_create">{t("resourceDetail.auditLogs.actions.vm_create")}</SelectItem>
                  <SelectItem value="lxc_create">{t("resourceDetail.auditLogs.actions.lxc_create")}</SelectItem>
                  <SelectItem value="resource_start">{t("resourceDetail.auditLogs.actions.resource_start")}</SelectItem>
                  <SelectItem value="resource_stop">{t("resourceDetail.auditLogs.actions.resource_stop")}</SelectItem>
                  <SelectItem value="resource_delete">{t("resourceDetail.auditLogs.actions.resource_delete")}</SelectItem>
                  <SelectItem value="snapshot_create">{t("resourceDetail.auditLogs.actions.snapshot_create")}</SelectItem>
                  <SelectItem value="spec_change_request">{t("resourceDetail.auditLogs.actions.spec_change_request")}</SelectItem>
                  <SelectItem value="user_create">{t("admin.auditLogs.userCreate")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button onClick={() => refetch()} variant="outline">
              {t("common.refresh")}
            </Button>
          </div>

          {/* Table */}
          {auditLogs.data.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              {t("resourceDetail.auditLogs.noRecords")}
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("resourceDetail.auditLogs.time")}</TableHead>
                    <TableHead>{t("admin.auditLogs.vmid")}</TableHead>
                    <TableHead>{t("resourceDetail.auditLogs.operator")}</TableHead>
                    <TableHead>{t("resourceDetail.auditLogs.action")}</TableHead>
                    <TableHead>{t("resourceDetail.auditLogs.details")}</TableHead>
                    <TableHead>{t("admin.auditLogs.ipAddress")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {auditLogs.data.map((log) => (
                    <TableRow key={log.id}>
                      <TableCell className="whitespace-nowrap">
                        {new Date(log.created_at).toLocaleString()}
                      </TableCell>
                      <TableCell>{log.vmid || "-"}</TableCell>
                      <TableCell>
                        <div>
                          <div className="font-medium">{log.user_full_name || "Unknown"}</div>
                          <div className="text-xs text-muted-foreground">{log.user_email}</div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge className={getActionBadgeColor(log.action)}>
                          {t(`resourceDetail.auditLogs.actions.${log.action}`, log.action)}
                        </Badge>
                      </TableCell>
                      <TableCell className="max-w-md truncate">{log.details}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {log.ip_address || "-"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="mt-4 flex items-center justify-between">
                  <div className="text-sm text-muted-foreground">
                    {t("admin.auditLogs.page")} {page + 1} / {totalPages}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      onClick={() => setPage(Math.max(0, page - 1))}
                      disabled={page === 0}
                    >
                      {t("common.previous")}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                      disabled={page >= totalPages - 1}
                    >
                      {t("common.next")}
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
