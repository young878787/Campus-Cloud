import { useSuspenseQuery } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { useState } from "react"
import { useNavigate } from "@tanstack/react-router"

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
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

export default function OperationRecords() {
  const { t } = useTranslation("settings")
  const navigate = useNavigate()
  const [page, setPage] = useState(0)
  const limit = 50

  const { data: auditLogs, refetch } = useSuspenseQuery({
    queryKey: ["myAuditLogs", page],
    queryFn: () =>
      AuditLogsService.getMyAuditLogs({
        skip: page * limit,
        limit,
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

  const handleVmidClick = (vmid: number | null) => {
    if (vmid) {
      navigate({ to: "/resources/$vmid", params: { vmid: vmid.toString() } })
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("operationRecords.title")}</CardTitle>
        <CardDescription>
          {t("operationRecords.description")} - {t("admin.auditLogs.showing")} {auditLogs.count} {t("operationRecords.records")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {auditLogs.data.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            {t("operationRecords.noRecords")}
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("resourceDetail.auditLogs.time")}</TableHead>
                  <TableHead>{t("admin.auditLogs.vmid")}</TableHead>
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
                    <TableCell>
                      {log.vmid ? (
                        <button
                          type="button"
                          onClick={() => handleVmidClick(log.vmid)}
                          className="text-blue-600 hover:underline cursor-pointer"
                          title={t("operationRecords.clickToView")}
                        >
                          {log.vmid}
                        </button>
                      ) : (
                        "-"
                      )}
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
  )
}
