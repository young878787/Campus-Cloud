import {
  useMutation,
  useQuery,
  useQueryClient,
  useSuspenseQuery,
} from "@tanstack/react-query"

import { createFileRoute, Link, redirect } from "@tanstack/react-router"
import {
  ArrowLeft,
  CheckCircle2,
  Circle,
  Loader2,
  Plus,
  ServerCog,
  Upload,
  UserMinus,
  XCircle,
} from "lucide-react"
import { Suspense, useCallback, useEffect, useRef, useState } from "react"
import { useForm } from "react-hook-form"

import { GroupsService, LxcService, OpenAPI, UsersService, VmService } from "@/client"
import { request as __request } from "@/client/core/request"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useCustomToast from "@/hooks/useCustomToast"

// ─── Types ────────────────────────────────────────────────────────────────────

type CsvImportResult = {
  created: string[]
  already_existed: string[]
  added_to_group: number
  errors: string[]
}

type TaskStatus = "pending" | "running" | "completed" | "failed"

type BatchTask = {
  id: string
  user_id: string
  user_email: string | null
  user_name: string | null
  member_index: number
  vmid: number | null
  status: TaskStatus
  error: string | null
  started_at: string | null
  finished_at: string | null
}

type BatchJob = {
  id: string
  group_id: string
  resource_type: string
  hostname_prefix: string
  status: "pending" | "running" | "completed" | "failed"
  total: number
  done: number
  failed_count: number
  created_at: string
  finished_at: string | null
  tasks: BatchTask[]
}

// ─── Route ────────────────────────────────────────────────────────────────────

export const Route = createFileRoute("/_layout/groups_/$groupId")({
  component: GroupDetailPage,
  beforeLoad: async () => {
    const user = await UsersService.readUserMe()
    if (!(user.role === "admin" || user.is_superuser)) {
      throw redirect({ to: "/" })
    }
  },
  head: () => ({
    meta: [{ title: "群組詳情 - Campus Cloud" }],
  }),
})

// ─── Helpers ──────────────────────────────────────────────────────────────────

function TaskStatusIcon({ status }: { status: TaskStatus }) {
  if (status === "completed")
    return <CheckCircle2 className="h-4 w-4 text-green-500" />
  if (status === "failed") return <XCircle className="h-4 w-4 text-destructive" />
  if (status === "running")
    return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
  return <Circle className="h-4 w-4 text-muted-foreground" />
}

function ProgressBar({ done, total }: { done: number; total: number }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  return (
    <div className="w-full rounded-full bg-muted h-2 overflow-hidden">
      <div
        className="h-full bg-primary transition-all duration-300"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

// ─── Import CSV Dialog ────────────────────────────────────────────────────────

function ImportCsvDialog({ groupId }: { groupId: string }) {
  const [open, setOpen] = useState(false)
  const [result, setResult] = useState<CsvImportResult | null>(null)
  const [loading, setLoading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const handleImport = async () => {
    const file = fileRef.current?.files?.[0]
    if (!file) return
    setLoading(true)
    setResult(null)
    try {
      const data = await __request<CsvImportResult>(OpenAPI, {
        method: "POST",
        url: `/api/v1/groups/${groupId}/import-csv`,
        formData: { file },
      })
      setResult(data)
      queryClient.invalidateQueries({ queryKey: ["group", groupId] })
      showSuccessToast(
        `匯入完成：新建 ${data.created.length} 人，加入群組 ${data.added_to_group} 人`,
      )
    } catch (err: any) {
      showErrorToast(err?.body?.detail ?? "匯入失敗")
    } finally {
      setLoading(false)
    }
  }

  const handleOpenChange = (v: boolean) => {
    setOpen(v)
    if (!v) {
      setResult(null)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Upload className="mr-1 h-4 w-4" />
          匯入 CSV
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>從 CSV 大量匯入學生</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <p className="text-sm text-muted-foreground">
            CSV 格式：學號, 姓名, 班級（支援 Big5 / UTF-8）。
            帳號不存在時自動建立，email 為 <code>學號@ntub.edu.tw</code>
            ，系統將寄送通知信。
          </p>
          <div className="grid gap-2">
            <Label htmlFor="csv-file">選擇 CSV 檔案</Label>
            <input
              id="csv-file"
              type="file"
              accept=".csv"
              ref={fileRef}
              className="text-sm file:mr-2 file:rounded file:border-0 file:bg-muted file:px-3 file:py-1 file:text-sm"
            />
          </div>
          {result && (
            <div className="rounded border bg-muted/40 p-3 text-sm space-y-1">
              <p>
                ✅ 新建帳號：<strong>{result.created.length}</strong> 人
              </p>
              <p>
                ℹ️ 帳號已存在：<strong>{result.already_existed.length}</strong>{" "}
                人
              </p>
              <p>
                👥 加入群組：<strong>{result.added_to_group}</strong> 人
              </p>
              {result.errors.length > 0 && (
                <div className="text-destructive">
                  <p>❌ 錯誤（{result.errors.length}）：</p>
                  <ul className="ml-4 list-disc text-xs">
                    {result.errors.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" disabled={loading}>
              關閉
            </Button>
          </DialogClose>
          <LoadingButton loading={loading} onClick={handleImport}>
            匯入
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─── Add Members Dialog ───────────────────────────────────────────────────────

function AddMembersDialog({ groupId }: { groupId: string }) {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { register, handleSubmit, reset } = useForm<{ emailsText: string }>()

  const mutation = useMutation({
    mutationFn: (emails: string[]) =>
      GroupsService.addMembers({ groupId, requestBody: { emails } }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["group", groupId] })
      if (data.message.includes("Not found:")) {
        showErrorToast(data.message)
      } else {
        showSuccessToast(data.message)
        reset()
        setOpen(false)
      }
    },
    onError: (err: any) => showErrorToast(err?.body?.detail ?? "加入成員失敗"),
  })

  const onSubmit = ({ emailsText }: { emailsText: string }) => {
    const emails = emailsText
      .split(/[\n,]/)
      .map((e) => e.trim())
      .filter(Boolean)
    mutation.mutate(emails)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Plus className="mr-1 h-4 w-4" />
          加入成員
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>加入成員</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Email 列表（每行一個或逗號分隔）</Label>
              <textarea
                {...register("emailsText", { required: true })}
                placeholder={"student1@example.com\nstudent2@example.com"}
                rows={6}
                className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              />
            </div>
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline" disabled={mutation.isPending}>
                取消
              </Button>
            </DialogClose>
            <LoadingButton type="submit" loading={mutation.isPending}>
              加入
            </LoadingButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ─── Batch Provision Dialog ───────────────────────────────────────────────────

function BatchProvisionDialog({
  groupId,
  memberCount,
}: {
  groupId: string
  memberCount: number
}) {
  const [open, setOpen] = useState(false)
  const [resourceType, setResourceType] = useState<"lxc" | "qemu">("lxc")
  const [jobId, setJobId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const { showErrorToast } = useCustomToast()

  // form state
  const [hostnamePrefix, setHostnamePrefix] = useState("")
  const [password, setPassword] = useState("")
  const [cores, setCores] = useState(2)
  const [memory, setMemory] = useState(2048)
  const [rootfsSize, setRootfsSize] = useState(8)
  const [diskSize, setDiskSize] = useState(20)
  const [ostemplate, setOstemplate] = useState("")
  const [templateId, setTemplateId] = useState<number | null>(null)
  const [username, setUsername] = useState("")
  const [expiryDate, setExpiryDate] = useState("")

  const { data: lxcTemplates } = useQuery({
    queryKey: ["lxc-templates"],
    queryFn: () => LxcService.getTemplates(),
    enabled: open && resourceType === "lxc",
  })

  const { data: vmTemplates } = useQuery({
    queryKey: ["vm-templates"],
    queryFn: () => VmService.getVmTemplates(),
    enabled: open && resourceType === "qemu",
  })

  // 輪詢進度
  const {
    data: jobStatus,
    isLoading: jobLoading,
  } = useQuery<BatchJob>({
    queryKey: ["batch-job", jobId],
    queryFn: () =>
      __request<BatchJob>(OpenAPI, {
        method: "GET",
        url: `/api/v1/batch-provision/${jobId}/status`,
      }),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === "completed" || status === "failed") return false
      return 2000
    },
  })

  const isRunning =
    jobStatus?.status === "pending" || jobStatus?.status === "running"

  const handleSubmit = async () => {
    if (!hostnamePrefix.trim() || !password) return
    if (resourceType === "lxc" && !ostemplate) return
    if (resourceType === "qemu" && (!templateId || !username.trim())) return

    setSubmitting(true)
    try {
      const body: Record<string, any> = {
        resource_type: resourceType,
        hostname_prefix: hostnamePrefix.trim(),
        password,
        cores,
        memory,
        environment_type: "批量建立",
      }
      if (expiryDate) body.expiry_date = expiryDate
      if (resourceType === "lxc") {
        body.ostemplate = ostemplate
        body.rootfs_size = rootfsSize
      } else {
        body.template_id = templateId
        body.username = username.trim()
        body.disk_size = diskSize
      }

      const job = await __request<BatchJob>(OpenAPI, {
        method: "POST",
        url: `/api/v1/batch-provision/${groupId}`,
        body,
      })
      setJobId(job.id)
    } catch (err: any) {
      showErrorToast(err?.body?.detail ?? "批量建立失敗")
    } finally {
      setSubmitting(false)
    }
  }

  const handleOpenChange = (v: boolean) => {
    if (isRunning) return // 執行中不允許關閉
    setOpen(v)
    if (!v) {
      setJobId(null)
      setHostnamePrefix("")
      setPassword("")
      setCores(2)
      setMemory(2048)
      setOstemplate("")
      setTemplateId(null)
      setUsername("")
      setExpiryDate("")
    }
  }

  const pct =
    jobStatus && jobStatus.total > 0
      ? Math.round((jobStatus.done / jobStatus.total) * 100)
      : 0

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm">
          <ServerCog className="mr-1 h-4 w-4" />
          批量建立資源
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>批量建立資源</DialogTitle>
        </DialogHeader>

        {!jobId ? (
          /* ── 表單 ── */
          <div className="space-y-5 py-2">
            <p className="text-sm text-muted-foreground">
              將為群組 <strong>{memberCount}</strong>{" "}
              位成員各自建立一台資源，並自動分配給對應帳號。
              Hostname 會自動加上流水號（例如 <code>webdev-1</code>、
              <code>webdev-2</code>…）。
            </p>

            <Tabs
              value={resourceType}
              onValueChange={(v) => setResourceType(v as "lxc" | "qemu")}
            >
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="lxc">LXC 容器</TabsTrigger>
                <TabsTrigger value="qemu">VM 虛擬機</TabsTrigger>
              </TabsList>

              {/* ── LXC ── */}
              <TabsContent value="lxc" className="mt-4 space-y-4">
                <div className="grid gap-2">
                  <Label>
                    Hostname 前綴 <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    placeholder="webdev"
                    value={hostnamePrefix}
                    onChange={(e) => setHostnamePrefix(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    實際 hostname：{hostnamePrefix || "prefix"}-1、
                    {hostnamePrefix || "prefix"}-2…
                  </p>
                </div>

                <div className="grid gap-2">
                  <Label>
                    OS Template <span className="text-destructive">*</span>
                  </Label>
                  <Select value={ostemplate} onValueChange={setOstemplate}>
                    <SelectTrigger>
                      <SelectValue placeholder="選擇 OS 模板" />
                    </SelectTrigger>
                    <SelectContent>
                      {lxcTemplates?.map((t) => (
                        <SelectItem key={t.volid} value={t.volid}>
                          {t.volid.split("/").pop()?.replace(".tar.zst", "")}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid gap-2">
                  <Label>
                    Root 密碼 <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    type="password"
                    placeholder="統一密碼"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>

                <div className="grid gap-2">
                  <Label>到期日</Label>
                  <Input
                    type="date"
                    value={expiryDate}
                    onChange={(e) => setExpiryDate(e.target.value)}
                  />
                </div>

                <div className="rounded-xl border bg-muted/20 p-4 space-y-4">
                  <p className="text-sm font-medium">硬體規格</p>
                  <div className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span>CPU</span>
                      <span className="font-semibold text-primary">
                        {cores} Cores
                      </span>
                    </div>
                    <Slider
                      min={1} max={8} step={1}
                      value={[cores]}
                      onValueChange={([v]) => setCores(v)}
                    />
                  </div>
                  <div className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span>記憶體</span>
                      <span className="font-semibold text-primary">
                        {(memory / 1024).toFixed(1)} GB
                      </span>
                    </div>
                    <Slider
                      min={512} max={32768} step={512}
                      value={[memory]}
                      onValueChange={([v]) => setMemory(v)}
                    />
                  </div>
                  <div className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span>磁碟</span>
                      <span className="font-semibold text-primary">
                        {rootfsSize} GB
                      </span>
                    </div>
                    <Slider
                      min={8} max={500} step={1}
                      value={[rootfsSize]}
                      onValueChange={([v]) => setRootfsSize(v)}
                    />
                  </div>
                </div>
              </TabsContent>

              {/* ── VM ── */}
              <TabsContent value="qemu" className="mt-4 space-y-4">
                <div className="grid gap-2">
                  <Label>
                    Hostname 前綴 <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    placeholder="lab-vm"
                    value={hostnamePrefix}
                    onChange={(e) => setHostnamePrefix(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    實際 hostname：{hostnamePrefix || "prefix"}-1、
                    {hostnamePrefix || "prefix"}-2…
                  </p>
                </div>

                <div className="grid gap-2">
                  <Label>
                    OS Template <span className="text-destructive">*</span>
                  </Label>
                  <Select
                    value={templateId?.toString() ?? ""}
                    onValueChange={(v) => setTemplateId(Number(v))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="選擇 VM 模板" />
                    </SelectTrigger>
                    <SelectContent>
                      {vmTemplates?.map((t) => (
                        <SelectItem key={t.vmid} value={t.vmid.toString()}>
                          {t.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="grid gap-2">
                    <Label>
                      用戶名 <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      placeholder="student"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label>
                      密碼 <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      type="password"
                      placeholder="統一密碼"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </div>
                </div>

                <div className="grid gap-2">
                  <Label>到期日</Label>
                  <Input
                    type="date"
                    value={expiryDate}
                    onChange={(e) => setExpiryDate(e.target.value)}
                  />
                </div>

                <div className="rounded-xl border bg-muted/20 p-4 space-y-4">
                  <p className="text-sm font-medium">硬體規格</p>
                  <div className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span>CPU</span>
                      <span className="font-semibold text-primary">
                        {cores} Cores
                      </span>
                    </div>
                    <Slider
                      min={1} max={8} step={1}
                      value={[cores]}
                      onValueChange={([v]) => setCores(v)}
                    />
                  </div>
                  <div className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span>記憶體</span>
                      <span className="font-semibold text-primary">
                        {(memory / 1024).toFixed(1)} GB
                      </span>
                    </div>
                    <Slider
                      min={512} max={32768} step={512}
                      value={[memory]}
                      onValueChange={([v]) => setMemory(v)}
                    />
                  </div>
                  <div className="space-y-1">
                    <div className="flex justify-between text-sm">
                      <span>磁碟</span>
                      <span className="font-semibold text-primary">
                        {diskSize} GB
                      </span>
                    </div>
                    <Slider
                      min={20} max={500} step={1}
                      value={[diskSize]}
                      onValueChange={([v]) => setDiskSize(v)}
                    />
                  </div>
                </div>
              </TabsContent>
            </Tabs>

            <DialogFooter className="pt-2">
              <DialogClose asChild>
                <Button variant="outline" disabled={submitting}>
                  取消
                </Button>
              </DialogClose>
              <LoadingButton
                loading={submitting}
                onClick={handleSubmit}
                disabled={
                  !hostnamePrefix.trim() ||
                  !password ||
                  (resourceType === "lxc" && !ostemplate) ||
                  (resourceType === "qemu" && (!templateId || !username.trim()))
                }
              >
                開始批量建立（{memberCount} 台）
              </LoadingButton>
            </DialogFooter>
          </div>
        ) : (
          /* ── 進度追蹤 ── */
          <div className="space-y-4 py-2">
            {/* 總覽 */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">
                  {jobStatus?.done ?? 0} / {jobStatus?.total ?? memberCount} 台完成
                </span>
                <div className="flex items-center gap-2">
                  {jobStatus?.failed_count ? (
                    <Badge variant="destructive">
                      {jobStatus.failed_count} 台失敗
                    </Badge>
                  ) : null}
                  <Badge
                    variant={
                      jobStatus?.status === "completed"
                        ? "default"
                        : jobStatus?.status === "failed"
                          ? "destructive"
                          : "secondary"
                    }
                  >
                    {jobStatus?.status === "pending" && "等待中"}
                    {jobStatus?.status === "running" && "執行中"}
                    {jobStatus?.status === "completed" && "已完成"}
                    {jobStatus?.status === "failed" && "失敗"}
                  </Badge>
                </div>
              </div>
              <ProgressBar done={jobStatus?.done ?? 0} total={jobStatus?.total ?? memberCount} />
            </div>

            {/* 每台進度列表 */}
            <div className="max-h-72 overflow-y-auto rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8">#</TableHead>
                    <TableHead>成員</TableHead>
                    <TableHead>Hostname</TableHead>
                    <TableHead className="w-16">VMID</TableHead>
                    <TableHead className="w-8" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(jobStatus?.tasks ?? []).map((task) => (
                    <TableRow key={task.id}>
                      <TableCell className="text-muted-foreground text-xs">
                        {task.member_index}
                      </TableCell>
                      <TableCell className="text-sm">
                        <div>{task.user_name ?? "-"}</div>
                        <div className="text-xs text-muted-foreground">
                          {task.user_email}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">
                        {jobStatus
                          ? `${jobStatus.hostname_prefix}-${task.member_index}`
                          : "-"}
                      </TableCell>
                      <TableCell className="text-xs">
                        {task.vmid ?? "-"}
                      </TableCell>
                      <TableCell>
                        <div title={task.error ?? undefined}>
                          <TaskStatusIcon status={task.status} />
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* 失敗訊息 */}
            {(jobStatus?.tasks ?? []).some((t) => t.status === "failed") && (
              <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-xs space-y-1">
                <p className="font-medium text-destructive">失敗項目：</p>
                {jobStatus!.tasks
                  .filter((t) => t.status === "failed")
                  .map((t) => (
                    <p key={t.id} className="text-muted-foreground">
                      #{t.member_index} {t.user_email}：{t.error}
                    </p>
                  ))}
              </div>
            )}

            <DialogFooter>
              <Button
                variant={isRunning ? "outline" : "default"}
                disabled={isRunning}
                onClick={() => handleOpenChange(false)}
              >
                {isRunning ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    建立中，請稍候…
                  </>
                ) : (
                  "關閉"
                )}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ─── Group Detail Content ─────────────────────────────────────────────────────

function GroupDetailContent({ groupId }: { groupId: string }) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const { data: group } = useSuspenseQuery({
    queryKey: ["group", groupId],
    queryFn: () => GroupsService.getGroup({ groupId }),
  })
  const members = group.members ?? []

  const removeMutation = useMutation({
    mutationFn: (userId: string) =>
      GroupsService.removeMember({ groupId, userId }),
    onSuccess: () => {
      showSuccessToast("成員已移除")
      queryClient.invalidateQueries({ queryKey: ["group", groupId] })
    },
    onError: (err: any) => showErrorToast(err?.body?.detail ?? "移除失敗"),
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link
              to="/groups"
              className="text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <h1 className="text-2xl font-bold tracking-tight">{group.name}</h1>
          </div>
          {group.description && (
            <p className="text-muted-foreground">{group.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <ImportCsvDialog groupId={groupId} />
          <AddMembersDialog groupId={groupId} />
          {members.length > 0 && (
            <BatchProvisionDialog
              groupId={groupId}
              memberCount={members.length}
            />
          )}
        </div>
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-3">
          成員列表（{members.length} 人）
        </h2>
        {members.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            尚無成員，點擊「加入成員」開始新增
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>姓名</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>加入時間</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((member) => (
                <TableRow key={member.user_id}>
                  <TableCell>{member.full_name ?? "-"}</TableCell>
                  <TableCell>{member.email}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {member.added_at
                      ? new Date(member.added_at).toLocaleDateString("zh-TW")
                      : "-"}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-destructive hover:text-destructive"
                      onClick={() => removeMutation.mutate(member.user_id)}
                      disabled={removeMutation.isPending}
                    >
                      <UserMinus className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

function GroupDetailPage() {
  const { groupId } = Route.useParams()
  return (
    <Suspense fallback={<div className="text-muted-foreground">載入中…</div>}>
      <GroupDetailContent groupId={groupId} />
    </Suspense>
  )
}
