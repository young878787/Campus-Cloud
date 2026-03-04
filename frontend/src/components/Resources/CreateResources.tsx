import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { useMemo, useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"
import { LxcService, VmService } from "@/client"
import { FastTemplatesTab } from "@/components/Applications/FastTemplatesTab"
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
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

const CreateContainer = () => {
  const { t } = useTranslation(["resources", "validation", "common"])
  const [isOpen, setIsOpen] = useState(false)
  const [resourceType, setResourceType] = useState<"lxc" | "vm">("lxc")
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const formSchema = useMemo(
    () =>
      z.object({
        resource_type: z.enum(["lxc", "vm"]),
        hostname: z
          .string()
          .min(1, { message: t("validation:name.required") })
          .regex(/^[a-z0-9-]+$/, {
            message: t("validation:name.invalid"),
          }),
        // LXC specific
        ostemplate: z.string().optional(),
        rootfs_size: z.number().min(8).max(500).optional(),
        // VM specific
        template_id: z.number().optional(),
        disk_size: z.number().min(20).max(500).optional(),
        username: z.string().optional(),
        // Common fields
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

  type FormData = z.infer<typeof formSchema>

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
      os_info: "",
      expiry_date: "",
    },
  })

  // Fetch available LXC templates
  const { data: lxcTemplates, isLoading: lxcTemplatesLoading } = useQuery({
    queryKey: ["lxc-templates"],
    queryFn: () => LxcService.getTemplates(),
    enabled: isOpen && resourceType === "lxc",
  })

  // Fetch available VM templates
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
        return LxcService.createLxc({
          requestBody: {
            hostname: data.hostname,
            ostemplate: data.ostemplate,
            cores: data.cores,
            memory: data.memory,
            rootfs_size: data.rootfs_size,
            password: data.password,
            storage: data.storage,
            environment_type: t("resources:create.customSpec"),
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
      form.reset()
      setIsOpen(false)
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["resources"] })
    },
  })

  const onSubmit = (data: FormData) => {
    mutation.mutate(data)
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          {t("resources:create.title")}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-3xl md:max-w-4xl lg:max-w-5xl max-h-[90vh] overflow-hidden flex flex-col hidden-scroll">
        <DialogHeader className="shrink-0 pb-2">
          <DialogTitle>{t("resources:create.heading")}</DialogTitle>
          <DialogDescription>
            {t("resources:create.description")}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="flex-1 overflow-y-auto hidden-scroll pl-1 pr-4 -mr-4 pb-1"
          >
            <Tabs defaultValue="custom" className="w-full">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="quick">
                  {t("resources:create.quickTemplate")}
                </TabsTrigger>
                <TabsTrigger value="custom">
                  {t("resources:create.customSpec")}
                </TabsTrigger>
              </TabsList>

              <TabsContent value="quick" className="mt-4 pb-4">
                <FastTemplatesTab />
              </TabsContent>

              <TabsContent value="custom" className="space-y-4 py-4">
                {/* Resource Type Tabs */}
                <Tabs
                  defaultValue="lxc"
                  onValueChange={(value) => {
                    setResourceType(value as "lxc" | "vm")
                    form.setValue("resource_type", value as "lxc" | "vm")
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

                  <TabsContent value="lxc" className="mt-4">
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                      <div className="space-y-4">
                        {/* Container Name */}
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

                        {/* OS Template */}
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

                        {/* OS Info */}
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

                        {/* Root Password */}
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

                        {/* Expiry Date */}
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

                      {/* Hardware Resources */}
                      <div className="space-y-6 border rounded-lg p-5 bg-card/50 h-fit sticky top-0">
                        <h3 className="font-medium">
                          {t("resources:form.hardware")}
                        </h3>

                        {/* CPU Cores */}
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

                        {/* Memory (RAM) */}
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

                        {/* Disk Size */}
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
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                      <div className="space-y-4">
                        {/* VM Name */}
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

                        {/* OS Template */}
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

                        {/* OS Info */}
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

                        {/* Username */}
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

                        {/* Root Password */}
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

                        {/* Expiry Date */}
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

                      {/* Hardware Resources */}
                      <div className="space-y-6 border rounded-lg p-5 bg-card/50 h-fit sticky top-0">
                        <h3 className="font-medium">
                          {t("resources:form.hardware")}
                        </h3>

                        {/* CPU Cores */}
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

                        {/* Memory (RAM) */}
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

                        {/* Disk Size */}
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

            <DialogFooter className="mt-6">
              <DialogClose asChild>
                <Button variant="outline" disabled={mutation.isPending}>
                  {t("common:buttons.cancel")}
                </Button>
              </DialogClose>
              <LoadingButton type="submit" loading={mutation.isPending}>
                {t("resources:create.submitButton")}
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

export default CreateContainer
