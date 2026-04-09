import { createFileRoute, redirect } from "@tanstack/react-router"
import { Suspense } from "react"

import { UsersService } from "@/client"
import VMRequestReviewPage from "@/components/Applications/VMRequestReviewPage"
import PendingItems from "@/components/Pending/PendingItems"

export const Route = createFileRoute("/_layout/approvals_/$requestId")({
  component: ApprovalReviewRoute,
  beforeLoad: async () => {
    const user = await UsersService.readUserMe()
    if (!(user.role === "admin" || user.is_superuser)) {
      throw redirect({
        to: "/applications",
      })
    }
  },
  head: () => ({
    meta: [
      {
        title: "Request Review - Campus Cloud",
      },
    ],
  }),
})

function ApprovalReviewRoute() {
  const { requestId } = Route.useParams()

  return (
    <Suspense fallback={<PendingItems />}>
      <VMRequestReviewPage requestId={requestId} />
    </Suspense>
  )
}
