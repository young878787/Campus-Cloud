// @ts-expect-error
import rawData from "virtual:templates"

import type { FastTemplate } from "@/components/Applications/FastTemplatesTab"

const allData = rawData as Record<string, FastTemplate>

const allTemplates = Object.entries(allData)
  .filter(
    ([path]) =>
      !path.endsWith("metadata.json") &&
      !path.endsWith("versions.json") &&
      !path.endsWith("github-versions.json"),
  )
  .map(([_, value]) => value)

export const QUICK_START_TEMPLATE_SLUGS = [
  "postgresql",
  "mongodb",
  "grafana",
  "homepage",
  "openwebui",
  "wordpress",
] as const

export type QuickStartTemplateSlug = (typeof QUICK_START_TEMPLATE_SLUGS)[number]

type QuickStartTemplateSummary = {
  slug: QuickStartTemplateSlug
  fallbackName: string
}

type QuickStartTemplateCategory = {
  id: string
  title: string
  templates: QuickStartTemplateSummary[]
}

export const QUICK_START_TEMPLATE_CATEGORIES: QuickStartTemplateCategory[] = [
  {
    id: "databases",
    title: "資料庫",
    templates: [
      { slug: "postgresql", fallbackName: "PostgreSQL" },
      { slug: "mongodb", fallbackName: "MongoDB" },
    ],
  },
  {
    id: "monitoring",
    title: "監控與分析",
    templates: [{ slug: "grafana", fallbackName: "Grafana" }],
  },
  {
    id: "dashboards",
    title: "儀表板與入口",
    templates: [{ slug: "homepage", fallbackName: "Homepage" }],
  },
  {
    id: "ai-devtools",
    title: "AI / 開發工具",
    templates: [{ slug: "openwebui", fallbackName: "Open WebUI" }],
  },
  {
    id: "webservers",
    title: "網站與代理",
    templates: [{ slug: "wordpress", fallbackName: "Wordpress" }],
  },
]

export function getQuickStartTemplate(
  slug?: QuickStartTemplateSlug | null,
): FastTemplate | null {
  if (!slug) return null
  return allTemplates.find((template) => template.slug === slug) ?? null
}

export function getQuickStartTemplateName(
  slug: QuickStartTemplateSlug,
  fallbackName: string,
): string {
  return getQuickStartTemplate(slug)?.name || fallbackName
}

export function getQuickStartTemplateDescription(
  slug: QuickStartTemplateSlug,
): string {
  const template = getQuickStartTemplate(slug)
  return (
    template?.description_zh ||
    template?.description ||
    "直接使用模板預設配置建立。"
  )
}

export function getQuickStartTemplateLogo(
  slug: QuickStartTemplateSlug,
): string | undefined {
  return getQuickStartTemplate(slug)?.logo || undefined
}

export function generateQuickStartHostname(
  slug: QuickStartTemplateSlug,
): string {
  const suffix = new Date()
    .toISOString()
    .replace(/[-:TZ.]/g, "")
    .slice(4, 10)

  return `${slug}-${suffix}`.slice(0, 63)
}
