import { useMutation } from "@tanstack/react-query"
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Loader2,
  Rocket,
  ScrollText,
  Server,
  XCircle,
} from "lucide-react"
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { OpenAPI } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import useCustomToast from "@/hooks/useCustomToast"

import type { FastTemplate } from "./FastTemplatesTab"

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function apiRequest<T>(
  method: string,
  url: string,
  body?: unknown,
): Promise<T> {
  const token = localStorage.getItem("access_token") || ""
  const base = OpenAPI.BASE || ""
  const res = await fetch(`${base}${url}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

type DeployResponse = { task_id: string; message: string }
type DeployStatus = {
  task_id: string
  status: "running" | "completed" | "failed"
  progress: string | null
  vmid: number | null
  message: string | null
  error: string | null
  output: string | null
}

// ---------------------------------------------------------------------------
// ANSI / terminal escape code stripper
// ---------------------------------------------------------------------------

function stripAnsi(text: string): string {
  return (
    text
      .replace(/\x1B\[[0-9;]*[A-Za-z]/g, "")
      .replace(/\x1B\][^\x07]*\x07/g, "")
      .replace(/\x1B[^[\]()][^\x1B]*/g, "")
      .replace(/\x1B/g, "")
      .replace(/\[([0-9;]*)[A-Za-z]/g, "")
      .replace(/\[\?[0-9;]*[A-Za-z]/g, "")
      .replace(/\r/g, "")
      .replace(/\n{3,}/g, "\n\n")
      .trim()
  )
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export type ScriptDeployFormData = {
  hostname: string
  password: string
  cpu: number
  ram: number
  disk: number
  unprivileged: boolean
  ssh: boolean
}

type ScriptDeployPageProps = {
  template: FastTemplate
  formData: ScriptDeployFormData
  onBack: () => void
  onComplete: () => void
}

export function ScriptDeployPage({
  template,
  formData,
  onBack,
  onComplete,
}: ScriptDeployPageProps) {
  const { t } = useTranslation("applications")
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const defaultMethod = template.install_methods?.[0]
  const scriptPath = defaultMethod?.script || `ct/${template.slug}.sh`

  // Deployment state
  const [taskId, setTaskId] = useState<string | null>(null)
  const [, setDeploying] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const deployStartedRef = useRef(false)
  const [status, setStatus] = useState<DeployStatus | null>(null)
  const logEndRef = useRef<HTMLDivElement | null>(null)
  const logContainerRef = useRef<HTMLPreElement | null>(null)

  // Clean ANSI codes from output
  const cleanedOutput = useMemo(
    () => (status?.output ? stripAnsi(status.output) : ""),
    [status?.output],
  )

  // Auto-scroll log to bottom
  useLayoutEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [cleanedOutput])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  // Start deployment
  const deployMutation = useMutation({
    mutationFn: () =>
      apiRequest<DeployResponse>("POST", "/api/v1/script-deploy/deploy", {
        template_slug: template.slug,
        script_path: scriptPath,
        hostname: formData.hostname,
        password: formData.password,
        cpu: formData.cpu,
        ram: formData.ram,
        disk: formData.disk,
        unprivileged: formData.unprivileged,
        ssh: formData.ssh,
        environment_type: "服務模板",
        os_info: template.name || null,
      }),
    onSuccess: (data) => {
      setTaskId(data.task_id)
      setDeploying(true)
      pollRef.current = setInterval(async () => {
        try {
          const s = await apiRequest<DeployStatus>(
            "GET",
            `/api/v1/script-deploy/status/${data.task_id}`,
          )
          setStatus(s)
          if (s.status === "completed" || s.status === "failed") {
            if (pollRef.current) clearInterval(pollRef.current)
            pollRef.current = null
            setDeploying(false)

            if (s.status === "completed") {
              try {
                await apiRequest(
                  "POST",
                  `/api/v1/script-deploy/register/${data.task_id}`,
                )
              } catch {
                // registration failure is non-fatal
              }
              showSuccessToast(s.message || `部署成功！VMID: ${s.vmid}`)
            } else {
              showErrorToast(s.error || "部署失敗")
            }
          }
        } catch {
          // polling error — ignore, will retry
        }
      }, 3000)
    },
    onError: (err) => {
      showErrorToast(err.message || "啟動部署失敗")
    },
  })

  // Auto-start deployment on mount (use ref to prevent double-invoke in React Strict Mode)
  useEffect(() => {
    if (!deployStartedRef.current) {
      deployStartedRef.current = true
      deployMutation.mutate()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const isDone = status?.status === "completed" || status?.status === "failed"

  return (
    <div className="mx-auto w-full max-w-[760px] space-y-6">
      {/* Header */}
      <div className="flex items-start gap-3">
        <Button
          variant="outline"
          size="icon"
          className="mt-0.5 shrink-0"
          onClick={isDone ? onBack : undefined}
          disabled={!isDone}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Rocket className="h-5 w-5 text-primary" />
            <h1 className="text-2xl font-bold tracking-tight">
              {t("deploy.title", { defaultValue: "一鍵部署" })}
            </h1>
            <Badge variant="secondary">{template.name}</Badge>
          </div>
          <p className="text-muted-foreground">
            {t("deploy.description", {
              defaultValue:
                "從 community-scripts 下載腳本，以無人值守方式部署服務容器。",
            })}
          </p>
        </div>
      </div>

      {/* Deploy info cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border bg-card p-3">
          <div className="text-xs text-muted-foreground">Hostname</div>
          <div className="mt-0.5 truncate text-sm font-medium">
            {formData.hostname}
          </div>
        </div>
        <div className="rounded-lg border bg-card p-3">
          <div className="text-xs text-muted-foreground">CPU</div>
          <div className="mt-0.5 text-sm font-medium">
            {formData.cpu} Cores
          </div>
        </div>
        <div className="rounded-lg border bg-card p-3">
          <div className="text-xs text-muted-foreground">RAM</div>
          <div className="mt-0.5 text-sm font-medium">
            {(formData.ram / 1024).toFixed(1)} GB
          </div>
        </div>
        <div className="rounded-lg border bg-card p-3">
          <div className="text-xs text-muted-foreground">Disk</div>
          <div className="mt-0.5 text-sm font-medium">{formData.disk} GB</div>
        </div>
      </div>

      {/* Script path */}
      <div className="rounded-lg border bg-muted/50 p-3 text-sm text-muted-foreground">
        <span className="font-medium">
          {t("deploy.scriptPath", { defaultValue: "腳本路徑" })}：
        </span>
        <code className="ml-1">{scriptPath}</code>
      </div>

      {/* Status */}
      <div className="flex items-center gap-2">
        {(!status || status.status === "running") && (
          <>
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
            <span className="text-sm">
              {status?.progress || "正在啟動部署…"}
            </span>
          </>
        )}
        {status?.status === "completed" && (
          <>
            <CheckCircle2 className="h-5 w-5 text-green-500" />
            <span className="text-sm font-medium text-green-600">
              {status.message}
            </span>
          </>
        )}
        {status?.status === "failed" && (
          <>
            <XCircle className="h-5 w-5 text-destructive" />
            <span className="text-sm text-destructive">
              {t("deploy.failed", { defaultValue: "部署失敗" })}
            </span>
          </>
        )}
      </div>

      {/* Live deployment log */}
      {cleanedOutput && (
        <div className="overflow-hidden rounded-lg border border-border/50 bg-zinc-950">
          <div className="flex items-center gap-1.5 border-b border-border/30 bg-zinc-900/80 px-3 py-1.5">
            <ScrollText className="h-3.5 w-3.5 text-zinc-500" />
            <span className="text-xs font-medium text-zinc-400">
              {t("deploy.log", { defaultValue: "部署日誌" })}
            </span>
            {status?.status === "running" && (
              <span className="ml-auto flex items-center gap-1 text-[10px] text-emerald-500">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
                LIVE
              </span>
            )}
          </div>
          <pre
            ref={logContainerRef}
            className="max-h-[60vh] overflow-auto px-3 py-2 font-mono text-xs leading-relaxed text-zinc-300 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-zinc-700"
          >
            {cleanedOutput}
            <div ref={logEndRef} />
          </pre>
        </div>
      )}

      {/* Error details */}
      {status?.status === "failed" && status.error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3">
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-destructive">
            <AlertTriangle className="h-3.5 w-3.5" />
            {t("deploy.errorDetail", {
              defaultValue: "錯誤詳情（已自動回滾）",
            })}
          </div>
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
            {stripAnsi(status.error)}
          </pre>
        </div>
      )}

      {/* Success VMID */}
      {status?.status === "completed" && status.vmid && (
        <div className="rounded-lg border bg-green-500/5 p-3">
          <div className="flex items-center gap-1.5 text-sm">
            <Server className="h-4 w-4" />
            VMID:{" "}
            <span className="font-mono font-bold">{status.vmid}</span>
          </div>
        </div>
      )}

      {/* Action buttons */}
      {isDone && (
        <div className="flex gap-3 border-t pt-4">
          <Button variant="outline" onClick={onBack}>
            {t("deploy.close", { defaultValue: "返回" })}
          </Button>
          {status?.status === "completed" && (
            <Button onClick={onComplete}>
              {t("deploy.goToResources", {
                defaultValue: "前往資源列表",
              })}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
