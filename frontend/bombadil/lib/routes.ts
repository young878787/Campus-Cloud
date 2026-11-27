/**
 * 各角色的帳號與路由清單。不依賴 Bombadil，analyze.py 也會用 node 讀這個檔算路由涵蓋率。
 */
export type Role = "student" | "teacher" | "admin";

export const ACCOUNTS: Record<Role, { email: string; password: string }> = {
  student: { email: "student@example.com", password: "UiTest-Pass-1234" },
  teacher: { email: "teacher@example.com", password: "UiTest-Pass-1234" },
  admin: { email: "admin@example.com", password: "UiTest-Admin-1234" },
};

/** 所有登入後角色都能進的頁面（101 / 102 是 fixtures 裡的機器） */
const COMMON = [
  "/dashboard",
  "/my-resources",
  "/my-resources/101",
  "/my-resources/102",
  "/my-requests",
  "/quick-create",
  "/account",
  "/ai-api",
  "/jobs",
  "/firewall",
];
const STUDENT_ONLY = ["/courses"];
const TEACH = ["/templates", "/course-cms", "/course-template-management", "/course-template-management/new", "/class-management", "/class-setup"];
const ADMIN = [
  "/admin", "/pve-connections", "/scheduler", "/governance", "/ldap", "/storage", "/ip-management", "/monitoring",
  "/audit", "/feedback", "/resource-mgmt", "/resource-mgmt/101", "/request-review", "/gpu-mgmt", "/batch-review",
  "/ai-api-review", "/ai-api-keys", "/ai-monitoring", "/domain", "/gateway",
];

export const ROUTES: Record<Role, string[]> = {
  student: [...COMMON, ...STUDENT_ONLY],
  teacher: [...COMMON, ...TEACH],
  admin: [...COMMON, ...STUDENT_ONLY, ...TEACH, ...ADMIN],
};

/** 非管理員進去只能看到 404 的路由（App.jsx 的 isAdmin 區塊） */
export const ADMIN_ONLY = new RegExp(`^(${ADMIN.map((p) => p.replace(/\/\d+$/, "")).filter((p, i, a) => a.indexOf(p) === i).join("|")})(/|$)`);
/** 學生進去會被導回的教學路由（App.jsx 的 canTeach） */
export const TEACH_ONLY = /^\/(templates|course-cms|course-template-management|class-management|class-setup)(\/|$)/;
/**
 * 權限探測用：角色不該進的路由，按類別分組；探測時各組機率相同。
 * 不分組的話學生的 6 條教學路由淹沒在 27 條管理員路由裡，3 分鐘很難探到（P5 實測 S2 漏抓）。
 */
export const FORBIDDEN: Record<Role, string[][]> = {
  student: [TEACH, ADMIN],
  teacher: [ADMIN],
  admin: [],
};
