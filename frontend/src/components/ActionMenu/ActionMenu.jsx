import { Fragment } from "react";
import { createPortal } from "react-dom";
import MIcon from "../MIcon";
import useAnchoredMenu from "../../hooks/useAnchoredMenu";
import useMenuKeyboard from "../../hooks/useMenuKeyboard";
import styles from "./ActionMenu.module.scss";

/** 選單寬度：中文動作名稱 6～8 個字加圖示放得下 */
export const ACTION_MENU_WIDTH = 220;

const ITEM_SELECTOR = '[role="menuitem"]:not(:disabled)';

/**
 * 「⋮」按下去的動作選單（例如班級頁首的延長、封存；側欄的帳號選單）。
 * 定位、外點與 Esc 關閉、portal 到 body 共用 useAnchoredMenu，鍵盤操作共用 useMenuKeyboard（同 PowerMenu、ListboxPopover）。
 *
 * - 開啟時焦點放在第一個可用的選項；上下鍵（頭尾相接）、Home／End 移動，Enter／空白鍵執行。
 * - Esc、Tab 關閉並把焦點交回觸發鈕；Esc 會標成已處理，同頁其他聽 Esc 的元件（批量列、對話框）不會跟著動作。
 * - 選了選項：先關選單、焦點回觸發鈕，再執行動作（動作若開對話框，對話框關掉時焦點會回到觸發鈕）。
 * - 呼叫端用 useDialogPresence(open, 130) 保留離場動畫：關閉期間傳 closing。
 * - header 是選項上方的說明區（例如帳號選單的頭像、姓名），不能聚焦，下面自動接一條分隔線。
 * - placement="side" 給側欄底部的選單，貼著側欄外緣彈出（見 useAnchoredMenu）。
 * - 底色一律是 popover-glass（跟側欄彈出同一套玻璃，隨介面風格與主題色變）。
 *
 * items: [{ key, label, icon?, onSelect, danger?, disabled?, title?, separatorBefore?, bombadil? }]
 * bombadil: true 標記「點了就直接送出、沒有確認框」的項目，UI 自動探索測試不會點（見 docs/ui-test-bombadil）。
 * 危險項（刪除、封存）放最後並加 separatorBefore，跟一般動作用分隔線隔開。
 */
export default function ActionMenu({
  id,
  anchorRef,
  ariaLabel,
  items,
  onClose,
  closing = false,
  width = ACTION_MENU_WIDTH,
  align = "right",
  placement,
  header,
}) {
  const { ref, pos } = useAnchoredMenu({ anchorRef, onClose, width, align, placement });
  const handleKeyDown = useMenuKeyboard({
    ref, anchorRef, onClose, closing, positioned: pos !== null, itemSelector: ITEM_SELECTOR,
  });

  function choose(item) {
    anchorRef?.current?.focus();
    onClose();
    item.onSelect();
  }

  const className = [
    styles.menu,
    pos?.openUp ? styles.menuUp : styles.menuDown,
    closing ? styles.menuOut : "",
  ].filter(Boolean).join(" ");

  return createPortal(
    <div
      ref={ref}
      id={id}
      role="menu"
      aria-label={ariaLabel}
      className={className}
      style={pos ? { top: pos.top, left: pos.left, width } : { top: 0, left: 0, width, visibility: "hidden" }}
      onKeyDown={handleKeyDown}
      // portal 的 React 事件仍沿元件樹冒泡，別讓外層可點的列也收到這次點擊
      onClick={(event) => event.stopPropagation()}
    >
      {header && (
        <>
          <div role="none" className={styles.header}>{header}</div>
          <span role="separator" className={styles.separator} />
        </>
      )}
      {items.map((item) => (
        <Fragment key={item.key}>
          {item.separatorBefore && <span role="separator" className={styles.separator} />}
          <button
            type="button"
            role="menuitem"
            tabIndex={-1}
            className={item.danger ? styles.itemDanger : styles.item}
            data-bombadil={item.bombadil ? "danger" : undefined}
            disabled={item.disabled}
            title={item.title}
            onClick={() => choose(item)}
          >
            {item.icon && <MIcon name={item.icon} size={16} />}
            {item.label}
          </button>
        </Fragment>
      ))}
    </div>,
    document.body,
  );
}
