import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "@tanstack/react-router"
import { ArrowLeft, LayoutTemplate, X } from "lucide-react"
import { useCallback, useMemo, useState } from "react"
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
import { handleError } from "@/utils"

function normalizeHostname(value: string) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 63)
}

export function ResourceCreatePage() {
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

  const formSchema = useMemo(
    () =>
      z.object({
        resource_type: z.enum(["lxc", "vm"]),
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

  const watchedResourceType = useWatch({
    control: form.control,
    name: "resource_type",
  })
  const watchedHostname = useWatch({ control: form.control, name: "hostname" })
  const watchedPassword = useWatch({ control: form.control, name: "password" })
  const watchedOsTemplate = useWatch({
    control: form.control,
    name: "ostemplate",
  })
  const watchedTemplateId = useWatch({
    control: form.control,
    name: "template_id",
  })
  const watchedUsername = useWatch({ control: form.control, name: "username" })

  const isSubmitReady = useMemo(() => {
    const basicReady = Boolean(watchedHostname?.trim() && watchedPassword)

    if (!basicReady) return false

    if (watchedResourceType === "vm") {
      return Boolean(watchedTemplateId && watchedUsername?.trim())
    }

    return Boolean(watchedOsTemplate)
  }, [
    watchedHostname,
    watchedOsTemplate,
    watchedPassword,
    watchedResourceType,
    watchedTemplateId,
    watchedUsername,
  ])

  const { data: lxcTemplates, isLoading: lxcTemplatesLoading } = useQuery({
    queryKey: ["lxc-templates"],
    queryFn: () => LxcService.getTemplates(),
    enabled: resourceType === "lxc",
  })

  const { data: vmTemplates, isLoading: vmTemplatesLoading } = useQuery({
    queryKey: ["vm-templates"],
    queryFn: () => VmService.getVmTemplates(),
    enabled: resourceType === "vm",
  })

  const mutation = useMutation({
    mutationFn: (data: FormData) => {
      if (data.resource_type === "lxc") {
        if (!data.ostemplate || !data.rootfs_size) {
          throw new Error(t("validation:requirement.lxc"))
        }
        return LxcService.createLxc({
          requestBody: {
            hostname: data.hostname,
            ostemplate: data.ostemplate,
            cores: data.cores,
            memory: data.memory,
            rootfs_size: data.rootfs_size,
            password: data.password,
            storage: data.storage,
            environment_type:
              serviceTemplateName || t("resources:create.customSpec"),
            os_info: data.os_info || null,
            expiry_date: data.expiry_date || null,
            start: true,
            unprivileged: true,
          },
        })
      }
      if (!data.template_id || !data.disk_size || !data.username) {
        throw new Error(t("validation:requirement.vm"))
      }
      return VmService.createVm({
        requestBody: {
          hostname: data.hostname,
          template_id: data.template_id,
          username: data.username,
          password: data.password,
          cores: data.cores,
          memory: data.memory,
          disk_size: data.disk_size,
          environment_type: t("resources:create.customSpec"),
          os_info: data.os_info || null,
          expiry_date: data.expiry_date || null,
          start: true,
        },
      })
    },
    onSuccess: (data) => {
      showSuccessToast(
        `${data.message || t("messages:success.resourceCreated")}`,
      )
      queryClient.invalidateQueries({ queryKey: ["resources"] })
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
      if (template.name) {
        updateFormValue("hostname", normalizeHostname(template.name))
      }
      setShowTemplateSelector(false)
    },
    [updateFormValue],
  )

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
            {t("resources:create.heading")}
          </h1>
          <p className="text-muted-foreground">
            {t("resources:create.description")}
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
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
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
                          <Input {...field} placeholder="Ubuntu 22.04 LTS" />
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
                disabled={!isSubmitReady}
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
