import { useSuspenseQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { useState } from "react"

import { ResourcesService, ResourceDetailsService, SpecChangeRequestsService } from "@/client"
import type { Body_create_spec_change_request_api_v1_spec_change_requests__post } from "@/client"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { toast } from "sonner"
import useAuth from "@/hooks/useAuth"

interface SpecificationsTabProps {
  vmid: number
}

export default function SpecificationsTab({ vmid }: SpecificationsTabProps) {
  const { t } = useTranslation("resourceDetail")
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const isAdmin = user?.is_superuser || false

  const { data: config } = useSuspenseQuery({
    queryKey: ["resourceConfig", vmid],
    queryFn: () => ResourcesService.getResourceConfig({ vmid }),
  })

  const [cores, setCores] = useState<number>(config.cores || 1)
  const [memory, setMemory] = useState<number>(config.memory || 512)
  const [reason, setReason] = useState<string>("")

  const directUpdateMutation = useMutation({
    mutationFn: (data: { cores?: number; memory?: number }) =>
      ResourceDetailsService.directUpdateSpec({ vmid, requestBody: data }),
    onSuccess: () => {
      toast.success(t("specifications.updateSuccess"))
      queryClient.invalidateQueries({ queryKey: ["resourceConfig", vmid] })
    },
    onError: () => {
      toast.error(t("specifications.updateError"))
    },
  })

  const requestMutation = useMutation({
    mutationFn: (data: Body_create_spec_change_request_api_v1_spec_change_requests__post) =>
      SpecChangeRequestsService.createSpecChangeRequest({ requestBody: data }),
    onSuccess: () => {
      toast.success(t("specifications.requestSubmitted"))
      setReason("")
    },
    onError: () => {
      toast.error(t("specifications.requestError"))
    },
  })

  const handleSubmit = () => {
    if (isAdmin) {
      // Admin: direct update
      directUpdateMutation.mutate({
        cores: cores !== config.cores ? cores : undefined,
        memory: memory !== config.memory ? memory : undefined,
      })
    } else {
      // User: submit request
      if (reason.length < 10) {
        toast.error(t("specifications.reasonTooShort"))
        return
      }

      const hasChanges = cores !== config.cores || memory !== config.memory
      if (!hasChanges) {
        toast.error(t("specifications.noChanges"))
        return
      }

      requestMutation.mutate({
        vmid,
        change_type: "combined",
        reason,
        requested_cpu: cores !== config.cores ? cores : undefined,
        requested_memory: memory !== config.memory ? memory : undefined,
      })
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("specifications.title")}</CardTitle>
          <CardDescription>
            {isAdmin
              ? t("specifications.adminDesc")
              : t("specifications.userDesc")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="cores">
                CPU {t("overview.cores")}
              </Label>
              <Input
                id="cores"
                type="number"
                min={1}
                max={32}
                value={cores}
                onChange={(e) => setCores(Number.parseInt(e.target.value))}
              />
              <p className="text-xs text-muted-foreground">
                {t("specifications.currentValue")}: {config.cores}
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="memory">
                {t("overview.memory")} (MB)
              </Label>
              <Input
                id="memory"
                type="number"
                min={512}
                max={65536}
                step={512}
                value={memory}
                onChange={(e) => setMemory(Number.parseInt(e.target.value))}
              />
              <p className="text-xs text-muted-foreground">
                {t("specifications.currentValue")}: {config.memory} MB
              </p>
            </div>
          </div>

          {!isAdmin && (
            <div className="space-y-2">
              <Label htmlFor="reason">
                {t("specifications.reason")} *
              </Label>
              <Textarea
                id="reason"
                placeholder={t("specifications.reasonPlaceholder")}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={4}
              />
              <p className="text-xs text-muted-foreground">
                {t("specifications.reasonMinLength")}
              </p>
            </div>
          )}

          <Button
            onClick={handleSubmit}
            disabled={directUpdateMutation.isPending || requestMutation.isPending}
          >
            {isAdmin
              ? t("specifications.applyChanges")
              : t("specifications.submitRequest")}
          </Button>
        </CardContent>
      </Card>

      {!isAdmin && (
        <Card>
          <CardHeader>
            <CardTitle>{t("specifications.approvalProcess")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="list-decimal list-inside space-y-2 text-sm text-muted-foreground">
              <li>{t("specifications.step1")}</li>
              <li>{t("specifications.step2")}</li>
              <li>{t("specifications.step3")}</li>
            </ol>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
