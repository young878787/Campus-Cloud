import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { BOOK, WORDMARK } from "../../../frontend/src/components/PixelArt/pixelArt";
import { CLOUD_SEA_BACK, CLOUD_SEA_FRONT, HERO_CLOUD } from "../../../frontend/src/components/PixelArt/pixelScenery";
import { CONTACT_EMAIL, DOCS_URL, GITHUB_URL } from "../config";
import { LANGUAGES, languageInfo } from "../languages";
import { rememberLanguageChoice } from "../languagePreference";
import RotatingTagline from "../RotatingTagline";
import { ICONS } from "./icons";
import Octo from "./Octo";
import OctoPose from "./OctoPose";
import PixelSprite from "./PixelSprite";
import PlayIcon from "./PlayIcon";
import { STUDENT_CHAPTERS } from "./tour/studentChapters";
import Tour from "./tour/Tour";
import CampusMap from "./campus/CampusMap";
import SpecSheet from "./specs/SpecSheet";
import SkyLayer, { OUTRO_SKY } from "./SkyLayer";
import useTypeIn from "./useTypeIn";
import RoomScene from "./campus/RoomScene";
import RoleKicker from "./campus/RoleKicker";
import styles from "./PixelLanding.module.scss";

const MODE_KEY = "skylab.pixel.mode";

/*
 * 校園裡的四個地方：每個地方（stop）對應幾種人（roles）、有幾件事（station），在校園區做成一間房間（room，
 * 場景在 campus/roomArt.js）。chapter 是章魚導覽裡對應的那一章（tour/chapters.js），
 * shot 是那件事的實際操作影片（public/demo），在房間裡按「看實際畫面」彈窗播。
 */
const STOPS = [
  {
    id: "serverRoom",
    room: "serverRoom",
    roles: ["admin"],
    stations: [
      { id: "cloud", chapter: "lifecycle" },
      { id: "placement", chapter: "placement" },
      { id: "firewall", chapter: "firewall", shot: { id: "firewall", path: "/firewall" } },
    ],
  },
  {
    id: "office",
    // 申請審核只有管理員能做（老師沒有審核權限）
    roles: ["admin"],
    room: "office",
    stations: [{ id: "review", chapter: "review", shot: { id: "review", path: "/request-review" } }],
  },
  {
    id: "classroom",
    roles: ["teacher"],
    room: "classroom",
    stations: [
      { id: "class", chapter: "classroom", shot: { id: "class", path: "/class-management" } },
      { id: "check", chapter: "classroom" },
    ],
  },
  {
    id: "home",
    roles: ["student"],
    room: "home",
    stations: [{ id: "browser", chapter: "terminal", shot: { id: "console", path: "/my-resources" } }],
  },
];

/*
 * 第一屏先分流：你是哪一種使用者？每個身分做成一張掛在掛繩上的識別證，
 * 證上是品牌的「身分章魚」（學生拿鉛筆、老師博士帽抱書、管理員安全帽拿扳手），no 是證件編號。
 * 學生走學生篇章魚導覽（The Evolution of Trust 的節奏）；老師、管理員在校園地圖上打開對應的那一棟。
 */
const ROLES = [
  { id: "student", pose: "role-student", no: "S-001", set: "student", chapter: "intro" },
  { id: "teacher", pose: "role-teacher", no: "T-002", set: "general", chapter: "classroom" },
  { id: "admin", pose: "role-admin", no: "A-003", set: "general", chapter: "lifecycle" },
];

const WORD = { t: "var(--px-word-top)", b: "var(--px-word-bottom)" };
const CLOUD = { o: "var(--px-cloud-line)", f: "var(--px-cloud-fill)", h: "var(--px-cloud-hi)", s: "var(--px-cloud-shade)" };
const BOOK_PALETTE = {
  g: "var(--px-book-line)",
  a: "var(--px-cloud-line)",
  c: "var(--px-book-page)",
  b: "var(--px-book-shade)",
  d: "var(--px-gold)",
  j: "var(--px-gold-dark)",
};

/*
 * 舊介紹頁共用的 landing 文案在繁中混了半形的「,」「?」，像素版顯示時換成全形（舊頁不受影響）。
 * 只換緊貼中文的那幾個，英數裡的不動。
 */
const CJK = "[\u3000-\u9fff\uff00-\uffef]";
const HALF_PUNCT = new RegExp(`(?<=${CJK})[,?]|[,?](?=${CJK})`, "g");
function fullWidth(text, lang) {
  if (lang !== "zh-TW") return text;
  return text.replace(HALF_PUNCT, (ch) => (ch === "," ? "，" : "？"));
}

function contactHref(tl) {
  return `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(tl("contact.subject"))}`;
}

/* GitHub 官方標誌（Octicons mark-github）。官方規範不准改造，所以照原樣用、不畫成像素風；顏色跟著按鈕文字 */
function GitHubMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" focusable="false">
      <path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z" />
    </svg>
  );
}

/* 日夜：記得上次的選擇，沒選過就跟系統 */
function useMode() {
  const [mode, setMode] = useState("day");
  useLayoutEffect(() => {
    let saved = null;
    try {
      saved = window.localStorage.getItem(MODE_KEY);
    } catch {
      // 無痕模式等存取失敗時跟系統
    }
    if (saved === "day" || saved === "night") setMode(saved);
    else if (window.matchMedia("(prefers-color-scheme: dark)").matches) setMode("night");
  }, []);
  const toggle = () =>
    setMode((current) => {
      const next = current === "day" ? "night" : "day";
      try {
        window.localStorage.setItem(MODE_KEY, next);
      } catch {
        // 只在這次生效
      }
      return next;
    });
  return [mode, toggle];
}

/*
 * 第一屏字標與雲的舞台每格幾 px：跟著視窗寬度（整數，像素才不糊）。
 * 手機上要塞得進畫面：字標 35 格、舞台 60 格寬，左右各留 20px。
 */
function cellsFor(vw) {
  if (vw <= 720) {
    const avail = vw - 40;
    return { word: Math.min(10, Math.floor(avail / 35)), stage: Math.max(3, Math.min(6, Math.floor(avail / 60))) };
  }
  const cell = vw >= 1800 ? 9 : vw >= 1400 ? 8 : vw >= 1100 ? 7 : 5;
  // 右邊舞台最多 9（540px）：內容寬上限 1200，舞台再大，左邊標語欄就排不下一行
  return { word: cell + 5, stage: Math.min(cell + 1, 9) };
}

function useCells() {
  const [cells, setCells] = useState(() => cellsFor(1440));
  useLayoutEffect(() => {
    const onResize = () => setCells(cellsFor(window.innerWidth));
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return cells;
}

/* 決定性的小抖動：同一格每次延遲一樣 */
const jitter = (x, y) => ((x * 7 + y * 13) % 5) * 28;

/**
 * 開場（只演一次）：SkyLab 字標一格一格掉進位置，從左到右拼出來。
 * 每一格是一個 rect，用 CSS 動畫加延遲；減少動態效果時直接整個出現。
 */
function AssembleWordmark({ cell }) {
  const cells = useMemo(() => {
    const out = [];
    WORDMARK.forEach((row, y) => [...row].forEach((ch, x) => ch !== "." && out.push({ x, y, ch })));
    return out;
  }, []);
  const w = WORDMARK[0].length;
  const h = WORDMARK.length;
  return (
    <svg
      className={styles.heroWordmark}
      viewBox={`0 0 ${w} ${h}`}
      width={w * cell}
      height={h * cell}
      shapeRendering="crispEdges"
      aria-hidden="true"
    >
      {cells.map(({ x, y, ch }) => (
        <rect
          key={`${x}-${y}`}
          className={styles.assembleCell}
          x={x}
          y={y}
          width="1.02"
          height="1.02"
          style={{ fill: WORD[ch], animationDelay: `${x * 22 + jitter(x, y)}ms` }}
        />
      ))}
    </svg>
  );
}

/**
 * 第一屏右邊：同登入頁的舞台，一朵像素雲、雲前一本打開的書，章魚學士坐在書上
 * （平台同一隻：會眨眼、東張西望、眼睛跟著游標，放著不管會看書、打瞌睡）。
 * 開場時從上面掉到書上彈一下；點一下會開心地跳。
 */
function HeroStage({ cell, mode }) {
  return (
    <div className={styles.stage} style={{ "--cell": `${cell}px` }}>
      <PixelSprite className={styles.stageCloud} rows={HERO_CLOUD} palette={CLOUD} />
      <PixelSprite className={styles.stageBook} rows={BOOK} palette={BOOK_PALETTE} />
      <CheerOcto className={styles.stageOcto} scale={cell} mode={mode} />
    </div>
  );
}

/*
 * 會動的章魚學士（平台同一隻）當按鈕：眨眼、東張西望、眼睛跟著游標、在身上來回滑會冒愛心，
 * 點一下開心地跳。第一屏的雲上和結尾各一隻。
 */
function CheerOcto({ className, scale, mode }) {
  const { t } = useTranslation("pixel");
  const [cheer, setCheer] = useState(0);
  useEffect(() => {
    if (!cheer) return undefined;
    const id = window.setTimeout(() => setCheer(0), 1400);
    return () => window.clearTimeout(id);
  }, [cheer]);
  return (
    <button type="button" className={className} onClick={() => setCheer(Date.now())} aria-label={t("hero.octoLabel")}>
      <Octo key={mode} activity={cheer ? "done" : "idle"} scale={scale} bubble={false} />
    </button>
  );
}

/*
 * 證件被游標拂過時左右晃：支點在掛繩頂端，證件下緣畫圓弧。
 * 游標往哪邊掃，下緣就被帶往哪邊；掃得越快晃得越大，之後像鐘擺一樣來回幾下慢慢停（彈簧＋阻尼）。
 * 角度寫在 CSS 的 rotate 屬性，不會跟 hover、開場動畫用的 transform 打架。
 * 只認滑鼠和觸控筆（手指捲頁時不要讓證件亂晃）；偏好減少動態效果時不晃。
 */
const SWING_W0 = 5.6; // 自然頻率（rad/s）：一個來回約 1.1 秒
const SWING_ZETA = 0.12; // 阻尼比：晃好幾下才停
const SWING_MAX = 12; // 最大角度（度）

function useSwing() {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;
    let angle = 0;
    let vel = 0;
    let raf = 0;
    let last = 0;
    let lastMove = 0;
    let movedAt = 0;
    const tick = (now) => {
      const dt = Math.min(0.032, Math.max(0.001, (now - last) / 1000));
      last = now;
      vel += (-SWING_W0 * SWING_W0 * angle - 2 * SWING_ZETA * SWING_W0 * vel) * dt;
      angle = Math.max(-SWING_MAX, Math.min(SWING_MAX, angle + vel * dt));
      // 游標還在動就不停；停下來且幾乎不晃了才收工
      if (now - movedAt > 120 && Math.abs(angle) < 0.05 && Math.abs(vel) < 0.5) {
        angle = 0;
        vel = 0;
        el.style.rotate = "";
        raf = 0;
        return;
      }
      el.style.rotate = `${angle.toFixed(2)}deg`;
      raf = window.requestAnimationFrame(tick);
    };
    const onMove = (e) => {
      if (e.pointerType === "touch" || !e.movementX) return;
      const gap = lastMove ? Math.max(8, e.timeStamp - lastMove) : 16;
      lastMove = e.timeStamp;
      movedAt = performance.now();
      const speed = (Math.abs(e.movementX) / gap) * 1000; // px/s
      // 往右掃（movementX > 0）→ 角度往負的方向（逆時針），下緣跟著往右；慢慢滑過也會輕輕晃
      vel -= e.movementX * 0.09 * Math.min(1.6, 0.35 + speed / 900);
      vel = Math.max(-160, Math.min(160, vel));
      if (!raf) {
        last = performance.now();
        raf = window.requestAnimationFrame(tick);
      }
    };
    el.addEventListener("pointermove", onMove);
    return () => {
      el.removeEventListener("pointermove", onMove);
      window.cancelAnimationFrame(raf);
      el.style.rotate = "";
    };
  }, []);
  return ref;
}

/* 第一屏的身分證件：掛繩、證件頭（字標、穿繩孔、編號）、身分章魚、名稱與一句話、按鈕 */
function RoleBadge({ role, index, onPick }) {
  const { t } = useTranslation("pixel");
  const ref = useSwing();
  return (
    <button
      ref={ref}
      type="button"
      className={styles.choice}
      data-role={role.id}
      style={{ "--i": index }}
      onClick={() => onPick(role)}
    >
      <span className={styles.strap} aria-hidden="true" />
      <span className={styles.badgeTop} aria-hidden="true">
        <PixelSprite rows={WORDMARK} palette={WORD} cell={2} />
        <i />
        <small>No. {role.no}</small>
      </span>
      <span className={styles.badgeBody}>
        <span className={styles.choiceArt}>
          <OctoPose name={role.pose} className={styles.choicePose} />
        </span>
        <span className={styles.badgeInfo}>
          <b>{t(`fork.${role.id}.name`)}</b>
          <span>{t(`fork.${role.id}.line`)}</span>
          <em><PlayIcon />{t(`fork.${role.id}.go`)}</em>
        </span>
      </span>
    </button>
  );
}

/**
 * 實際操作畫面：平常是一張截圖，按了才在原地播放那段操作影片（不自動播，頁面上不會到處在動）。
 */
function Shot({ shot, lang, autoPlay = false }) {
  const { t } = useTranslation("pixel");
  const { t: tl } = useTranslation("landing");
  const [playing, setPlaying] = useState(autoPlay);
  const videoRef = useRef(null);
  const base = `/demo/${lang === "zh-TW" ? "zh-TW" : "en"}`;

  /* React 的 muted 不會寫成屬性，自動播放規則看不到；換成影片後自己設靜音再播 */
  useEffect(() => {
    const video = videoRef.current;
    if (!playing || !video) return;
    video.muted = true;
    video.play().catch(() => {});
  }, [playing]);

  return (
    <figure className={styles.shot}>
      <div className={styles.shotBar} aria-hidden="true">
        <span />
        <span />
        <span />
        <b>campus.skylab-tw.com{shot.path}</b>
      </div>
      {playing ? (
        <video
          ref={videoRef}
          className={styles.shotMedia}
          src={`${base}/${shot.id}.mp4`}
          poster={`${base}/${shot.id}.jpg`}
          muted
          playsInline
          controls
          aria-label={tl(`demo.${shot.id}.title`)}
        />
      ) : (
        <button type="button" className={styles.shotPlay} onClick={() => setPlaying(true)} aria-label={t("route.play")}>
          <img className={styles.shotMedia} src={`${base}/${shot.id}.jpg`} alt="" loading="lazy" />
          <span className={styles.shotPlayLabel} aria-hidden="true">
            <PlayIcon /><span className={styles.playLong}>{t("route.play")}</span>
            <span className={styles.playShort}>{t("route.playShort")}</span>
          </span>
        </button>
      )}
      <figcaption>{fullWidth(tl(`demo.${shot.id}.caption`), lang)}</figcaption>
    </figure>
  );
}

/* 校園區一棟一頁（機房 → 辦公室 → 教室 → 宿舍），每頁是那棟的房間 */
const CAMPUS_SLIDES = STOPS;

/* 像素箭頭（往右；往左用 scaleX(-1)） */
const ARROW = ["o....", "oo...", "ooo..", "oooo.", "ooooo", "oooo.", "ooo..", "oo...", "o...."];

/*
 * 地圖下方的內容區：兩側箭頭一棟一棟切（也可以按鍵盤左右鍵），地圖上亮著的那棟跟著換；右上的點點是第幾棟。
 */
function CampusSlides({ index, dir, onStep, lang, onTry, onWatch }) {
  const { t } = useTranslation("pixel");
  const stop = CAMPUS_SLIDES[index];
  const place = t(`route.stops.${stop.id}.place`);
  return (
    <div className={styles.slides} data-room-area>
      <button
        type="button"
        className={`${styles.slideArrow} ${styles.slidePrev}`}
        onClick={() => onStep(-1)}
        disabled={index === 0}
        aria-label={t("campus.prev")}
      >
        <PixelSprite rows={ARROW} palette={{ o: "currentColor" }} cell={3} />
      </button>
      {/* 頁點：桌機在房間右上，手機在下面兩顆箭頭中間（位置由 grid 排） */}
      <span className={styles.slideDots} aria-hidden="true">
        {CAMPUS_SLIDES.map((s, i) => (
          <i key={s.id} data-on={i === index || undefined} />
        ))}
      </span>
      <section className={styles.slide} aria-labelledby="campus-slide-title">
        {/* 畫面上不放標題（地圖上已經亮著是哪一棟），只留給讀屏 */}
        <h3 className={styles.srOnly} id="campus-slide-title" aria-live="polite">
          {place}：{t(`route.stops.${stop.id}.who`)}
        </h3>
        <div key={index} className={styles.slideBody} data-dir={dir}>
          <RoomScene roomId={stop.room} roles={stop.roles} stations={stop.stations} onTry={onTry} onWatch={onWatch} />
        </div>
      </section>
      <button
        type="button"
        className={`${styles.slideArrow} ${styles.slideNext}`}
        onClick={() => onStep(1)}
        disabled={index === CAMPUS_SLIDES.length - 1}
        aria-label={t("campus.next")}
      >
        <PixelSprite rows={ARROW} palette={{ o: "currentColor" }} cell={3} />
      </button>
    </div>
  );
}

/* 「看實際畫面」：原生 dialog 彈出那段操作的影片，一打開就播（靜音）；Esc、按關閉或點視窗外面都會收起 */
function ShotDialog({ station, lang, onClose }) {
  const { t } = useTranslation("pixel");
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={styles.shotDialog}
      onClose={onClose}
      aria-label={t(`route.stations.${station.id}.title`)}
      onClick={(e) => {
        // 點在視窗外（灰色遮罩上）就關：遮罩的點擊也會算在 dialog 身上，用座標判斷
        const r = e.currentTarget.getBoundingClientRect();
        const outside = e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
        if (outside) ref.current?.close();
      }}
    >
      <div className={styles.shotDialogHead}>
        <b>{t(`route.stations.${station.id}.title`)}</b>
        <button type="button" className={styles.shotDialogClose} onClick={() => ref.current?.close()}>
          {t("campus.close")} <span aria-hidden="true">×</span>
        </button>
      </div>
      <Shot shot={station.shot} lang={lang} autoPlay />
    </dialog>
  );
}

/**
 * 官網像素版首頁（目前只在 pixel.html 預覽；正式首頁是原版 LandingPage）。
 * 由上而下：第一屏 → 功能一覽 → 從機房到家裡（像素校園地圖：機房＝管理員、辦公室＝管理員、教室＝老師、
 * 宿舍或家裡＝學生，一棟一頁，房間裡的東西自動一步步講這裡在做的事）→ 用你的身分走一遍（識別證）→ 結尾聯絡。
 * 「跟章魚試一次」進全功能導覽的那一章、「看實際畫面」彈窗播操作影片（導覽都學 The Evolution of Trust）。
 * 預渲染（Node）也會畫這一頁：畫面上用到 window 的都放在 effect 裡，伺服器與瀏覽器第一次畫的要一樣。
 */
export default function PixelLandingPage({ lang }) {
  const { t } = useTranslation("pixel");
  const { t: tl } = useTranslation("landing");
  const [mode, toggleMode] = useMode();
  const cells = useCells();
  /* 標語開場打字（折成兩行時一行一行打） */
  const typedRef = useRef(null);
  const caretRef = useRef(null);
  useTypeIn(typedRef, caretRef);
  /* 開著的導覽：{ set: "general"｜"student", start: 從哪一章開始 }；null＝關著 */
  const [tour, setTour] = useState(null);
  const openTour = (start, set = "general") => setTour({ set, start });
  const closeTour = useCallback(() => setTour(null), []);
  /* 導覽開著時按頂列的錨點（字標、校園地圖）：先關導覽，關完再捲過去（關的時候焦點會回到原本的按鈕） */
  const leaveTourTo = (e) => {
    if (!tour) return;
    e.preventDefault();
    const target = document.querySelector(e.currentTarget.getAttribute("href"));
    setTour(null);
    requestAnimationFrame(() => target?.scrollIntoView());
  };
  /* 校園區看到第幾頁（dir：往哪邊切，給切換動畫用）；預設打開機房 */
  const campusRef = useRef(null);
  const [slide, setSlide] = useState({ i: 0, dir: 0 });
  /* 正在看實際畫面的那件事（null＝彈窗關著） */
  const [watch, setWatch] = useState(null);
  const stepSlide = (d) =>
    setSlide((s) => {
      const i = Math.max(0, Math.min(CAMPUS_SLIDES.length - 1, s.i + d));
      return i === s.i ? s : { i, dir: d };
    });
  /* 切到某一棟的第一頁，並把整個校園區捲進畫面（一個畫面看完） */
  const openPlace = (stopId) => {
    const i = CAMPUS_SLIDES.findIndex((s) => s.id === stopId);
    setSlide((s) => (i === s.i ? s : { i, dir: i > s.i ? 1 : -1 }));
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    campusRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  };
  /* 學生進學生篇導覽；老師、管理員在校園地圖上打開教室／機房 */
  const pickRole = (role) => openTour(role.chapter, role.set);

  const docsHref = `${DOCS_URL}${languageInfo(lang).docsPath}guides/deployment`;

  return (
    <div className={styles.page} data-mode={mode}>
      {/* 頂列在導覽開著時也照常可用（導覽從頂列下方開始蓋）：換語言、日夜、GitHub、聯繫我們都按得到 */}
      <header className={styles.topbar}>
        <a href="#top" className={styles.brand} aria-label="SkyLab" onClick={leaveTourTo}>
          <PixelSprite rows={WORDMARK} palette={WORD} cell={3} />
        </a>
        <nav className={styles.nav}>
          <a href="#campus" onClick={leaveTourTo}>
            {t("nav.route")}
          </a>
          <button
            type="button"
            onClick={() => openTour("intro")}
            aria-current={tour?.set === "general" ? "page" : undefined}
          >
            {t("nav.tour")}
          </button>
        </nav>
        <div className={styles.topActions}>
          {LANGUAGES.map((l) => (
            <a
              key={l.code}
              href={l.path}
              hrefLang={l.code}
              // 記住點過的語言：之後打開根網址會直接到這個語言（languagePreference.js）
              onClick={() => rememberLanguageChoice(l.code)}
              aria-current={lang === l.code ? "page" : undefined}
              className={`${styles.langBtn} ${lang === l.code ? styles.langBtnOn : ""}`}
            >
              {l.label}
            </a>
          ))}
          <button
            type="button"
            className={styles.langBtn}
            onClick={toggleMode}
            aria-label={tl(mode === "night" ? "modeToDay" : "modeToNight")}
            title={tl(mode === "night" ? "modeToDay" : "modeToNight")}
          >
            <PixelSprite rows={mode === "night" ? ICONS.sun : ICONS.moon} palette={mode === "night" ? GOLD_SUN : MOON} cell={2} />
          </button>
          <a
            className={styles.langBtn}
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            aria-label={tl("outro.githubCta")}
            title={tl("outro.githubCta")}
          >
            <GitHubMark />
          </a>
          <a className={styles.btnTop} href={contactHref(tl)}>{tl("contact.cta")}</a>
        </div>
      </header>

      {/* 導覽開著時，底下整頁不能點、不能被 Tab 到 */}
      <div inert={tour ? true : undefined}>
        <section className={styles.hero} id="top">
          <SkyLayer />
          <div className={styles.heroText}>
            <h1 className={styles.heroTitle}>
              <span className={styles.srOnly}>SkyLab</span>
              <AssembleWordmark cell={cells.word} />
            </h1>
            <p className={styles.heroTagline}>
              <span className={styles.typed} ref={typedRef}>
                <RotatingTagline wordClassName={styles.taglineWord} />
              </span>
              <i className={styles.typeCaret} ref={caretRef} aria-hidden="true" />
            </p>
            <p className={styles.heroLead}>{t("hero.lead")}</p>
          </div>
          <HeroStage cell={cells.stage} mode={mode} />
        </section>

        <SpecSheet />

        <section
          className={styles.campusSection}
          id="campus"
          data-fit-screen
          ref={campusRef}
          onKeyDown={(e) => {
            // 影片自己用左右鍵快轉，不搶
            if (e.target.tagName === "VIDEO") return;
            if (e.key === "ArrowLeft") stepSlide(-1);
            if (e.key === "ArrowRight") stepSlide(1);
          }}
        >
          <h2 className={styles.campusTitle}>{t("campus.title")}</h2>
          <CampusMap selected={CAMPUS_SLIDES[slide.i].id} onSelect={openPlace} />
          <CampusSlides
            index={slide.i}
            dir={slide.dir}
            onStep={stepSlide}
            lang={lang}
            onTry={openTour}
            onWatch={setWatch}
          />
          {watch && <ShotDialog station={watch} lang={lang} onClose={() => setWatch(null)} />}
        </section>

        {/* 看完功能，用自己的身分走一遍：每張證件接一段章魚導覽 */}
        <section className={styles.trySection} id="try">
          <div className={styles.fork}>
            <h2 className={styles.forkAsk}>{t("fork.ask")}</h2>
            <div className={styles.choices}>
              {ROLES.map((role, i) => (
                <RoleBadge key={role.id} role={role} index={i} onPick={pickRole} />
              ))}
            </div>
            <p className={styles.forkMore}>
              <button type="button" onClick={() => openTour("intro")}>
                {t("fork.all")}
              </button>
            </p>
          </div>
        </section>

        <section className={styles.outro} id="contact">
          <SkyLayer layout={OUTRO_SKY} />
          <div className={styles.outroInner}>
            <CheerOcto className={styles.outroOcto} scale={Math.min(8, cells.stage)} mode={mode} />
            <h2 className={styles.outroTitle}>{fullWidth(tl("outro.title"), lang)}</h2>
            <p className={styles.outroNote}>{fullWidth(tl("contact.note"), lang)}</p>
            <div className={styles.ctaRow}>
              <a className={styles.btn} href={contactHref(tl)}>{tl("contact.cta")}</a>
              <a className={styles.btnGhost} href={GITHUB_URL} target="_blank" rel="noreferrer">{tl("outro.githubCta")}</a>
              <a className={styles.btnGhost} href={docsHref} target="_blank" rel="noreferrer">{tl("outro.docsCta")}</a>
            </div>
          </div>
          <div className={styles.sea} aria-hidden="true">
            <PixelSprite className={styles.seaBack} rows={CLOUD_SEA_BACK} palette={{ f: "var(--px-sea-back)" }} cell={8} />
            <PixelSprite className={styles.seaFront} rows={CLOUD_SEA_FRONT} palette={{ f: "var(--px-sea-front)" }} cell={8} />
          </div>
          <footer className={styles.footer}>
            <span>{t("footer")}</span>
            <span>
              {tl("contact.emailLabel")} <a href={contactHref(tl)}>{CONTACT_EMAIL}</a>
            </span>
          </footer>
        </section>
      </div>

      {tour && (
        <Tour
          key={tour.set}
          chapters={tour.set === "student" ? STUDENT_CHAPTERS : undefined}
          copy={tour.set === "student" ? "studentTour" : "tour"}
          // 全部功能導覽在頂列已經反白，不用再寫一次名稱；學生篇頂列沒有對應的項目，要寫
          titled={tour.set === "student"}
          startAt={tour.start}
          mode={mode}
          contactHref={contactHref(tl)}
          githubUrl={GITHUB_URL}
          onClose={closeTour}
        />
      )}
    </div>
  );
}

const GOLD_SUN = { g: "var(--px-gold)" };
const MOON = { o: "var(--px-moon-line)", l: "var(--px-moon)" };
