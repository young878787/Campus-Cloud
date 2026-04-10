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
  useSidebar,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { type Item, Main } from "./Main"
import { User } from "./User"

export function AppSidebar() {
  const { user: currentUser } = useAuth()
  const { t } = useTranslation("navigation")
  const { setOpen } = useSidebar()

  const overviewItems: Item[] = [
    { icon: Home, title: t("sidebar.dashboard"), path: "/" },
  ]

  const resourceItems: Item[] = [
    { icon: ServerCog, title: t("sidebar.myResources"), path: "/my-resources" },
    { icon: Shield, title: "防火牆", path: "/firewall" },
  ]

  const aiItems: Item[] = [{ icon: Bot, title: "AI API", path: "/ai-api" }]

  const teacherItems: Item[] = [...overviewItems, ...resourceItems, ...aiItems]

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

  // currentUser 為 undefined 時（初次載入 / token refresh 中）不要 fallback 到
  // 任何角色的選單，避免 admin 使用者在 refresh 期間被暫時降級成 teacher 選單。
  const items: Item[] = !currentUser
    ? []
    : currentUser.role === "student"
      ? studentItems
      : currentUser.role === "admin" || currentUser.is_superuser
        ? adminItems
        : teacherItems

  return (
    <Sidebar
      collapsible="icon"
      variant="floating"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <SidebarHeader className="px-4 py-3.75 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <hr style={{ borderColor: "rgba(13, 66, 195, 0.5)", margin: "0 8px 10px" }} />
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
