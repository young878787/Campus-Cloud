/**
 * L4 動作過濾：Bombadil 產生的點擊、輸入、按鍵，碰到危險元素就不做。
 *
 * 危險元素 = 產品程式上標了 data-bombadil="danger" 的元素（與其子孫），
 * 加上結構規則：另開分頁的連結、下載連結、檔案選擇器。
 * 規則見 docs/ui-test-bombadil/bombadil-ui-test-plan.md §4。
 */
import { extract } from "@antithesishq/bombadil/browser";
import { isAction } from "@antithesishq/bombadil/actions";
import { clicks as defaultClicks, inputs as defaultInputs, lastAction } from "@antithesishq/bombadil/browser/defaults/actions";

const DANGER_SELECTOR = [
  '[data-bombadil="danger"]',
  'a[target="_blank"]',
  "a[download]",
  'input[type="file"]',
  'label:has(input[type="file"])',
  // sonner toast 的動作鈕（例如「開啟桌面通知」）：toast 由程式產生，無法逐一加屬性；取消鈕（data-cancel）照常可點
  "[data-sonner-toast] [data-button]:not([data-cancel])",
].join(", ");

type Rect = { x: number; y: number; w: number; h: number };

export const danger = extract((s) => {
  const rects: Rect[] = [];
  for (const el of Array.from(s.document.querySelectorAll(DANGER_SELECTOR))) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) rects.push({ x: r.x, y: r.y, w: r.width, h: r.height });
  }
  const active = s.document.activeElement;
  /*
   * 跟上一個 state 比：危險元素的位置沒變，才代表版面已經停下來（見 safeClicks、explore.ts 的 settle）。
   * 連續 5 個 state 都在動（例如一直變動的元素）就當作停下，避免探索卡死；這時仍有 L3 兜底。
   */
  const w: any = s.window;
  const sig = rects.map((r) => [r.x, r.y, r.w, r.h].map(Math.round).join(",")).join(";");
  const same = w.__bbDangerSig === sig;
  w.__bbDangerSig = sig;
  w.__bbUnsettled = same ? 0 : (w.__bbUnsettled ?? 0) + 1;
  const settled = same || w.__bbUnsettled > 5;
  return {
    rects,
    settled,
    /** 目前焦點在危險元素裡（例如 Enter 送出的 AI 輸入框、Monaco 編輯器） */
    focusInDanger: !!active?.closest(DANGER_SELECTOR),
    /** 目前焦點在表單裡：Enter 會送出表單，一律不按 */
    focusInForm: !!active?.closest("form"),
  };
});

const inRect = (p: { x: number; y: number }) =>
  danger.current.rects.some((r) => p.x >= r.x - 1 && p.x <= r.x + r.w + 1 && p.y >= r.y - 1 && p.y <= r.y + r.h + 1);

/** 外部網址：只允許相對路徑與本機（受測站一定在 127.0.0.1 / localhost，見 run.sh 的 L2 檢查） */
const external = (href: string | null) =>
  !!href && /^[a-z][a-z0-9+.-]*:/i.test(href) && !/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?(\/|$)/.test(href);

/**
 * 剛捲動完的 state 可能是捲到一半拍的（平滑捲動），座標會過期：
 * 實測在首頁點「查看完整資訊」卻點到旁邊的「啟動並進入」。捲動後的下一步不點擊，等下一個 state 重新取座標。
 */
const justScrolled = () => {
  const a = lastAction.current;
  return !!a && typeof a === "object" && ("ScrollUp" in a || "ScrollDown" in a);
};

/**
 * 版面還在動（換頁進場、側欄展開帶動主區捲動與變寬）時，state 拍到的座標點下去會落在別的元素上：
 * 校準實測兩次在首頁點「查看完整資訊」或電源鈕，實際點到隔壁卡片的「啟動並進入」。
 * 危險元素的位置跟上一個 state 一樣才點擊；不一樣就這一步不點，等下一個 state。
 */
export const safeClicks = defaultClicks.filter((a) => {
  if (!isAction(a, "Click")) return true;
  if (justScrolled()) return false;
  if (!danger.current.settled) return false;
  if (external(a.Click.fingerprint.href)) return false;
  return !inRect(a.Click.point);
});

const ENTER = 13;
export const safeInputs = defaultInputs.filter((a) => {
  if (danger.current.focusInDanger) return false;
  if (isAction(a, "PressKey") && a.PressKey.code === ENTER && danger.current.focusInForm) return false;
  return true;
});
