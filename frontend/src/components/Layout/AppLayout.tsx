import { Outlet, useRouterState } from "@tanstack/react-router"

import { Footer } from "@/components/Common/Footer"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { cn } from "@/lib/utils"

// 這些路由會填滿整個內容區域，不套用 padding / max-width / footer
const FULLSCREEN_ROUTES = ["/firewall"]

export function AppLayout() {
  const { location } = useRouterState()
  const isFullscreen = FULLSCREEN_ROUTES.includes(location.pathname)
  const hasFixedFooter =
    location.pathname === "/applications-create" ||
    location.pathname === "/resources-create"

  return (
    <div className="app-layout min-h-svh w-full">
      <SidebarProvider defaultOpen={false}>
        <AppSidebar />
        <SidebarInset className="min-w-0 overflow-x-hidden">
          {isFullscreen ? (
            <main className="flex-1 min-w-0 overflow-hidden">
              <Outlet />
            </main>
          ) : (
            <>
              <main
                className={cn(
                  "flex-1 min-w-0 overflow-x-hidden py-7.5 px-20",
                  hasFixedFooter && "pb-28 md:pb-32",
                )}
              >
                <div className="w-full min-w-0 max-w-full">
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