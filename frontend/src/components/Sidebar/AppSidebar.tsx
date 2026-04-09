import {
  ArrowRightLeft,
  Bot,
  ClipboardCheck,
  FileText,
  Home,
  Monitor,
  Network,
  KeyRound,
  ScrollText,
  ServerCog,
  Settings2,
  Shield,
  Users,
  UsersRound,
} from "lucide-react"
import { useTranslation } from "react-i18next"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { SidebarLanguageSwitcher } from "@/components/Common/LanguageSwitcher"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { type Item, Main } from "./Main"
import { User } from "./User"

export function AppSidebar() {
  const { user: currentUser } = useAuth()
  const { t } = useTranslation("navigation")

  const overviewItems: Item[] = [
    { icon: Home, title: t("sidebar.dashboard"), path: "/" },
  ]

  const resourceItems: Item[] = [
    { icon: ServerCog, title: t("sidebar.myResources"), path: "/my-resources" },
    { icon: Shield, title: "防火牆", path: "/firewall" },
  ]

  const aiItems: Item[] = [{ icon: Bot, title: "AI API", path: "/ai-api" }]

  const commonItems: Item[] = [...overviewItems, ...resourceItems, ...aiItems]

  const studentItems: Item[] = [
    ...overviewItems,
    ...resourceItems,
    { icon: FileText, title: t("sidebar.applications"), path: "/applications" },
    ...aiItems,
  ]

  const adminItems: Item[] = [
    ...overviewItems,
    ...resourceItems,
    { icon: Monitor, title: t("sidebar.resources"), path: "/resources" },
    { icon: ClipboardCheck, title: t("sidebar.approvals"), path: "/approvals" },
    ...aiItems,
    { icon: ClipboardCheck, title: "AI API 審核", path: "/ai-api-approvals" },
    { icon: KeyRound, title: "AI API 金鑰狀態", path: "/ai-api-credentials" },
    { icon: UsersRound, title: "群組管理", path: "/groups" },
    { icon: Users, title: t("sidebar.admin"), path: "/admin" },
    { icon: Settings2, title: "系統設定", path: "/admin/configuration" },
    {
      icon: ArrowRightLeft,
      title: "Migration Jobs",
      path: "/admin/migration-jobs",
    },
    { icon: Network, title: "Gateway VM", path: "/admin/gateway" },
    { icon: ScrollText, title: "稽核日誌", path: "/admin/audit-logs" },
  ]

  const items =
    currentUser?.role === "student"
      ? studentItems
      : currentUser?.role === "admin" || currentUser?.is_superuser
        ? adminItems
        : commonItems

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <Main items={items} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarLanguageSwitcher />
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
