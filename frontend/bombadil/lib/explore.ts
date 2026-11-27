/**
 * 各角色共用的探索動作組合。
 *
 * 在登入頁時只做登入；登入後依權重隨機點擊、輸入、捲動、返上一頁、
 * 跳到角色路由（保證路由涵蓋），以及少量權限探測（跳到不該進的路由）。
 * 版面還在動時只等待（settle），等停下來再探索：不然點擊會被 safeClicks 濾掉，
 * 空出來的步數全變成跳頁與返回，點擊數減半、探索變淺（實測 3 分鐘 340 → 140 次）。
 */
import { actions, weighted } from "@antithesishq/bombadil";
import { back, scroll } from "@antithesishq/bombadil/browser/defaults/actions";
import { ACCOUNTS, FORBIDDEN, ROUTES, goto, loginAs, onLogin, visitedPaths, type Role } from "./navigation.ts";
import { danger, safeClicks, safeInputs } from "./safety.ts";

export function exploration(role: Role) {
  const { email, password } = ACCOUNTS[role];
  const login = actions(() => (onLogin.current ? [loginAs(email, password)] : []));
  /* 先跳還沒去過的路由，全部去過後再隨機：admin 有 36 條，純隨機 5 分鐘內常漏 1–2 條（短校準 5 次有 2 次） */
  const routes = actions(() => {
    const todo = ROUTES[role].filter((p) => !visitedPaths.current.includes(p));
    return (todo.length ? todo : ROUTES[role]).map((p) => goto(p));
  });
  const probeGroups = FORBIDDEN[role].map((group) => [1, actions(() => group.map((p) => goto(p)))]);
  const wait = actions(() => ["Wait" as const]);
  const explore = weighted([
    [12, safeClicks],
    [4, safeInputs],
    [2, scroll],
    [1, back],
    [3, routes],
    ...(probeGroups.length ? [[1, weighted(probeGroups as any)]] : []),
    [1, wait],
  ] as any).when(() => !onLogin.current && danger.current.settled);
  const settle = wait.when(() => !onLogin.current && !danger.current.settled);
  return { login, explore, settle };
}
