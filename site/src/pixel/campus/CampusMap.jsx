import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { SKY_CLOUDS } from "../../../../frontend/src/components/PixelArt/pixelScenery";
import OctoPose from "../OctoPose";
import PixelSprite from "../PixelSprite";
import { BUILDINGS, GROUND_Y, MAP_H, MAP_W, TREE, TREES } from "./campusArt";
import styles from "./CampusMap.module.scss";

/* 字元 → 顏色變數（日夜兩組在 CampusMap.module.scss） */
const PALETTE = {
  o: "var(--map-line)",
  w: "var(--map-white)",
  g: "var(--map-glass)",
  G: "var(--map-lit)",
  d: "var(--map-door)",
  e: "var(--map-led-green)",
  y: "var(--map-gold)",
  b: "var(--map-led-blue)",
  v: "var(--map-vent)",
  a: "var(--map-ac)",
  S: "var(--map-server)",
  R: "var(--map-server-hi)",
  W: "var(--map-office)",
  U: "var(--map-office-roof)",
  C: "var(--map-class)",
  K: "var(--map-class-roof)",
  D: "var(--map-dorm)",
  r: "var(--map-dorm-roof)",
  s: "var(--map-shade)",
  B: "var(--map-board)",
};
const TREE_PALETTE = { t: "var(--map-tree)", T: "var(--map-tree-dark)", n: "var(--map-trunk)" };
const CLOUD_PALETTE = { f: "var(--map-cloud)", s: "var(--map-cloud-shade)" };

/*
 * 地圖每格幾 px：跟著容器寬度（整數，像素才不糊）。桌機／筆電上整個校園區要一個畫面看完，
 * 所以地圖最多佔螢幕高的 32%；太窄時最小 3 格，地圖改成可以左右滑。
 */
function useMapCell(ref) {
  const [cell, setCell] = useState(5);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const update = () => {
      const oneScreen = window.innerWidth > 720 && window.innerHeight >= 640;
      const byHeight = oneScreen ? Math.floor((window.innerHeight * 0.32) / MAP_H) : 6;
      setCell(Math.max(3, Math.min(6, Math.floor(el.clientWidth / MAP_W), byHeight)));
    };
    const ro = new ResizeObserver(update);
    ro.observe(el);
    window.addEventListener("resize", update);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [ref]);
  return cell;
}

/*
 * 窄螢幕地圖要左右滑時，換站（點地名、點箭頭）就把那棟建築捲到中間。
 * 第一次與格子大小改變時直接跳過去，之後用平滑捲動（偏好減少動態效果時也直接跳）。
 */
function useCenterSelected(ref, selected, cell) {
  const lastCell = useRef(null);
  useEffect(() => {
    const el = ref.current;
    const b = BUILDINGS.find((item) => item.stop === selected);
    if (!el || !b || el.scrollWidth <= el.clientWidth) return;
    const center = (b.x + b.rows[0].length / 2) * cell;
    const smooth = lastCell.current === cell && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ left: center - el.clientWidth / 2, behavior: smooth ? "smooth" : "auto" });
    lastCell.current = cell;
  }, [ref, selected, cell]);
}

/**
 * 像素校園地圖：機房、辦公室、教學樓、宿舍四棟建築排在草地上，機房送出來的小方塊沿著小路跑向每一棟。
 * 滑過建築：建築浮起、章魚從屋頂後面探出頭；點下去切到那個地方（內容在地圖下方，由頁面畫）。
 * 沒人碰的時候，四隻章魚輪流探頭，提示可以點。selected：目前看的那一站（stop id）。
 */
export default function CampusMap({ selected, onSelect }) {
  const { t } = useTranslation("pixel");
  const scrollerRef = useRef(null);
  const cell = useMapCell(scrollerRef);
  useCenterSelected(scrollerRef, selected, cell);
  const poseW = Math.max(2, Math.round(cell * 0.8)) * 32;
  const poseH = (poseW * 26) / 32;

  const place = (stop) => t(`route.stops.${stop}.place`);

  return (
    <div className={styles.campus}>
      <div className={styles.scroller} ref={scrollerRef}>
        <div
          className={styles.scene}
          style={{ "--c": `${cell}px`, width: MAP_W * cell, height: MAP_H * cell }}
          role="group"
          aria-label={t("campus.label")}
        >
          <PixelSprite className={`${styles.cloud} ${styles.cloudA}`} rows={SKY_CLOUDS.a} palette={CLOUD_PALETTE} cell={cell} />
          <PixelSprite className={`${styles.cloud} ${styles.cloudB}`} rows={SKY_CLOUDS.c} palette={CLOUD_PALETTE} cell={cell} />

          <div className={styles.ground} style={{ top: GROUND_Y * cell }} aria-hidden="true">
            <div className={styles.path}>
              <i />
              <i />
              <i />
            </div>
          </div>

          {TREES.map((tree) => (
            <PixelSprite
              key={tree.x}
              className={styles.tree}
              rows={TREE}
              palette={TREE_PALETTE}
              cell={cell}
              style={{ left: tree.x * cell, top: tree.y * cell }}
            />
          ))}

          {BUILDINGS.map((b) => (
            <button
              key={b.stop}
              type="button"
              className={styles.building}
              style={{ left: b.x * cell, top: b.y * cell }}
              aria-pressed={selected === b.stop}
              aria-label={t("campus.open", { place: place(b.stop) })}
              onClick={() => onSelect(b.stop)}
            >
              <span
                className={styles.peek}
                style={{ left: b.peekX * cell, top: b.roofY * cell - poseH, width: poseW, height: poseH, "--peek-w": `${poseW}px` }}
                aria-hidden="true"
              >
                <OctoPose name={b.pose} className={styles.peekPose} />
              </span>
              <PixelSprite className={styles.sprite} rows={b.rows} palette={PALETTE} cell={cell} />
              <span className={styles.label} aria-hidden="true">
                {place(b.stop)}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* 窄螢幕地圖要左右滑，底下另外排一列地名可以直接點 */}
      <div className={styles.chips}>
        {BUILDINGS.map((b) => (
          <button
            key={b.stop}
            type="button"
            className={styles.chip}
            aria-pressed={selected === b.stop}
            onClick={() => onSelect(b.stop)}
          >
            {place(b.stop)}
          </button>
        ))}
      </div>
    </div>
  );
}
