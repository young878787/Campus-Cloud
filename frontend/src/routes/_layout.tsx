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
    <div className="app-layout min-h-svh w-full">
    <SidebarProvider defaultOpen={false}>
      <AppSidebar />
      <SidebarInset>
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
              <div className="max-w-7xl">
                <Outlet />
              </div>
            </main>
            <Footer
              data-app-footer={hasFixedFooter ? "fixed" : undefined}
              className={
                hasFixedFooter
                  ? "sticky bottom-0 z-20 mt-auto bg-background/95 backdrop-blur supports-backdrop-filter:bg-background/80"
                  : undefined
              }
            />
          </>
        )}
      </SidebarInset>
    </SidebarProvider>
    </div>
  )
}

export default Layout
