/**
 * 章魚導覽的章節（學 The Evolution of Trust：一次只講一件事，講一句 → 你做一個動作 → 看結果 → 一句解釋）。
 * 每一步（beat）的台詞在 locales 的 tour.chapters.<id>.beats；wait 是要等小遊戲報的事件，
 * 寫 "名稱" 或 "名稱:細節"（例如 cmd:whoami），沒寫就是看完按「下一步」。
 * 章節順序跟頁面的路線一樣：機房（一台機器、AI、防火牆）→ 辦公室（審核）→ 教室（整班）→ 宿舍（瀏覽器）。
 */
import ClassroomGame from "../games/ClassroomGame";
import FirewallGame from "../games/FirewallGame";
import LifecycleGame from "../games/LifecycleGame";
import PlacementGame from "../games/PlacementGame";
import ReviewGame from "../games/ReviewGame";
import TerminalGame from "../games/TerminalGame";
import IntroScene from "./IntroScene";

export const CHAPTERS = [
  { id: "intro", Scene: IntroScene, beats: [{}, {}, {}, {}] },
  {
    id: "lifecycle",
    Game: LifecycleGame,
    beats: [{ wait: "created" }, { wait: "snapshot" }, { wait: "resized" }, { wait: "recycled" }, {}],
  },
  {
    id: "placement",
    Game: PlacementGame,
    beats: [{ wait: "course" }, { wait: "moved" }, {}],
  },
  {
    id: "firewall",
    Game: FirewallGame,
    beats: [{ wait: "web" }, { wait: "db" }, {}],
  },
  {
    id: "review",
    Game: ReviewGame,
    beats: [{ wait: "approved" }, { wait: "booted" }, { wait: "moved" }, {}],
  },
  {
    id: "classroom",
    Game: ClassroomGame,
    beats: [{ wait: "built" }, { wait: "fixed" }, { wait: "checked" }, {}],
  },
  {
    id: "terminal",
    Game: TerminalGame,
    beats: [{ wait: "cmd:whoami" }, { wait: "cmd:ls" }, {}],
  },
  { id: "outro", beats: [{}] },
];
