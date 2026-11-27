/** 學生角色的唯讀探索（計畫 §5：G + S 系列） */
import { exploration } from "../lib/explore.ts";

export * from "../properties/common.ts";
export { adminRoutesShowNotFound, teachRoutesRedirectStudent, noAdminLinks, noTeachLinks } from "../properties/auth.ts";

export const { login, explore, settle } = exploration("student");
