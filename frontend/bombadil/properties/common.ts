/**
 * 所有角色共用的性質（G 系列，見計畫 §5）。
 */
import { always } from "@antithesishq/bombadil";
import { extract } from "@antithesishq/bombadil/browser";
import { guard, http5xx } from "../lib/guard.ts";

export { noUncaughtExceptions, noUnhandledPromiseRejections } from "@antithesishq/bombadil/browser/defaults/properties";

/** G1：唯讀探索不應碰到任何寫入請求；被 L3 擋下代表 L4 標記有漏（該補 data-bombadil） */
export const noWriteAttempted = always(() => guard.current.writes === 0);

/** G2：/api 不回 5xx（沒有 PVE 的端點由 fixtures 補上） */
export const noServerErrors = always(() => http5xx.current.length === 0);

/** 畫面文字裡的壞值：undefined / NaN / [object Object]，或沒翻譯到的 i18n key（Page.someKey 形式） */
const brokenText = extract((s) => {
  const text = s.document.body?.innerText ?? "";
  const bad = text.match(/\bundefined\b|\bNaN\b|\[object Object\]|\b[A-Z][A-Za-z]+(Page|Dialog|Panel|Tab|Card|Section|Menu|Form)\.[a-z][A-Za-z0-9]+\b/g);
  return bad ? Array.from(new Set(bad)).slice(0, 5) : [];
});

/** G5：畫面上不出現壞值或未翻譯的 key */
export const noBrokenText = always(() => brokenText.current.length === 0);
