import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Octo from "../Octo";
import { CHAPTERS } from "./chapters";
import styles from "./Tour.module.scss";

// 做完動作後停一下（看得到結果、章魚開心一下）再自動換下一句；這段時間不放「下一步」，免得按鈕冒出來又被收走
const ADVANCE_MS = 600;

/* 從手指底下的元素往上找：這個拖曳方向（dx、dy 是想捲動的量）上有沒有還能捲的內層區塊。
   沒有的話這一下拖曳會變成捲整個頁面，導覽開著時要擋掉 */
function canScrollInside(target, dx, dy) {
  if (target instanceof HTMLInputElement && target.type === "range") return true;
  const vertical = Math.abs(dy) >= Math.abs(dx);
  const root = document.documentElement;
  for (let el = target; el instanceof Element && el !== root && el !== document.body; el = el.parentElement) {
    const style = getComputedStyle(el);
    const overflow = vertical ? style.overflowY : style.overflowX;
    if (overflow !== "auto" && overflow !== "scroll") continue;
    const pos = vertical ? el.scrollTop : el.scrollLeft;
    const max = vertical ? el.scrollHeight - el.clientHeight : el.scrollWidth - el.clientWidth;
    const delta = vertical ? dy : dx;
    if (max <= 0) continue;
    if (delta > 0 ? pos < max - 1 : pos > 0) return true;
  }
  return false;
}

/* 手機寬度：章魚縮小一號，講話那一列才不會佔掉半個畫面 */
function useNarrow() {
  const query = "(max-width: 720px)";
  const [narrow, setNarrow] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setNarrow(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return narrow;
}

/* 章節列放不下時橫捲：哪一邊還有東西，那一邊就淡出，看得出可以捲 */
function useScrollEdges(ref) {
  const [edges, setEdges] = useState({ start: false, end: false });
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const update = () => {
      const start = el.scrollLeft > 2;
      const end = el.scrollLeft + el.clientWidth < el.scrollWidth - 2;
      setEdges((prev) => (prev.start === start && prev.end === end ? prev : { start, end }));
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      ro.disconnect();
    };
  }, [ref]);
  return edges;
}

/**
 * 章魚導覽（全螢幕）：上面是章節列，左邊章魚講一句話，右邊是那一章的小遊戲（或開場畫面 Scene）。
 * 要你動手的那一步，做完遊戲會報事件，停一下就自動換下一句；不想做可以按「這步先跳過」。
 * 疊在頁面上（不 portal，才吃得到 .page 的配色變數），開著時鎖住背景捲動，Esc 關閉。
 *
 * chapters：章節表（預設是全功能導覽 chapters.js；學生篇是 studentChapters.js）。
 * copy：文案的 key 開頭（tour／studentTour），底下有 label、chapters.<id>.nav／beats，
 *       可選 chapters.<id>.stage（右邊遊戲上方的標題）與 recap（總結那一行）。
 */
export default function Tour({
  chapters = CHAPTERS,
  copy = "tour",
  startAt = "intro",
  titled = false,
  mode,
  contactHref,
  githubUrl,
  onClose,
}) {
  const { t } = useTranslation("pixel");
  const [ch, setCh] = useState(() => Math.max(0, chapters.findIndex((c) => c.id === startAt)));
  const [beat, setBeat] = useState(0);
  // 這一章最遠講到第幾句：進度點可以點回去重看，最遠只到這裡
  const [reached, setReached] = useState(0);
  const [seen, setSeen] = useState(() => new Set());
  const [round, setRound] = useState(0);
  const [finished, setFinished] = useState(() => new Set());
  const [cheer, setCheer] = useState(0);
  // 正要自動換句的那一句（"章-句"）：這段時間按鈕區顯示「做到了」
  const [autoNext, setAutoNext] = useState(null);
  const dialogRef = useRef(null);
  const beatRef = useRef({ ch, beat });
  beatRef.current = { ch, beat };
  const chaptersRef = useRef(chapters);
  chaptersRef.current = chapters;
  const timer = useRef(0);

  const chapter = chapters[ch];
  const key = (id, part) => `${copy}.chapters.${id}.${part}`;
  const beats = t(key(chapter.id, "beats"), { returnObjects: true });
  const def = chapter.beats[beat];
  const waiting = Boolean(def.wait) && !seen.has(def.wait);
  const isLastBeat = beat === chapter.beats.length - 1;
  const next = chapters[ch + 1];
  const games = chapters.filter((c) => c.Game);
  const gameNo = (c) => games.indexOf(c) + 1;

  /* 開著時鎖背景捲動、焦點移進來；Esc 關閉 */
  useEffect(() => {
    const html = document.documentElement;
    const prev = html.style.overflow;
    html.style.overflow = "hidden";
    const back = document.activeElement;
    dialogRef.current?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    /* iOS／iPadOS 的瀏覽器不完全理會 html 的 overflow: hidden：手指拖在捲不動的地方
       （頁面頂列、內容沒超出的導覽主體、已捲到底的區塊），捲動會傳到底下的首頁。
       所以觸控另外擋：這一下拖曳方向上沒有任何內層區塊能捲，就不讓它變成頁面捲動 */
    let startX = 0;
    let startY = 0;
    const onTouchStart = (e) => {
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
    };
    const onTouchMove = (e) => {
      if (e.touches.length > 1 || !e.cancelable) return;
      const dx = startX - e.touches[0].clientX;
      const dy = startY - e.touches[0].clientY;
      if (!canScrollInside(e.target, dx, dy)) e.preventDefault();
    };
    document.addEventListener("touchstart", onTouchStart, { passive: true });
    document.addEventListener("touchmove", onTouchMove, { passive: false });
    return () => {
      html.style.overflow = prev;
      document.removeEventListener("touchstart", onTouchStart);
      document.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("keydown", onKey);
      window.clearTimeout(timer.current);
      back?.focus?.({ preventScroll: true });
    };
  }, [onClose]);

  /* 章節列窄的時候會橫捲：換章時把目前這一章捲進畫面 */
  const navRef = useRef(null);
  const navEdges = useScrollEdges(navRef);
  const narrow = useNarrow();
  // 捲到正中間：貼邊的話會被兩端的淡出遮住半截。換章時平滑捲；第一次與視窗寬度改變時直接跳
  const centerCurrent = useCallback((smooth) => {
    const nav = navRef.current;
    const btn = nav?.querySelector('[aria-current="step"]');
    if (!nav || !btn) return;
    const offset = btn.getBoundingClientRect().left - nav.getBoundingClientRect().left;
    const left = nav.scrollLeft + offset - (nav.clientWidth - btn.offsetWidth) / 2;
    const motion = smooth && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    nav.scrollTo({ left, behavior: motion ? "smooth" : "auto" });
  }, []);
  const navPlaced = useRef(false);
  useEffect(() => {
    centerCurrent(navPlaced.current);
    navPlaced.current = true;
  }, [ch, centerCurrent]);
  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return undefined;
    const ro = new ResizeObserver(() => centerCurrent(false));
    ro.observe(nav);
    return () => ro.disconnect();
  }, [centerCurrent]);

  useEffect(() => {
    if (!cheer) return undefined;
    const id = window.setTimeout(() => setCheer(0), 1400);
    return () => window.clearTimeout(id);
  }, [cheer]);

  const goChapter = useCallback((index) => {
    window.clearTimeout(timer.current);
    setAutoNext(null);
    setCh(index);
    setBeat(0);
    setReached(0);
    setSeen(new Set());
    setRound((n) => n + 1);
  }, []);

  const advance = useCallback(() => {
    window.clearTimeout(timer.current);
    setAutoNext(null);
    const list = chaptersRef.current;
    const { ch: c, beat: b } = beatRef.current;
    if (b < list[c].beats.length - 1) {
      setBeat(b + 1);
      setReached((r) => Math.max(r, b + 1));
      return;
    }
    setFinished((prev) => new Set(prev).add(list[c].id));
    if (c < list.length - 1) goChapter(c + 1);
  }, [goChapter]);

  /* 小遊戲報事件：記下來；剛好是這一步在等的，就開心一下、停一會兒自動往下 */
  const onEvent = useCallback(
    (name, detail) => {
      const keys = detail === undefined ? [name] : [name, `${name}:${detail}`];
      setSeen((prev) => {
        const nextSeen = new Set(prev);
        keys.forEach((k) => nextSeen.add(k));
        return nextSeen;
      });
      const { ch: c, beat: b } = beatRef.current;
      const want = chaptersRef.current[c].beats[b].wait;
      if (want && keys.includes(want)) {
        setCheer(Date.now());
        setAutoNext(`${c}-${b}`);
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => {
          if (beatRef.current.ch === c && beatRef.current.beat === b) advance();
        }, ADVANCE_MS);
      }
    },
    [advance],
  );

  const restartChapter = () => goChapter(ch);

  /* 點進度點回到講過的那一句（遊戲狀態不動；做過的動作已記下，不會再卡住等） */
  const goBeat = (i) => {
    window.clearTimeout(timer.current);
    setAutoNext(null);
    setBeat(i);
  };

  let nextLabel = t("tour.next");
  if (isLastBeat && chapter.id === "intro") nextLabel = t("tour.start");
  else if (isLastBeat && next?.id === "outro") nextLabel = t("tour.finish");
  else if (isLastBeat && next) nextLabel = t("tour.nextChapter", { name: t(key(next.id, "nav")) });

  const { Game, Scene } = chapter;
  const label = t(`${copy}.label`);

  return (
    // 不設 aria-modal：頁面頂列在導覽開著時也能用（底下其他內容由頁面設 inert）
    <div className={styles.overlay} role="dialog" aria-label={label} ref={dialogRef} tabIndex={-1}>
      <header className={styles.head}>
        {titled && <strong className={styles.title}>{label}</strong>}
        <nav
          className={styles.chapters}
          aria-label={t("tour.chaptersLabel")}
          ref={navRef}
          data-more-start={navEdges.start || undefined}
          data-more-end={navEdges.end || undefined}
        >
          {chapters.map((c, i) => (
            <button
              key={c.id}
              type="button"
              className={styles.chapterBtn}
              aria-current={i === ch ? "step" : undefined}
              data-done={finished.has(c.id) || undefined}
              onClick={() => goChapter(i)}
            >
              {c.Game && <span className={styles.chapterNo}>{gameNo(c)}</span>}
              {t(key(c.id, "nav"))}
            </button>
          ))}
        </nav>
        <button type="button" className={styles.close} onClick={onClose}>
          {t("tour.close")} <span aria-hidden="true">×</span>
        </button>
      </header>

      <div className={styles.body} data-fill={Scene ? "" : undefined}>
        {/* 章名在上面的章節列已經反白，這裡不再重複；手機上這一塊固定在頂部，捲到遊戲下方也看得到指示 */}
        <aside className={styles.narrator} data-no-octo={chapter.hideNarrator || undefined}>
          <p key={`${ch}-${beat}`} className={styles.bubble} aria-live="polite">
            {beats[beat]}
            <i />
          </p>
          {!chapter.hideNarrator && (
            <span className={styles.octo}>
              <Octo key={`${mode}-${narrow}`} activity={cheer ? "done" : "idle"} scale={narrow ? 3 : 5} bubble={false} />
            </span>
          )}
          {/* 進度點：講過的句子可以點回去重看 */}
          {chapter.beats.length > 1 && (
            <div className={styles.dots} role="group" aria-label={t("tour.beatsLabel")}>
              {chapter.beats.map((_, i) => (
                <button
                  key={i}
                  type="button"
                  className={styles.dot}
                  onClick={() => goBeat(i)}
                  disabled={i > reached}
                  aria-label={t("tour.beat", { n: i + 1 })}
                  aria-current={i === beat ? "step" : undefined}
                  data-done={(i !== beat && i <= reached) || undefined}
                >
                  <i />
                </button>
              ))}
            </div>
          )}
          {chapter.id !== "outro" && (
            <div className={styles.actions}>
              {/* 等你動手時不放灰掉的「下一步」：只說去哪裡做，不想做可以跳過 */}
              {waiting ? (
                <>
                  <p className={styles.hint}>
                    <i className={styles.hintArrow} aria-hidden="true" />
                    <span className={styles.hintSide}>{t("tour.waiting")}</span>
                    <span className={styles.hintBelow}>{t("tour.waitingBelow")}</span>
                  </p>
                  <button type="button" className={styles.skipBtn} onClick={advance}>
                    {t("tour.skip")}
                  </button>
                </>
              ) : autoNext === `${ch}-${beat}` ? (
                <p className={styles.doneNote} role="status">
                  ✓ {t("tour.done")}
                </p>
              ) : (
                <button type="button" className={styles.btn} onClick={advance}>
                  {nextLabel}
                </button>
              )}
            </div>
          )}
        </aside>

        {/* data-want：正在等的事件，遊戲裡 data-act 對得上的按鈕會跳動提示；data-bare：開場畫面不套白底卡片 */}
        <section className={styles.stage} data-want={waiting ? def.wait : undefined} data-bare={Scene ? "" : undefined}>
          {Game && (
            <>
              <div className={styles.stageBar}>
                <span>{t(key(chapter.id, "stage"), { defaultValue: t(`${chapter.id}.kicker`) })}</span>
                <button type="button" className={styles.skip} onClick={restartChapter}>
                  {t("tour.restart")}
                </button>
              </div>
              <Game key={`${chapter.id}-${round}`} onEvent={onEvent} />
            </>
          )}
          {Scene && <Scene beat={beat} />}
          {chapter.id === "outro" && (
            <div className={styles.recap}>
              <h3>{t("tour.recapTitle", { n: games.length })}</h3>
              <ol>
                {games.map((c) => (
                  <li key={c.id} data-done={finished.has(c.id) || undefined}>
                    <button type="button" onClick={() => goChapter(chapters.indexOf(c))}>
                      <span className={styles.recapMark} aria-hidden="true">
                        {finished.has(c.id) ? "✓" : gameNo(c)}
                      </span>
                      <b>{t(key(c.id, "nav"))}</b>
                      <span>{t(key(c.id, "recap"), { defaultValue: t(`${c.id}.summary`) })}</span>
                    </button>
                  </li>
                ))}
              </ol>
              <div className={styles.recapCta}>
                <a className={styles.btn} href={contactHref}>{t("tour.contact")}</a>
                <a className={styles.btnGhost} href={githubUrl} target="_blank" rel="noreferrer">
                  {t("tour.github")}
                </a>
                <button type="button" className={styles.btnGhost} onClick={() => goChapter(0)}>
                  {t("tour.replay")}
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
