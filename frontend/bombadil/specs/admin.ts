/** 管理員角色的唯讀探索（計畫 §5：G 系列） */
import { exploration } from "../lib/explore.ts";

export * from "../properties/common.ts";

export const { login, explore, settle } = exploration("admin");
