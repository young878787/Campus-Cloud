import { useEffect, useRef } from "react";
import { LAYOUT } from "../../../frontend/src/components/OctoPet/octoBrain";
import { mountOctoPet } from "../../../frontend/src/components/OctoPet/octoController";
import { SPRITE_W } from "../../../frontend/src/components/OctoPet/octoSprites";
import styles from "./PixelLanding.module.scss";

/**
 * 章魚學士（官網版）：直接用平台前端的畫布控制器（純 JS），外框與配色變數在這裡給。
 * activity 同平台：idle／thinking／done／error／shy。日夜切換時外層用 key 重新掛載換色。
 * 外層有自己的對話泡泡時傳 bubble={false}，不畫頭上的「…」泡泡。
 */
export default function Octo({ activity = "idle", scale = 4, quiet = false, bubble = true, className = "" }) {
  const rootRef = useRef(null);
  const canvasRef = useRef(null);
  const controllerRef = useRef(null);
  const activityRef = useRef(activity);
  activityRef.current = activity;

  useEffect(() => {
    const controller = mountOctoPet(canvasRef.current, rootRef.current, { scale, quiet, bubble, activity: activityRef.current });
    controllerRef.current = controller;
    return () => controller.destroy();
  }, [scale, quiet, bubble]);

  useEffect(() => {
    controllerRef.current?.setActivity(activity);
  }, [activity]);

  const { CW, CH, OX, OY } = LAYOUT;
  return (
    <span
      ref={rootRef}
      className={`${styles.octo} ${className}`}
      style={{ width: SPRITE_W * scale, height: 16 * scale }}
      aria-hidden="true"
    >
      <canvas
        ref={canvasRef}
        className={styles.octoCanvas}
        style={{ left: -OX * scale, top: -OY * scale, width: CW * scale, height: CH * scale }}
      />
    </span>
  );
}
