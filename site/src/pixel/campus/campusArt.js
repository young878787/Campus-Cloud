/**
 * 像素校園地圖的圖：四棟建築與樹（字元格，用 PixelSprite 畫）。形狀在模組載入時算一次。
 * 配色字元（對應 CampusMap.module.scss 的 --map-* 變數，日夜各一組）：
 *   o 描邊、w 白、g 玻璃、G 亮著的窗、d 門、e 綠燈、y 金、b 藍燈、v 散熱孔、a 冷氣機、
 *   S/R 機房牆/屋簷、W/U 辦公室牆/屋頂、C/K 教學樓牆/屋簷、D/r 宿舍牆/屋頂、s 陰影、
 *   t/T 樹葉、n 樹幹
 */

import { blank, box, fill, toRows } from "./draw";

/* 窗戶：玻璃＋左上一點反光 */
function windowAt(g, x, y, w, h, glass = "g") {
  box(g, x, y, w, h, glass);
  if (glass === "g") fill(g, x + 1, y + 1, 1, 1, "w");
}

/* 機房：矮而寬的深色建築，屋頂冷氣機、天線，牆上兩排燈號、散熱孔 */
function serverRoom() {
  const g = blank(44, 26);
  fill(g, 21, 0, 1, 1, "y");
  fill(g, 21, 1, 1, 6, "o");
  box(g, 4, 3, 11, 5, "a");
  fill(g, 6, 5, 7, 1, "v");
  box(g, 29, 4, 9, 4, "a");
  fill(g, 31, 5, 5, 1, "v");
  box(g, 0, 7, 44, 19, "S");
  fill(g, 1, 8, 42, 2, "R");
  const leds = "eyeb";
  for (let i = 0; i < 9; i += 1) {
    fill(g, 4 + i * 4, 12, 2, 1, leds[i % 4]);
    fill(g, 4 + i * 4, 15, 2, 1, leds[(i + 2) % 4]);
  }
  for (let x = 3; x < 41; x += 2) fill(g, x, 19, 1, 2, "v");
  box(g, 18, 18, 8, 8, "d");
  fill(g, 20, 20, 4, 2, "g");
  return toRows(g);
}

/* 辦公室：方正的三層樓，屋頂女兒牆、旗桿，兩排窗、雙開門 */
function office() {
  const g = blank(40, 34);
  fill(g, 33, 0, 1, 9, "o");
  box(g, 34, 0, 6, 4, "y");
  fill(g, 0, 8, 40, 3, "o");
  fill(g, 1, 9, 38, 1, "U");
  box(g, 1, 10, 38, 24, "W");
  for (let r = 0; r < 2; r += 1) {
    for (let c = 0; c < 5; c += 1) windowAt(g, 4 + c * 7, 13 + r * 6, 5, 4);
  }
  box(g, 15, 26, 10, 8, "d");
  fill(g, 20, 27, 1, 7, "o");
  fill(g, 1, 32, 14, 1, "s");
  fill(g, 25, 32, 13, 1, "s");
  return toRows(g);
}

/* 教學樓：最高的一棟，中間三角山牆上有鐘，三排窗（其中一扇看得到黑板），大門 */
function classroom() {
  const g = blank(56, 44);
  for (let j = 0; j < 10; j += 1) {
    const half = 2 + j * 2;
    fill(g, 28 - half, 3 + j, half * 2, 1, j === 0 ? "o" : "C");
    // 斜邊每列往外兩格，描邊也畫兩格才連得起來
    fill(g, 28 - half, 3 + j, 2, 1, "o");
    fill(g, 28 + half - 2, 3 + j, 2, 1, "o");
  }
  box(g, 25, 6, 6, 6, "w");
  fill(g, 27, 7, 1, 3, "o");
  fill(g, 28, 9, 2, 1, "o");
  fill(g, 0, 13, 56, 1, "o");
  fill(g, 0, 14, 56, 2, "K");
  box(g, 1, 15, 54, 29, "C");
  for (let r = 0; r < 3; r += 1) {
    for (let c = 0; c < 7; c += 1) {
      const x = 4 + c * 7 + (c > 3 ? 1 : 0);
      const y = 19 + r * 7;
      if (r === 2 && (c === 3 || c === 4)) continue;
      if (r === 1 && c === 1) {
        box(g, x, y, 5, 5, "B");
        fill(g, x + 1, y + 2, 3, 1, "w");
      } else {
        windowAt(g, x, y, 5, 5);
      }
    }
  }
  box(g, 24, 35, 9, 9, "d");
  fill(g, 28, 36, 1, 8, "o");
  fill(g, 22, 43, 13, 1, "s");
  return toRows(g);
}

/* 宿舍：斜屋頂、四排小窗（有的亮著燈）、每排窗下有陽台欄杆 */
function dorm() {
  const g = blank(44, 40);
  for (let j = 0; j < 8; j += 1) {
    const inset = 8 - j;
    fill(g, inset, j, 44 - inset * 2, 1, j === 0 ? "o" : "r");
    g[j][inset] = "o";
    g[j][44 - inset - 1] = "o";
  }
  fill(g, 0, 8, 44, 1, "o");
  box(g, 1, 8, 42, 32, "D");
  for (let r = 0; r < 4; r += 1) {
    for (let c = 0; c < 5; c += 1) {
      if (r === 3 && c === 2) continue;
      const lit = (r * 5 + c) % 3 === 1;
      windowAt(g, 4 + c * 8, 11 + r * 7, 5, 5, lit ? "G" : "g");
      fill(g, 3 + c * 8, 16 + r * 7, 7, 1, "s");
    }
  }
  box(g, 18, 33, 8, 7, "d");
  fill(g, 20, 35, 4, 2, "G");
  return toRows(g);
}

export const TREE = [
  "..ttttt..",
  ".ttTtttt.",
  "tttttTttt",
  "ttTttttTt",
  "tttttttTt",
  ".tTttttt.",
  "..ttTtt..",
  "....n....",
  "....n....",
  "...nnn...",
];

/* 整張地圖 240×62 格，草地從第 52 列開始 */
export const MAP_W = 240;
export const MAP_H = 62;
export const GROUND_Y = 52;

/*
 * 四棟建築：stop 對應路線的那一站，x/y 是左上角（格），roofY 是牆面從第幾列開始（章魚從那條線後面探出頭），
 * peekX 是章魚在建築裡的橫向位置（格），pose 是探出頭的章魚。
 */
export const BUILDINGS = [
  { stop: "serverRoom", rows: serverRoom(), x: 8, y: GROUND_Y - 24, roofY: 7, peekX: 6, pose: "role-admin" },
  { stop: "office", rows: office(), x: 66, y: GROUND_Y - 32, roofY: 8, peekX: 4, pose: "approve" },
  { stop: "classroom", rows: classroom(), x: 120, y: GROUND_Y - 42, roofY: 13, peekX: 2, pose: "role-teacher" },
  { stop: "home", rows: dorm(), x: 188, y: GROUND_Y - 38, roofY: 6, peekX: 12, pose: "role-student" },
];

export const TREES = [
  { x: 56, y: GROUND_Y - 8 },
  { x: 109, y: GROUND_Y - 8 },
  { x: 178, y: GROUND_Y - 8 },
  { x: 232, y: GROUND_Y - 8 },
  { x: -2, y: GROUND_Y - 8 },
];
