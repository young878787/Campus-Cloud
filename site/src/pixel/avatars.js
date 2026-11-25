import { decorativeSvg } from "./decorativeSvg";

/* 品牌身分章魚的圓形頭像（桌面「品牌元素\身分章魚\頭像」），以 student／teacher／admin 為鍵，內容是 SVG 原始碼 */
export const AVATARS = Object.fromEntries(
  Object.entries(import.meta.glob("./assets/avatar/*.svg", { query: "?raw", import: "default", eager: true })).map(
    ([path, svg]) => [path.split("/").pop().replace(".svg", ""), decorativeSvg(svg)],
  ),
);
