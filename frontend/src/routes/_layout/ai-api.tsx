import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import {
  CheckCircle2,
  Clock3,
  Copy,
  Eye,
  EyeOff,
  KeyRound,
  Link2,
  Pencil,
  RefreshCw,
  Save,
  Send,
  Trash2,
  X,
  XCircle,
} from "lucide-react"
import { type ReactNode, useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import useCustomToast from "@/hooks/useCustomToast"
import {
  type AiApiCredentialPublic,
  type AiApiRequestPublic,
  type AiApiRequestStatus,
  AiApiService,
} from "@/services/aiApi"
import { handleError } from "@/utils"

export const Route = createFileRoute("/_layout/ai-api")({
  component: AiApiPage,
  head: () => ({
    meta: [
      {
        title: "AI API - Campus Cloud",
      },
    ],
  }),
})

const DURATION_OPTIONS = [
  { value: "1h", label: "1 小時" },
  { value: "1d", label: "1 天" },
  { value: "7d", label: "1 週" },
  { value: "30d", label: "1 個月" },
  { value: "never", label: "永不過期" },
]

function formatTime(value?: string | null) {
  if (!value) return "尚未處理"
  return new Date(value).toLocaleString()
}

function formatExpiry(value?: string | null) {
  if (!value) return "永不過期"
  const d = new Date(value)
  const now = new Date()
  if (d < now) return `已過期（${d.toLocaleString()}）`
  return d.toLocaleString()
}

function isExpired(value?: string | null) {
  if (!value) return false
  return new Date(value) < new Date()
}

function maskApiKey(value: string) {
  if (value.length <= 14) return value
  return `${value.slice(0, 8)}••••••${value.slice(-6)}`
}

function requestStatusStyle(status: AiApiRequestStatus) {
  if (status === "approved") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
  }
  if (status === "rejected") {
    return "border-destructive/20 bg-destructive/10 text-destructive"
  }
  return "border-amber-500/20 bg-amber-500/10 text-amber-700"
}

function requestStatusLabel(status: AiApiRequestStatus) {
  if (status === "approved") return "已通過"
  if (status === "rejected") return "已拒絕"
  return "待審核"
}

function RequestStatusIcon({ status }: { status: AiApiRequestStatus }) {
  if (status === "approved") {
    return <CheckCircle2 className="h-3.5 w-3.5" />
  }
  if (status === "rejected") {
    return <XCircle className="h-3.5 w-3.5" />
  }
  return <Clock3 className="h-3.5 w-3.5" />
}

function StatPill({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-full border bg-background px-4 py-2">
      <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold leading-none">{value}</div>
    </div>
  )
}

function Panel({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <div className="rounded-2xl border bg-background/80 p-5 shadow-sm">
      <div className="mb-4 space-y-1">
        <div className="text-base font-semibold">{title}</div>
        {description ? (
          <div className="text-sm text-muted-foreground">{description}</div>
        ) : null}
      </div>
      {children}
    </div>
  )
}

function CredentialRow({
  item,
  onSuccess,
  onError,
}: {
  item: AiApiCredentialPublic
  onSuccess: (message: string) => void
  onError: (message: string) => void
}) {
  const queryClient = useQueryClient()
  const [showKey, setShowKey] = useState(false)
  const [editingName, setEditingName] = useState(false)
  const [nameInput, setNameInput] = useState(item.api_key_name)
  const isInactive = Boolean(item.revoked_at)
  const expired = isExpired(item.expires_at)

  const rotateMutation = useMutation({
    mutationFn: () =>
      AiApiService.rotateCredential({
        credentialId: item.id,
      }),
    onSuccess: () => {
      onSuccess("API Key 已刷新，請同步更新你的客戶端設定")
      queryClient.invalidateQueries({ queryKey: ["ai-api"] })
    },
    onError: handleError.bind(onError),
  })

  const deleteMutation = useMutation({
    mutationFn: () =>
      AiApiService.deleteCredential({
        credentialId: item.id,
      }),
    onSuccess: () => {
      onSuccess("API Key 已刪除")
      queryClient.invalidateQueries({ queryKey: ["ai-api"] })
    },
    onError: handleError.bind(onError),
  })

  const renameMutation = useMutation({
    mutationFn: () =>
      AiApiService.updateCredentialName({
        credentialId: item.id,
        requestBody: { api_key_name: nameInput.trim() },
      }),
    onSuccess: () => {
      onSuccess(`名稱已更新為「${nameInput.trim()}」`)
      setEditingName(false)
      queryClient.invalidateQueries({ queryKey: ["ai-api"] })
    },
    onError: handleError.bind(onError),
  })

  const copyValue = async (label: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value)
      onSuccess(label)
    } catch {
      onError(`${label}失敗`)
    }
  }

  const handleCancelRename = () => {
    setNameInput(item.api_key_name)
    setEditingName(false)
  }

  const statusBadge = (() => {
    if (isInactive)
      return { label: "已替換", cls: "border-muted-foreground/20 bg-muted text-muted-foreground" }
    if (expired)
      return { label: "已過期", cls: "border-destructive/20 bg-destructive/10 text-destructive" }
    return { label: "使用中", cls: "border-emerald-500/20 bg-emerald-500/10 text-emerald-700" }
  })()

  return (
    <div className="border-b py-4 last:border-b-0 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-3">
          {/* 名稱列 */}
          <div className="flex flex-wrap items-center gap-2">
            {editingName ? (
              <div className="flex items-center gap-2">
                <Input
                  id={`rename-input-${item.id}`}
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  maxLength={20}
                  className="h-7 w-44 text-sm font-medium"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === "Enter") renameMutation.mutate()
                    if (e.key === "Escape") handleCancelRename()
                  }}
                />
                <LoadingButton
                  loading={renameMutation.isPending}
                  size="sm"
                  variant="outline"
                  className="h-7 px-2"
                  onClick={() => renameMutation.mutate()}
                  disabled={nameInput.trim().length === 0}
                >
                  <Save className="h-3.5 w-3.5" />
                </LoadingButton>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2"
                  onClick={handleCancelRename}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-1.5">
                <div className="font-medium">{item.api_key_name}</div>
                <Button
                  id={`rename-btn-${item.id}`}
                  size="sm"
                  variant="ghost"
                  className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground"
                  onClick={() => {
                    setNameInput(item.api_key_name)
                    setEditingName(true)
                  }}
                >
                  <Pencil className="h-3 w-3" />
                </Button>
              </div>
            )}
            <span
              className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${statusBadge.cls}`}
            >
              {statusBadge.label}
            </span>
          </div>

          {/* Base URL & API Key */}
          <div className="grid gap-3 text-sm text-muted-foreground md:grid-cols-2">
            <div className="space-y-1">
              <div className="flex items-center gap-1.5 text-xs uppercase tracking-[0.16em]">
                <Link2 className="h-3.5 w-3.5" />
                Base URL
              </div>
              <div className="break-all font-mono text-foreground">
                {item.base_url}
              </div>
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-1.5 text-xs uppercase tracking-[0.16em]">
                <KeyRound className="h-3.5 w-3.5" />
                API Key
              </div>
              <div className="break-all font-mono text-foreground">
                {showKey ? item.api_key : maskApiKey(item.api_key)}
              </div>
            </div>
          </div>

          {/* Meta info */}
          <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground">
            <span>Key Prefix：{item.api_key_prefix}</span>
            <span>建立時間：{formatTime(item.created_at)}</span>
            <span className={expired ? "text-destructive font-medium" : ""}>
              過期時間：{formatExpiry(item.expires_at)}
            </span>
            {item.revoked_at ? (
              <span>失效時間：{formatTime(item.revoked_at)}</span>
            ) : null}
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setShowKey((previous) => !previous)}
          >
            {showKey ? (
              <EyeOff className="mr-1.5 h-4 w-4" />
            ) : (
              <Eye className="mr-1.5 h-4 w-4" />
            )}
            {showKey ? "隱藏" : "顯示"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => copyValue("Base URL 已複製", item.base_url)}
          >
            <Copy className="mr-1.5 h-4 w-4" />
            Base URL
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => copyValue("API Key 已複製", item.api_key)}
          >
            <Copy className="mr-1.5 h-4 w-4" />
            API Key
          </Button>
          <LoadingButton
            loading={rotateMutation.isPending}
            onClick={() => rotateMutation.mutate()}
            disabled={isInactive || deleteMutation.isPending}
            size="sm"
            variant="outline"
          >
            <RefreshCw className="mr-1.5 h-4 w-4" />
            刷新
          </LoadingButton>
          <LoadingButton
            loading={deleteMutation.isPending}
            onClick={() => deleteMutation.mutate()}
            disabled={rotateMutation.isPending}
            size="sm"
            variant="destructive"
          >
            <Trash2 className="mr-1.5 h-4 w-4" />
            刪除
          </LoadingButton>
        </div>
      </div>
    </div>
  )
}

function RequestRow({ item }: { item: AiApiRequestPublic }) {
  return (
    <div className="border-b py-4 last:border-b-0 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="font-medium">AI API 申請 - {item.api_key_name}</div>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${requestStatusStyle(
                item.status,
              )}`}
            >
              <RequestStatusIcon status={item.status} />
              {requestStatusLabel(item.status)}
            </span>
          </div>

          <div className="space-y-1">
            <div className="text-sm font-medium">用途</div>
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">
              {item.purpose}
            </p>
          </div>
        </div>

        <div className="min-w-56 space-y-2 text-sm text-muted-foreground">
          <div>申請時間：{formatTime(item.created_at)}</div>
          <div>審核時間：{formatTime(item.reviewed_at)}</div>
          {item.review_comment ? (
            <div>審核備註：{item.review_comment}</div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function AiApiPage() {
  const [purpose, setPurpose] = useState("")
  const [apiKeyName, setApiKeyName] = useState("test")
  const [duration, setDuration] = useState("never")
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const requestsQuery = useQuery({
    queryKey: ["ai-api", "my-requests"],
    queryFn: () => AiApiService.listMyRequests(),
  })

  const credentialsQuery = useQuery({
    queryKey: ["ai-api", "my-credentials"],
    queryFn: () => AiApiService.listMyCredentials(),
  })

  const createMutation = useMutation({
    mutationFn: () =>
      AiApiService.createRequest({
        requestBody: {
          purpose: purpose.trim(),
          api_key_name: apiKeyName.trim(),
          duration,
        },
      }),
    onSuccess: () => {
      setPurpose("")
      setApiKeyName("test")
      setDuration("never")
      showSuccessToast("AI API 申請已送出")
      queryClient.invalidateQueries({ queryKey: ["ai-api"] })
    },
    onError: handleError.bind(showErrorToast),
  })

  const requests = requestsQuery.data?.data ?? []
  const credentials = credentialsQuery.data?.data ?? []
  const activeCredentials = credentials.filter((item) => !item.revoked_at)
  const approvedRequests = requests.filter((item) => item.status === "approved")

  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-4">
        <div className="space-y-2">
          <div className="text-xs uppercase tracking-[0.22em] text-muted-foreground">
            Campus Cloud AI API
          </div>
          <h1 className="text-2xl font-bold tracking-tight">
            AI API 金鑰申請與管理
          </h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            這裡只負責核發專屬 API Key 與 Base
            URL。模型由你自己的客戶端決定，頁面則集中處理申請、查看、刷新與刪除。
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <StatPill label="申請紀錄" value={requests.length} />
          <StatPill label="使用中金鑰" value={activeCredentials.length} />
          <StatPill label="已通過申請" value={approvedRequests.length} />
        </div>
      </div>

      <Tabs defaultValue="request" className="space-y-5">
        <TabsList className="grid h-auto w-full grid-cols-3 p-1 md:w-[520px]">
          <TabsTrigger value="request">申請</TabsTrigger>
          <TabsTrigger value="keys">API Keys</TabsTrigger>
          <TabsTrigger value="history">申請紀錄</TabsTrigger>
        </TabsList>

        <TabsContent value="request" className="space-y-5">
          <Panel
            title="送出新申請"
            description="簡短描述你的使用目的，管理員審核後就會核發可直接使用的連線參數。"
          >
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">金鑰名稱</label>
                <Input
                  value={apiKeyName}
                  onChange={(event) => setApiKeyName(event.target.value)}
                  placeholder="例如：課程專案用、測試用、我的 App"
                  maxLength={20}
                />
                <p className="text-xs text-muted-foreground">
                  為你的金鑰取一個好辨識的名字（最多 20 字）。
                </p>
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium">申請目的</label>
                <Textarea
                  value={purpose}
                  onChange={(event) => setPurpose(event.target.value)}
                  placeholder="例如：課程專題串接聊天模型、工具原型開發、知識庫問答測試或自動化腳本整合。"
                  rows={5}
                />
              </div>

              {/* 過期時間選單 */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium">金鑰有效期限</label>
                <Select value={duration} onValueChange={setDuration}>
                  <SelectTrigger id="duration-select" className="w-48">
                    <SelectValue placeholder="選擇有效期限" />
                  </SelectTrigger>
                  <SelectContent>
                    {DURATION_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  金鑰核發後將從核發當下開始計算有效期。
                </p>
              </div>

              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="text-xs text-muted-foreground">
                  至少輸入 10 個字，方便管理員快速理解用途。
                </div>
                <LoadingButton
                  onClick={() => createMutation.mutate()}
                  loading={createMutation.isPending}
                  disabled={purpose.trim().length < 10}
                >
                  <Send className="mr-2 h-4 w-4" />
                  送出申請
                </LoadingButton>
              </div>
            </div>
          </Panel>

          <Panel
            title="使用提醒"
            description="這個頁面負責核發存取金鑰，不會替你綁定模型。"
          >
            <div className="grid gap-3 text-sm text-muted-foreground md:grid-cols-3">
              <div className="rounded-xl bg-muted/40 p-4">
                通過後會拿到固定的 Base URL 與系統產生的專屬 API Key。
              </div>
              <div className="rounded-xl bg-muted/40 p-4">
                如果你刷新 API Key，舊金鑰會立即變成已替換狀態。刷新後過期時間同步保留。
              </div>
              <div className="rounded-xl bg-muted/40 p-4">
                呼叫時要使用哪個 model，請在你的客戶端請求中自行帶入。
              </div>
            </div>
          </Panel>
        </TabsContent>

        <TabsContent value="keys" className="space-y-5">
          <Panel
            title="我的 API Keys"
            description="保留你現在正在使用的金鑰，需要換新時直接刷新即可。點擊名稱旁的鉛筆圖示可以隨時修改名稱。"
          >
            {credentials.length ? (
              <div>
                {credentials.map((item) => (
                  <CredentialRow
                    key={item.id}
                    item={item}
                    onSuccess={showSuccessToast}
                    onError={(message) =>
                      showErrorToast(`無法完成操作：${message}`)
                    }
                  />
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
                目前還沒有任何已核發的 AI API
                Key。當申請通過後，新的金鑰會出現在這裡。
              </div>
            )}
          </Panel>
        </TabsContent>

        <TabsContent value="history" className="space-y-5">
          <Panel
            title="申請紀錄"
            description="查看每筆申請目前是否仍在審核、已通過或已拒絕。"
          >
            {requests.length ? (
              <div>
                {requests.map((item) => (
                  <RequestRow key={item.id} item={item} />
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
                目前還沒有 AI API 申請紀錄。
              </div>
            )}
          </Panel>
        </TabsContent>
      </Tabs>
    </div>
  )
}
