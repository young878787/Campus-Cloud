import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "@tanstack/react-router"
import {
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  LayoutTemplate,
  X,
} from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { useForm, useWatch } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"

import { LxcService, VmService } from "@/client"
import {
  type FastTemplate,
  FastTemplatesTab,
} from "@/components/Applications/FastTemplatesTab"
import { Button } from "@/components/ui/button"
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
import useCustomToast from "@/hooks/useCustomToast"
import { queryKeys } from "@/lib/queryKeys"
import {
  toLxcCreateRequestBody,
  toVmCreateRequestBody,
} from "@/lib/resourcePayloads"
import { pickMatchingOsTemplate } from "@/lib/serviceTemplates"
import {
  generateQuickStartHostname,
  getQuickStartTemplate,
  type QuickStartTemplateSlug,
} from "@/lib/templateQuickStart"
import { FirewallService } from "@/services/firewall"
import { ReverseProxyApiService } from "@/services/reverseProxy"
import { handleError } from "@/utils"

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

function normalizeDomainLabel(value: string) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 63)
}

function getTemplateInterfacePort(
  template: FastTemplate | null,
): number | null {
  return typeof template?.interface_port === "number"
    ? template.interface_port
    : null
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  if (
    error &&
    typeof error === "object" &&
    "body" in error &&
    error.body &&
    typeof error.body === "object" &&
    "detail" in error.body &&
    typeof error.body.detail === "string"
  ) {
    return error.body.detail
  }
  return "設定進階網路時發生錯誤。"
}

type QuickStartAccessMode = "private" | "public-website" | "public-port"
type QuickStartFirewallPreset = "safe" | "website" | "internal"

export function ResourceCreatePage({
  quickStartTemplate,
}: {
  quickStartTemplate?: QuickStartTemplateSlug
}) {
  const { t } = useTranslation([
    "resources",
    "validation",
    "common",
    "messages",
    "applications",
  ])
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [showTemplateSelector, setShowTemplateSelector] = useState(false)
  const [resourceType, setResourceType] = useState<"lxc" | "vm">("lxc")
  const [serviceTemplateName, setServiceTemplateName] = useState("")
  const [serviceTemplateSlug, setServiceTemplateSlug] = useState("")
  const [lastAutoHostname, setLastAutoHostname] = useState("")
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false)
  const [accessMode, setAccessMode] = useState<QuickStartAccessMode>("private")
  const [enableHttps, setEnableHttps] = useState("on")
  const [firewallPreset, setFirewallPreset] =
    useState<QuickStartFirewallPreset>("safe")
  const [autoDomain, setAutoDomain] = useState("on")
  const [externalPort, setExternalPort] = useState("")
  const activeQuickStartTemplate = useMemo(
    () => getQuickStartTemplate(quickStartTemplate),
    [quickStartTemplate],
  )
  const isQuickStartMode = Boolean(activeQuickStartTemplate)
  const quickStartInterfacePort = useMemo(
    () => getTemplateInterfacePort(activeQuickStartTemplate),
    [activeQuickStartTemplate],
  )

  const formSchema = useMemo(
    () =>
      z.object({
        resource_type: z.enum(["lxc", "vm"]),
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
        password: z
          .string()
          .min(1, { message: t("validation:password.required") })
          .min(6, {
            message: t("validation:password.minLength", { count: 6 }),
          }),
        storage: z.string().default("local-lvm"),
        os_info: z.string().optional(),
        expiry_date: z.string().optional(),
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
      hostname: "",
      ostemplate: "",
      template_id: undefined,
      username: "",
      cores: 2,
      memory: 2048,
      disk_size: 20,
      rootfs_size: 8,
      password: "",
      storage: "local-lvm",
      os_info: "",
      expiry_date: "",
    },
  })

  const watchedOsTemplate = useWatch({
    control: form.control,
    name: "ostemplate",
  })
  const watchedHostname = useWatch({
    control: form.control,
    name: "hostname",
  })

  const isQuickStartTemplateReady =
    !isQuickStartMode || Boolean(watchedOsTemplate)

  const { data: reverseProxySetupContext } = useQuery({
    queryKey: ["reverse-proxy-setup-context"],
    queryFn: () => ReverseProxyApiService.getSetupContext(),
    enabled: isQuickStartMode,
  })

  const canAutoCreateWebsite =
    Boolean(quickStartInterfacePort) &&
    Boolean(reverseProxySetupContext?.enabled) &&
    Boolean(reverseProxySetupContext?.gateway_ready) &&
    Boolean(reverseProxySetupContext?.cloudflare_ready) &&
    Boolean(reverseProxySetupContext?.zones.length)

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

  const applyQuickStartNetworkSettings = useCallback(
    async (vmid: number, hostname: string) => {
      const notices: string[] = []
      const warnings: string[] = []

      if (!isQuickStartMode) return { notices, warnings }
      const requiresServicePort =
        accessMode !== "private" || firewallPreset === "website"
      if (!quickStartInterfacePort && requiresServicePort) {
        warnings.push("此模板沒有預設對外服務 Port，已略過進階網路設定。")
        return { notices, warnings }
      }

      if (accessMode === "public-website") {
        const zone = reverseProxySetupContext?.zones[0]
        if (!canAutoCreateWebsite || !zone) {
          warnings.push("目前無法自動建立公開網站，請稍後於反向代理頁面設定。")
        } else if (autoDomain !== "on") {
          warnings.push("你已關閉自動網域，建立後可再手動設定公開網站。")
        } else {
          const hostnamePrefix = normalizeDomainLabel(hostname) || `app-${vmid}`
          await ReverseProxyApiService.createRule({
            vmid,
            zone_id: zone.id,
            hostname_prefix: hostnamePrefix,
            internal_port: quickStartInterfacePort!,
            enable_https: enableHttps === "on",
          })
          notices.push(`已建立公開網站：${hostnamePrefix}.${zone.name}`)
        }
      }

      if (accessMode === "public-port") {
        const requestedExternalPort =
          Number.parseInt(externalPort, 10) || quickStartInterfacePort
        if (!Number.isInteger(requestedExternalPort)) {
          warnings.push("外部 Port 格式無效，已略過公開 Port 設定。")
        } else {
          await FirewallService.createFirewallConnection({
            requestBody: {
              source_vmid: null,
              target_vmid: vmid,
              ports: [
                {
                  port: quickStartInterfacePort!,
                  protocol: "tcp",
                  external_port: requestedExternalPort,
                },
              ],
              direction: "one_way",
            },
          })
          notices.push(`已開放公開 Port：${requestedExternalPort}`)
        }
      }

      if (firewallPreset === "website" && accessMode === "private") {
        await FirewallService.createFirewallConnection({
          requestBody: {
            source_vmid: null,
            target_vmid: vmid,
            ports: [
              {
                port: quickStartInterfacePort!,
                protocol: "tcp",
              },
            ],
            direction: "one_way",
          },
        })
        notices.push(
          `已套用網站防火牆預設，開放內部服務 Port ${quickStartInterfacePort}`,
        )
      }

      return { notices, warnings }
    },
    [
      accessMode,
      autoDomain,
      canAutoCreateWebsite,
      enableHttps,
      externalPort,
      firewallPreset,
      isQuickStartMode,
      quickStartInterfacePort,
      reverseProxySetupContext?.zones,
    ],
  )

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

      if (data.resource_type === "lxc") {
        return LxcService.createLxc({
          requestBody: toLxcCreateRequestBody(
            {
              ...data,
              service_template_slug: serviceTemplateSlug || undefined,
            },
            payloadOptions,
          ),
        })
      }

      return VmService.createVm({
        requestBody: toVmCreateRequestBody(
          { ...data, service_template_slug: serviceTemplateSlug || undefined },
          payloadOptions,
        ),
      })
    },
    onSuccess: async (data) => {
      const successMessages = [
        data.message || t("messages:success.resourceCreated"),
      ]

      if (isQuickStartMode) {
        try {
          const networkResult = await applyQuickStartNetworkSettings(
            data.vmid,
            form.getValues("hostname"),
          )
          successMessages.push(...networkResult.notices)
          if (networkResult.warnings.length > 0) {
            showErrorToast(networkResult.warnings.join(" "))
          }
        } catch (error) {
          showErrorToast(getErrorMessage(error))
        }
      }

      showSuccessToast(successMessages.join(" "))
      queryClient.invalidateQueries({ queryKey: queryKeys.resources.all })
      navigate({ to: "/resources" })
    },
    onError: handleError.bind(showErrorToast),
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

  const handleSelectTemplate = useCallback(
    (template: FastTemplate) => {
      setServiceTemplateName(template.name || "")
      setServiceTemplateSlug(template.slug || "")
      setResourceType("lxc")
      updateFormValue("resource_type", "lxc")

      const method = template.install_methods?.[0]
      // 帶入模板的預設資源值，但保留使用者已輸入的容器名稱
      if (method?.resources) {
        if (method.resources.cpu) updateFormValue("cores", method.resources.cpu)
        if (method.resources.ram)
          updateFormValue("memory", method.resources.ram)
        if (method.resources.hdd)
          updateFormValue("rootfs_size", Math.max(method.resources.hdd, 8))
      }

      // 自動挑選一個符合模板要求 OS / version 的 ostemplate volid
      const volids = (lxcTemplates ?? []).map((t) => t.volid)
      const picked =
        pickMatchingOsTemplate(volids, method?.resources) || volids[0]
      if (picked) {
        updateFormValue("ostemplate", picked)
      }
      if (method?.resources?.os) {
        const osLabel = method.resources.version
          ? `${method.resources.os} ${method.resources.version}`
          : String(method.resources.os)
        updateFormValue("os_info", osLabel)
      }

      setShowTemplateSelector(false)
    },
    [lxcTemplates, updateFormValue],
  )

  useEffect(() => {
    if (!activeQuickStartTemplate) return
    handleSelectTemplate(activeQuickStartTemplate)
  }, [activeQuickStartTemplate, handleSelectTemplate])

  useEffect(() => {
    if (!activeQuickStartTemplate?.slug) return

    const currentHostname = form.getValues("hostname")
    if (currentHostname.trim() && currentHostname !== lastAutoHostname) return

    const generatedHostname = generateQuickStartHostname(
      activeQuickStartTemplate.slug as QuickStartTemplateSlug,
    )
    updateFormValue("hostname", generatedHostname)
    setLastAutoHostname(generatedHostname)
  }, [activeQuickStartTemplate, form, lastAutoHostname, updateFormValue])

  useEffect(() => {
    if (!quickStartInterfacePort) {
      setExternalPort("")
      return
    }
    setExternalPort((currentValue) =>
      currentValue.trim() ? currentValue : String(quickStartInterfacePort),
    )
  }, [quickStartInterfacePort])

  useEffect(() => {
    if (accessMode === "public-website" && !canAutoCreateWebsite) {
      setAccessMode("private")
    }
  }, [accessMode, canAutoCreateWebsite])

  const onSubmit = (data: FormData) => {
    mutation.mutate(data)
  }

  return (
    <div className="mx-auto flex w-full max-w-[760px] flex-col gap-6">
      <div className="flex items-start gap-3">
        <Button
          asChild
          variant="outline"
          size="icon"
          className="mt-0.5 shrink-0"
        >
          <Link to="/resources" aria-label={t("common:buttons.back")}>
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="min-w-0">
          <h1 className="text-2xl font-bold tracking-tight">
            {isQuickStartMode ? "快速入門" : t("resources:create.heading")}
          </h1>
          <p className="text-muted-foreground">
            {isQuickStartMode
              ? `已選擇 ${activeQuickStartTemplate?.name || ""}，先填名稱與密碼即可直接建立。`
              : t("resources:create.description")}
          </p>
        </div>
      </div>

      {isQuickStartMode ? (
        <div className="rounded-2xl border border-primary/20 bg-primary/5 px-4 py-3">
          <div className="flex min-w-0 items-start gap-3">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-xl border bg-background">
              {activeQuickStartTemplate?.logo ? (
                <img
                  src={activeQuickStartTemplate.logo}
                  alt={activeQuickStartTemplate.name}
                  className="h-8 w-8 object-contain"
                  loading="lazy"
                />
              ) : (
                <LayoutTemplate className="h-5 w-5 text-primary" />
              )}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium text-primary">
                {activeQuickStartTemplate?.name}
              </p>
              <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                {activeQuickStartTemplate?.description_zh ||
                  activeQuickStartTemplate?.description ||
                  "使用模板預設配置，不顯示進階設定。"}
              </p>
              <p className="mt-2 text-xs text-muted-foreground">
                名稱已自動產生，可直接修改。
              </p>
            </div>
          </div>
          {!isQuickStartTemplateReady ? (
            <p className="mt-3 text-xs text-muted-foreground">
              正在準備基礎映像，完成後即可建立。
            </p>
          ) : null}
          <div className="mt-3 flex justify-end">
            <div className="hidden min-w-0">
              <p className="text-sm font-medium text-primary">
                {activeQuickStartTemplate?.name}
              </p>
              <p className="text-sm text-muted-foreground">
                使用模板預設配置，不顯示進階設定。
              </p>
            </div>
            <Button asChild variant="ghost" size="sm" className="shrink-0">
              <Link to="/resources-create">改用完整設定</Link>
            </Button>
          </div>
        </div>
      ) : null}

      {isQuickStartMode ? (
        <div className="rounded-2xl border bg-background/70 p-4">
          <button
            type="button"
            className="flex w-full items-center justify-between gap-3 text-left"
            onClick={() => setShowAdvancedSettings((current) => !current)}
          >
            <div>
              <p className="text-sm font-medium">進階設定</p>
              <p className="text-xs text-muted-foreground">
                公開網站、公開 Port、防火牆、HTTPS、自動網域
              </p>
            </div>
            {showAdvancedSettings ? (
              <ChevronUp className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            )}
          </button>

          {showAdvancedSettings ? (
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <p className="text-sm font-medium">公開存取</p>
                <Select
                  value={accessMode}
                  onValueChange={(value) =>
                    setAccessMode(value as QuickStartAccessMode)
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="private">不公開</SelectItem>
                    <SelectItem
                      value="public-website"
                      disabled={!canAutoCreateWebsite}
                    >
                      公開網站
                    </SelectItem>
                    <SelectItem
                      value="public-port"
                      disabled={!quickStartInterfacePort}
                    >
                      公開 Port
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium">防火牆預設</p>
                <Select
                  value={firewallPreset}
                  onValueChange={(value) =>
                    setFirewallPreset(value as QuickStartFirewallPreset)
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="safe">安全</SelectItem>
                    <SelectItem
                      value="website"
                      disabled={!quickStartInterfacePort}
                    >
                      網站
                    </SelectItem>
                    <SelectItem value="internal">內部</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {accessMode === "public-website" ? (
                <>
                  <div className="space-y-2">
                    <p className="text-sm font-medium">HTTPS</p>
                    <Select value={enableHttps} onValueChange={setEnableHttps}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="on">開</SelectItem>
                        <SelectItem value="off">關</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <p className="text-sm font-medium">自動網域</p>
                    <Select value={autoDomain} onValueChange={setAutoDomain}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="on">開</SelectItem>
                        <SelectItem value="off">關</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </>
              ) : null}

              {accessMode === "public-port" ? (
                <div className="space-y-2 md:col-span-2">
                  <p className="text-sm font-medium">外部 Port</p>
                  <Input
                    aria-label="外部 Port"
                    type="number"
                    min={1}
                    max={65535}
                    value={externalPort}
                    onChange={(event) => setExternalPort(event.target.value)}
                    placeholder={
                      quickStartInterfacePort
                        ? String(quickStartInterfacePort)
                        : "8080"
                    }
                  />
                </div>
              ) : null}

              <div className="md:col-span-2 rounded-xl bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                {quickStartInterfacePort ? (
                  <p>模板預設服務 Port：{quickStartInterfacePort}</p>
                ) : (
                  <p>此模板沒有預設服務 Port，公開網站與公開 Port 會停用。</p>
                )}
                {accessMode === "public-website" && canAutoCreateWebsite ? (
                  <p className="mt-1">
                    會使用 `{normalizeDomainLabel(watchedHostname) || "app"}`
                    作為子網域前綴。
                  </p>
                ) : null}
                {accessMode === "public-website" && !canAutoCreateWebsite ? (
                  <p className="mt-1">
                    目前反向代理或 DNS 尚未完成設定，暫時不能自動建立公開網站。
                  </p>
                ) : null}
                {firewallPreset === "internal" ? (
                  <p className="mt-1">內部模式不會自動建立對外公開規則。</p>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {showTemplateSelector && !isQuickStartMode ? (
        <FastTemplatesTab
          onSelectTemplate={handleSelectTemplate}
          onBack={() => setShowTemplateSelector(false)}
        />
      ) : (
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <Tabs
              value={resourceType}
              onValueChange={(value) => {
                if (isQuickStartMode) return
                const nextType = value as "lxc" | "vm"
                setResourceType(nextType)
                updateFormValue("resource_type", nextType)
              }}
              className="w-full"
            >
              {isQuickStartMode ? null : (
                <TabsList className="grid w-full grid-cols-2">
                  <TabsTrigger value="lxc">
                    {t("resources:form.type.lxc")}
                  </TabsTrigger>
                  <TabsTrigger value="vm">
                    {t("resources:form.type.qemu")}
                  </TabsTrigger>
                </TabsList>
              )}

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
                      <FormItem
                        className={serviceTemplateSlug ? "hidden" : undefined}
                      >
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

                  {isQuickStartMode ? null : (
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
                  )}

                  {isQuickStartMode ? null : (
                    <FormField
                      control={form.control}
                      name="os_info"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>{t("resources:form.osInfo")}</FormLabel>
                          <FormControl>
                            <Input {...field} placeholder="Ubuntu 22.04 LTS" />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}

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

                  {isQuickStartMode ? null : (
                    <FormField
                      control={form.control}
                      name="expiry_date"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>
                            {t("resources:form.expiryDate")}
                          </FormLabel>
                          <FormControl>
                            <Input type="date" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}
                </div>

                {isQuickStartMode ? null : (
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
                              <FormLabel>{t("resources:form.disk")}</FormLabel>
                              <div className="flex items-center gap-2">
                                <Input
                                  className="h-8 w-20 text-right"
                                  type="number"
                                  min={8}
                                  max={500}
                                  value={field.value ?? 8}
                                  onChange={(event) =>
                                    field.onChange(
                                      Number.parseInt(event.target.value, 10) ||
                                        8,
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
                )}
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
                          <Input {...field} placeholder="Ubuntu 22.04 LTS" />
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

                  <FormField
                    control={form.control}
                    name="expiry_date"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t("resources:form.expiryDate")}</FormLabel>
                        <FormControl>
                          <Input type="date" {...field} />
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
                            <FormLabel>{t("resources:form.memory")}</FormLabel>
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
                            <FormLabel>{t("resources:form.disk")}</FormLabel>
                            <div className="flex items-center gap-2">
                              <Input
                                className="h-8 w-20 text-right"
                                type="number"
                                min={20}
                                max={500}
                                value={field.value ?? 20}
                                onChange={(event) =>
                                  field.onChange(
                                    Number.parseInt(event.target.value, 10) ||
                                      20,
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
              </TabsContent>
            </Tabs>

            <div className="flex flex-col gap-3 border-t pt-6 sm:flex-row sm:items-center sm:justify-end">
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate({ to: "/resources" })}
                disabled={mutation.isPending}
              >
                {t("common:buttons.cancel")}
              </Button>
              <LoadingButton
                type="submit"
                loading={mutation.isPending}
                disabled={!isSubmitReady || !isQuickStartTemplateReady}
              >
                {t("resources:create.submitButton")}
              </LoadingButton>
            </div>
          </form>
        </Form>
      )}
    </div>
  )
}
