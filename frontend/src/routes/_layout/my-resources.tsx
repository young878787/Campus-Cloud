import { useQueryClient, useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Monitor, RefreshCw } from "lucide-react"
import { Suspense, useCallback, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import { ResourcesService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import PendingItems from "@/components/Pending/PendingItems"
import { createColumns } from "@/components/Resources/columns"
import { TerminalConsoleDialog } from "@/components/Terminal"
import { Button } from "@/components/ui/button"
import { VNCConsoleDialog } from "@/components/VNC"

function getMyResourcesQueryOptions() {
  return {
    queryFn: () => ResourcesService.listMyResources(),
    queryKey: ["my-resources"],
  }
}

export const Route = createFileRoute("/_layout/my-resources")({
  component: MyResources,
  head: () => ({
    meta: [
      {
        title: "My Resources - Campus Cloud",
      },
    ],
  }),
})

function MyResourcesTableContent({
  onOpenConsole,
}: {
  onOpenConsole: (vmid: number, name: string, type: string) => void
}) {
  const { t } = useTranslation(["resources"])
  const navigate = useNavigate()
  const { data: resources } = useSuspenseQuery(getMyResourcesQueryOptions())

  const handleRowClick = useCallback(
    (vmid: number) => {
      navigate({ to: "/my-resources/$vmid", params: { vmid: vmid.toString() } })
    },
    [navigate],
  )

  const columns = useMemo(
    () => createColumns(t, onOpenConsole, handleRowClick),
    [t, onOpenConsole, handleRowClick],
  )

  if (resources.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center text-center py-12">
        <div className="rounded-full bg-muted p-4 mb-4">
          <Monitor className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold">
          {t("resources:page.noResources")}
        </h3>
        <p className="text-muted-foreground">
          {t("resources:page.noResourcesDescription")}
        </p>
      </div>
    )
  }

  return (
    <DataTable
      columns={columns}
      data={resources}
      onRowClick={(row) => handleRowClick(row.vmid)}
    />
  )
}

function MyResourcesTable({
  onOpenConsole,
}: {
  onOpenConsole: (vmid: number, name: string, type: string) => void
}) {
  return (
    <Suspense fallback={<PendingItems />}>
      <MyResourcesTableContent onOpenConsole={onOpenConsole} />
    </Suspense>
  )
}

function RefreshButton() {
  const { t } = useTranslation(["resources"])
  const queryClient = useQueryClient()

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["my-resources"] })
  }

  return (
    <Button variant="outline" onClick={handleRefresh}>
      <RefreshCw className="mr-2 h-4 w-4" />
      {t("resources:page.refresh")}
    </Button>
  )
}

function MyResources() {
  const { t } = useTranslation(["resources"])
  const [vncConsoleOpen, setVncConsoleOpen] = useState(false)
  const [terminalConsoleOpen, setTerminalConsoleOpen] = useState(false)
  const [selectedVM, setSelectedVM] = useState<{
    vmid: number
    name: string
    type: string
  } | null>(null)

  const handleOpenConsole = (vmid: number, name: string, type: string) => {
    setSelectedVM({ vmid, name, type })
    const isLxc = type === "lxc"
    setTerminalConsoleOpen(isLxc)
    setVncConsoleOpen(!isLxc)
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {t("resources:page.myResourcesTitle")}
          </h1>
          <p className="text-muted-foreground">
            {t("resources:page.myResourcesDescription")}
          </p>
        </div>
        <RefreshButton />
      </div>
      <MyResourcesTable onOpenConsole={handleOpenConsole} />
      <VNCConsoleDialog
        vmid={selectedVM?.type === "qemu" ? selectedVM.vmid : null}
        vmName={selectedVM?.name}
        open={vncConsoleOpen}
        onOpenChange={setVncConsoleOpen}
      />
      <TerminalConsoleDialog
        vmid={selectedVM?.type === "lxc" ? selectedVM.vmid : null}
        vmName={selectedVM?.name}
        open={terminalConsoleOpen}
        onOpenChange={setTerminalConsoleOpen}
      />
    </div>
  )
}
