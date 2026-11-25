/**
 * 學生篇章魚導覽（學 The Evolution of Trust：講一句 → 你做一個動作 → 看結果 → 一句解釋）。
 * 從學生的角度走一學期：申請一台機器 → 打開瀏覽器就能用 → 改設定前先存檔 → 交作業前看 AI 導師檢查。
 * 台詞在 locales 的 studentTour.chapters.<id>.beats；wait 是要等小遊戲報的事件（同 chapters.js）。
 */
import CheckGame from "../games/CheckGame";
import RequestGame from "../games/RequestGame";
import SnapshotGame from "../games/SnapshotGame";
import TerminalGame from "../games/TerminalGame";
import StudentIntro from "./StudentIntro";

export const STUDENT_CHAPTERS = [
  /* 開場畫面本身就是一隻大章魚在演，左邊講話的那隻先收起來，畫面上只留一隻 */
  { id: "intro", Scene: StudentIntro, hideNarrator: true, beats: [{}, {}, {}, {}] },
  {
    id: "request",
    Game: RequestGame,
    beats: [{ wait: "submitted" }, { wait: "approved" }, { wait: "booted" }, {}],
  },
  {
    id: "browser",
    Game: TerminalGame,
    beats: [{ wait: "cmd:whoami" }, { wait: "cmd:ls" }, {}],
  },
  {
    id: "snapshot",
    Game: SnapshotGame,
    beats: [{ wait: "snapshot" }, { wait: "broke" }, { wait: "restored" }, {}],
  },
  {
    id: "check",
    Game: CheckGame,
    beats: [{ wait: "checked" }, { wait: "fixed" }, { wait: "passed" }, {}],
  },
  { id: "outro", beats: [{}] },
];
