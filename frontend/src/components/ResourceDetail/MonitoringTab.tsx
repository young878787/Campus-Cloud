import { useSuspenseQuery } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { useState } from "react"
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts"

import { ResourceDetailsService } from "@/client"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

interface MonitoringTabProps {
  vmid: number
}

export default function MonitoringTab({ vmid }: MonitoringTabProps) {
  const { t } = useTranslation("resourceDetail")
  const [timeframe, setTimeframe] = useState<string>("hour")

  const { data: currentStats } = useSuspenseQuery({
    queryKey: ["currentStats", vmid],
    queryFn: () => ResourceDetailsService.getCurrentStats({ vmid }),
    refetchInterval: 5000, // Refresh every 5 seconds
  })

  const { data: rrdData } = useSuspenseQuery({
    queryKey: ["rrdStats", vmid, timeframe],
    queryFn: () => ResourceDetailsService.getRrdStats({ vmid, timeframe }),
    refetchInterval: 30000, // Refresh every 30 seconds
  })

  const formatBytes = (bytes: number | null | undefined) => {
    if (!bytes) return "0 B"
    const gb = bytes / 1024 / 1024 / 1024
    if (gb >= 1) return `${gb.toFixed(2)} GB`
    const mb = bytes / 1024 / 1024
    return `${mb.toFixed(2)} MB`
  }

  const formatPercentage = (value: number | null | undefined, max: number | null | undefined) => {
    if (!value || !max) return "0%"
    return `${((value / max) * 100).toFixed(1)}%`
  }

  const formatTimestamp = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleTimeString("zh-TW", {
      hour: "2-digit",
      minute: "2-digit",
    })
  }

  const formatChartData = () => {
    if (!rrdData?.data) return []

    return rrdData.data.map((point) => ({
      time: formatTimestamp(point.time),
      timestamp: point.time,
      cpu: point.cpu ? (point.cpu * 100).toFixed(2) : null,
      memory: point.mem && point.maxmem ? ((point.mem / point.maxmem) * 100).toFixed(2) : null,
      memoryGB: point.mem ? (point.mem / 1024 / 1024 / 1024).toFixed(2) : null,
      disk: point.disk && point.maxdisk ? ((point.disk / point.maxdisk) * 100).toFixed(2) : null,
      diskGB: point.disk ? (point.disk / 1024 / 1024 / 1024).toFixed(2) : null,
      netinMB: point.netin ? (point.netin / 1024 / 1024).toFixed(2) : null,
      netoutMB: point.netout ? (point.netout / 1024 / 1024).toFixed(2) : null,
    }))
  }

  const chartData = formatChartData()

  return (
    <div className="space-y-6">
      {/* Timeframe Selector */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">
          {t("monitoring.title")}
        </h3>
        <Select value={timeframe} onValueChange={setTimeframe}>
          <SelectTrigger className="w-[180px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="hour">{t("monitoring.hour")}</SelectItem>
            <SelectItem value="day">{t("monitoring.day")}</SelectItem>
            <SelectItem value="week">{t("monitoring.week")}</SelectItem>
            <SelectItem value="month">{t("monitoring.month")}</SelectItem>
            <SelectItem value="year">{t("monitoring.year")}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Current Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">CPU {t("monitoring.usage")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {currentStats.cpu ? `${(currentStats.cpu * 100).toFixed(1)}%` : "0%"}
            </div>
            <p className="text-xs text-muted-foreground">
              {currentStats.maxcpu} {t("overview.cores")}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              {t("overview.memory")} {t("monitoring.usage")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatPercentage(currentStats.mem, currentStats.maxmem)}
            </div>
            <p className="text-xs text-muted-foreground">
              {formatBytes(currentStats.mem)} / {formatBytes(currentStats.maxmem)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              {t("monitoring.disk")} {t("monitoring.usage")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatPercentage(currentStats.disk, currentStats.maxdisk)}
            </div>
            <p className="text-xs text-muted-foreground">
              {formatBytes(currentStats.disk)} / {formatBytes(currentStats.maxdisk)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              {t("monitoring.network")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-sm">
              <div className="flex justify-between">
                <span>{t("monitoring.in")}:</span>
                <span className="font-semibold">{formatBytes(currentStats.netin)}</span>
              </div>
              <div className="flex justify-between">
                <span>{t("monitoring.out")}:</span>
                <span className="font-semibold">{formatBytes(currentStats.netout)}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Historical Data Charts */}
      <Card>
        <CardHeader>
          <CardTitle>{t("monitoring.historicalData")}</CardTitle>
          <CardDescription>
            {t("monitoring.showing")} {rrdData?.data.length || 0} {t("monitoring.dataPoints")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="cpu" className="space-y-4">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="cpu">CPU</TabsTrigger>
              <TabsTrigger value="memory">{t("overview.memory")}</TabsTrigger>
              <TabsTrigger value="network">{t("monitoring.network")}</TabsTrigger>
            </TabsList>

            <TabsContent value="cpu" className="space-y-4">
              <div className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="colorCpu" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis
                      dataKey="time"
                      className="text-xs"
                      tick={{ fill: "hsl(var(--muted-foreground))" }}
                    />
                    <YAxis
                      className="text-xs"
                      tick={{ fill: "hsl(var(--muted-foreground))" }}
                      label={{ value: "%", position: "insideLeft" }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "hsl(var(--background))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "8px",
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="cpu"
                      stroke="hsl(var(--primary))"
                      strokeWidth={2}
                      fill="url(#colorCpu)"
                      name="CPU %"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </TabsContent>

            <TabsContent value="memory" className="space-y-4">
              <div className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="colorMemory" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis
                      dataKey="time"
                      className="text-xs"
                      tick={{ fill: "hsl(var(--muted-foreground))" }}
                    />
                    <YAxis
                      className="text-xs"
                      tick={{ fill: "hsl(var(--muted-foreground))" }}
                      label={{ value: "%", position: "insideLeft" }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "hsl(var(--background))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "8px",
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="memory"
                      stroke="#10b981"
                      strokeWidth={2}
                      fill="url(#colorMemory)"
                      name="Memory %"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </TabsContent>

            <TabsContent value="network" className="space-y-4">
              <div className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis
                      dataKey="time"
                      className="text-xs"
                      tick={{ fill: "hsl(var(--muted-foreground))" }}
                    />
                    <YAxis
                      className="text-xs"
                      tick={{ fill: "hsl(var(--muted-foreground))" }}
                      label={{ value: "MB", position: "insideLeft" }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "hsl(var(--background))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "8px",
                      }}
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="netinMB"
                      stroke="#3b82f6"
                      strokeWidth={2}
                      name={t("monitoring.in")}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="netoutMB"
                      stroke="#ef4444"
                      strokeWidth={2}
                      name={t("monitoring.out")}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  )
}
