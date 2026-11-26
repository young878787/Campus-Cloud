import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import MIcon from "../MIcon";
import useAnchoredMenu from "../../hooks/useAnchoredMenu";
import useMenuKeyboard from "../../hooks/useMenuKeyboard";
import styles from "./PowerMenu.module.scss";

/* 選單 portal 到 body 並用 position: fixed 定位——列表容器（表格的
   .tableWrap 等）有 overflow，外層也可能有 backdrop-filter，
   absolute 選單會被裁掉、z-index 也出不了那層 stacking context。 */

const ITEMS = [
  { action: "start",    labelKey: "PowerMenu.start",    icon: "play_arrow",         needs: "stopped", tone: "ok"   },
  { action: "stop",     labelKey: "PowerMenu.stop",     icon: "stop",               needs: "poweredOn", tone: "warn" },
  { action: "shutdown", labelKey: "PowerMenu.shutdown", icon: "power_settings_new", needs: "running"               },
  { action: "reset",    labelKey: "PowerMenu.reset",    icon: "restart_alt",        needs: "running", tone: "warn" },
  { action: "reboot",   labelKey: "PowerMenu.reboot",   icon: "replay",             needs: "running"               },
];

const ITEM_SELECTOR = '[role="menuitem"]:not(:disabled)';

/* items 讓呼叫端自帶動作清單（例如整組機器只有開機／關機／結束練習）。
   定位、外點關閉、Esc、portal 共用 useAnchoredMenu，鍵盤操作共用 useMenuKeyboard（同 ActionMenu）：
   開啟時焦點在第一個可用的動作，上下鍵頭尾相接、Home／End 移動，Esc、Tab 關閉並把焦點交回觸發鈕；
   選了動作先把焦點交回觸發鈕再執行，動作若開確認對話框，關掉時焦點會回到觸發鈕。 */
export default function PowerMenu({
  resource,
  items,
  title,
  actionLoading,
  onControl,
  onDeleteClick,
  onConvertTemplate,
  onClose,
  anchorRef,
  closing,
}) {
  const { t } = useTranslation("components");
  const { ref, pos } = useAnchoredMenu({ anchorRef, onClose });
  const handleKeyDown = useMenuKeyboard({
    ref, anchorRef, onClose, closing, positioned: pos !== null, itemSelector: ITEM_SELECTOR,
  });
  const menuTitle = title ?? t("PowerMenu.title");

  /* starting＝開機 task 還在跑：只留強制停止（開機卡住時的退路），其餘要等開完機 */
  const enabled = {
    running: resource?.status === "running",
    poweredOn: resource?.status === "running" || resource?.status === "starting",
    stopped: resource?.status === "stopped" || resource?.status === "paused",
  };
  /* 個人申請的使用時段沒開始／已結束：後端一定擋開機，選單先把開機停用並講原因 */
  const windowBlocked = resource?.status !== "running" ? resource?.start_blocked_reason ?? null : null;
  const entries = items ?? ITEMS.map((item) => ({
    ...item,
    disabled: !enabled[item.needs] || (item.action === "start" && Boolean(windowBlocked)),
  }));

  const className = [
    styles.powerMenu,
    pos?.openUp ? styles.powerMenuUp : styles.powerMenuDown,
    closing ? styles.powerMenuOut : "",
  ].filter(Boolean).join(" ");

  return createPortal(
    <div
      ref={ref}
      role="menu"
      aria-label={menuTitle}
      className={className}
      data-guide="resource-power-menu"
      style={pos ? { top: pos.top, left: pos.left } : { top: 0, left: 0, visibility: "hidden" }}
      onKeyDown={handleKeyDown}
      /* portal 的 React 事件仍沿元件樹冒泡：點到標題、提示或空白處不能觸發外層 <tr onClick>。
         按鈕自己的 onClick 先跑完才冒泡到這裡；外點關閉走 document mousedown，不受影響 */
      onClick={(e) => e.stopPropagation()}
    >
      <div className={styles.powerMenuTitle} aria-hidden="true">{menuTitle}</div>
      {!items && windowBlocked && (
        <div className={styles.powerMenuNote}>
          <MIcon name="event_busy" size={14} />
          {t(windowBlocked === "window_ended" ? "PowerMenu.windowEnded" : "PowerMenu.windowNotStarted")}
        </div>
      )}
      <div className={styles.powerMenuGrid}>
        {entries.map(({ action, label, labelKey, icon, tone, disabled }) => (
          <button
            key={action}
            type="button"
            role="menuitem"
            tabIndex={-1}
            data-bombadil={action === "start" ? undefined : "danger"}
            className={`${styles.powerMenuItem} ${tone === "warn" ? styles.powerMenuItemWarn : ""} ${tone === "danger" ? styles.powerMenuItemDanger : ""}`}
            disabled={disabled || !!actionLoading}
            onClick={() => { anchorRef?.current?.focus(); onClose(); onControl(action); }}
          >
            <span className={tone === "ok" ? styles.powerMenuIconOk : styles.powerMenuIcon}>
              <MIcon name={icon} size={15} />
            </span>
            {label ?? t(labelKey)}
          </button>
        ))}
        {/* 老師／管理員把調好的機器轉成範本；沒有 onConvertTemplate 就不顯示。
            轉範本與刪除這兩個額外動作由呼叫端自己關選單（callback 內先 closeMenu），這裡不再呼叫 onClose */}
        {onConvertTemplate && <button
          type="button"
          role="menuitem"
          tabIndex={-1}
          className={styles.powerMenuItem}
          data-bombadil="danger"
          disabled={!!actionLoading}
          onClick={() => { anchorRef?.current?.focus(); onConvertTemplate(); }}
        >
          <span className={styles.powerMenuIcon}><MIcon name="library_add" size={15} /></span>
          {t("PowerMenu.convertTemplate")}
        </button>}
        {/* 環境內的機器不能單台刪除，整組回收由環境層級處理；沒有 onDeleteClick 就不顯示 */}
        {onDeleteClick && <button
          type="button"
          role="menuitem"
          tabIndex={-1}
          className={`${styles.powerMenuItem} ${styles.powerMenuItemDanger}`}
          onClick={() => { anchorRef?.current?.focus(); onDeleteClick(); }}
        >
          <span className={styles.powerMenuIcon}><MIcon name="delete_outline" size={15} /></span>
          {t("PowerMenu.delete")}
        </button>}
      </div>
    </div>,
    document.body,
  );
}
