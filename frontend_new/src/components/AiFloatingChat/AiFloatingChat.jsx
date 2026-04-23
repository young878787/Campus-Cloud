/**
 * AiFloatingChat
 * 浮動 AI 助手 — FAB 按鈕 + 右下角彈出聊天視窗
 * 設計為放在任何有 position:relative 容器內使用
 */
import { useEffect, useRef, useState } from "react";
import styles from "./AiFloatingChat.module.scss";

const MIcon = ({ name, size = 20 }) => (
  <span className="material-icons-outlined" style={{ fontSize: size, lineHeight: 1 }}>
    {name}
  </span>
);

function TypingIndicator() {
  return (
    <div className={styles.bubble}>
      <span className={styles.dot} />
      <span className={styles.dot} />
      <span className={styles.dot} />
    </div>
  );
}

function Message({ msg }) {
  const isUser = msg.role === "user";
  return (
    <div className={`${styles.msgRow} ${isUser ? styles.msgRowUser : ""}`}>
      {!isUser && (
        <div className={styles.avatar}>
          <MIcon name="smart_toy" size={14} />
        </div>
      )}
      <div className={`${styles.msgBubble} ${isUser ? styles.msgBubbleUser : styles.msgBubbleAi}`}>
        {msg.content}
      </div>
    </div>
  );
}

const GREETING = "嗨！我是 AI 助手，可以幫你決定要申請什麼規格的資源。\n你有什麼需求嗎？";

export default function AiFloatingChat({ context }) {
  const [open, setOpen]       = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput]     = useState("");
  const [loading, setLoading] = useState(false);
  const [closing, setClosing] = useState(false);
  const scrollRef             = useRef(null);
  const inputRef              = useRef(null);

  /* 開啟時若無訊息，顯示問候語 */
  useEffect(() => {
    if (open && messages.length === 0) {
      setMessages([{ role: "assistant", content: GREETING }]);
    }
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 120);
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  /* 自動捲到最新訊息 */
  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, loading]);

  function handleClose() {
    setClosing(true);
    setTimeout(() => {
      setOpen(false);
      setClosing(false);
    }, 180);
  }

  async function send() {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    const userMsg = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      /* TODO: 接入真實 AI API（參考 AiTemplateRecommendationApi.chat）*/
      await new Promise((r) => setTimeout(r, 900));
      const reply = `（AI 回覆 placeholder）你說：「${text}」`;
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "發生錯誤，請稍後再試。" },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  function clearChat() {
    setMessages([{ role: "assistant", content: GREETING }]);
  }

  return (
    <div className={styles.root}>
      {/* ── Chat panel ── */}
      {open && (
        <div className={`${styles.panel} ${closing ? styles.panelOut : styles.panelIn}`}>
          {/* Header */}
          <div className={styles.header}>
            <span className={styles.headerIcon}>
              <MIcon name="smart_toy" size={16} />
            </span>
            <span className={styles.headerTitle}>AI 助手</span>
            <button type="button" className={styles.headerClear} onClick={clearChat} title="清除對話">
              <MIcon name="refresh" size={16} />
            </button>
            <button type="button" className={styles.headerClose} onClick={handleClose} title="關閉">
              <MIcon name="close" size={18} />
            </button>
          </div>

          {/* Messages */}
          <div className={styles.messages} ref={scrollRef}>
            {messages.map((msg, i) => (
              <Message key={i} msg={msg} />
            ))}
            {loading && (
              <div className={styles.msgRow}>
                <div className={styles.avatar}>
                  <MIcon name="smart_toy" size={14} />
                </div>
                <TypingIndicator />
              </div>
            )}
          </div>

          {/* Input */}
          <div className={styles.inputWrap}>
            <textarea
              ref={inputRef}
              className={styles.input}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="輸入訊息… (Enter 送出)"
              rows={1}
              disabled={loading}
            />
            <button
              type="button"
              className={styles.sendBtn}
              onClick={send}
              disabled={loading || !input.trim()}
              title="送出"
            >
              <MIcon name="send" size={16} />
            </button>
          </div>
        </div>
      )}

      {/* ── FAB ── */}
      <button
        type="button"
        className={`${styles.fab} ${open ? styles.fabOpen : ""}`}
        onClick={() => (open ? handleClose() : setOpen(true))}
        title="AI 助手"
        aria-label="開啟 AI 助手"
      >
        <span className={`${styles.fabIcon} ${styles.fabIconAi}`}>
          <MIcon name="smart_toy" size={22} />
        </span>
        <span className={`${styles.fabIcon} ${styles.fabIconClose}`}>
          <MIcon name="close" size={22} />
        </span>
        {!open && <span className={styles.fabLabel}>AI 助手</span>}
      </button>
    </div>
  );
}
