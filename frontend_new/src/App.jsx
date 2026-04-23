import { useState } from "react";
import { useAuth } from "./contexts/AuthContext";
import DashboardLayout from "./layout/DashboardLayout";
import LoginPage from "./pages/login/LoginPage";

// 個人
import DashboardPage   from "./pages/personal/dashboard/DashboardPage";
import ResourcesPage   from "./pages/personal/resources/ResourcesPage";
import RequestsPage    from "./pages/personal/requests/RequestsPage";

// 資源
import ResourceMgmtPage  from "./pages/resource/resource-mgmt/ResourceMgmtPage";
import RequestReviewPage from "./pages/resource/request-review/RequestReviewPage";

// AI
import AiApiPage       from "./pages/ai/ai-api/AiApiPage";
import AiApiReviewPage from "./pages/ai/ai-api-review/AiApiReviewPage";
import AiApiKeysPage   from "./pages/ai/ai-api-keys/AiApiKeysPage";

// 系統管理
import GroupsPage    from "./pages/system/groups/GroupsPage";
import AdminPage     from "./pages/system/admin/AdminPage";
import SettingsPage  from "./pages/system/settings/SettingsPage";
import MigrationPage from "./pages/system/migration/MigrationPage";
import AuditPage     from "./pages/system/audit/AuditPage";

// 網路
import FirewallPage       from "./pages/network/firewall/FirewallPage";
import DomainPage         from "./pages/network/domain/DomainPage";
import GatewayPage        from "./pages/network/gateway/GatewayPage";
import ReverseProxyPage   from "./pages/network/reverse-proxy/ReverseProxyPage";

const PAGE_MAP = {
  dashboard:        <DashboardPage />,
  "my-resources":   <ResourcesPage />,
  "my-requests":    <RequestsPage />,
  "resource-mgmt":  <ResourceMgmtPage />,
  "request-review": <RequestReviewPage />,
  "ai-api":         <AiApiPage />,
  "ai-api-review":  <AiApiReviewPage />,
  "ai-api-keys":    <AiApiKeysPage />,
  groups:           <GroupsPage />,
  admin:            <AdminPage />,
  settings:         <SettingsPage />,
  migration:        <MigrationPage />,
  audit:            <AuditPage />,
  firewall:         <FirewallPage />,
  domain:           <DomainPage />,
  gateway:          <GatewayPage />,
  "reverse-proxy":  <ReverseProxyPage />,
};

function App() {
  const { user, loading } = useAuth();
  const [activePage, setActivePage] = useState("dashboard");

  // 初始化時驗證 token，避免未登入畫面閃爍
  if (loading) return null;

  // 未登入 → 顯示登入頁
  if (!user) return <LoginPage />;

  const page = PAGE_MAP[activePage] ?? PAGE_MAP.dashboard;

  return (
    <DashboardLayout activePage={activePage} onNavigate={setActivePage}>
      {page}
    </DashboardLayout>
  );
}

export default App;
