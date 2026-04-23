import { useEffect, useRef, useState } from "react";
import styles from "./RequestsPage.module.scss";

const MIcon = ({ name, size = 20 }) => (
  <span className="material-icons-outlined" style={{ fontSize: size, lineHeight: 1 }}>
    {name}
  </span>
);

const GREETING = "嗨！我是 AI 助手，可以幫你決定要申請什麼規格的資源。\n你有什麼需求嗎？";

export default function AiSidePanel({ className = "" }) {
  const [messages, setMessages] = useState([{ role: "assistant", content: GREETING }]);
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const scrollRef               = useRef(null);
  const inputRef                = useRef(null);

  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, loading]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);
    try {
      /* TODO: 接入真實 AI API */
      await new Promise((r) => setTimeout(r, 800));
      setMessages((prev) => [...prev, { role: "assistant", content: `（AI placeholder）你說：「${text}」` }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "發生錯誤，請稍後再試。" }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  }

  return (
    <div className={`${styles.aiPanel} ${className}`}>
      <div className={styles.aiMessages} ref={scrollRef}>
        {messages.map((msg, i) => (
          <div key={i} className={`${styles.aiMsgRow} ${msg.role === "user" ? styles.aiMsgRowUser : ""}`}>
            {msg.role === "assistant" && (
              <div className={styles.aiAvatar}><MIcon name="smart_toy" size={13} /></div>
            )}
            <div className={`${styles.aiMsgBubble} ${msg.role === "user" ? styles.aiMsgBubbleUser : styles.aiMsgBubbleAi}`}>
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className={styles.aiMsgRow}>
            <div className={styles.aiAvatar}><MIcon name="smart_toy" size={13} /></div>
            <div className={styles.aiTyping}>
              <span /><span /><span />
            </div>
          </div>
        )}
      </div>

      <div className={styles.aiInputWrap}>
        <textarea
          ref={inputRef}
          className={styles.aiInput}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="輸入訊息… (Enter 送出)"
          disabled={loading}
        />
        <div className={styles.aiInputToolbar}>
          <button type="button" className={styles.aiTemplateBtn} disabled={loading}>
            <MIcon name="auto_fix_high" size={14} />
            產生推薦配置
          </button>
<button
            type="button"
            className={styles.aiSendBtn}
            onClick={send}
            disabled={loading || !input.trim()}
          >
            <MIcon name="send" size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
