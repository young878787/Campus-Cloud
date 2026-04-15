import {
  ArrowRightLeft,
  BarChart3,
  Bot,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Cloud,
  FileText,
  Globe,
  Home,
  KeyRound,
  Monitor,
  Network,
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
  useSidebar,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { type Item, Main } from "./Main"
import { User } from "./User"

export function AppSidebar() {
  const { user: currentUser } = useAuth()
  const { t } = useTranslation("navigation")
  const { open, toggleSidebar } = useSidebar()

  const overviewItems: Item[] = [
    { icon: Home, title: t("sidebar.dashboard"), path: "/" },
  ]

  const resourceItems: Item[] = [
    { icon: ServerCog, title: t("sidebar.myResources"), path: "/my-resources" },
    { icon: Shield, title: "防火牆", path: "/firewall" },
    { icon: Globe, title: "反向代理", path: "/reverse-proxy" },
  ]

  const aiItems: Item[] = [{ icon: Bot, title: "AI API", path: "/ai-api" }]

  const studentItems: Item[] = [
    ...overviewItems,
    ...resourceItems,
    { icon: FileText, title: t("sidebar.applications"), path: "/applications" },
    ...aiItems,
  ]

  const teacherItems: Item[] = [
    ...overviewItems,
    ...resourceItems,
    { icon: FileText, title: t("sidebar.applications"), path: "/applications" },
    ...aiItems,
    { icon: UsersRound, title: "Groups", path: "/groups" },
  ]

  const adminItems: Item[] = [
    ...overviewItems,
    ...resourceItems,
    { icon: FileText, title: t("sidebar.applications"), path: "/applications" },
    { icon: Monitor, title: t("sidebar.resources"), path: "/resources" },
    { icon: ClipboardCheck, title: t("sidebar.approvals"), path: "/approvals" },
    ...aiItems,
    { icon: ClipboardCheck, title: "AI API Review", path: "/ai-api-approvals" },
    { icon: KeyRound, title: "AI API Keys", path: "/ai-api-credentials" },
    { icon: BarChart3, title: "AI 用量監控", path: "/admin/ai-monitoring" },
    { icon: UsersRound, title: "Groups", path: "/groups" },
    { icon: Users, title: t("sidebar.admin"), path: "/admin" },
    { icon: Settings2, title: "System Settings", path: "/admin/configuration" },
    {
      icon: ArrowRightLeft,
      title: "Migration Jobs",
      path: "/admin/migration-jobs",
    },
    { icon: Cloud, title: "網域管理", path: "/admin/domains" },
    { icon: Network, title: "Gateway VM", path: "/admin/gateway" },
    { icon: ScrollText, title: "Audit Logs", path: "/admin/audit-logs" },
  ]

  const items: Item[] = !currentUser
    ? []
    : currentUser.role === "admin" || currentUser.is_superuser
      ? adminItems
      : currentUser.role === "teacher"
        ? teacherItems
        : studentItems

  return (
    <Sidebar collapsible="icon" variant="floating">
      <button
        type="button"
        onClick={toggleSidebar}
        className="absolute -right-3 top-9 z-50 flex h-6 w-6 items-center justify-center rounded-full border border-border bg-background shadow-md transition-colors hover:bg-accent"
        title={open ? "Collapse sidebar" : "Expand sidebar"}
      >
        {open ? <ChevronLeft size={12} /> : <ChevronRight size={12} />}
      </button>
      <SidebarHeader className="px-4 py-3.75 group-data-[collapsible=icon]:items-center group-data-[collapsible=icon]:px-0">
        <Logo variant="responsive" />
      </SidebarHeader>
      <hr
        style={{ borderColor: "rgba(13, 66, 195, 0.5)", margin: "0 8px 10px" }}
      />
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
