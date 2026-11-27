/**
 * 登入、路由跳轉與各角色可走的路由清單。
 *
 * Bombadil 只會點畫面上看得到的東西；側欄收在選單裡、或要先有資料才出現的頁面
 * 不容易隨機走到，所以每個角色另外給一組 goto 動作，保證路由涵蓋率。
 */
import { extract, registerCustomAction } from "@antithesishq/bombadil/browser";

export { ACCOUNTS, ADMIN_ONLY, FORBIDDEN, ROUTES, TEACH_ONLY, type Role } from "./routes.ts";

export const route = extract((s) => s.window.location.pathname);

/** 這次瀏覽走過的路徑：每個 state 累加在頁面上（goto 是 SPA 內跳轉，不會清掉），給 goto 挑沒去過的路由 */
export const visitedPaths = extract((s) => {
  const w: any = s.window;
  w.__bbVisited ??= [];
  const p = s.window.location.pathname;
  if (!w.__bbVisited.includes(p)) w.__bbVisited.push(p);
  return w.__bbVisited.slice() as string[];
});

/**
 * 這個路由上還沒選過的分頁（role=tab）的位置。分頁多半是元件狀態、不在網址上，
 * 隨機點擊常漏掉：admin 10 分鐘實測詳情頁的「進階設定」一次都沒點到（計畫 §14.2 A3）。
 * 選過的分頁（aria-selected）記在 window 上，重新載入會清掉。
 */
export const freshTabs = extract((s) => {
  const w: any = s.window;
  w.__bbTabsSeen ??= [];
  const path = s.window.location.pathname;
  const tabs = Array.from(s.document.querySelectorAll("[role=tab]"));
  const key = (el: Element) => `${path}|${el.textContent?.trim()}`;
  for (const el of tabs)
    if (el.getAttribute("aria-selected") === "true" && !w.__bbTabsSeen.includes(key(el))) w.__bbTabsSeen.push(key(el));
  return tabs
    .filter((el) => !w.__bbTabsSeen.includes(key(el)))
    .map((el) => {
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height };
    })
    .filter((r) => r.w > 0 && r.h > 0);
});

export const onLogin = extract(
  (s) => s.window.location.pathname === "/login" && !!s.document.querySelector("form input[type=password]"),
);

/** 畫面上是否是 404 頁（NotFoundPage 的標題，三種語系） */
export const notFound = extract((s) => {
  const titles = Array.from(s.document.querySelectorAll("h1, h2")).map((h) => h.textContent ?? "");
  return titles.some((h) => /找不到這個頁面|Page not found|ページが見つかりません/.test(h));
});

/** React 受控 input 要用原生 setter 再發 input 事件，才會更新 state */
export const loginAs = registerCustomAction("loginAs", async (document, window, email: string, password: string) => {
  const set = (el: HTMLInputElement, v: string) => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
    setter.call(el, v);
    el.dispatchEvent(new window.Event("input", { bubbles: true }));
  };
  const form = document.querySelector("form") as HTMLFormElement | null;
  if (!form) return;
  const user = form.querySelector("input:not([type=password])") as HTMLInputElement | null;
  const pass = form.querySelector("input[type=password]") as HTMLInputElement | null;
  if (!user || !pass) return;
  set(user, email);
  set(pass, password);
  (form.querySelector("button[type=submit]") as HTMLButtonElement | null)?.click();
  await new Promise((r) => setTimeout(r, 1500));
});

/** SPA 內跳轉（不重新載入頁面，L3 防護不會掉） */
export const goto = registerCustomAction("goto", async (_document, window, path: string) => {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new window.PopStateEvent("popstate"));
  await new Promise((r) => setTimeout(r, 1200));
});
