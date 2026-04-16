import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { ArrowLeft, LayoutTemplate, X } from "lucide-react"
import {
  type CSSProperties,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import { useForm, useWatch } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"

import { type ApiError, LxcService, VmService } from "@/client"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { queryKeys } from "@/lib/queryKeys"
import { toVmRequestCreateRequestBody } from "@/lib/resourcePayloads"
import { cn } from "@/lib/utils"
import { GpuService, type GPUSummary } from "@/services/gpu"
import { VmRequestsApi } from "@/services/vmRequests"
import { handleError } from "@/utils"
import { AiChatPanel, type AiPlanResult } from "./AiChatPanel"
import { type FastTemplate, FastTemplatesTab } from "./FastTemplatesTab"
import { RequestAvailabilityPanel } from "./RequestAvailabilityPanel"

function normalizeHostname(value: string) {
  return (
    String(value || "")
      .toLowerCase()
      // 保留 Unicode 字母、數字和連字符，其他替換為連字符
      .replace(/[^\p{L}\p{N}-]/gu, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 63)
  )
}

function formatScheduleSummary(startAt?: string, endAt?: string) {
  if (!startAt || !endAt) return "尚未選擇時段"

  const formatter = new Intl.DateTimeFormat("zh-TW", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    timeZone: "Asia/Taipei",
  })

  return `${formatter.format(new Date(startAt))} - ${formatter.format(new Date(endAt))}`
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border/70 py-2.5 last:border-b-0">
      <span className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </span>
      <span className="max-w-[72%] text-right text-sm leading-snug">
        {value}
      </span>
    </div>
  )
}

type ImportedFormPrefill = NonNullable<
  NonNullable<AiPlanResult["final_plan"]>["form_prefill"]
>

type DesktopPanelFrame = {
  height: number
  left: number
  top: number
  width: number
}

const AI_PANEL_BOTTOM_GAP = 16

export function ApplicationRequestPage() {
  const { t } = useTranslation([
    "applications",
    "resources",
    "validation",
    "common",
    "messages",
  ])
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { user } = useAuth()
  const backPath =
    user?.role === "admin" || user?.is_superuser
      ? "/approvals"
      : "/applications"
  const showAiAssistant = true
  const [showTemplateSelector, setShowTemplateSelector] = useState(false)
  const [resourceType, setResourceType] = useState<"lxc" | "vm">("lxc")
  const [serviceTemplateName, setServiceTemplateName] = useState("")
  const [serviceTemplateSlug, setServiceTemplateSlug] = useState("")
  const aiColumnRef = useRef<HTMLElement | null>(null)
  const [desktopPanelFrame, setDesktopPanelFrame] =
    useState<DesktopPanelFrame | null>(null)

  const formSchema = useMemo(
    () =>
      z.object({
        resource_type: z.enum(["lxc", "vm"]),
        mode: z.enum(["scheduled", "immediate"]).default("scheduled"),
        reason: z
          .string()
          .min(1, { message: t("validation:reason.required") })
          .min(10, {
            message: t("validation:reason.minLength", { count: 10 }),
          }),
        hostname: z
          .string()
          .min(1, { message: t("validation:name.required") })
          .max(63)
          .regex(/^[\p{L}\p{N}]([\p{L}\p{N}-]*[\p{L}\p{N}])?$/u, {
            message: t("validation:name.invalid"),
          }),
        ostemplate: z.string().optional(),
        rootfs_size: z.number().min(8).max(500).optional(),
        template_id: z.number().optional(),
        disk_size: z.number().min(20).max(500).optional(),
        username: z.string().optional(),
        cores: z.number().min(1).max(8),
        memory: z.number().min(512).max(32768),
        gpu_mapping_id: z.string().optional(),
        password: z
          .string()
          .min(1, { message: t("validation:password.required") })
          .min(8, {
            message: t("validation:password.minLength", { count: 8 }),
          }),
        storage: z.string().default("local-lvm"),
        os_info: z.string().optional(),
        start_at: z.string().optional(),
        end_at: z.string().optional(),
        immediate_no_end: z.boolean().optional(),
      }),
    [t],
  )

  type FormData = z.input<typeof formSchema>

  const form = useForm<FormData>({
    resolver: standardSchemaResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      resource_type: "lxc",
      mode: "scheduled",
      reason: "",
      hostname: "",
      ostemplate: "",
      template_id: undefined,
      username: "",
      cores: 2,
      memory: 2048,
      gpu_mapping_id: "",
      disk_size: 20,
      rootfs_size: 8,
      password: "",
      storage: "local-lvm",
      os_info: "",
      start_at: "",
      end_at: "",
      immediate_no_end: true,
    },
  })

  const watchedResourceType = useWatch({
    control: form.control,
    name: "resource_type",
  })
  const watchedHostname = useWatch({ control: form.control, name: "hostname" })
  const watchedPassword = useWatch({ control: form.control, name: "password" })
  const watchedReason = useWatch({ control: form.control, name: "reason" })
  const watchedOsTemplate = useWatch({
    control: form.control,
    name: "ostemplate",
  })
  const watchedTemplateId = useWatch({
    control: form.control,
    name: "template_id",
  })
  const watchedUsername = useWatch({ control: form.control, name: "username" })
  const watchedCores = useWatch({ control: form.control, name: "cores" })
  const watchedMemory = useWatch({ control: form.control, name: "memory" })
  const watchedRootfsSize = useWatch({
    control: form.control,
    name: "rootfs_size",
  })
  const watchedDiskSize = useWatch({
    control: form.control,
    name: "disk_size",
  })
  const watchedStartAt = useWatch({ control: form.control, name: "start_at" })
  const watchedEndAt = useWatch({ control: form.control, name: "end_at" })
  const watchedMode = useWatch({ control: form.control, name: "mode" })
  const watchedImmediateNoEnd = useWatch({
    control: form.control,
    name: "immediate_no_end",
  })

  function getSelectedTemplateLabel() {
    if (resourceType === "lxc") {
      if (!watchedOsTemplate) return serviceTemplateName || "尚未選擇"
      const matchedTemplate = lxcTemplates?.find(
        (template) => template.volid === watchedOsTemplate,
      )
      return (
        serviceTemplateName ||
        matchedTemplate?.volid.split("/").pop()?.replace(".tar.zst", "") ||
        watchedOsTemplate
      )
    }

    if (!watchedTemplateId) return "尚未選擇"
    return (
      vmTemplates?.find((template) => template.vmid === watchedTemplateId)
        ?.name || `Template #${watchedTemplateId}`
    )
  }

  const requestSpecSummary = useMemo(() => {
    const memoryGb = (Number(watchedMemory || 0) / 1024).toFixed(1)
    const storageGb =
      resourceType === "vm"
        ? Number(watchedDiskSize || 0)
        : Number(watchedRootfsSize || 0)
    const storageLabel = resourceType === "vm" ? "Disk" : "Rootfs"

    return `${Number(watchedCores || 0)} Core / ${memoryGb} GB RAM / ${storageGb} GB ${storageLabel}`
  }, [
    resourceType,
    watchedCores,
    watchedDiskSize,
    watchedMemory,
    watchedRootfsSize,
  ])

  const requestWindowSummary = useMemo(
    () => formatScheduleSummary(watchedStartAt, watchedEndAt),
    [watchedEndAt, watchedStartAt],
  )

  const isSubmitReady = useMemo(() => {
    const reasonReady = Boolean(watchedReason?.trim())
    const basicReady = Boolean(
      reasonReady && watchedHostname?.trim() && watchedPassword,
    )

    const isImmediate = watchedMode === "immediate"
    const slotReady = isImmediate
      ? true
      : Boolean(watchedStartAt && watchedEndAt)

    if (!basicReady || !slotReady) return false

    if (watchedResourceType === "vm") {
      return Boolean(watchedTemplateId && watchedUsername?.trim())
    }

    return Boolean(watchedOsTemplate)
  }, [
    watchedHostname,
    watchedMode,
    watchedOsTemplate,
    watchedPassword,
    watchedReason,
    watchedResourceType,
    watchedStartAt,
    watchedTemplateId,
    watchedEndAt,
    watchedUsername,
  ])

  const requestReadinessLabel = isSubmitReady ? "可送出申請" : "尚有欄位待完成"

  const { data: lxcTemplates, isLoading: lxcTemplatesLoading } = useQuery({
    queryKey: queryKeys.resources.templates.lxc,
    queryFn: () => LxcService.getTemplates(),
    enabled: resourceType === "lxc",
  })

  const { data: vmTemplates, isLoading: vmTemplatesLoading } = useQuery({
    queryKey: queryKeys.resources.templates.vm,
    queryFn: () => VmService.getVmTemplates(),
    enabled: resourceType === "vm",
  })

  const { data: gpuOptions } = useQuery({
    queryKey: queryKeys.gpu.options,
    queryFn: () => GpuService.listOptions(),
    enabled: resourceType === "vm",
  })

  const selectedTemplateLabel = getSelectedTemplateLabel()

  const mutation = useMutation({
    mutationFn: (data: FormData) => {
      const payloadOptions = {
        lxcEnvironmentType:
          serviceTemplateName || t("resources:create.customSpec"),
        vmEnvironmentType: t("resources:create.customSpec"),
        validationMessages: {
          lxcRequirements: t("validation:requirement.lxc"),
          vmRequirements: t("validation:requirement.vm"),
        },
      }

      return VmRequestsApi.create({
        requestBody: toVmRequestCreateRequestBody(data, payloadOptions),
      })
    },
    onSuccess: () => {
      showSuccessToast(t("messages:success.applicationSubmitted"))
      queryClient.invalidateQueries({ queryKey: queryKeys.vmRequests.all })
      navigate({ to: backPath })
    },
    onError: (err) => handleError.call(showErrorToast, err as ApiError),
  })

  const updateFormValue = useCallback(
    (field: keyof FormData, value: FormData[keyof FormData]) => {
      form.setValue(field, value as never, {
        shouldDirty: true,
        shouldTouch: true,
        shouldValidate: true,
      })
    },
    [form],
  )

  const handleImportPlan = useCallback(
    (prefill: ImportedFormPrefill | undefined) => {
      if (!prefill) return

      const type = prefill.resource_type === "vm" ? "vm" : "lxc"

      setResourceType(type)
      updateFormValue("resource_type", type)

      if (prefill.hostname) {
        updateFormValue("hostname", normalizeHostname(prefill.hostname))
      }
      if (prefill.cores) updateFormValue("cores", prefill.cores)
      if (prefill.memory_mb) updateFormValue("memory", prefill.memory_mb)
      if (prefill.reason) updateFormValue("reason", prefill.reason)

      if (type === "lxc") {
        if (prefill.disk_gb) updateFormValue("rootfs_size", prefill.disk_gb)
        if (prefill.lxc_os_image) {
          updateFormValue("ostemplate", prefill.lxc_os_image)
        }
        if (prefill.service_template_slug) {
          setServiceTemplateSlug(prefill.service_template_slug)
          setServiceTemplateName(prefill.service_template_slug)
        }
      } else {
        if (prefill.disk_gb) updateFormValue("disk_size", prefill.disk_gb)
        if (prefill.vm_template_id) {
          updateFormValue("template_id", prefill.vm_template_id)
        }
        if (prefill.username) updateFormValue("username", prefill.username)
      }
    },
    [updateFormValue],
  )

  const handleImportReason = useCallback(
    (reason: string) => {
      if (!reason) return

      updateFormValue("reason", reason)
      showSuccessToast(t("applications:aiChat.reasonImportSuccess"))
    },
    [showSuccessToast, t, updateFormValue],
  )

  const handleSelectTemplate = useCallback(
    (template: FastTemplate) => {
      setServiceTemplateName(template.name || "")
      setServiceTemplateSlug(template.slug || "")
      setResourceType("lxc")
      updateFormValue("resource_type", "lxc")
      if (template.name) {
        updateFormValue("hostname", normalizeHostname(template.name))
      }
      // 帶入模板的預設資源值
      const method = template.install_methods?.[0]
      if (method?.resources) {
        if (method.resources.cpu) updateFormValue("cores", method.resources.cpu)
        if (method.resources.ram)
          updateFormValue("memory", method.resources.ram)
        if (method.resources.hdd)
          updateFormValue("rootfs_size", Math.max(method.resources.hdd, 8))
      }
      setShowTemplateSelector(false)
    },
    [updateFormValue],
  )

  const onSubmit = (data: FormData) => {
    mutation.mutate(data)
  }

  useEffect(() => {
    const updateDesktopPanelFrame = () => {
      const node = aiColumnRef.current
      if (!node || window.innerWidth < 1024) {
        setDesktopPanelFrame(null)
        return
      }

      const rect = node.getBoundingClientRect()
      const footerNode = document.querySelector<HTMLElement>(
        '[data-app-footer="fixed"]',
      )
      const footerHeight = footerNode?.getBoundingClientRect().height ?? 0
      setDesktopPanelFrame({
        height: Math.max(
          320,
          window.innerHeight - rect.top - footerHeight - AI_PANEL_BOTTOM_GAP,
        ),
        left: rect.left,
        top: rect.top,
        width: rect.width,
      })
    }

    updateDesktopPanelFrame()

    const node = aiColumnRef.current
    const resizeObserver =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => updateDesktopPanelFrame())
        : null

    if (node && resizeObserver) {
      resizeObserver.observe(node)
    }

    window.addEventListener("resize", updateDesktopPanelFrame)

    return () => {
      resizeObserver?.disconnect()
      window.removeEventListener("resize", updateDesktopPanelFrame)
    }
  }, [])

  const desktopPanelStyle = useMemo<CSSProperties | undefined>(() => {
    if (!desktopPanelFrame) return undefined

    return {
      height: `${desktopPanelFrame.height}px`,
      left: `${desktopPanelFrame.left}px`,
      position: "fixed",
      top: `${desktopPanelFrame.top}px`,
      width: `${desktopPanelFrame.width}px`,
    }
  }, [desktopPanelFrame])

  const aiColumnStyle = useMemo<CSSProperties | undefined>(() => {
    if (!desktopPanelFrame) return undefined

    return {
      height: `${desktopPanelFrame.height}px`,
    }
  }, [desktopPanelFrame])

  return (
    <div
      className={`mx-auto flex w-full ${showAiAssistant ? "max-w-[1180px]" : "max-w-[760px]"} flex-col gap-6`}
    >
      <div
        className={`grid items-start gap-6 ${showAiAssistant ? "lg:grid-cols-[minmax(0,1fr)_400px] xl:grid-cols-[minmax(0,1fr)_420px]" : ""}`}
      >
        <div className="min-w-0 max-w-[760px] space-y-6">
          <div className="flex items-start gap-3">
            <Button
              variant="outline"
              size="icon"
              className="mt-0.5 shrink-0"
              onClick={() => navigate({ to: backPath })}
              aria-label={t("common:buttons.back")}
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div className="min-w-0">
              <h1 className="text-2xl font-bold tracking-tight">
                {t("applications:create.heading")}
              </h1>
              <p className="text-muted-foreground">
                {t("applications:create.description")}
              </p>
            </div>
          </div>

          {showTemplateSelector ? (
            <FastTemplatesTab
              onSelectTemplate={handleSelectTemplate}
              onBack={() => setShowTemplateSelector(false)}
            />
          ) : (
            <Form {...form}>
              <form
                onSubmit={form.handleSubmit(onSubmit)}
                className="space-y-6"
              >
                {(user?.is_superuser ||
                  user?.role === "admin" ||
                  user?.role === "teacher") && (
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => form.setValue("mode", "scheduled")}
                      className={cn(
                        "rounded-lg border px-4 py-2 text-sm transition-colors",
                        watchedMode === "scheduled"
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border text-muted-foreground hover:bg-muted/50",
                      )}
                    >
                      預約模式
                    </button>
                    <button
                      type="button"
                      onClick={() => form.setValue("mode", "immediate")}
                      className={cn(
                        "rounded-lg border px-4 py-2 text-sm transition-colors",
                        watchedMode === "immediate"
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border text-muted-foreground hover:bg-muted/50",
                      )}
                    >
                      立即模式
                    </button>
                  </div>
                )}

                <Tabs
                  value={resourceType}
                  onValueChange={(value) => {
                    const nextType = value as "lxc" | "vm"
                    setResourceType(nextType)
                    updateFormValue("resource_type", nextType)
                  }}
                  className="w-full"
                >
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="lxc">
                      {t("resources:form.type.lxc")}
                    </TabsTrigger>
                    <TabsTrigger value="vm">
                      {t("resources:form.type.qemu")}
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="lxc" className="mt-6 space-y-6">
                    <div className="space-y-5">
                      <FormField
                        control={form.control}
                        name="hostname"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>
                              {t("resources:form.name")}{" "}
                              <span className="text-destructive">*</span>
                            </FormLabel>
                            <FormControl>
                              <Input
                                {...field}
                                placeholder="project-alpha-web"
                                onBlur={(event) => {
                                  const normalized = normalizeHostname(
                                    event.target.value,
                                  )
                                  field.onChange(normalized)
                                  field.onBlur()
                                }}
                                required
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="ostemplate"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>
                              {t("resources:form.osTemplate")}{" "}
                              <span className="text-destructive">*</span>
                            </FormLabel>
                            <Select
                              onValueChange={field.onChange}
                              value={field.value}
                            >
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue
                                    placeholder={t("resources:form.os")}
                                  />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {lxcTemplatesLoading ? (
                                  <SelectItem value="loading" disabled>
                                    {t("common:status.loading")}
                                  </SelectItem>
                                ) : lxcTemplates && lxcTemplates.length > 0 ? (
                                  lxcTemplates.map((template) => (
                                    <SelectItem
                                      key={template.volid}
                                      value={template.volid}
                                    >
                                      {template.volid
                                        .split("/")
                                        .pop()
                                        ?.replace(".tar.zst", "")}
                                    </SelectItem>
                                  ))
                                ) : (
                                  <SelectItem value="none" disabled>
                                    {t("common:common.none")}
                                  </SelectItem>
                                )}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormItem>
                        <FormLabel>
                          {t("applications:form.serviceTemplate")}
                        </FormLabel>
                        {serviceTemplateName ? (
                          <div className="flex items-center gap-2 rounded-md border bg-muted/30 px-3 py-2">
                            <LayoutTemplate className="h-4 w-4 shrink-0 text-primary" />
                            <div className="flex-1 min-w-0">
                              <span className="block truncate text-sm font-medium">
                                {serviceTemplateName}
                              </span>
                              {serviceTemplateSlug ? (
                                <span className="block truncate text-xs text-muted-foreground">
                                  {serviceTemplateSlug}
                                </span>
                              ) : null}
                            </div>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 shrink-0"
                              onClick={() => {
                                setServiceTemplateName("")
                                setServiceTemplateSlug("")
                              }}
                            >
                              <X className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        ) : (
                          <Button
                            type="button"
                            variant="outline"
                            className="w-full justify-start gap-2 text-muted-foreground"
                            onClick={() => setShowTemplateSelector(true)}
                          >
                            <LayoutTemplate className="h-4 w-4" />
                            {t("applications:form.selectTemplate")}
                          </Button>
                        )}
                      </FormItem>

                      <FormField
                        control={form.control}
                        name="os_info"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>{t("resources:form.osInfo")}</FormLabel>
                            <FormControl>
                              <Input
                                {...field}
                                placeholder="Ubuntu 22.04 LTS"
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="password"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>
                              {t("resources:form.rootPassword")}{" "}
                              <span className="text-destructive">*</span>
                            </FormLabel>
                            <FormControl>
                              <Input
                                {...field}
                                placeholder="root password"
                                type="password"
                                required
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>

                    <div className="rounded-2xl border bg-muted/20 p-5">
                      <h3 className="mb-4 font-medium">
                        {t("resources:form.hardware")}
                      </h3>
                      <div className="space-y-5">
                        <FormField
                          control={form.control}
                          name="cores"
                          render={({ field }) => (
                            <FormItem>
                              <div className="flex items-center justify-between">
                                <FormLabel>
                                  {t("resources:form.cpuCores")}
                                </FormLabel>
                                <span className="text-sm font-semibold text-primary">
                                  {field.value} Cores
                                </span>
                              </div>
                              <FormControl>
                                <Slider
                                  min={1}
                                  max={8}
                                  step={1}
                                  value={[field.value]}
                                  onValueChange={(values) =>
                                    field.onChange(values[0])
                                  }
                                />
                              </FormControl>
                              <div className="flex justify-between text-xs text-muted-foreground">
                                <span>1</span>
                                <span>2</span>
                                <span>4</span>
                                <span>8</span>
                              </div>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="memory"
                          render={({ field }) => (
                            <FormItem>
                              <div className="flex items-center justify-between">
                                <FormLabel>
                                  {t("resources:form.memory")}
                                </FormLabel>
                                <span className="text-sm font-semibold text-primary">
                                  {(field.value / 1024).toFixed(1)} GB
                                </span>
                              </div>
                              <FormControl>
                                <Slider
                                  min={512}
                                  max={32768}
                                  step={512}
                                  value={[field.value]}
                                  onValueChange={(values) =>
                                    field.onChange(values[0])
                                  }
                                />
                              </FormControl>
                              <div className="flex justify-between text-xs text-muted-foreground">
                                <span>1GB</span>
                                <span>8GB</span>
                                <span>16GB</span>
                                <span>32GB</span>
                              </div>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="rootfs_size"
                          render={({ field }) => (
                            <FormItem>
                              <div className="flex items-center justify-between">
                                <FormLabel>
                                  {t("resources:form.disk")}
                                </FormLabel>
                                <div className="flex items-center gap-2">
                                  <Input
                                    className="h-8 w-20 text-right"
                                    type="number"
                                    min={8}
                                    max={500}
                                    value={field.value ?? 8}
                                    onChange={(event) =>
                                      field.onChange(
                                        Number.parseInt(
                                          event.target.value,
                                          10,
                                        ) || 8,
                                      )
                                    }
                                  />
                                  <span className="text-sm font-semibold text-primary">
                                    GB
                                  </span>
                                </div>
                              </div>
                              <FormControl>
                                <Slider
                                  min={8}
                                  max={500}
                                  step={1}
                                  value={[field.value ?? 8]}
                                  onValueChange={(values) =>
                                    field.onChange(values[0])
                                  }
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="vm" className="mt-6 space-y-6">
                    <div className="space-y-5">
                      <FormField
                        control={form.control}
                        name="hostname"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>
                              {t("resources:form.vmName")}{" "}
                              <span className="text-destructive">*</span>
                            </FormLabel>
                            <FormControl>
                              <Input
                                {...field}
                                placeholder="web-server-01"
                                onBlur={(event) => {
                                  const normalized = normalizeHostname(
                                    event.target.value,
                                  )
                                  field.onChange(normalized)
                                  field.onBlur()
                                }}
                                required
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="template_id"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>
                              {t("resources:form.os")}{" "}
                              <span className="text-destructive">*</span>
                            </FormLabel>
                            <Select
                              onValueChange={(value) =>
                                field.onChange(Number.parseInt(value, 10))
                              }
                              value={field.value?.toString()}
                            >
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue
                                    placeholder={t("resources:form.os")}
                                  />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {vmTemplatesLoading ? (
                                  <SelectItem value="loading" disabled>
                                    {t("common:status.loading")}
                                  </SelectItem>
                                ) : vmTemplates && vmTemplates.length > 0 ? (
                                  vmTemplates.map((template) => (
                                    <SelectItem
                                      key={template.vmid}
                                      value={template.vmid.toString()}
                                    >
                                      {template.name}
                                    </SelectItem>
                                  ))
                                ) : (
                                  <SelectItem value="none" disabled>
                                    {t("common:common.none")}
                                  </SelectItem>
                                )}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="os_info"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>{t("resources:form.osInfo")}</FormLabel>
                            <FormControl>
                              <Input
                                {...field}
                                placeholder="Ubuntu 22.04 LTS"
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="username"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>
                              {t("resources:form.username")}{" "}
                              <span className="text-destructive">*</span>
                            </FormLabel>
                            <FormControl>
                              <Input {...field} placeholder="admin" required />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="password"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>
                              {t("resources:form.password")}{" "}
                              <span className="text-destructive">*</span>
                            </FormLabel>
                            <FormControl>
                              <Input
                                {...field}
                                placeholder="password"
                                type="password"
                                required
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>

                    <div className="rounded-2xl border bg-muted/20 p-5">
                      <h3 className="mb-4 font-medium">
                        {t("resources:form.hardware")}
                      </h3>
                      <div className="space-y-5">
                        <FormField
                          control={form.control}
                          name="cores"
                          render={({ field }) => (
                            <FormItem>
                              <div className="flex items-center justify-between">
                                <FormLabel>
                                  {t("resources:form.cpuCores")}
                                </FormLabel>
                                <span className="text-sm font-semibold text-primary">
                                  {field.value} Cores
                                </span>
                              </div>
                              <FormControl>
                                <Slider
                                  min={1}
                                  max={8}
                                  step={1}
                                  value={[field.value]}
                                  onValueChange={(values) =>
                                    field.onChange(values[0])
                                  }
                                />
                              </FormControl>
                              <div className="flex justify-between text-xs text-muted-foreground">
                                <span>1</span>
                                <span>2</span>
                                <span>4</span>
                                <span>8</span>
                              </div>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="memory"
                          render={({ field }) => (
                            <FormItem>
                              <div className="flex items-center justify-between">
                                <FormLabel>
                                  {t("resources:form.memory")}
                                </FormLabel>
                                <span className="text-sm font-semibold text-primary">
                                  {(field.value / 1024).toFixed(1)} GB
                                </span>
                              </div>
                              <FormControl>
                                <Slider
                                  min={512}
                                  max={32768}
                                  step={512}
                                  value={[field.value]}
                                  onValueChange={(values) =>
                                    field.onChange(values[0])
                                  }
                                />
                              </FormControl>
                              <div className="flex justify-between text-xs text-muted-foreground">
                                <span>1GB</span>
                                <span>8GB</span>
                                <span>16GB</span>
                                <span>32GB</span>
                              </div>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="disk_size"
                          render={({ field }) => (
                            <FormItem>
                              <div className="flex items-center justify-between">
                                <FormLabel>
                                  {t("resources:form.disk")}
                                </FormLabel>
                                <div className="flex items-center gap-2">
                                  <Input
                                    className="h-8 w-20 text-right"
                                    type="number"
                                    min={20}
                                    max={500}
                                    value={field.value ?? 20}
                                    onChange={(event) =>
                                      field.onChange(
                                        Number.parseInt(
                                          event.target.value,
                                          10,
                                        ) || 20,
                                      )
                                    }
                                  />
                                  <span className="text-sm font-semibold text-primary">
                                    GB
                                  </span>
                                </div>
                              </div>
                              <FormControl>
                                <Slider
                                  min={20}
                                  max={500}
                                  step={1}
                                  value={[field.value ?? 20]}
                                  onValueChange={(values) =>
                                    field.onChange(values[0])
                                  }
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>
                    </div>

                    {/* GPU Selection */}
                    {gpuOptions && gpuOptions.length > 0 && (
                      <div className="rounded-2xl border bg-muted/20 p-5">
                        <h3 className="mb-4 font-medium">GPU 加速</h3>
                        <FormField
                          control={form.control}
                          name="gpu_mapping_id"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>選擇 GPU（可選）</FormLabel>
                              <Select
                                onValueChange={(value) =>
                                  field.onChange(
                                    value === "__none__" ? "" : value,
                                  )
                                }
                                value={field.value || "__none__"}
                              >
                                <FormControl>
                                  <SelectTrigger>
                                    <SelectValue placeholder="不需要 GPU" />
                                  </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                  <SelectItem value="__none__">
                                    不需要 GPU
                                  </SelectItem>
                                  {gpuOptions.map((gpu: GPUSummary) => (
                                    <SelectItem
                                      key={gpu.mapping_id}
                                      value={gpu.mapping_id}
                                      disabled={gpu.available_count <= 0}
                                    >
                                      <div className="flex items-center gap-2">
                                        <span>{gpu.description || gpu.mapping_id}</span>
                                        {gpu.has_mdev && (
                                          <span className="text-xs text-blue-500">vGPU</span>
                                        )}
                                        {gpu.total_vram_mb > 0 && (
                                          <span className="text-xs text-muted-foreground">
                                            ({gpu.total_vram_mb >= 1024 ? `${(gpu.total_vram_mb / 1024).toFixed(0)} GB` : `${gpu.total_vram_mb} MB`}
                                            {gpu.has_mdev && gpu.used_vram_mb > 0 ? `, 已分配 ${gpu.used_vram_mb >= 1024 ? `${(gpu.used_vram_mb / 1024).toFixed(0)} GB` : `${gpu.used_vram_mb} MB`}` : ""})
                                          </span>
                                        )}
                                        {!gpu.total_vram_mb && gpu.vram && (
                                          <span className="text-xs text-muted-foreground">
                                            ({gpu.vram})
                                          </span>
                                        )}
                                        <span className="text-xs text-muted-foreground">
                                          [{gpu.available_count}/{gpu.device_count} 可用]
                                        </span>
                                        {gpu.available_count <= 0 && (
                                          <span className="text-xs text-destructive">
                                            已滿
                                          </span>
                                        )}
                                      </div>
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                              <p className="text-xs text-muted-foreground">
                                GPU 將透過 PCI Passthrough 或 vGPU
                                方式分配給虛擬機
                              </p>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>
                    )}
                  </TabsContent>

                  <FormField
                    control={form.control}
                    name="reason"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          {t("applications:form.reason")}{" "}
                          <span className="text-destructive">*</span>
                        </FormLabel>
                        <FormControl>
                          <Textarea
                            {...field}
                            className="min-h-[140px] resize-y"
                            placeholder={t(
                              "applications:form.reasonPlaceholder",
                            )}
                            required
                          />
                        </FormControl>
                        <div className="flex justify-end text-xs text-muted-foreground">
                          {(field.value || "").length}
                        </div>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </Tabs>
                {watchedMode !== "immediate" ? (
                  <RequestAvailabilityPanel
                    mode="draft"
                    onChange={(value) => {
                      updateFormValue("start_at", value.start_at ?? "")
                      updateFormValue("end_at", value.end_at ?? "")
                    }}
                    draft={{
                      resource_type: resourceType,
                      cores: Number(watchedCores || 0),
                      memory: Number(watchedMemory || 0),
                      disk_size:
                        resourceType === "vm"
                          ? Number(watchedDiskSize || 0)
                          : null,
                      rootfs_size:
                        resourceType === "lxc"
                          ? Number(watchedRootfsSize || 0)
                          : null,
                      instance_count: 1,
                      days: 7,
                      timezone: "Asia/Taipei",
                    }}
                  />
                ) : (
                  <div className="rounded-2xl border bg-muted/20 p-5 space-y-4">
                    <h3 className="font-medium">立即模式設定</h3>
                    <p className="text-sm text-muted-foreground">
                      立即模式會在送出申請後馬上開始部署，不需要選擇開始時間。
                    </p>
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id="immediate-no-end"
                        checked={watchedImmediateNoEnd ?? true}
                        onCheckedChange={(checked) =>
                          form.setValue("immediate_no_end", Boolean(checked))
                        }
                      />
                      <label
                        htmlFor="immediate-no-end"
                        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                      >
                        無限期 (No end date)
                      </label>
                    </div>
                    {!watchedImmediateNoEnd && (
                      <FormField
                        control={form.control}
                        name="end_at"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>結束時間</FormLabel>
                            <FormControl>
                              <Input
                                type="datetime-local"
                                value={field.value ?? ""}
                                onChange={field.onChange}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    )}
                  </div>
                )}
                <section className="hidden rounded-2xl border bg-card/60 p-5">
                  <div className="flex flex-col gap-3 border-b border-border/70 pb-4 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <h3 className="text-lg font-semibold tracking-tight">
                        申請摘要
                      </h3>
                      <p className="text-sm text-muted-foreground">
                        送出前先確認這筆申請會提交的內容，讓這裡的顯示資訊和審核頁看到的摘要更一致。
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="rounded-full border border-border/70 bg-background/70 px-3 py-1 text-xs font-medium text-muted-foreground">
                        {resourceType === "vm" ? "QEMU 虛擬機" : "LXC 容器"}
                      </span>
                      <span className="rounded-full bg-teal-500/15 px-3 py-1 text-xs font-medium text-teal-300">
                        {requestReadinessLabel}
                      </span>
                    </div>
                  </div>

                  <div className="mt-4 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                    <div className="rounded-xl border border-border/70 bg-background/40 px-4 py-2">
                      <SummaryRow
                        label="主機名稱"
                        value={watchedHostname?.trim() || "尚未填寫"}
                      />
                      <SummaryRow
                        label="映像 / 模板"
                        value={selectedTemplateLabel}
                      />
                      <SummaryRow label="規格" value={requestSpecSummary} />
                      <SummaryRow label="時段" value={requestWindowSummary} />
                    </div>

                    <div className="rounded-xl border border-border/70 bg-background/40 px-4 py-3">
                      <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        申請原因
                      </div>
                      <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-foreground/90">
                        {watchedReason?.trim() ||
                          "尚未填寫申請原因。建議在這裡說明用途、課程或專案背景，以及需要這個時段的原因。"}
                      </p>
                    </div>
                  </div>
                </section>
                <div className="flex flex-col gap-3 border-t pt-6 sm:flex-row sm:items-center sm:justify-between">
                  {showAiAssistant ? (
                    <p className="text-sm text-muted-foreground">
                      使用 AI 協助整理需求後，再確認規格、可申請時段與申請原因。
                    </p>
                  ) : (
                    <div />
                  )}
                  <div className="flex flex-col-reverse gap-3 sm:flex-row">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() =>
                        navigate({
                          to: backPath,
                        })
                      }
                      disabled={mutation.isPending}
                    >
                      {t("common:buttons.cancel")}
                    </Button>
                    <LoadingButton
                      type="submit"
                      loading={mutation.isPending}
                      disabled={!isSubmitReady}
                    >
                      {t("applications:create.submitButton")}
                    </LoadingButton>
                  </div>
                </div>
              </form>
            </Form>
          )}
        </div>

        {showAiAssistant && (
          <aside
            ref={aiColumnRef}
            className="min-w-0 lg:min-h-[32rem]"
            style={aiColumnStyle}
          >
            <div
              className="h-full overflow-hidden glass-panel rounded-2xl p-3"
              style={desktopPanelStyle}
            >
              <AiChatPanel
                onImportPlan={handleImportPlan}
                onImportReason={handleImportReason}
              />
            </div>
          </aside>
        )}
      </div>
    </div>
  )
}
