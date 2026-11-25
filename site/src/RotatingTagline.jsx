import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./RotatingTagline.module.scss";

const START_DELAY = 3600; // 等進場動畫跑完、第一個詞看清楚再開始換
const HOLD = 2400;
const DELETE_STEP = 90;
const TYPE_STEP = 150;
const EMPTY_PAUSE = 260;

/* 打字機輪播：刪掉目前的詞、打出下一個。回傳目前該顯示的字串與是否已開始輪播 */
function useRotatingWord(words) {
  const key = words.join("|");
  const [state, setState] = useState({ text: words[0] ?? "", started: false });

  useEffect(() => {
    const list = key.split("|").map((w) => Array.from(w));
    setState({ text: list[0].join(""), started: false });
    if (list.length < 2 || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;

    let index = 0;
    let count = list[0].length;
    let deleting = true;
    let timer;
    const show = () => setState({ text: list[index].slice(0, count).join(""), started: true });
    const tick = () => {
      if (deleting) {
        count -= 1;
        show();
        if (count > 0) {
          timer = setTimeout(tick, DELETE_STEP);
        } else {
          deleting = false;
          index = (index + 1) % list.length;
          timer = setTimeout(tick, EMPTY_PAUSE);
        }
      } else {
        count += 1;
        show();
        if (count < list[index].length) {
          timer = setTimeout(tick, TYPE_STEP);
        } else {
          deleting = true;
          timer = setTimeout(tick, HOLD);
        }
      }
    };
    timer = setTimeout(tick, START_DELAY);
    return () => clearTimeout(timer);
  }, [key]);

  return state;
}

/**
 * 標語（hero.tagline）。語系檔有 hero.taglineRotate（before／words／after）時，
 * 中間那個詞用打字機效果輪播；沒有的語言照原樣顯示整句。
 * 輪播的詞位保留最長詞的寬度，後面的字不會跟著左右跳。
 */
export default function RotatingTagline({ wordClassName = "" }) {
  const { t, i18n } = useTranslation("landing");
  // 不走 t()：fallbackLng 會讓沒設定的語言拿到中文的輪播詞
  const rotate = i18n.getResource(i18n.language, "landing", "hero.taglineRotate");
  const words = Array.isArray(rotate?.words) ? rotate.words : [];
  const { text, started } = useRotatingWord(words);

  if (words.length === 0) return t("hero.tagline");

  const longest = words.reduce((a, b) => (Array.from(b).length > Array.from(a).length ? b : a));
  return (
    <>
      <span className={styles.srOnly}>{t("hero.tagline")}</span>
      <span aria-hidden="true">
        {rotate.before}
        <span className={styles.slot}>
          <span className={styles.sizer}>{longest}</span>
          <span className={`${styles.word} ${wordClassName}`}>
            {text}
            {started && <i className={styles.caret} />}
          </span>
        </span>
        {rotate.after}
      </span>
    </>
  );
}
