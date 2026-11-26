/**
 * L3 頁內防護：在受測頁面的 main world 包住 fetch 與 WebSocket。
 *
 * - 非 GET 的 /api 請求一律擋下回 409 並記錄（登入、換 token、純查詢 POST 例外）。
 * - WebSocket 換成不連線的假物件（終端機、VNC、課堂即時通道都不會真的連上）。
 * - 沒有 PVE 時會 502 的唯讀端點，用 fixtures 回假資料（見 fixtures.ts）。
 *
 * extractor 每個 state 都會執行，第一次執行時安裝；頁面重新載入後會再裝一次。
 * 頁面載入到第一個 state 之間的請求不經過這層，所以 L6（資料庫寫入稽核）才是最後防線。
 */
import { extract } from "@antithesishq/bombadil/browser";
import { FIXTURES } from "./fixtures.ts";

/** 會寫入但必須放行的端點：登入與換發 token（只寫 audit_logs） */
const AUTH_ALLOW = /^\/api\/v1\/login\/(access-token|refresh-token)$/;
/**
 * 頁面自動送出的低風險寫入：照樣擋下（不進資料庫），但另外計數、不算 L4 漏網。
 * - 看過頁面導覽就自動標記已看過（UserGuide.jsx）
 * - 防火牆拓撲拖動節點後存版面（FirewallPage.jsx）
 */
const EXPECTED_WRITE = /^(POST \/api\/v1\/users\/me\/user-guides\/[^/]+\/seen|PUT \/api\/v1\/firewall\/layout)$/;
/** 用 POST 送查詢條件、不寫資料的端點（已讀過後端確認） */
const QUERY_POST_ALLOW = /^\/api\/v1\/(vm-requests\/(availability|window-availability)|policies\/username\/check)$/;

export type GuardState = {
  /** 最近擋下的請求（method path，已去掉 query 與 token） */
  blocked: string[];
  /** 累計擋下的寫入請求數（不含 EXPECTED_WRITE） */
  writes: number;
  /** 累計擋下的預期內寫入數 */
  expected: number;
  /** 依「method path」分類的擋下次數 */
  byPath: Record<string, number>;
  /** 累計擋下的 WebSocket 數 */
  sockets: number;
  /** 累計回 fixture 的次數 */
  fixtures: number;
};

export const guard = extract((s): GuardState => {
  const w: any = s.window;
  if (!w.__bbGuard) {
    w.__bbGuard = { blocked: [], writes: 0, expected: 0, byPath: {}, sockets: 0, fixtures: 0 };
    const g = w.__bbGuard;
    // 預設 250 筆會滿，滿了之後的回應狀態就看不到（5xx 規則會漏）
    w.performance.setResourceTimingBufferSize(100000);
    const json = (body: unknown, status: number) =>
      new w.Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
    const orig = w.fetch.bind(w);
    w.fetch = async (input: any, init: any = {}) => {
      const url = new URL(typeof input === "string" ? input : input.url, w.location.href);
      const method = String(init.method || input?.method || "GET").toUpperCase();
      if (url.pathname.startsWith("/api/")) {
        for (const f of FIXTURES) {
          if (f.method === method && f.path.test(url.pathname)) {
            g.fixtures += 1;
            return json(typeof f.body === "function" ? f.body(url) : f.body, 200);
          }
        }
        if (method !== "GET" && !AUTH_ALLOW.test(url.pathname) && !QUERY_POST_ALLOW.test(url.pathname)) {
          const key = `${method} ${url.pathname}`;
          if (EXPECTED_WRITE.test(key)) g.expected += 1;
          else g.writes += 1;
          g.byPath[key] = (g.byPath[key] ?? 0) + 1;
          g.blocked.push(key);
          return json({ detail: "blocked by bombadil read-only guard" }, 409);
        }
      }
      return orig(input, init);
    };
    w.WebSocket = function FakeSocket(u: string) {
      g.sockets += 1;
      g.blocked.push(`WS ${String(u).split("?")[0]}`);
      // 停在 CONNECTING：不觸發 onclose，避免頁面不停重連
      return { readyState: 0, send() {}, close() {}, addEventListener() {}, removeEventListener() {} };
    };
  }
  const g = w.__bbGuard;
  return { blocked: g.blocked.slice(-10), writes: g.writes, expected: g.expected, byPath: { ...g.byPath }, sockets: g.sockets, fixtures: g.fixtures };
});

/** 本頁 /api 回應中 5xx 的清單（performance resource timing；fixture 回應不在其中） */
export const http5xx = extract((s) =>
  (s.window.performance.getEntriesByType("resource") as any[])
    .filter((e) => typeof e.responseStatus === "number" && e.responseStatus >= 500 && e.name.includes("/api/"))
    .map((e) => `${e.responseStatus} ${new URL(e.name).pathname}`),
);
