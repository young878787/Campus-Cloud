import { createFileRoute, Link } from "@tanstack/react-router"
import { Sparkles } from "lucide-react"
import { useTranslation } from "react-i18next"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import useAuth from "@/hooks/useAuth"
import {
  getQuickStartTemplateDescription,
  getQuickStartTemplateLogo,
  getQuickStartTemplateName,
  QUICK_START_TEMPLATE_CATEGORIES,
} from "@/lib/templateQuickStart"

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
    <div className="space-y-8">
      <div>
        <h1
          className="text-4xl font-bold tracking-tight truncate max-w-lg"
          style={{ color: "#5471BF" }}
        >
          {t("dashboard.welcome", {
            name: currentUser?.full_name || currentUser?.email,
          })}
        </h1>
        <p className="mt-2 text-base" style={{ color: "#5471BF" }}>
          {t("dashboard.description")}
        </p>
      </div>

      {currentUser?.is_superuser ? (
        <section className="space-y-4">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary/10">
                <Sparkles className="h-4 w-4 text-primary" />
              </div>
              <h2 className="text-2xl font-semibold tracking-tight">
                快速入門
              </h2>
            </div>
            <p className="max-w-3xl text-sm text-muted-foreground">
              直接選模板建立，不處理申請與時段。
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {QUICK_START_TEMPLATE_CATEGORIES.map((category) => (
              <Card key={category.id} className="border-border/70 shadow-sm">
                <CardHeader className="pb-4">
                  <CardTitle className="text-lg">{category.title}</CardTitle>
                  <CardDescription>選一個模板直接建立</CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-2">
                  {category.templates.map((template) => (
                    <Link
                      key={template.slug}
                      to="/resources-create"
                      search={{ quickStartTemplate: template.slug }}
                      className="flex items-start gap-3 rounded-xl border border-border/70 px-3 py-3 transition-colors hover:border-primary/40 hover:bg-muted/40"
                    >
                      <div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-lg border bg-background">
                        {getQuickStartTemplateLogo(template.slug) ? (
                          <img
                            src={getQuickStartTemplateLogo(template.slug)}
                            alt={getQuickStartTemplateName(
                              template.slug,
                              template.fallbackName,
                            )}
                            className="h-8 w-8 object-contain"
                            loading="lazy"
                          />
                        ) : (
                          <Sparkles className="h-4 w-4 text-primary" />
                        )}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium leading-5">
                          {getQuickStartTemplateName(
                            template.slug,
                            template.fallbackName,
                          )}
                        </p>
                        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                          {getQuickStartTemplateDescription(template.slug)}
                        </p>
                      </div>
                    </Link>
                  ))}
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  )
}
