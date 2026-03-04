import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { FileText } from "lucide-react"
import { Suspense, useMemo } from "react"
import { useTranslation } from "react-i18next"

import { VmRequestsService } from "@/client"
import CreateVMRequest from "@/components/Applications/CreateVMRequest"
import { createMyRequestColumns } from "@/components/Applications/columns"
import { DataTable } from "@/components/Common/DataTable"
import PendingItems from "@/components/Pending/PendingItems"

function getMyRequestsQueryOptions() {
  return {
    queryFn: () => VmRequestsService.listMyVmRequests({}),
    queryKey: ["vm-requests"],
  }
}

export const Route = createFileRoute("/_layout/applications")({
  component: Applications,
  head: () => ({
    meta: [
      {
        title: "Applications - Campus Cloud",
      },
    ],
  }),
})

function RequestsTableContent() {
  const { t } = useTranslation(["applications"])
  const { data } = useSuspenseQuery(getMyRequestsQueryOptions())

  const columns = useMemo(() => createMyRequestColumns(t), [t])

  if (data.data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center text-center py-12">
        <div className="rounded-full bg-muted p-4 mb-4">
          <FileText className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold">
          {t("applications:page.noApplications")}
        </h3>
        <p className="text-muted-foreground">
          {t("applications:page.noApplicationsDescription")}
        </p>
      </div>
    )
  }

  return <DataTable columns={columns} data={data.data} />
}

function RequestsTable() {
  return (
    <Suspense fallback={<PendingItems />}>
      <RequestsTableContent />
    </Suspense>
  )
}

function Applications() {
  const { t } = useTranslation(["applications"])

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {t("applications:page.title")}
          </h1>
          <p className="text-muted-foreground">
            {t("applications:page.description")}
          </p>
        </div>
        <CreateVMRequest />
      </div>
      <RequestsTable />
    </div>
  )
}
