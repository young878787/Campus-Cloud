import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import OctoPose from "../OctoPose";
import PixelSprite from "../PixelSprite";
import PlayIcon from "../PlayIcon";
import RoleKicker from "./RoleKicker";
import { ROOMS, ROOM_H, ROOM_W } from "./roomArt";
import styles from "./Room.module.scss";

/* 字元 → 顏色變數（日夜兩組在 Room.module.scss） */
const PALETTE = {
  o: "var(--room-line)",
  W: "var(--room-wall)",
  V: "var(--room-wainscot)",
  v: "var(--room-rail)",
  F: "var(--room-floor)",
  f: "var(--room-floor-line)",
  k: "var(--room-sky)",
  c: "var(--room-cloud)",
  B: "var(--room-cork)",
  p: "var(--room-paper)",
  l: "var(--room-ink)",
  r: "var(--room-red)",
  y: "var(--room-gold)",
  D: "var(--room-desk)",
  d: "var(--room-desk-front)",
  M: "var(--room-metal)",
  m: "var(--room-metal-dark)",
  P: "var(--room-pot)",
  G: "var(--room-leaf)",
  g: "var(--room-leaf-dark)",
  K: "var(--room-screen)",
  e: "var(--room-green)",
  b: "var(--room-blue)",
  t: "var(--room-wood)",
  R: "var(--room-stamp)",
  s: "var(--room-shade)",
  Q: "var(--room-board)",
  w: "var(--room-chalk)",
};

/* 外層標了 data-fit-screen 的區塊要整個塞進一個畫面（桌機／筆電；頂列 64px、區塊底部留 28px） */
const FIT_QUERY = "(min-width: 721px) and (min-height: 640px)";
const TOPBAR_H = 64;
const FIT_BOTTOM = 28;

/*
 * 房間每格幾 px（整數，像素才不糊）：
 *   寬：外層標了 data-room-area 的內容區寬度扣掉 --side-w（兩側箭頭佔的寬），房間本身是縮到剛好的寬度；
 *   高：要塞進一個畫面時，看從房間頂端到畫面底部還剩多高（用房間在區塊裡的位置算，不看捲到哪裡）。
 * 手機上連每格 3px 都放不下時，改照寬度縮滿（非整數；圖是向量，不會糊，只是格子大小略不均）。
 */
function useRoomCell(ref) {
  const [cell, setCell] = useState(5);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const update = () => {
      const area = el.closest("[data-room-area]");
      const sideW = area ? parseFloat(getComputedStyle(area).getPropertyValue("--side-w")) || 0 : 0;
      const exactW = (area ? area.clientWidth - sideW : el.clientWidth) / ROOM_W;
      let byH = 6;
      const fit = el.closest("[data-fit-screen]");
      if (fit && window.matchMedia(FIT_QUERY).matches) {
        const offset = el.getBoundingClientRect().top - fit.getBoundingClientRect().top;
        byH = Math.floor((window.innerHeight - TOPBAR_H - FIT_BOTTOM - offset) / ROOM_H);
      }
      const next = exactW < 3 ? Math.min(exactW, byH) : Math.min(6, Math.floor(exactW), byH);
      setCell(Math.max(1, next));
    };
    update();
    // 上面的東西（地圖）高度變了，房間的位置跟著變，也要重算；區塊本身也一起看
    const ro = new ResizeObserver(update);
    ro.observe(el);
    const fit = el.closest("[data-fit-screen]");
    if (fit) ro.observe(fit);
    const area = el.closest("[data-room-area]");
    if (area) ro.observe(area);
    window.addEventListener("resize", update);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [ref]);
  return cell;
}

/* 每一步停多久（毫秒）；泡泡底下的進度條也用這個時間跑 */
const STEP_MS = 3600;

/* 房間在畫面裡才輪播（捲走就停，省得在背景一直換） */
function useInView(ref) {
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const io = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: 0.4 });
    io.observe(el);
    return () => io.disconnect();
  }, [ref]);
  return inView;
}

/**
 * 走進建築裡：一間房間的像素場景，房間裡的東西依序代表這一站每件事的每一步（設定在 roomArt.js 的 ROOMS）。
 * 泡泡自己一步一步輪播，輪到的那樣東西跟著動、章魚換成那一步的動作，有的步驟會蓋印記或讓螢幕亮起來
 * （辦公室：申請單 → 容量螢幕 → 印章蓋「核准」；教室：黑板 → 座位螢幕一台台亮 → 大螢幕 → 作業蓋「AI ✓」）。
 * 泡泡的標題跟著那一步屬於哪件事；序號可以直接點，滑過房間裡的東西也會跳到那一步。
 * 滑鼠在房間裡、鍵盤停在裡面、房間不在畫面內、偏好減少動態效果時都不自動換。
 * 泡泡下方是「跟章魚試一次」（進導覽那一章）和「看實際畫面」（那件事有影片才有，彈窗播）。
 */
export default function RoomScene({ roomId, roles, stations, onTry, onWatch }) {
  const { t } = useTranslation("pixel");
  const room = ROOMS[roomId];
  const wrapRef = useRef(null);
  const cell = useRoomCell(wrapRef);
  const inView = useInView(wrapRef);
  const [step, setStep] = useState(0);
  const [hovering, setHovering] = useState(false);
  const [focused, setFocused] = useState(false);
  // 預渲染（Node）沒有 window：先當成不減少動態，掛上之後再讀偏好，伺服器與瀏覽器第一次畫的才一樣
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    setReduce(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }, []);
  const paused = hovering || focused || reduce || !inView;
  const order = room.items.map((item) => item.facet);
  const current = room.items[step];
  const facet = current.facet;
  const station = stations[current.station ?? 0];
  const pose = current.pose ?? room.octo.pose;
  const poseW = 32 * Math.max(2, Math.round(cell * 1.2));
  const poseH = (poseW * 26) / 32;
  const copy = (key) => t(`campus.rooms.${roomId}.${key}`);
  const lightsFrom = room.lights ? order.indexOf(room.lights.from) : -1;

  useEffect(() => {
    if (paused) return undefined;
    const id = window.setTimeout(() => setStep((s) => (s + 1) % order.length), STEP_MS);
    return () => window.clearTimeout(id);
  }, [paused, step, order.length]);

  const pick = (name) => setStep(order.indexOf(name));

  return (
    <div className={styles.roomWrap} ref={wrapRef} data-room={roomId}>
      {/* stage：房間＋泡泡（桌機泡泡疊在房間左上，手機改排在房間下面） */}
      <div
        className={styles.stage}
        // 寬度鎖在房間寬：泡泡排在下面時才會照房間寬度折行，不會被長句撐寬、超出畫面
        style={{ "--c": `${cell}px`, "--step-ms": `${STEP_MS}ms`, "--bubble-w": room.bubbleW, width: ROOM_W * cell }}
        data-paused={paused || undefined}
        data-compact={cell <= 4 || undefined}
        data-stack={cell <= 3 || undefined}
        onMouseEnter={() => setHovering(true)}
        onMouseLeave={() => setHovering(false)}
        onFocus={() => setFocused(true)}
        onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget)) setFocused(false);
        }}
      >
        <div className={styles.roomScroll}>
          <div
            className={styles.room}
            style={{
              "--stamp-to": room.stampTo,
              width: ROOM_W * cell,
              height: ROOM_H * cell,
            }}
          >
            <PixelSprite className={styles.layer} rows={room.room} palette={PALETTE} cell={cell} />
            <span
              className={styles.octo}
              style={{
                left: room.octo.x * cell,
                top: room.octo.base * cell - poseH,
                "--octo-w": `${poseW}px`,
              }}
              aria-hidden="true"
            >
              <OctoPose key={pose} name={pose} className={styles.octoPose} />
            </span>
            {room.layers.map((layer) => (
              <PixelSprite
                key={`${layer.x}-${layer.y}`}
                className={styles.layer}
                rows={layer.rows}
                palette={PALETTE}
                cell={cell}
                style={{ left: layer.x * cell, top: layer.y * cell }}
              />
            ))}

            {/* 從某一步開始亮起來的螢幕（教室：座位那步一台台亮，之後一直亮著；回到第一步再暗掉） */}
            {lightsFrom >= 0 &&
              step >= lightsFrom &&
              room.lights.rects.map((r, i) => (
                <span
                  key={`${r.x}-${r.y}`}
                  className={styles.light}
                  data-animate={step === lightsFrom || undefined}
                  style={{
                    left: r.x * cell,
                    top: r.y * cell,
                    width: r.w * cell,
                    height: r.h * cell,
                    animationDelay: `${i * 0.22}s`,
                  }}
                  aria-hidden="true"
                />
              ))}

            {room.mark && facet === room.mark.facet && (
              <span
                className={styles.mark}
                data-tone={room.mark.tone}
                style={{ left: room.mark.x * cell, top: room.mark.y * cell }}
                aria-hidden="true"
              >
                {copy("mark")}
              </span>
            )}

            {room.items.map((item) => (
              <button
                key={item.facet}
                type="button"
                className={styles.item}
                data-facet={item.facet}
                data-anim={item.anim}
                data-on={facet === item.facet || undefined}
                style={{ left: item.x * cell, top: item.y * cell }}
                aria-label={copy(`${item.facet}Label`)}
                aria-pressed={facet === item.facet}
                onMouseEnter={() => pick(item.facet)}
                onFocus={() => pick(item.facet)}
                onClick={() => pick(item.facet)}
              >
                <PixelSprite rows={item.rows} palette={PALETTE} cell={cell} />
              </button>
            ))}
          </div>
        </div>

        <div className={styles.bubble}>
          {/* 這間是誰在用 */}
          <RoleKicker roles={roles} />
          <h4>{t(`route.stations.${station.id}.title`)}</h4>
          {/* 步驟序號：現在輪到第幾步；也可以直接點（名稱只給讀屏和滑鼠提示） */}
          <div className={styles.steps}>
            {order.map((name, i) => (
              <button
                key={name}
                type="button"
                className={styles.stepBtn}
                aria-pressed={i === step}
                aria-label={`${i + 1} ${copy(`${name}Label`)}`}
                title={copy(`${name}Label`)}
                onClick={() => setStep(i)}
              >
                {i + 1}
              </button>
            ))}
          </div>
          {/* 自動輪播時不讓讀屏每幾秒唸一次，使用者自己換的時候才唸 */}
          <p aria-live={paused ? "polite" : "off"}>{copy(facet)}</p>
          {!paused && <span key={step} className={styles.timer} aria-hidden="true" />}
          <div className={styles.actions}>
            <button type="button" className={styles.try} onClick={() => onTry(station.chapter)}>
              <PlayIcon />{t("route.try")}
            </button>
            {station.shot && (
              /* 只有這件事有實際畫面時才出現 */
              <button type="button" className={styles.watch} onClick={() => onWatch(station)}>
                {t("campus.watch")}
              </button>
            )}
          </div>
          <i />
        </div>
      </div>
    </div>
  );
}
