/**
 * 走進建築裡：室內場景（字元格，PixelSprite 畫）。分層畫，章魚才能夾在牆和家具中間：
 *   room（牆、窗、地板、裝飾）→ 章魚 → layers（擋在章魚前面的家具）→ items（可以滑過的那幾樣）。
 * 每間房間左上角留給章魚的對話泡泡（那一塊只放窗、盆栽這類裝飾，被蓋住也沒關係）。
 * 配色字元對應 Room.module.scss 的 --room-* 變數：
 *   o 描邊、W 牆、V 牆裙、v 牆裙壓條、F 地板、f 地板縫、k 窗外天空、c 雲、B 軟木板、p 紙、l 紙上的字、
 *   r 紅、y 金、D 木頭（桌面、框）、d 桌身、M 櫃子、m 櫃子暗面、P 花盆、G/g 葉子、K 螢幕底、e 綠、b 藍、
 *   t 印章木柄、R 印泥紅、s 陰影、Q 黑板、w 粉筆
 */
import { blank, box, fill, toRows } from "./draw";

export const ROOM_W = 192;
export const ROOM_H = 72;

/* 共用的房間外殼：整面牆、牆裙、踢腳板、木地板 */
function shell() {
  const g = blank(ROOM_W, ROOM_H, "W");
  fill(g, 0, 44, ROOM_W, 10, "V");
  fill(g, 0, 44, ROOM_W, 1, "v");
  fill(g, 0, 54, ROOM_W, 1, "o");
  fill(g, 0, 55, ROOM_W, 17, "F");
  for (const y of [60, 66]) fill(g, 0, y, ROOM_W, 1, "f");
  for (let x = 6; x < ROOM_W; x += 24) {
    fill(g, x, 55, 1, 5, "f");
    fill(g, x + 12, 61, 1, 5, "f");
    fill(g, x + 6, 67, 1, 5, "f");
  }
  return g;
}

/* 窗：天空、兩朵雲、十字窗框、窗台 */
function windowAt(g, x, y, w, h) {
  box(g, x, y, w, h, "k");
  fill(g, x + 3, y + 4, 6, 2, "c");
  fill(g, x + 5, y + 3, 3, 1, "c");
  fill(g, x + w - 12, y + h - 10, 8, 2, "c");
  fill(g, x + w - 10, y + h - 11, 3, 1, "c");
  fill(g, x + Math.floor(w / 2) - 1, y + 1, 2, h - 2, "o");
  fill(g, x + 1, y + Math.floor(h / 2), w - 2, 1, "o");
  fill(g, x - 2, y + h, w + 4, 2, "D");
  fill(g, x - 2, y + h + 2, w + 4, 1, "o");
}

/* 盆栽（擺在地板上） */
function plantAt(g, x) {
  box(g, x, 48, 10, 11, "P");
  fill(g, x + 1, 49, 8, 1, "s");
  const leaves = ["...GG.....", "..GGgG.G..", ".GgGGGGgG.", "GGGGgGGGGG", ".GgGGGgGG.", "..GGGGGG.."];
  leaves.forEach((row, j) => [...row].forEach((ch, i) => ch !== "." && fill(g, x + i, 42 + j, 1, 1, ch)));
}

/* 時鐘 */
function clockAt(g, x, y) {
  box(g, x, y, 11, 11, "p");
  fill(g, x + 5, y + 2, 1, 4, "o");
  fill(g, x + 5, y + 5, 3, 1, "o");
}

/* 一疊紙（申請單、作業） */
function paperStack(lines = "l") {
  const g = blank(20, 8);
  box(g, 2, 3, 17, 5, "p");
  box(g, 1, 1, 17, 5, "p");
  box(g, 0, 0, 17, 5, "p");
  for (const y of [1, 3]) fill(g, 2, y, 11, 1, lines);
  return toRows(g);
}

/* ── 辦公室 ── */

/* 桌面那一列（章魚坐在桌子後面，下半身躲在這條線後面） */
const OFFICE_DESK_TOP = 38;

/* 左邊窗、布告欄貼著申請單、時鐘，右邊檔案櫃 */
function officeRoom() {
  const g = shell();
  windowAt(g, 10, 8, 34, 26);
  const bx = 74;
  box(g, bx, 6, 30, 20, "B");
  box(g, bx + 3, 9, 8, 10, "p");
  for (const y of [11, 13, 15]) fill(g, bx + 4, y, 5, 1, "l");
  fill(g, bx + 6, 8, 2, 1, "r");
  box(g, bx + 14, 8, 7, 7, "p");
  fill(g, bx + 15, 10, 4, 1, "l");
  fill(g, bx + 17, 7, 1, 1, "y");
  box(g, bx + 22, 11, 6, 11, "p");
  for (const y of [13, 15, 17, 19]) fill(g, bx + 23, y, 3, 1, "l");
  fill(g, bx + 24, 10, 2, 1, "r");
  clockAt(g, 114, 4);
  box(g, 170, 24, 20, 35, "M");
  fill(g, 171, 25, 2, 33, "m");
  for (const y of [35, 46]) fill(g, 170, y, 20, 1, "o");
  for (const y of [29, 40, 51]) fill(g, 177, y, 6, 1, "y");
  plantAt(g, 50);
  return toRows(g);
}

/* 辦公桌（擋在章魚前面）：桌面、桌身、抽屜把手、桌腳 */
function officeDesk() {
  const w = 98;
  const g = blank(w, 21);
  box(g, 0, 0, w, 5, "D");
  fill(g, 1, 1, w - 2, 1, "p");
  box(g, 2, 4, w - 4, 14, "d");
  fill(g, w / 2, 5, 1, 12, "o");
  fill(g, 22, 10, 6, 1, "y");
  fill(g, w - 28, 10, 6, 1, "y");
  fill(g, 4, 18, 3, 3, "o");
  fill(g, w - 7, 18, 3, 3, "o");
  return toRows(g);
}

/* 看容量的螢幕：三條時段的用量長條，中間那條是這次申請的時段（金色） */
function capacityMonitor() {
  const g = blank(28, 22);
  box(g, 0, 0, 28, 17, "K");
  fill(g, 3, 3, 14, 2, "e");
  fill(g, 3, 7, 18, 2, "y");
  fill(g, 3, 11, 9, 2, "e");
  fill(g, 22, 7, 3, 2, "e");
  fill(g, 12, 17, 4, 3, "o");
  fill(g, 8, 20, 12, 2, "o");
  return toRows(g);
}

/* 印章：木柄、紅色印面 */
function stamp() {
  const g = blank(9, 10);
  box(g, 2, 0, 5, 4, "t");
  fill(g, 3, 4, 3, 3, "t");
  fill(g, 3, 4, 1, 3, "o");
  fill(g, 5, 4, 1, 3, "o");
  box(g, 0, 7, 9, 3, "R");
  return toRows(g);
}

/* 印泥 */
function inkPad() {
  const g = blank(11, 3);
  box(g, 0, 0, 11, 3, "R");
  return toRows(g);
}

/* ── 教室 ── */

/* 黑板：木框、課表格子（幾格用黃粉筆塗上）、左邊一串名單、粉筆槽 */
function blackboard() {
  const g = blank(88, 31);
  box(g, 0, 0, 88, 28, "D");
  fill(g, 2, 2, 84, 24, "Q");
  fill(g, 6, 5, 20, 1, "w");
  for (let i = 0; i < 5; i += 1) fill(g, 6, 9 + i * 3, 14 - (i % 3) * 3, 1, "w");
  for (let c = 0; c <= 5; c += 1) fill(g, 30 + c * 10, 5, 1, 19, "w");
  for (let r = 0; r <= 3; r += 1) fill(g, 30, 5 + r * 6, 51, 1, "w");
  fill(g, 32, 7, 7, 3, "y");
  fill(g, 52, 13, 7, 3, "y");
  fill(g, 72, 19, 7, 3, "y");
  fill(g, 42, 19, 7, 3, "w");
  fill(g, 0, 28, 88, 2, "D");
  fill(g, 0, 30, 88, 1, "o");
  fill(g, 12, 27, 4, 1, "w");
  fill(g, 20, 27, 3, 1, "y");
  return toRows(g);
}

/* 學生座位：兩排各四張桌子，每張桌上一台螢幕（平常是暗的，建好時一台台亮起來） */
const SEAT_GAP = 22;
const SEAT_BACK = [2, 2 + SEAT_GAP, 2 + SEAT_GAP * 2, 2 + SEAT_GAP * 3];
const SEAT_FRONT = SEAT_BACK.map((x) => x + 9);
const SEAT_ROWS_Y = [0, 14];

function studentDesks() {
  const g = blank(SEAT_FRONT[3] + 13, 29);
  const desk = (x, y) => {
    box(g, x + 1, y, 10, 7, "K");
    fill(g, x + 5, y + 7, 2, 1, "o");
    box(g, x, y + 8, 12, 3, "D");
    fill(g, x + 1, y + 11, 1, 4, "o");
    fill(g, x + 10, y + 11, 1, 4, "o");
  };
  SEAT_BACK.forEach((x) => desk(x, SEAT_ROWS_Y[0]));
  SEAT_FRONT.forEach((x) => desk(x, SEAT_ROWS_Y[1]));
  return toRows(g);
}

/* 每台學生螢幕的發亮範圍（相對座位那張圖），依由後往前、由左往右的順序亮 */
const SEAT_SCREENS = [
  ...SEAT_BACK.map((x) => ({ x: x + 2, y: SEAT_ROWS_Y[0] + 1, w: 8, h: 5 })),
  ...SEAT_FRONT.map((x) => ({ x: x + 2, y: SEAT_ROWS_Y[1] + 1, w: 8, h: 5 })),
];

/* 教室前面的大螢幕：全班用量的熱力圖（綠＝正常、金＝偏高、紅＝要注意） */
function classDisplay() {
  const g = blank(34, 22);
  box(g, 0, 0, 34, 20, "K");
  const heat = ["eeyeee", "eereye", "yeeeee"];
  heat.forEach((row, r) =>
    [...row].forEach((ch, c) => fill(g, 3 + c * 5, 3 + r * 5, 4, 4, ch)),
  );
  fill(g, 14, 20, 6, 2, "o");
  return toRows(g);
}

/* 老師的小桌（擋在章魚前面一點） */
function teacherTable() {
  const g = blank(18, 12);
  box(g, 0, 0, 18, 4, "D");
  box(g, 2, 3, 14, 7, "d");
  fill(g, 3, 10, 2, 2, "o");
  fill(g, 13, 10, 2, 2, "o");
  return toRows(g);
}

const CLASS_TABLE_TOP = 49;

/* ── 機房 ── */

const SERVER_DESK_TOP = 44;

/* 天花板的線槽、左邊一台機房空調（被泡泡蓋住一部分，只當裝飾） */
function serverRoomBase() {
  const g = shell();
  fill(g, 0, 1, ROOM_W, 2, "m");
  fill(g, 0, 3, ROOM_W, 1, "o");
  box(g, 6, 26, 36, 33, "M");
  for (let y = 30; y < 54; y += 3) fill(g, 9, y, 30, 1, "m");
  fill(g, 30, 29, 6, 2, "e");
  return toRows(g);
}

/* 伺服器機櫃：深色櫃體裡疊著七台伺服器，每台有散熱孔和燈號 */
function serverRack() {
  const g = blank(28, 54);
  box(g, 0, 0, 28, 52, "K");
  for (let i = 0; i < 7; i += 1) {
    const y = 3 + i * 7;
    box(g, 3, y, 22, 6, "M");
    fill(g, 5, y + 2, 10, 1, "m");
    fill(g, 5, y + 3, 10, 1, "m");
    fill(g, 18, y + 2, 2, 2, "e");
    fill(g, 21, y + 2, 2, 2, i % 3 === 1 ? "y" : "b");
  }
  fill(g, 2, 52, 4, 2, "o");
  fill(g, 22, 52, 4, 2, "o");
  return toRows(g);
}

/* 網路拓撲螢幕：兩台機器之間拉了一條綠線，線上一面小盾牌 */
function topologyScreen() {
  const g = blank(40, 20);
  box(g, 0, 0, 40, 18, "K");
  box(g, 4, 3, 9, 6, "p");
  fill(g, 6, 5, 5, 1, "l");
  box(g, 27, 9, 9, 6, "p");
  fill(g, 29, 11, 5, 1, "l");
  fill(g, 13, 6, 8, 1, "e");
  fill(g, 20, 6, 1, 6, "e");
  fill(g, 20, 11, 7, 1, "e");
  fill(g, 22, 3, 3, 3, "y");
  fill(g, 23, 6, 1, 1, "y");
  fill(g, 18, 18, 4, 2, "o");
  return toRows(g);
}

/* 節點負載螢幕：四個節點的負載長條，最空的那台旁邊一顆金星（建議放這台） */
function placementScreen() {
  const g = blank(40, 20);
  box(g, 0, 0, 40, 18, "K");
  const loads = [24, 16, 28, 9];
  loads.forEach((len, i) => {
    fill(g, 3, 3 + i * 4, 2, 2, "b");
    fill(g, 7, 3 + i * 4, len, 2, len > 20 ? "y" : "e");
  });
  fill(g, 33, 15, 3, 2, "y");
  fill(g, 34, 14, 1, 1, "y");
  fill(g, 18, 18, 4, 2, "o");
  return toRows(g);
}

/* 管理主控台：三張機器卡片，綠點＝在跑 */
function consoleMonitor() {
  const g = blank(28, 16);
  box(g, 0, 0, 28, 12, "K");
  for (let i = 0; i < 3; i += 1) {
    box(g, 2 + i * 8, 3, 7, 6, "p");
    fill(g, 3 + i * 8, 4, 2, 1, "e");
    fill(g, 3 + i * 8, 6, 5, 1, "l");
  }
  fill(g, 12, 12, 4, 2, "o");
  fill(g, 8, 14, 12, 2, "o");
  return toRows(g);
}

/* 主控台桌（擋在章魚前面） */
function consoleDesk() {
  const w = 92;
  const g = blank(w, 15);
  box(g, 0, 0, w, 4, "D");
  fill(g, 1, 1, w - 2, 1, "p");
  box(g, 2, 3, w - 4, 10, "d");
  fill(g, w / 2, 4, 1, 8, "o");
  fill(g, 4, 13, 3, 2, "o");
  fill(g, w - 7, 13, 3, 2, "o");
  return toRows(g);
}

/* ── 宿舍 ── */

const DORM_DESK_TOP = 38;

/* 左邊窗和盆栽（會被泡泡蓋住一部分，只當裝飾）、牆上海報、終端機螢幕上方的書架 */
function dormRoom() {
  const g = shell();
  windowAt(g, 8, 6, 34, 20);
  plantAt(g, 46);
  // 海報：天空底、一朵白雲、一顆星，下面一條白邊寫著兩行字
  box(g, 64, 6, 22, 24, "k");
  fill(g, 68, 13, 14, 5, "c");
  fill(g, 70, 11, 8, 2, "c");
  fill(g, 79, 8, 2, 2, "y");
  fill(g, 65, 21, 20, 8, "p");
  for (const y of [23, 26]) fill(g, 67, y, 16 - (y % 2) * 4, 1, "l");
  // 書架與書（在左邊螢幕上方，避開右邊的大螢幕）
  fill(g, 118, 10, 32, 2, "D");
  fill(g, 118, 12, 32, 1, "o");
  const books = "brybGerb";
  [...books].forEach((ch, i) => fill(g, 120 + i * 4, 3 + (i % 3), 3, 7 - (i % 3), ch));
  return toRows(g);
}

/* 長書桌（擋在章魚前面） */
function dormDesk() {
  const w = 126;
  const g = blank(w, 21);
  box(g, 0, 0, w, 5, "D");
  fill(g, 1, 1, w - 2, 1, "p");
  box(g, 2, 4, 30, 14, "d");
  fill(g, 12, 10, 8, 1, "y");
  fill(g, w - 5, 4, 3, 17, "o");
  fill(g, 4, 18, 3, 3, "o");
  return toRows(g);
}

/* 筆電：瀏覽器裡就是 VNC 桌面（藍色桌布、一個視窗、幾個圖示） */
function laptop() {
  const g = blank(30, 13);
  box(g, 2, 0, 26, 10, "K");
  fill(g, 3, 1, 24, 1, "p");
  fill(g, 3, 2, 24, 7, "b");
  box(g, 10, 3, 12, 5, "p");
  fill(g, 11, 4, 10, 1, "e");
  for (const y of [3, 5, 7]) fill(g, 4, y, 2, 1, "c");
  fill(g, 0, 10, 30, 2, "M");
  fill(g, 0, 12, 30, 1, "o");
  return toRows(g);
}

/* 終端機螢幕：幾行指令、最後一行游標 */
function terminalMonitor() {
  const g = blank(26, 20);
  box(g, 0, 0, 26, 15, "K");
  fill(g, 2, 2, 9, 1, "e");
  fill(g, 2, 4, 15, 1, "w");
  fill(g, 2, 6, 7, 1, "e");
  fill(g, 2, 8, 17, 1, "w");
  fill(g, 2, 10, 12, 1, "w");
  fill(g, 2, 12, 3, 1, "e");
  fill(g, 6, 12, 2, 1, "w");
  fill(g, 11, 15, 4, 3, "o");
  fill(g, 7, 18, 12, 2, "o");
  return toRows(g);
}

/* SkyLab Connect 桌面 App：一個視窗、三台機器、每台旁邊一顆連線鈕 */
function connectMonitor() {
  const g = blank(30, 24);
  box(g, 0, 0, 30, 18, "K");
  box(g, 2, 2, 26, 14, "p");
  fill(g, 3, 3, 24, 2, "b");
  fill(g, 4, 3, 2, 2, "y");
  for (let r = 0; r < 3; r += 1) {
    fill(g, 4, 7 + r * 3, 2, 2, "e");
    fill(g, 7, 7 + r * 3, 10, 1, "l");
    fill(g, 20, 7 + r * 3, 6, 2, "b");
  }
  fill(g, 13, 18, 4, 3, "o");
  fill(g, 9, 21, 12, 3, "o");
  return toRows(g);
}
const SEATS_AT = { x: 62, y: 37 };

/*
 * 每間房間的設定（座標都用格）：
 *   octo：章魚（x、圖的下緣 base、平常的動作 pose）；items 依序就是泡泡輪播的步驟，
 *   facet 對應文案 campus.rooms.<room>.<facet>，station 是這一步屬於這一站的第幾件事，
 *   anim 是輪到時的動作（lift 浮起、blink 閃、stamp 蓋章、glow 不動只讓別的東西變化），pose 是輪到時章魚換的動作；
 *   mark：輪到某一步時蓋在某處的印記；lights：從某一步開始亮起來的螢幕；bubbleW：泡泡寬（格）。
 */
export const ROOMS = {
  office: {
    room: officeRoom(),
    bubbleW: 62,
    octo: { pose: "approve", x: 100, base: OFFICE_DESK_TOP + 5 },
    layers: [
      { rows: officeDesk(), x: 68, y: OFFICE_DESK_TOP },
      { rows: inkPad(), x: 93, y: OFFICE_DESK_TOP - 3 },
    ],
    stampTo: 16,
    items: [
      { facet: "papers", rows: paperStack(), x: 72, y: OFFICE_DESK_TOP - 8, anim: "lift" },
      { facet: "monitor", rows: capacityMonitor(), x: 138, y: OFFICE_DESK_TOP - 22, anim: "blink" },
      { facet: "stamp", rows: stamp(), x: 94, y: OFFICE_DESK_TOP - 13, anim: "stamp" },
    ],
    mark: { facet: "stamp", x: 76, y: OFFICE_DESK_TOP - 9, tone: "red" },
  },
  classroom: {
    room: (() => {
      const g = shell();
      windowAt(g, 10, 8, 34, 24);
      plantAt(g, 44);
      clockAt(g, 154, 30);
      return toRows(g);
    })(),
    bubbleW: 56,
    octo: { pose: "role-teacher", x: 144, base: 62 },
    layers: [{ rows: teacherTable(), x: 172, y: CLASS_TABLE_TOP }],
    items: [
      { facet: "board", rows: blackboard(), x: 62, y: 3, anim: "blink", pose: "present" },
      { facet: "seats", rows: studentDesks(), x: SEATS_AT.x, y: SEATS_AT.y, anim: "glow" },
      { facet: "display", rows: classDisplay(), x: 154, y: 4, anim: "blink" },
      { facet: "check", station: 1, rows: paperStack("e"), x: 171, y: CLASS_TABLE_TOP - 8, anim: "lift", pose: "inspect" },
    ],
    mark: { facet: "check", x: 174, y: CLASS_TABLE_TOP - 10, tone: "green" },
    lights: {
      from: "seats",
      rects: SEAT_SCREENS.map((r) => ({ ...r, x: r.x + SEATS_AT.x, y: r.y + SEATS_AT.y })),
    },
  },
  serverRoom: {
    room: serverRoomBase(),
    bubbleW: 56,
    octo: { pose: "role-admin", x: 112, base: SERVER_DESK_TOP + 5 },
    layers: [{ rows: consoleDesk(), x: 98, y: SERVER_DESK_TOP }],
    items: [
      { facet: "pool", rows: serverRack(), x: 64, y: 5, anim: "blink" },
      { facet: "vms", rows: consoleMonitor(), x: 154, y: SERVER_DESK_TOP - 16, anim: "lift" },
      { facet: "placement", station: 1, rows: placementScreen(), x: 146, y: 4, anim: "blink", pose: "idea" },
      { facet: "firewall", station: 2, rows: topologyScreen(), x: 100, y: 4, anim: "blink", pose: "guard" },
    ],
    mark: { facet: "firewall", x: 107, y: 14, tone: "green" },
  },
  home: {
    room: dormRoom(),
    bubbleW: 56,
    octo: { pose: "role-student", x: 86, base: DORM_DESK_TOP + 5 },
    layers: [{ rows: dormDesk(), x: 64, y: DORM_DESK_TOP }],
    items: [
      { facet: "desktop", rows: laptop(), x: 66, y: DORM_DESK_TOP - 13, anim: "blink" },
      { facet: "terminal", rows: terminalMonitor(), x: 122, y: DORM_DESK_TOP - 20, anim: "blink", pose: "coding" },
      { facet: "app", rows: connectMonitor(), x: 154, y: DORM_DESK_TOP - 24, anim: "blink" },
    ],
    mark: { facet: "app", x: 158, y: DORM_DESK_TOP - 27, tone: "green" },
  },
};
