import { useSuspenseQuery } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { Server, Cpu, MemoryStick, Calendar, Package, Network } from "lucide-react"

import { ResourcesService } from "@/client"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

interface OverviewTabProps {
  vmid: number
}

export default function OverviewTab({ vmid }: OverviewTabProps) {
  const { t } = useTranslation("resourceDetail")

  const { data: resource } = useSuspenseQuery({
    queryKey: ["resource", vmid],
    queryFn: () => ResourcesService.getResource({ vmid }),
  })

  const getStatusBadge = (status: string) => {
    const statusConfig = {
      running: { variant: "default" as const, className: "bg-green-500 hover:bg-green-600 text-white" },
      stopped: { variant: "secondary" as const, className: "bg-gray-500 hover:bg-gray-600 text-white" },
      paused: { variant: "default" as const, className: "bg-yellow-500 hover:bg-yellow-600 text-white" },
    }
    return statusConfig[status as keyof typeof statusConfig] || statusConfig.stopped
  }

  const statusBadge = getStatusBadge(resource.status as string)

  return (
    <div className="space-y-6">
      {/* Basic Information */}
      <Card className="border-2">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Server className="h-5 w-5 text-muted-foreground" />
            <CardTitle>{t("overview.basicInfo")}</CardTitle>
          </div>
          <CardDescription>
            {t("overview.basicInfoDesc")}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {t("overview.vmid")}
            </div>
            <div className="text-2xl font-bold">{resource.vmid}</div>
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {t("overview.name")}
            </div>
            <div className="text-2xl font-bold truncate">{resource.name}</div>
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {t("overview.type")}
            </div>
            <div className="text-2xl font-bold uppercase">{resource.type}</div>
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {t("overview.status")}
            </div>
            <div className="pt-1">
              <Badge className={statusBadge.className} variant={statusBadge.variant}>
                {resource.status}
              </Badge>
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {t("overview.node")}
            </div>
            <div className="text-2xl font-bold">{resource.node}</div>
          </div>
          {resource.ip_address && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                <Network className="h-3 w-3" />
                {t("overview.ipAddress")}
              </div>
              <div className="text-2xl font-bold font-mono">{resource.ip_address}</div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Resource Configuration */}
      <Card className="border-2">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Package className="h-5 w-5 text-muted-foreground" />
            <CardTitle>{t("overview.resourceConfig")}</CardTitle>
          </div>
          <CardDescription>
            {t("overview.resourceConfigDesc")}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 md:grid-cols-2">
          <div className="flex items-start gap-4 p-4 rounded-lg bg-muted/50 border">
            <div className="p-2 rounded-md bg-primary/10">
              <Cpu className="h-6 w-6 text-primary" />
            </div>
            <div className="space-y-1">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                CPU
              </div>
              <div className="text-3xl font-bold">
                {resource.maxcpu}
              </div>
              <div className="text-sm text-muted-foreground">
                {t("overview.cores")}
              </div>
            </div>
          </div>
          <div className="flex items-start gap-4 p-4 rounded-lg bg-muted/50 border">
            <div className="p-2 rounded-md bg-primary/10">
              <MemoryStick className="h-6 w-6 text-primary" />
            </div>
            <div className="space-y-1">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                {t("overview.memory")}
              </div>
              <div className="text-3xl font-bold">
                {resource.maxmem ? (resource.maxmem / 1024 / 1024 / 1024).toFixed(2) : "N/A"}
              </div>
              <div className="text-sm text-muted-foreground">GB</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Environment Information */}
      {(resource.environment_type || resource.os_info || resource.expiry_date) && (
        <Card className="border-2">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Calendar className="h-5 w-5 text-muted-foreground" />
              <CardTitle>{t("overview.environmentInfo")}</CardTitle>
            </div>
            <CardDescription>
              {t("overview.environmentInfoDesc")}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {resource.environment_type && (
              <div className="space-y-1">
                <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {t("overview.environmentType")}
                </div>
                <div className="text-2xl font-bold">
                  {resource.environment_type}
                </div>
              </div>
            )}
            {resource.os_info && (
              <div className="space-y-1">
                <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {t("overview.osInfo")}
                </div>
                <div className="text-2xl font-bold">{resource.os_info}</div>
              </div>
            )}
            {resource.expiry_date && (
              <div className="space-y-1">
                <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {t("overview.expiryDate")}
                </div>
                <div className="text-2xl font-bold">
                  {new Date(resource.expiry_date).toLocaleDateString()}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
