/**
 * 防火牆拓撲（/firewall）的拖拉互動（計畫 §5：F 系列）。
 *
 * 拓撲資料來自 fixtures：Internet、自己的 web-101 / db-102、班級的 class-103（不可管理）、
 * 一條 Internet → 101 的連線。動作集中在拖動節點、從 handle 拉線、對話框只按 Escape。
 */
import { actions, weighted, always, eventually, now } from "@antithesishq/bombadil";
import { extract } from "@antithesishq/bombadil/browser";
import { ACCOUNTS, goto, loginAs, onLogin, route } from "../lib/navigation.ts";
import { safeClicks } from "../lib/safety.ts";

export { noUncaughtExceptions, noUnhandledPromiseRejections, noServerErrors, noWriteAttempted } from "../properties/common.ts";

/** fixtures 的 VM（101、102 自己的，103 班級的） */
const FIXTURE_VMS = new Set(["101", "102", "103"]);
/** fixtures 的連線數 */
const FIXTURE_EDGES = 1;

const flow = extract((s) => {
  const pane = s.document.querySelector(".react-flow__pane")?.getBoundingClientRect();
  const nodes = Array.from(s.document.querySelectorAll(".react-flow__node")).map((n) => {
    const r = n.getBoundingClientRect();
    return {
      id: n.getAttribute("data-id") ?? "",
      type: Array.from(n.classList).find((c) => c.startsWith("react-flow__node-"))?.slice(17) ?? "",
      x: r.x, y: r.y, w: r.width, h: r.height,
      transform: (n as HTMLElement).style.transform,
    };
  });
  const handles = Array.from(s.document.querySelectorAll(".react-flow__handle.source")).map((h) => {
    const r = h.getBoundingClientRect();
    return { node: h.closest(".react-flow__node")?.getAttribute("data-id") ?? "", x: r.x + r.width / 2, y: r.y + r.height / 2 };
  });
  /* F1：畫面條件（分組、只看對外、搜尋、群組篩選、各群組收合）沒變時，VM 節點不能少。
     條件一變（篩選、收合）就重新起算，而且 2 秒內不判定：按鈕狀態先變、節點下一個 state 才套用篩選
     （實測「只看對外開放」誤報）。上一個狀態的節點存在 window 上，換頁或重新載入會清掉 */
  const doc = s.document;
  const view = JSON.stringify([
    Array.from(doc.querySelectorAll("[aria-pressed]")).map((b) => b.getAttribute("aria-pressed")),
    Array.from(doc.querySelectorAll("[role=search] input, [role=search] select")).map((e) => (e as HTMLInputElement).value),
    Array.from(doc.querySelectorAll(".react-flow__node-vmGroup [aria-expanded]")).map((b) => b.getAttribute("aria-expanded")),
  ]);
  const vmIds = nodes.filter((n) => n.type === "vm").map((n) => n.id);
  const w: any = s.window;
  const prev = w.__bbFlowView;
  const now = Date.now();
  const since = prev && prev.view === view ? prev.since : now;
  const lost = prev && prev.view === view && now - since > 2000 && vmIds.length
    ? prev.ids.filter((id: string) => !vmIds.includes(id))
    : [];
  w.__bbFlowView = vmIds.length ? { view, ids: vmIds, since } : undefined;
  return {
    pane: pane ? { x: pane.x, y: pane.y, w: pane.width, h: pane.height } : null,
    nodes,
    lost,
    handles,
    edges: s.document.querySelectorAll(".react-flow__edge").length,
    /* 節點座標變成 NaN 時，節點的 CSS transform 會被瀏覽器當成無效值丟掉（DOM 看不到 NaN），
       但 SVG 連線的 d／transform 屬性不做檢查，會原樣留下 NaN */
    nanEdges: Array.from(s.document.querySelectorAll(".react-flow__edges [d], .react-flow__edges [transform]")).some((e) =>
      /NaN|Infinity/.test(`${e.getAttribute("d") ?? ""} ${e.getAttribute("transform") ?? ""}`),
    ),
    dialog: !!s.document.querySelector("[role=dialog], [role=alertdialog]"),
    view: { w: s.window.innerWidth, h: s.window.innerHeight },
  };
});

const onFirewall = () => route.current === "/firewall" && flow.current.pane !== null;
/** 拖拉座標要在視窗內且非負（節點被拖到畫面外時跳過） */
const visible = (p: { x: number; y: number }) => p.x >= 1 && p.y >= 1 && p.x < flow.current.view.w - 1 && p.y < flow.current.view.h - 1;
const clampRange = (lo: number, hi: number, max: number): [number, number] => {
  const a = Math.max(1, Math.min(lo, max - 2));
  const b = Math.max(a, Math.min(hi, max - 2));
  return [Math.round(a), Math.round(b)];
};
const vms = () => flow.current.nodes.filter((n) => n.type === "vm");

const { email, password } = ACCOUNTS.student;
export const login = actions(() => (onLogin.current ? [loginAs(email, password)] : []));
const go = actions(() => (route.current !== "/firewall" ? [goto("/firewall")] : []));

const drag = actions(() => {
  const p = flow.current.pane;
  if (!p) return [];
  const { w, h } = flow.current.view;
  return vms()
    .map((n) => ({ x: n.x + n.w / 2, y: n.y + n.h / 2 }))
    .filter(visible)
    .map((from) => ({
      MouseDrag: {
        from,
        to: { x: clampRange(p.x + 40, p.x + p.w - 40, w), y: clampRange(p.y + 40, p.y + p.h - 40, h) },
        steps: 12,
        delayMillis: 15,
      },
    }));
});
const connect = actions(() => {
  const out: any[] = [];
  for (const h of flow.current.handles)
    for (const n of flow.current.nodes)
      if (n.id !== h.node && n.type !== "vmGroup") {
        const to = { x: n.x + n.w / 2, y: n.y + n.h / 2 };
        if (visible(h) && visible(to)) out.push({ MouseDrag: { from: { x: h.x, y: h.y }, to, steps: 15, delayMillis: 15 } });
      }
  return out;
});
const ESCAPE = 27;

/** 對話框開著時只能按 Escape；沒開時拖、拉線、點畫面上的安全元素 */
export const explore = weighted([
  [1, go],
  [6, drag.when(() => onFirewall() && !flow.current.dialog)],
  [6, connect.when(() => onFirewall() && !flow.current.dialog)],
  [3, safeClicks.when(() => onFirewall() && !flow.current.dialog)],
  [1, actions(() => ["Wait" as const])],
] as any).when(() => !onLogin.current && !flow.current.dialog);
export const closeDialog = actions(() => [{ PressKey: { code: ESCAPE } }]).when(() => flow.current.dialog);

/** F1：VM 節點不重複、都來自伺服器資料；畫面條件沒變時不會少（篩選、收合會減少節點，但拖拉、拉線不會） */
export const vmNodesConsistent = always(() => {
  const ids = vms().map((n) => n.id);
  return new Set(ids).size === ids.length && ids.every((id) => FIXTURE_VMS.has(id)) && flow.current.lost.length === 0;
});

/** F2：節點位置永遠是有限數字（拖到邊界、快速連續拖動不產生 NaN）；連線的 SVG 屬性也不能有 NaN */
export const nodePositionsFinite = always(() =>
  !flow.current.nanEdges &&
  flow.current.nodes.every((n) => Number.isFinite(n.x) && Number.isFinite(n.y) && !/NaN|Infinity/.test(n.transform)),
);

/** F3：寫入一律被拒（409），畫面上的連線不能多於伺服器的資料超過 5 秒（不留下沒存成功的連線）；
 *  篩選只會讓連線變少，所以只檢查「變多」 */
export const noUnsavedEdges = always(
  now(() => !flow.current.dialog && flow.current.edges > FIXTURE_EDGES).implies(
    eventually(() => flow.current.dialog || flow.current.edges <= FIXTURE_EDGES).within(5, "seconds"),
  ),
);

/** F4：對話框按 Escape 會在 3 秒內關閉 */
export const dialogClosesOnEscape = always(now(() => flow.current.dialog).implies(eventually(() => !flow.current.dialog).within(3, "seconds")));
