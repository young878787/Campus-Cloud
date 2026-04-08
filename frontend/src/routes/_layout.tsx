import {
  createFileRoute,
  Outlet,
  redirect,
  useRouterState,
} from "@tanstack/react-router"

import { Footer } from "@/components/Common/Footer"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { isLoggedIn } from "@/hooks/useAuth"
import { cn } from "@/lib/utils"

// 這些路由會填滿整個內容區域，不套用 padding / max-width / footer
const FULLSCREEN_ROUTES = ["/firewall"]

export const Route = createFileRoute("/_layout")({
  component: Layout,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }
  },
})

function Layout() {
  const { location } = useRouterState()
  const isFullscreen = FULLSCREEN_ROUTES.includes(location.pathname)
  const hasFixedFooter =
    location.pathname === "/applications-create" ||
    location.pathname === "/resources-create"

  return (
    <SidebarProvider className="app-background">
      <AppSidebar />
      <SidebarInset>
        <header className="glass-header sticky top-0 z-10 flex h-16 shrink-0 items-center gap-2 px-4">
          <SidebarTrigger className="-ml-1 text-muted-foreground" />
        </header>
        {isFullscreen ? (
          <main className="flex-1 overflow-hidden">
            <Outlet />
          </main>
        ) : (
          <>
            <main
              className={cn(
                "flex-1 p-6 md:p-8",
                hasFixedFooter && "pb-28 md:pb-32",
              )}
            >
              <div className="mx-auto max-w-7xl">
                <Outlet />
              </div>
            </main>
            <Footer
              data-app-footer={hasFixedFooter ? "fixed" : undefined}
              className={
                hasFixedFooter
                  ? "glass-footer sticky bottom-0 z-20 mt-auto"
                  : undefined
              }
            />
          </>
        )}
      </SidebarInset>
    </SidebarProvider>
  )
}

export default Layout
