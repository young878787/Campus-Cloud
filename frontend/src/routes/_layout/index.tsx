import { createFileRoute } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"

import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [
      {
        title: "Dashboard - Campus Cloud",
      },
    ],
  }),
})

function Dashboard() {
  const { user: currentUser } = useAuth()
  const { t } = useTranslation("navigation")

  return (
    <div>
      <div>
        <h1 className="text-4xl font-bold tracking-tight truncate max-w-lg" style={{ color: "#5471BF" }}>
          {t("dashboard.welcome", {
            name: currentUser?.full_name || currentUser?.email,
          })}
        </h1>
        <p className="mt-2 text-base" style={{ color: "#5471BF" }}>{t("dashboard.description")}</p>
      </div>
    </div>
  )
}
