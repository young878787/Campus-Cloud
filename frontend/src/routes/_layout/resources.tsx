import { useQueryClient, useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Monitor, RefreshCw } from "lucide-react"
import { Suspense, useCallback, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { ResourcesService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import PendingItems from "@/components/Pending/PendingItems"
import CreateContainer from "@/components/Resources/CreateResources"
import { createColumns } from "@/components/Resources/columns"
import { TerminalConsoleDialog } from "@/components/Terminal"
import { Button } from "@/components/ui/button"
import { VNCConsoleDialog } from "@/components/VNC"

function getVMsQueryOptions() {
  return {
    queryFn: () => ResourcesService.listResources({}),
    queryKey: ["resources"],
  }
}

export const Route = createFileRoute("/_layout/resources")({
  component: VirtualMachines,
  head: () => ({
    meta: [
      {
        title: "Virtual Machines - Campus Cloud",
      },
    ],
  }),
})

function VMsTableContent({
  onOpenConsole,
}: {
  onOpenConsole: (vmid: number, name: string, type: string) => void
}) {
  const { t } = useTranslation(["resources"])
  const navigate = useNavigate()
  const { data: resources } = useSuspenseQuery(getVMsQueryOptions())

  const handleRowClick = useCallback(
    (vmid: number) => {
      navigate({ to: "/resources/$vmid", params: { vmid: vmid.toString() } })
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
        <h3 className="text-lg font-semibold">{t("resources:page.noVMs")}</h3>
        <p className="text-muted-foreground">
          {t("resources:page.noVMsDescription")}
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

function VMsTable({
  onOpenConsole,
}: {
  onOpenConsole: (vmid: number, name: string, type: string) => void
}) {
  return (
    <Suspense fallback={<PendingItems />}>
      <VMsTableContent onOpenConsole={onOpenConsole} />
    </Suspense>
  )
}

function RefreshButton() {
  const { t } = useTranslation(["resources"])
  const queryClient = useQueryClient()

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["resources"] })
  }

  return (
    <Button variant="outline" onClick={handleRefresh}>
      <RefreshCw className="mr-2 h-4 w-4" />
      {t("resources:page.refresh")}
    </Button>
  )
}

function VirtualMachines() {
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
    if (type === "lxc") {
      setTerminalConsoleOpen(true)
    } else {
      setVncConsoleOpen(true)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {t("resources:page.title")}
          </h1>
          <p className="text-muted-foreground">
            {t("resources:page.description")}
          </p>
        </div>
        <div className="flex gap-2">
          <CreateContainer />
          <RefreshButton />
        </div>
      </div>
      <VMsTable onOpenConsole={handleOpenConsole} />
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
