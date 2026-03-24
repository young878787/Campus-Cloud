import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Bot, Plus, X } from "lucide-react"
import { useCallback, useMemo, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"
import { LxcService, VmRequestsService, VmService } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
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
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"
import { AiChatPanel } from "./AiChatPanel"
import type { AiPlanResult } from "./AiChatPanel"
import { FastTemplatesTab, type FastTemplate } from "./FastTemplatesTab"

const CreateVMRequest = () => {
  const { t } = useTranslation([
    "applications",
    "resources",
    "validation",
    "common",
    "messages",
  ])
  const [isOpen, setIsOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<"quick" | "custom">("custom")
  const [resourceType, setResourceType] = useState<"lxc" | "vm">("lxc")
  const [showAiChat, setShowAiChat] = useState(false)
  const [serviceTemplateName, setServiceTemplateName] = useState("")
  const [serviceTemplateSlug, setServiceTemplateSlug] = useState("")
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const formSchema = useMemo(
    () =>
      z.object({
        resource_type: z.enum(["lxc", "vm"]),
        reason: z
          .string()
          .min(1, { message: t("validation:reason.required") })
          .min(10, {
            message: t("validation:reason.minLength", { count: 10 }),
          }),
        hostname: z
          .string()
          .min(1, { message: t("validation:name.required") })
          .regex(/^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/, {
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
          .min(8, {
            message: t("validation:password.minLength", { count: 8 }),
          }),
        storage: z.string().default("local-lvm"),
        os_info: z.string().optional(),
        expiry_date: z.string().optional(),
      }),
    [t],
  )

  type FormData = z.infer<typeof formSchema>

  const form = useForm<FormData>({
    resolver: standardSchemaResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      resource_type: "lxc",
      reason: "",
      hostname: "",
      ostemplate: "",
      template_id: undefined,
      username: "",
      cores: 2,
      memory: 2048,
      disk_size: 20,
      rootfs_size: 8,
      password: "",
      os_info: "",
      expiry_date: "",
    },
  })

  const { data: lxcTemplates, isLoading: lxcTemplatesLoading } = useQuery({
    queryKey: ["lxc-templates"],
    queryFn: () => LxcService.getTemplates(),
    enabled: isOpen && resourceType === "lxc",
  })

  const { data: vmTemplates, isLoading: vmTemplatesLoading } = useQuery({
    queryKey: ["vm-templates"],
    queryFn: () => VmService.getVmTemplates(),
    enabled: isOpen && resourceType === "vm",
  })

  const mutation = useMutation({
    mutationFn: (data: FormData) => {
      if (data.resource_type === "lxc") {
        if (!data.ostemplate || !data.rootfs_size) {
          throw new Error(t("validation:requirement.lxc"))
        }
        return VmRequestsService.createVmRequest({
          requestBody: {
            reason: data.reason,
            resource_type: "lxc",
            hostname: data.hostname,
            ostemplate: data.ostemplate,
            rootfs_size: data.rootfs_size,
            cores: data.cores,
            memory: data.memory,
            password: data.password,
            storage: data.storage,
            os_info: data.os_info || null,
            expiry_date: data.expiry_date || null,
          },
        })
      }
      if (!data.template_id || !data.disk_size || !data.username) {
        throw new Error(t("validation:requirement.vm"))
      }
      return VmRequestsService.createVmRequest({
        requestBody: {
          reason: data.reason,
          resource_type: "vm",
          hostname: data.hostname,
          template_id: data.template_id,
          username: data.username,
          password: data.password,
          cores: data.cores,
          memory: data.memory,
          disk_size: data.disk_size,
          os_info: data.os_info || null,
          expiry_date: data.expiry_date || null,
        },
      })
    },
    onSuccess: () => {
      showSuccessToast(t("messages:success.applicationSubmitted"))
      form.reset()
      setResourceType("lxc")
      setIsOpen(false)
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["vm-requests"] })
    },
  })

  const onSubmit = (data: FormData) => {
    mutation.mutate(data)
  }

  const handleImportPlan = useCallback(
    (prefill: AiPlanResult["final_plan"] extends infer P ? P extends { form_prefill?: infer F } ? F : never : never) => {
      if (!prefill) return
      const type = (prefill.resource_type === "vm" ? "vm" : "lxc") as "lxc" | "vm"
      setResourceType(type)
      form.setValue("resource_type", type)
      if (prefill.hostname) form.setValue("hostname", prefill.hostname)
      if (prefill.cores) form.setValue("cores", prefill.cores)
      if (prefill.memory_mb) form.setValue("memory", prefill.memory_mb)
      if (prefill.reason) form.setValue("reason", prefill.reason)

      if (type === "lxc") {
        if (prefill.disk_gb) form.setValue("rootfs_size", prefill.disk_gb)
        if (prefill.lxc_os_image) form.setValue("ostemplate", prefill.lxc_os_image)
        if (prefill.service_template_slug) {
          setServiceTemplateSlug(prefill.service_template_slug)
          setServiceTemplateName(prefill.service_template_slug)
        }
      } else {
        if (prefill.disk_gb) form.setValue("disk_size", prefill.disk_gb)
        if (prefill.vm_template_id) form.setValue("template_id", prefill.vm_template_id)
        if (prefill.username) form.setValue("username", prefill.username)
      }
      showSuccessToast(t("applications:aiChat.importSuccess"))
    },
    [form, showSuccessToast, t],
  )

  const handleImportReason = useCallback(
    (reason: string) => {
      if (reason) {
        form.setValue("reason", reason)
        showSuccessToast(t("applications:aiChat.reasonImportSuccess"))
      }
    },
    [form, showSuccessToast, t],
  )

  const handleSelectServiceTemplate = useCallback(
    (template: FastTemplate) => {
      const defaultInstallMethod =
        template.install_methods?.find(
          (method: { type?: string }) => method.type === "default",
        ) ?? template.install_methods?.[0]
      const resources = defaultInstallMethod?.resources
      const suggestedImage = lxcTemplates?.find((item) => {
        const haystack = `${item.volid || ""}`.toLowerCase()
        const keywords = [
          resources?.os,
          resources?.version,
          template.name,
          template.slug,
        ]
          .filter(Boolean)
          .map((value) => String(value).toLowerCase())

        return keywords.some((keyword) => keyword && haystack.includes(keyword))
      })

      setActiveTab("custom")
      setResourceType("lxc")
      form.setValue("resource_type", "lxc")
      setServiceTemplateName(template.name || template.slug || "")
      setServiceTemplateSlug(template.slug || "")

      if (resources?.cpu) form.setValue("cores", Number(resources.cpu))
      if (resources?.ram) form.setValue("memory", Number(resources.ram))
      if (resources?.hdd) form.setValue("rootfs_size", Number(resources.hdd))
      if (suggestedImage?.volid) form.setValue("ostemplate", suggestedImage.volid)

      showSuccessToast(
        t("applications:form.selectTemplate", {
          defaultValue: "已帶入服務範本設定",
        }),
      )
    },
    [form, lxcTemplates, showSuccessToast, t],
  )

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        setIsOpen(open)
        if (!open) {
          form.reset()
          setActiveTab("custom")
          setResourceType("lxc")
          setShowAiChat(false)
          setServiceTemplateName("")
          setServiceTemplateSlug("")
        }
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          {t("applications:create.title")}
        </Button>
      </DialogTrigger>
      <DialogContent className={`max-h-[90vh] overflow-hidden flex flex-col hidden-scroll transition-all duration-300 ${
        showAiChat
          ? "sm:max-w-[84vw] md:max-w-[82vw] lg:max-w-[1160px]"
          : "sm:max-w-3xl md:max-w-[860px] lg:max-w-[920px]"
      }`}>
        <DialogHeader
          className={`w-full shrink-0 pb-2 ${
            showAiChat ? "max-w-[720px]" : "mx-auto max-w-[820px]"
          }`}
        >
          <DialogTitle>{t("applications:create.heading")}</DialogTitle>
          <DialogDescription>
            {t("applications:create.description")}
          </DialogDescription>
        </DialogHeader>
        <div
          className={`flex-1 overflow-hidden flex min-h-0 ${
            showAiChat ? "gap-6" : "justify-center"
          }`}
        >
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className={`overflow-y-auto hidden-scroll pb-1 ${
              showAiChat
                ? "flex-1 min-w-0 max-w-[720px] pr-2"
                : "w-full max-w-[820px]"
            }`}
          >
            <Tabs
              value={activeTab}
              onValueChange={(value) => setActiveTab(value as "quick" | "custom")}
              className="mx-auto w-full max-w-[820px]"
            >
              <TabsContent value="quick" className="mt-0 pb-4">
                <FastTemplatesTab
                  onSelectTemplate={handleSelectServiceTemplate}
                  onBack={() => setActiveTab("custom")}
                />
              </TabsContent>

              <TabsContent value="custom" className="mt-0 space-y-4 py-4">
                <Tabs
                  value={resourceType}
                  onValueChange={(value) => {
                    setResourceType(value as "lxc" | "vm")
                    form.setValue("resource_type", value as "lxc" | "vm")
                  }}
                  className="mx-auto w-full max-w-[820px]"
                >
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="lxc">
                      {t("resources:form.type.lxc")}
                    </TabsTrigger>
                    <TabsTrigger value="vm">
                      {t("resources:form.type.qemu")}
                    </TabsTrigger>
                  </TabsList>

                  {/* LXC Container Form */}
                  <TabsContent value="lxc" className="mt-4">
                    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
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
                                  placeholder="例如：project-alpha-web"
                                  {...field}
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
                                defaultValue={field.value}
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
                                  ) : lxcTemplates &&
                                    lxcTemplates.length > 0 ? (
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

                        {/* Service Template (LXC only, display-only, not sent to backend) */}
                        <FormItem>
                          <FormLabel>
                            {t("applications:form.serviceTemplate")}
                          </FormLabel>
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                            <Input
                              value={serviceTemplateName}
                              placeholder={t("applications:form.serviceTemplatePlaceholder")}
                              readOnly
                              className="flex-1 min-w-0"
                            />
                            <div className="flex items-center gap-2 sm:shrink-0">
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                  setActiveTab("quick")
                                  setShowAiChat(false)
                                }}
                                className="sm:min-w-24"
                              >
                                {t("applications:form.selectTemplate")}
                              </Button>
                              {serviceTemplateName && (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => {
                                    setServiceTemplateName("")
                                    setServiceTemplateSlug("")
                                  }}
                                  className="shrink-0"
                                >
                                  {t("applications:form.clearTemplate")}
                                </Button>
                              )}
                            </div>
                          </div>
                        </FormItem>

                        <FormField
                          control={form.control}
                          name="os_info"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>
                                {t("resources:form.osInfo")}
                              </FormLabel>
                              <FormControl>
                                <Input
                                  placeholder="例如：Ubuntu 22.04 LTS"
                                  {...field}
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
                                  placeholder="設置 root 使用者密碼"
                                  type="password"
                                  {...field}
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
                      </div>
                      <div className="space-y-5 rounded-xl border bg-card/50 p-4 h-fit lg:sticky lg:top-0 self-start">
                        <h3 className="font-medium">
                          {t("resources:form.hardware")}
                        </h3>

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
                                  onValueChange={(vals) =>
                                    field.onChange(vals[0])
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
                                  onValueChange={(vals) =>
                                    field.onChange(vals[0])
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
                                    type="number"
                                    min={8}
                                    max={500}
                                    value={field.value}
                                    onChange={(e) =>
                                      field.onChange(
                                        Number.parseInt(e.target.value, 10) ||
                                          20,
                                      )
                                    }
                                    className="w-20 h-8 text-right"
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
                                  value={[field.value || 20]}
                                  onValueChange={(vals) =>
                                    field.onChange(vals[0])
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

                  {/* VM Form */}
                  <TabsContent value="vm" className="mt-4">
                    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
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
                                  placeholder="例如：web-server-01"
                                  {...field}
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
                              <FormLabel>
                                {t("resources:form.osInfo")}
                              </FormLabel>
                              <FormControl>
                                <Input
                                  placeholder="例如：Ubuntu 22.04 LTS"
                                  {...field}
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
                                <Input
                                  placeholder="例如：admin"
                                  {...field}
                                  required
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
                                {t("resources:form.password")}{" "}
                                <span className="text-destructive">*</span>
                              </FormLabel>
                              <FormControl>
                                <Input
                                  placeholder="設置使用者密碼"
                                  type="password"
                                  {...field}
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
                      </div>
                      <div className="space-y-5 rounded-xl border bg-card/50 p-4 h-fit lg:sticky lg:top-0 self-start">
                        <h3 className="font-medium">
                          {t("resources:form.hardware")}
                        </h3>

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
                                  onValueChange={(vals) =>
                                    field.onChange(vals[0])
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
                                  onValueChange={(vals) =>
                                    field.onChange(vals[0])
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
                                    type="number"
                                    min={20}
                                    max={500}
                                    value={field.value}
                                    onChange={(e) =>
                                      field.onChange(
                                        Number.parseInt(e.target.value, 10) ||
                                          20,
                                      )
                                    }
                                    className="w-20 h-8 text-right"
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
                                  value={[field.value || 20]}
                                  onValueChange={(vals) =>
                                    field.onChange(vals[0])
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
              </TabsContent>
            </Tabs>

            <div className="mt-6">
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
                        placeholder={t("applications:form.reasonPlaceholder")}
                        className="min-h-[120px] resize-y"
                        {...field}
                        required
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <DialogFooter className="mt-6">
              <div className="flex items-center gap-2 mr-auto">
                <Button
                  type="button"
                  variant={showAiChat ? "secondary" : "outline"}
                  size="sm"
                  onClick={() => {
                    setShowAiChat(!showAiChat)
                    setActiveTab("custom")
                  }}
                  className="gap-1.5"
                >
                  {showAiChat ? (
                    <>
                      <X className="h-3.5 w-3.5" />
                      {t("applications:create.closeAiChat")}
                    </>
                  ) : (
                    <>
                      <Bot className="h-3.5 w-3.5" />
                      {t("applications:create.openAiChat")}
                    </>
                  )}
                </Button>
              </div>
              <DialogClose asChild>
                <Button variant="outline" disabled={mutation.isPending}>
                  {t("common:buttons.cancel")}
                </Button>
              </DialogClose>
              <LoadingButton type="submit" loading={mutation.isPending}>
                {t("applications:create.submitButton")}
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>

        {/* AI Chat Panel */}
        {showAiChat && (
          <div className="w-[480px] shrink-0 border-l pl-6 flex flex-col min-h-0 animate-in slide-in-from-right-4 duration-300 xl:w-[560px]">
            <AiChatPanel
              onImportPlan={handleImportPlan}
              onImportReason={handleImportReason}
            />
          </div>
        )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default CreateVMRequest
