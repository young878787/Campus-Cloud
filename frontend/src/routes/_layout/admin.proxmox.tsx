import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import {
  AlertTriangle,
  CheckCircle,
  Database,
  HardDrive,
  Layers,
  Lock,
  RefreshCw,
  Save,
  Server,
  ShieldCheck,
  ShieldOff,
  Trash2,
  User,
  Wifi,
  WifiOff,
  XCircle,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { UsersService } from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"
import { request as __request } from "@/client/core/request"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { Separator } from "@/components/ui/separator"
import { Textarea } from "@/components/ui/textarea"

// ---- Types ----

interface ProxmoxConfigPublic {
  host: string
  user: string
  verify_ssl: boolean
  iso_storage: string
  data_storage: string
  api_timeout: number
  task_check_interval: number
  pool_name: string
  gateway_ip: string | null
  local_subnet: string | null
  default_node: string | null
  updated_at: string | null
  is_configured: boolean
  has_ca_cert: boolean
  ca_fingerprint: string | null
}

interface ProxmoxConfigUpdate {
  host: string
  user: string
  password?: string | null
  verify_ssl: boolean
  iso_storage: string
  data_storage: string
  api_timeout: number
  task_check_interval: number
  pool_name: string
  ca_cert?: string | null
  gateway_ip?: string | null
  local_subnet?: string | null
  default_node?: string | null
}

interface ProxmoxNodePublic {
  id?: number | null
  name: string
  host: string
  port: number
  is_primary: boolean
  is_online: boolean
  last_checked?: string | null
}

interface ClusterPreviewResult {
  success: boolean
  is_cluster: boolean
  nodes: ProxmoxNodePublic[]
  error?: string | null
}

interface ProxmoxConnectionTestResult {
  success: boolean
  message: string
}

interface CertParseResult {
  valid: boolean
  fingerprint: string | null
  subject: string | null
  issuer: string | null
  not_before: string | null
  not_after: string | null
  error: string | null
}

// ---- API Service ----

const ProxmoxConfigService = {
  getConfig: (): Promise<ProxmoxConfigPublic> =>
    __request(OpenAPI, { method: "GET", url: "/api/v1/proxmox-config/" }),

  updateConfig: (body: ProxmoxConfigUpdate): Promise<ProxmoxConfigPublic> =>
    __request(OpenAPI, {
      method: "PUT",
      url: "/api/v1/proxmox-config/",
      body,
      mediaType: "application/json",
    }),

  previewCluster: (body: ProxmoxConfigUpdate): Promise<ClusterPreviewResult> =>
    __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/proxmox-config/preview",
      body,
      mediaType: "application/json",
    }),

  syncNodes: (nodes: ProxmoxNodePublic[]): Promise<ProxmoxNodePublic[]> =>
    __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/proxmox-config/sync-nodes",
      body: nodes,
      mediaType: "application/json",
    }),

  getNodes: (): Promise<ProxmoxNodePublic[]> =>
    __request(OpenAPI, { method: "GET", url: "/api/v1/proxmox-config/nodes" }),

  checkNodes: (): Promise<ProxmoxNodePublic[]> =>
    __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/proxmox-config/check-nodes",
    }),

  testConnection: (): Promise<ProxmoxConnectionTestResult> =>
    __request(OpenAPI, { method: "POST", url: "/api/v1/proxmox-config/test" }),

  parseCert: (pem: string): Promise<CertParseResult> =>
    __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/proxmox-config/parse-cert",
      body: { pem },
      mediaType: "application/json",
    }),
}

// ---- Route ----

export const Route = createFileRoute("/_layout/admin/proxmox")({
  component: AdminProxmoxPage,
  beforeLoad: async () => {
    const user = await UsersService.readUserMe()
    if (!(user.role === "admin" || user.is_superuser)) {
      throw redirect({ to: "/" })
    }
  },
  head: () => ({
    meta: [{ title: "PVE 設定 - Campus Cloud" }],
  }),
})

// ---- Form type ----

interface FormData {
  host: string
  user: string
  password: string
  verify_ssl: boolean
  iso_storage: string
  data_storage: string
  api_timeout: number
  task_check_interval: number
  pool_name: string
  gateway_ip: string
  local_subnet: string
  default_node: string
}

// ---- Component ----

function AdminProxmoxPage() {
  const queryClient = useQueryClient()
  const [testResult, setTestResult] =
    useState<ProxmoxConnectionTestResult | null>(null)

  // CA cert state
  const [caCertInput, setCaCertInput] = useState("")
  const [certInfo, setCertInfo] = useState<CertParseResult | null>(null)
  const [isParsing, setIsParsing] = useState(false)
  const [caCertAction, setCaCertAction] = useState<
    "keep" | "clear" | "replace"
  >("keep")

  // Cluster confirm dialog
  const [dialogOpen, setDialogOpen] = useState(false)
  const [pendingFormData, setPendingFormData] = useState<FormData | null>(null)
  const [previewResult, setPreviewResult] =
    useState<ClusterPreviewResult | null>(null)
  const [isPreviewing, setIsPreviewing] = useState(false)

  const { data: config, isLoading } = useQuery({
    queryKey: ["proxmoxConfig"],
    queryFn: ProxmoxConfigService.getConfig,
  })

  const { data: nodes, isLoading: nodesLoading } = useQuery({
    queryKey: ["proxmoxNodes"],
    queryFn: ProxmoxConfigService.checkNodes,
  })

  const form = useForm<FormData>({
    defaultValues: {
      host: "",
      user: "",
      password: "",
      verify_ssl: false,
      iso_storage: "local",
      data_storage: "local-lvm",
      api_timeout: 30,
      task_check_interval: 2,
      pool_name: "CampusCloud",
      gateway_ip: "",
      local_subnet: "",
      default_node: "",
    },
  })

  useEffect(() => {
    if (config) {
      form.reset({
        host: config.host,
        user: config.user,
        password: "",
        verify_ssl: config.verify_ssl,
        iso_storage: config.iso_storage,
        data_storage: config.data_storage,
        api_timeout: config.api_timeout,
        task_check_interval: config.task_check_interval,
        pool_name: config.pool_name,
        gateway_ip: config.gateway_ip ?? "",
        local_subnet: config.local_subnet ?? "",
        default_node: config.default_node ?? "",
      })
    }
  }, [config, form])

  const handleCertInput = async (value: string) => {
    setCaCertInput(value)
    setCertInfo(null)
    setCaCertAction("replace")
    if (!value.trim()) {
      setCaCertAction("keep")
      return
    }
    if (!value.includes("BEGIN CERTIFICATE")) return
    setIsParsing(true)
    try {
      const result = await ProxmoxConfigService.parseCert(value.trim())
      setCertInfo(result)
    } catch {
      setCertInfo({
        valid: false,
        fingerprint: null,
        subject: null,
        issuer: null,
        not_before: null,
        not_after: null,
        error: "解析失敗",
      })
    } finally {
      setIsParsing(false)
    }
  }

  const handleClearCert = () => {
    setCaCertInput("")
    setCertInfo(null)
    setCaCertAction("clear")
  }

  const buildConfigPayload = (data: FormData): ProxmoxConfigUpdate => {
    let ca_cert: string | null | undefined
    if (caCertAction === "replace") {
      ca_cert = caCertInput.trim() || null
    } else if (caCertAction === "clear") {
      ca_cert = ""
    } else {
      ca_cert = null
    }
    return {
      host: data.host,
      user: data.user,
      password: data.password || null,
      verify_ssl: data.verify_ssl,
      iso_storage: data.iso_storage,
      data_storage: data.data_storage,
      api_timeout: data.api_timeout,
      task_check_interval: data.task_check_interval,
      pool_name: data.pool_name,
      ca_cert,
      gateway_ip: data.gateway_ip || null,
      local_subnet: data.local_subnet || null,
      default_node: data.default_node || null,
    }
  }

  const saveMutation = useMutation({
    mutationFn: async ({
      data,
      nodes,
    }: {
      data: FormData
      nodes: ProxmoxNodePublic[]
    }) => {
      await ProxmoxConfigService.updateConfig(buildConfigPayload(data))
      if (nodes.length > 0) {
        await ProxmoxConfigService.syncNodes(nodes)
      }
    },
    onSuccess: () => {
      toast.success("Proxmox 設定已儲存")
      setTestResult(null)
      setCaCertInput("")
      setCertInfo(null)
      setCaCertAction("keep")
      setDialogOpen(false)
      setPendingFormData(null)
      setPreviewResult(null)
      queryClient.invalidateQueries({ queryKey: ["proxmoxConfig"] })
      queryClient.invalidateQueries({ queryKey: ["proxmoxNodes"] })
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "儲存失敗，請稍後再試"
      toast.error(msg)
    },
  })

  const testMutation = useMutation({
    mutationFn: ProxmoxConfigService.testConnection,
    onSuccess: (result) => {
      setTestResult(result)
      if (result.success) toast.success(result.message)
      else toast.error(result.message)
    },
    onError: () => toast.error("測試請求失敗"),
  })

  const onSubmit = async (data: FormData) => {
    setIsPreviewing(true)
    try {
      const preview = await ProxmoxConfigService.previewCluster(
        buildConfigPayload(data),
      )
      if (!preview.success) {
        toast.error(`無法連線偵測節點：${preview.error}`)
        return
      }
      if (preview.is_cluster) {
        // 多節點：顯示確認 popup
        setPendingFormData(data)
        setPreviewResult(preview)
        setDialogOpen(true)
      } else {
        // 單節點：直接儲存
        saveMutation.mutate({ data, nodes: preview.nodes })
      }
    } catch {
      toast.error("偵測節點失敗，請確認設定後再試")
    } finally {
      setIsPreviewing(false)
    }
  }

  const handleConfirmSave = () => {
    if (!pendingFormData || !previewResult) return
    saveMutation.mutate({ data: pendingFormData, nodes: previewResult.nodes })
  }

  const isSaving = saveMutation.isPending
  const isSubmitting = isPreviewing || isSaving

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">PVE 主機設定</h1>
        <p className="text-muted-foreground">
          設定 Proxmox VE 主機的連線資訊，密碼將加密後儲存於資料庫。
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* 狀態 + 節點卡片 */}
        <div className="flex flex-col gap-4 lg:col-span-1">
          {/* 連線狀態 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Server className="h-4 w-4" />
                連線狀態
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex items-center gap-2">
                {isLoading ? (
                  <Badge variant="outline">載入中...</Badge>
                ) : config?.is_configured ? (
                  <Badge className="bg-green-500 hover:bg-green-600">
                    已設定
                  </Badge>
                ) : (
                  <Badge variant="destructive">未設定</Badge>
                )}
              </div>

              {config?.is_configured && (
                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Server className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{config.host}</span>
                  </div>
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <User className="h-3.5 w-3.5 shrink-0" />
                    <span>{config.user}</span>
                  </div>
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <HardDrive className="h-3.5 w-3.5 shrink-0" />
                    <span>ISO: {config.iso_storage}</span>
                  </div>
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Database className="h-3.5 w-3.5 shrink-0" />
                    <span>資料: {config.data_storage}</span>
                  </div>
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Layers className="h-3.5 w-3.5 shrink-0" />
                    <span>集區: {config.pool_name}</span>
                  </div>
                  {config.gateway_ip && (
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <Wifi className="h-3.5 w-3.5 shrink-0" />
                      <span>網關: {config.gateway_ip}</span>
                    </div>
                  )}
                  <div className="flex items-center gap-2 text-muted-foreground">
                    {config.has_ca_cert ? (
                      <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-green-500" />
                    ) : (
                      <ShieldOff className="h-3.5 w-3.5 shrink-0" />
                    )}
                    <span>
                      {config.has_ca_cert ? "已設定 CA 憑證" : "未設定 CA 憑證"}
                    </span>
                  </div>
                  {config.ca_fingerprint && (
                    <div className="rounded-md bg-muted p-2">
                      <p className="text-xs font-medium text-muted-foreground mb-1">
                        CA 指紋
                      </p>
                      <p className="break-all font-mono text-xs">
                        {config.ca_fingerprint}
                      </p>
                    </div>
                  )}
                  {config.updated_at && (
                    <p className="pt-1 text-xs text-muted-foreground">
                      最後更新：
                      {new Date(config.updated_at).toLocaleString("zh-TW")}
                    </p>
                  )}
                </div>
              )}

              <Separator />

              <Button
                variant="outline"
                size="sm"
                className="w-full"
                disabled={!config?.is_configured || testMutation.isPending}
                onClick={() => testMutation.mutate()}
              >
                {testMutation.isPending ? (
                  <>
                    <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" />
                    測試中...
                  </>
                ) : (
                  <>
                    <ShieldCheck className="mr-2 h-3.5 w-3.5" />
                    測試連線
                  </>
                )}
              </Button>

              {testResult && (
                <div
                  className={`flex items-start gap-2 rounded-md p-3 text-sm ${testResult.success ? "bg-green-50 text-green-800 dark:bg-green-950 dark:text-green-200" : "bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200"}`}
                >
                  {testResult.success ? (
                    <CheckCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  ) : (
                    <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  )}
                  <span>{testResult.message}</span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* 叢集節點清單：有節點資料或正在載入時顯示 */}
          {(nodesLoading || (nodes && nodes.length > 0)) && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Server className="h-4 w-4" />
                  叢集節點
                  {!nodesLoading && nodes && (
                    <Badge variant="outline" className="ml-auto">
                      {nodes.length} 台
                    </Badge>
                  )}
                  {nodesLoading && (
                    <div className="ml-auto h-5 w-10 animate-pulse rounded-full bg-muted" />
                  )}
                </CardTitle>
                <CardDescription>HA 模式會依序嘗試以下節點</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {nodesLoading
                  ? Array.from({ length: 3 }).map((_, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between rounded-md border p-2.5"
                      >
                        <div className="flex items-center gap-2">
                          <div className="h-3.5 w-3.5 animate-pulse rounded-full bg-muted" />
                          <div className="space-y-1.5">
                            <div className="h-3.5 w-20 animate-pulse rounded bg-muted" />
                            <div className="h-3 w-32 animate-pulse rounded bg-muted" />
                          </div>
                        </div>
                        <div className="h-5 w-10 animate-pulse rounded-full bg-muted" />
                      </div>
                    ))
                  : nodes!.map((node) => (
                      <div
                        key={node.id ?? node.name}
                        className="flex items-center justify-between rounded-md border p-2.5 text-sm"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          {node.is_online ? (
                            <Wifi className="h-3.5 w-3.5 shrink-0 text-green-500" />
                          ) : (
                            <WifiOff className="h-3.5 w-3.5 shrink-0 text-red-500" />
                          )}
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5">
                              <span className="font-medium">{node.name}</span>
                              {node.is_primary && (
                                <Badge
                                  variant="outline"
                                  className="text-xs px-1 py-0"
                                >
                                  主
                                </Badge>
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground truncate">
                              {node.host}:{node.port}
                            </p>
                          </div>
                        </div>
                        <Badge
                          variant={node.is_online ? "default" : "destructive"}
                          className={`text-xs shrink-0 ${node.is_online ? "bg-green-500 hover:bg-green-600" : ""}`}
                        >
                          {node.is_online ? "在線" : "離線"}
                        </Badge>
                      </div>
                    ))}
              </CardContent>
            </Card>
          )}
        </div>

        {/* 設定表單 */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">連線設定</CardTitle>
            <CardDescription>
              {config?.is_configured
                ? "更新 Proxmox 連線資訊。密碼欄位留空代表不更改。"
                : "填寫 Proxmox VE 主機連線資訊以完成初始設定。"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form
                onSubmit={form.handleSubmit(onSubmit)}
                className="space-y-4"
              >
                <FormField
                  control={form.control}
                  name="host"
                  rules={{ required: "請輸入主機位址" }}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        主機位址 <span className="text-destructive">*</span>
                      </FormLabel>
                      <FormControl>
                        <Input
                          placeholder="192.168.1.100 或 pve.example.com"
                          {...field}
                        />
                      </FormControl>
                      <FormDescription>
                        Proxmox VE 主機的 IP 或網域名稱（初始節點）
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="user"
                  rules={{ required: "請輸入 API 使用者" }}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        API 使用者 <span className="text-destructive">*</span>
                      </FormLabel>
                      <FormControl>
                        <Input placeholder="root@pam" {...field} />
                      </FormControl>
                      <FormDescription>
                        格式：username@realm（例如 root@pam）
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="password"
                  rules={{
                    required: config?.is_configured ? false : "請輸入密碼",
                  }}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        密碼
                        {!config?.is_configured && (
                          <span className="text-destructive"> *</span>
                        )}
                      </FormLabel>
                      <FormControl>
                        <div className="relative">
                          <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                          <Input
                            type="password"
                            placeholder={
                              config?.is_configured
                                ? "留空表示不更改密碼"
                                : "請輸入 API 密碼"
                            }
                            className="pl-9"
                            {...field}
                          />
                        </div>
                      </FormControl>
                      <FormDescription>
                        密碼將使用 Fernet 對稱加密後儲存
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="grid gap-4 sm:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="iso_storage"
                    rules={{ required: "請輸入 ISO 儲存區名稱" }}
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          ISO 儲存區 <span className="text-destructive">*</span>
                        </FormLabel>
                        <FormControl>
                          <Input placeholder="local" {...field} />
                        </FormControl>
                        <FormDescription>
                          存放 ISO 映像檔的儲存區
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="data_storage"
                    rules={{ required: "請輸入資料儲存區名稱" }}
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          資料儲存區 <span className="text-destructive">*</span>
                        </FormLabel>
                        <FormControl>
                          <Input placeholder="local-lvm" {...field} />
                        </FormControl>
                        <FormDescription>
                          存放 VM/LXC 磁碟的儲存區
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <FormField
                  control={form.control}
                  name="pool_name"
                  rules={{ required: "請輸入集區名稱" }}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        集區名稱（Pool）
                        <span className="text-destructive"> *</span>
                      </FormLabel>
                      <FormControl>
                        <div className="relative">
                          <Layers className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                          <Input
                            placeholder="CampusCloud"
                            className="pl-9"
                            {...field}
                          />
                        </div>
                      </FormControl>
                      <FormDescription>
                        僅顯示屬於此集區的 VM/LXC
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="gateway_ip"
                  rules={{ required: "請輸入網關地址" }}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        網關地址（Gateway IP）
                        <span className="text-destructive"> *</span>
                      </FormLabel>
                      <FormControl>
                        <Input placeholder="192.168.1.1" {...field} />
                      </FormControl>
                      <FormDescription>
                        防火牆拓撲中「Internet / 上網」節點所代表的網關 IP
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="local_subnet"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>本地網段（Local Subnet）</FormLabel>
                      <FormControl>
                        <Input placeholder="192.168.100.0/24" {...field} />
                      </FormControl>
                      <FormDescription>
                        新建容器/VM
                        預設封鎖出站至此網段，防止同網段互連。留空則不限制。
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="default_node"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>預設建立節點（Default Node）</FormLabel>
                      <FormControl>
                        <Input placeholder="pve1" {...field} />
                      </FormControl>
                      <FormDescription>
                        新建 LXC/VM 時優先選用的 Proxmox
                        節點名稱。留空則自動選取第一個可用節點。
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="grid gap-4 sm:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="api_timeout"
                    rules={{ required: true, min: 1 }}
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          API 逾時（秒）
                          <span className="text-destructive"> *</span>
                        </FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            min={1}
                            {...field}
                            onChange={(e) =>
                              field.onChange(Number(e.target.value))
                            }
                          />
                        </FormControl>
                        <FormDescription>
                          API 請求等待上限（預設 30 秒）
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="task_check_interval"
                    rules={{ required: true, min: 1 }}
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          任務輪詢間隔（秒）
                          <span className="text-destructive"> *</span>
                        </FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            min={1}
                            {...field}
                            onChange={(e) =>
                              field.onChange(Number(e.target.value))
                            }
                          />
                        </FormControl>
                        <FormDescription>
                          等待 Proxmox 任務完成的輪詢頻率
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                {/* CA 憑證 */}
                <div className="space-y-3 rounded-md border p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">CA 憑證（選填）</p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        設定後啟用 SSL 憑證驗證，防止中間人攻擊
                      </p>
                    </div>
                    {(config?.has_ca_cert || caCertAction === "replace") && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={handleClearCert}
                      >
                        <Trash2 className="mr-1 h-3.5 w-3.5" />
                        清除憑證
                      </Button>
                    )}
                  </div>

                  {config?.has_ca_cert && caCertAction === "keep" && (
                    <div className="rounded-md bg-green-50 dark:bg-green-950 p-3 text-sm">
                      <div className="flex items-center gap-2 text-green-700 dark:text-green-300 font-medium mb-1">
                        <ShieldCheck className="h-4 w-4" />
                        已設定 CA 憑證
                      </div>
                      {config.ca_fingerprint && (
                        <p className="font-mono text-xs break-all text-green-800 dark:text-green-200">
                          {config.ca_fingerprint}
                        </p>
                      )}
                      <p className="text-xs text-green-600 dark:text-green-400 mt-1">
                        貼上新憑證可覆蓋，或點擊「清除憑證」移除
                      </p>
                    </div>
                  )}

                  {caCertAction === "clear" && (
                    <div className="rounded-md bg-yellow-50 dark:bg-yellow-950 p-3 text-sm text-yellow-800 dark:text-yellow-200">
                      儲存後將移除 CA 憑證，SSL 驗證將依照下方勾選設定運作
                    </div>
                  )}

                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">
                      在 Proxmox 主機執行以下指令取得憑證：
                    </p>
                    <code className="block rounded bg-muted px-3 py-1.5 text-xs font-mono">
                      cat /etc/pve/pve-root-ca.pem
                    </code>
                  </div>

                  <Textarea
                    placeholder={
                      "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
                    }
                    className="font-mono text-xs min-h-[120px] resize-y"
                    value={caCertInput}
                    onChange={(e) => handleCertInput(e.target.value)}
                  />

                  {isParsing && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      解析憑證中...
                    </div>
                  )}

                  {certInfo && (
                    <div
                      className={`rounded-md p-3 text-sm space-y-1 ${certInfo.valid ? "bg-green-50 dark:bg-green-950" : "bg-red-50 dark:bg-red-950"}`}
                    >
                      {certInfo.valid ? (
                        <>
                          <div className="flex items-center gap-2 font-medium text-green-700 dark:text-green-300">
                            <CheckCircle className="h-4 w-4" />
                            憑證有效，請確認指紋與 PVE 介面一致後再儲存
                          </div>
                          <div className="mt-2 space-y-1 text-xs text-green-800 dark:text-green-200">
                            <div>
                              <span className="font-medium">
                                SHA-256 指紋：
                              </span>
                              <span className="font-mono break-all">
                                {certInfo.fingerprint}
                              </span>
                            </div>
                            {certInfo.subject && (
                              <div>
                                <span className="font-medium">主體：</span>
                                {certInfo.subject}
                              </div>
                            )}
                            {certInfo.not_before && certInfo.not_after && (
                              <div>
                                <span className="font-medium">有效期：</span>
                                {certInfo.not_before} ～ {certInfo.not_after}
                              </div>
                            )}
                          </div>
                        </>
                      ) : (
                        <div className="flex items-center gap-2 text-red-700 dark:text-red-300">
                          <XCircle className="h-4 w-4" />
                          憑證格式無效：{certInfo.error}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <FormField
                  control={form.control}
                  name="verify_ssl"
                  render={({ field }) => (
                    <FormItem className="flex items-start gap-3 space-y-0 rounded-md border p-4">
                      <FormControl>
                        <Checkbox
                          checked={field.value}
                          onCheckedChange={field.onChange}
                        />
                      </FormControl>
                      <div className="space-y-1">
                        <FormLabel className="font-normal">
                          驗證 SSL 憑證（備用）
                        </FormLabel>
                        <FormDescription>
                          已設定 CA 憑證時會優先使用 CA 憑證驗證，忽略此選項。
                          若 Proxmox 使用自簽憑證且未設定 CA 憑證，請取消勾選。
                        </FormDescription>
                      </div>
                    </FormItem>
                  )}
                />

                <div className="flex justify-end pt-2">
                  <LoadingButton
                    type="submit"
                    loading={isSubmitting}
                    disabled={
                      caCertAction === "replace" &&
                      certInfo !== null &&
                      !certInfo.valid
                    }
                    className="min-w-[120px]"
                  >
                    {isPreviewing ? (
                      <>
                        <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                        偵測節點中...
                      </>
                    ) : (
                      <>
                        <Save className="mr-2 h-4 w-4" />
                        儲存設定
                      </>
                    )}
                  </LoadingButton>
                </div>
              </form>
            </Form>
          </CardContent>
        </Card>
      </div>

      {/* 叢集確認 Dialog */}
      <Dialog
        open={dialogOpen}
        onOpenChange={(open) => {
          if (!isSaving) setDialogOpen(open)
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-yellow-500" />
              偵測到 Proxmox 叢集
            </DialogTitle>
            <DialogDescription>
              系統偵測到以下 {previewResult?.nodes.length}{" "}
              個節點。確認後將儲存設定並啟用 HA 自動切換。
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2 py-2">
            {previewResult?.nodes.map((node, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
              >
                <div className="flex items-center gap-2">
                  <Wifi className="h-3.5 w-3.5 text-green-500" />
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium">{node.name}</span>
                      {node.is_primary && (
                        <Badge variant="outline" className="text-xs px-1 py-0">
                          主節點
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {node.host}:{node.port}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-md bg-blue-50 dark:bg-blue-950 p-3 text-xs text-blue-800 dark:text-blue-200">
            連線時系統會先 TCP ping 各節點（2
            秒逾時），主節點無回應時自動切換至其他可用節點。
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDialogOpen(false)}
              disabled={isSaving}
            >
              取消
            </Button>
            <LoadingButton loading={isSaving} onClick={handleConfirmSave}>
              確認儲存
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
