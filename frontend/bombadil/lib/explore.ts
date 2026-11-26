/**
 * 各角色共用的探索動作組合。
 *
 * 在登入頁時只做登入；登入後依權重隨機點擊、輸入、捲動、返上一頁、
 * 跳到角色路由（保證路由涵蓋），以及少量權限探測（跳到不該進的路由）。
 */
import { actions, weighted } from "@antithesishq/bombadil";
import { back, scroll } from "@antithesishq/bombadil/browser/defaults/actions";
import { ACCOUNTS, FORBIDDEN, ROUTES, goto, loginAs, onLogin, type Role } from "./navigation.ts";
import { safeClicks, safeInputs } from "./safety.ts";

export function exploration(role: Role) {
  const { email, password } = ACCOUNTS[role];
  const login = actions(() => (onLogin.current ? [loginAs(email, password)] : []));
  const routes = actions(() => ROUTES[role].map((p) => goto(p)));
  const probe = actions(() => FORBIDDEN[role].map((p) => goto(p)));
  const wait = actions(() => ["Wait" as const]);
  const explore = weighted([
    [12, safeClicks],
    [4, safeInputs],
    [2, scroll],
    [1, back],
    [3, routes],
    ...(FORBIDDEN[role].length ? ([[1, probe]] as const) : []),
    [1, wait],
  ] as any).when(() => !onLogin.current);
  return { login, explore };
}
