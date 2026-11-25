import { useCallback, useRef } from "react";

/**
 * 小遊戲往外報「做了什麼」（建好 VM、核准、拉線…），章魚導覽靠這個知道可以往下一步。
 * 用 ref 包住 onEvent，遊戲裡的計時器拿到的永遠是最新那一個。
 */
export function useEmit(onEvent) {
  const ref = useRef(onEvent);
  ref.current = onEvent;
  return useCallback((name, detail) => ref.current?.(name, detail), []);
}
