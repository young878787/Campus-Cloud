/* 像素圖小工具：在字元格上畫方塊，最後轉成 PixelSprite 吃的字串列 */

export const blank = (w, h, c = ".") => Array.from({ length: h }, () => Array(w).fill(c));

export function fill(g, x, y, w, h, c) {
  for (let j = y; j < y + h; j += 1) {
    for (let i = x; i < x + w; i += 1) {
      if (g[j] && i >= 0 && i < g[j].length) g[j][i] = c;
    }
  }
}

/* 有描邊的方塊 */
export function box(g, x, y, w, h, c, line = "o") {
  fill(g, x, y, w, h, line);
  fill(g, x + 1, y + 1, w - 2, h - 2, c);
}

export const toRows = (g) => g.map((row) => row.join(""));
