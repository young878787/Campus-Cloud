import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Check, X } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"

import { type VMRequestPublic, VmRequestsService } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { LoadingButton } from "@/components/ui/loading-button"
import { Textarea } from "@/components/ui/textarea"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

interface ReviewDialogProps {
  request: VMRequestPublic
  action: "approved" | "rejected"
  open: boolean
  onOpenChange: (open: boolean) => void
}

const ReviewDialog = ({
  request,
  action,
  open,
  onOpenChange,
}: ReviewDialogProps) => {
  const { t } = useTranslation(["approvals", "messages", "common"])
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { handleSubmit } = useForm()
  const [comment, setComment] = useState("")

  const mutation = useMutation({
    mutationFn: () =>
      VmRequestsService.reviewVmRequest({
        requestId: request.id,
        requestBody: {
          status: action,
          review_comment: comment || null,
        },
      }),
    onSuccess: () => {
      const msg =
        action === "approved"
          ? t("messages:success.applicationApproved")
          : t("messages:success.applicationRejected")
      showSuccessToast(msg)
      onOpenChange(false)
      setComment("")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["vm-requests-admin"] })
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit(() => mutation.mutate())}>
          <DialogHeader>
            <DialogTitle>
              {action === "approved"
                ? t("approvals:review.approveTitle")
                : t("approvals:review.rejectTitle")}
            </DialogTitle>
            <DialogDescription>
              {action === "approved"
                ? t("approvals:review.approveDescription", {
                    type:
                      request.resource_type === "lxc"
                        ? "LXC Container"
                        : "QEMU Virtual Machine",
                  })
                : t("approvals:review.rejectDescription")}
            </DialogDescription>
          </DialogHeader>

          <div className="py-4 space-y-4">
            <div className="rounded-lg border p-3 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">
                  {t("approvals:review.applicant")}
                </span>
                <span>{request.user_full_name || request.user_email}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">
                  {t("approvals:review.hostname")}
                </span>
                <span className="font-medium">{request.hostname}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">
                  {t("approvals:review.type")}
                </span>
                <Badge variant="secondary">
                  {request.resource_type === "lxc" ? "LXC" : "QEMU"}
                </Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">
                  {t("approvals:review.specs")}
                </span>
                <span>
                  {request.cores} Core / {(request.memory / 1024).toFixed(1)} GB
                  RAM
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">
                  {t("approvals:review.reason")}
                </span>
                <p className="mt-1 text-sm">{request.reason}</p>
              </div>
            </div>

            <div>
              <label htmlFor="review-comment" className="text-sm font-medium">
                {t("approvals:review.reviewNote")}
              </label>
              <Textarea
                id="review-comment"
                placeholder={t("approvals:review.reviewNotePlaceholder")}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                className="mt-1"
              />
            </div>
          </div>

          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline" disabled={mutation.isPending}>
                {t("approvals:review.cancel")}
              </Button>
            </DialogClose>
            <LoadingButton
              type="submit"
              loading={mutation.isPending}
              variant={action === "approved" ? "default" : "destructive"}
            >
              {action === "approved"
                ? t("approvals:review.confirmApprove")
                : t("approvals:review.confirmReject")}
            </LoadingButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

interface ReviewActionsProps {
  request: VMRequestPublic
}

export const ReviewActions = ({ request }: ReviewActionsProps) => {
  const { t } = useTranslation(["approvals"])
  const [approveOpen, setApproveOpen] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)

  if (request.status !== "pending") {
    const statusMap: Record<
      string,
      { label: string; variant: "default" | "destructive" | "outline" }
    > = {
      approved: { label: t("approvals:filters.approved"), variant: "default" },
      rejected: {
        label: t("approvals:filters.rejected"),
        variant: "destructive",
      },
    }
    const s = statusMap[request.status]
    return (
      <div className="flex items-center gap-2">
        <Badge variant={s?.variant || "outline"}>
          {s?.label || request.status}
        </Badge>
        {request.vmid && (
          <span className="text-xs text-muted-foreground">
            VMID: {request.vmid}
          </span>
        )}
      </div>
    )
  }

  return (
    <div className="flex gap-2">
      <Button size="sm" variant="default" onClick={() => setApproveOpen(true)}>
        <Check className="mr-1 h-4 w-4" />
        {t("approvals:review.approve")}
      </Button>
      <Button
        size="sm"
        variant="destructive"
        onClick={() => setRejectOpen(true)}
      >
        <X className="mr-1 h-4 w-4" />
        {t("approvals:review.reject")}
      </Button>

      <ReviewDialog
        request={request}
        action="approved"
        open={approveOpen}
        onOpenChange={setApproveOpen}
      />
      <ReviewDialog
        request={request}
        action="rejected"
        open={rejectOpen}
        onOpenChange={setRejectOpen}
      />
    </div>
  )
}
