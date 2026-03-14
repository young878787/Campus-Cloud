# 開發過程總結

## 📋 項目演進歷程

### v1.0 - 後端核心（基礎）
建立了乾淨架構的 vLLM 推論服務：
- ✅ 高併發推論引擎
- ✅ OpenAI 兼容 API 客戶端
- ✅ 視覺模型支持
- ✅ 異步基準測試框架

### v1.2 - 影片分析功能（當前版本）
添加了完整的影片多模態推論支援：
- ✅ `utils/video_utils.py` 影格提取、分段、Base64 編碼
- ✅ `api/client.py` 同步 / 異步影片推論方法
- ✅ `config/settings.py` 影片相關設定（FPS、分段大小等）
- ✅ `/api/chat/video/info` 影片元資料分析端點
- ✅ `/api/chat/video/stream` 影片流式推論端點（SSE + `[INFO]` 事件）
- ✅ 前端影片上傳、縮圖預覽、拖放支援
- ✅ `MessageBubble` 可播放影片縮圖

### v1.1 - Web UI 完整上線
添加了優雅現代的網頁應用層：
- ✅ FastAPI 後端代理服務
- ✅ React 前端應用
- ✅ SSE 流式輸出
- ✅ 拖放圖片上傳
- ✅ 優雅夢幻視覺設計

---

## 🎯 需求來源與演進

### 初始需求
使用者要求基於現有 vLLM 服務開發網頁 UI，具體要點：
1. 使用 vLLM API 作為推論核心
2. 支援流式輸出（即時反饋）
3. 支援圖片辨識（視覺模型）
4. 動漫主題設計（優雅夢幻，非科技感）
5. 使用者友好（無學習曲線）

### 設計決策

| 決策 | 選項 | 採用 | 原因 |
|------|------|------|------|
| **通訊協議** | WebSocket vs SSE | SSE | 單向、簡單、標準、無持久連接開銷 |
| **前端框架** | Vue vs React | React | 生態成熟、組件更靈活 |
| **打包工具** | Webpack vs Vite | Vite | 更快的開發構建、現代工具 |
| **CSS 框架** | Bootstrap vs Tailwind | Tailwind | 細粒度控制、動畫友好 |
| **圖片傳輸** | 多部分上傳 vs Base64 | Base64 | 簡化前後端邏輯 |
| **狀態管理** | Redux vs 本地 State | 本地 State | 單次對話，無複雜狀態 |

---

## 🏗️ 架構設計原則

### 後端層次（分層架構）
```
config/     → 統一配置管理 (Settings + .env)
↓
core/       → vLLM 引擎生命週期管理
↓
api/        → OpenAI SDK 包裝層
↓
webapp/
  └─ backend/ → FastAPI 服務層 (REST + SSE)
```

**核心原則**:
- 關注點分離：每層單一職責
- 配置優先級：`.env` > 代碼預設值
- 錯誤明確：區分不同類型的異常

### 前端架構（組件式）
```
App.jsx (殼層)
  ├─ ChatBox (互動層)
  │   ├─ 文字輸入 + 發送
  │   ├─ 圖片上傳 + 預覽
  │   ├─ 拖放支援
  │   └─ 訊息容器
  │
  ├─ MessageBubble (展示層)
  │   ├─ 使用者訊息氣泡
  │   ├─ AI 回應氣泡
  │   └─ 進入動畫
  │
  └─ 背景效果層
      ├─ 星空背景
      └─ 浮動光球
```

**核心原則**:
- 單一職責：每個組件只負責一個視覺或邏輯部分
- 樣式隔離：使用 Tailwind 避免全局污染
- 無狀態設計：單次對話，不保存用戶數據

---

## 📊 通訊架構

### HTTP 通訊流

```
客戶端 (React)
  ↓ HTTP POST (JSON)
FastAPI 後端
  ↓ OpenAI SDK (async)
vLLM 推論服務
  ↓ GPU 推論
模型輸出
  ↑ SSE 流式回應 (data: xxx\n\n)
客戶端實時展示
```

### SSE 流式協議

```
連接: EventSource('/api/chat/stream')
接收格式:
  data: 第一個 token\n\n
  data: 第二個 token\n\n
  ...
  data: [DONE]\n\n

錯誤格式:
  data: [ERROR] 錯誤訊息\n\n
```

### 影片傳輸流

```
瀏覽器拖放/選擇影片
  ↓ File 物件保存（不讀入記憶體）
  ↓ createObjectURL 本地縮圖預覽
  ↓ FormData 打包（multipart/form-data）
  ↓ HTTP POST 到後端
後端接收
  ↓ 寫入 /tmp 臨時檔案
  ↓ OpenCV 提取影格（依 video_fps 取樣）
  ↓ 影格編碼 Base64 → 寫入臨時 MP4 分段
  ↓ SSE [INFO] 事件（時長/幀數/分段）
  ↓ vLLM 影片推論（自動分段 + 彙總）
流式 SSE token 回應 + 清理 tmp 檔案
```

### 圖片傳輸流

```
瀏覽器拖放/選擇
  ↓ 檔案讀取 (FileReader)
  ↓ 轉換 Base64
  ↓ FormData 打包
  ↓ HTTP POST 到後端
後端接收
  ↓ Base64 解碼為二進制
  ↓ OpenAI 多模態格式構建
  ↓ vLLM 視覺推論
模型回應 (SSE 流式)
```

---

## 🎨 設計系統文檔

### 顏色與排版

| 元素 | 配色 | 用途 |
|------|------|------|
| 主容器 | #7C3AED (主紫) | 品牌色 |
| 次級元素 | #A78BFA (淡紫) | 強調色 |
| 按鈕 CTA | #06B6D4 (青) | 行動色 |
| 背景 | 主紫→紫色漸變 | 視覺深度 |

### 視覺效果系統

| 效果 | 實現 | 用途 |
|------|------|------|
| 玻璃質感 | backdrop-blur + shadow | 卡片/輸入框 |
| 星空效果 | 絕對定位星點 + 動畫 | 背景視覺 |
| 光暈系統 | 浮動球 + animation | 環境光感 |
| 按鈕光澤 | 偽元素 + 滑動動畫 | 互動反饋 |
| 訊息進入 | fade-in + slide-up | 動態感 |

### 動畫系統

所有動畫統一時長 **300-500ms**，使用 **ease-in-out** 緩動：
- **進入動畫**: 訊息淡入 + 從下而上滑入
- **Hover 動畫**: 按鈕縮放 + 光澤滑動
- **脈衝動畫**: 模型狀態指示器雙層效果
- **加載動畫**: 旋轉圖標

---

## 🔧 關鍵實現細節

### 流式輸出實現

使用 FastAPI StreamingResponse + OpenAI Stream API：
```python
# 後端格式化 SSE
async def chat_stream():
    async with client.chat.completions.create(
        stream=True
    ) as stream:
        async for chunk in stream:
            yield f"data: {content}\n\n"
        yield "data: [DONE]\n\n"

# 前端接收 SSE
const eventSource = new EventSource('/api/chat/stream');
eventSource.onmessage = (e) => {
    if (e.data === '[DONE]') {
        eventSource.close();
    } else {
        // 實時渲染
    }
};
```

### 拖放上傳實現

識別四個拖放事件，提供清晰的視覺反饋：
- **dragenter**: 激活拖放區域高亮
- **dragleave**: 取消高亮（必須正確區分子元素）
- **dragover**: 阻止預設行為
- **drop**: 提取檔案，進行驗證與上傳

重點：正確處理 dragenter/dragleave 嵌套以避免閃爍

### 圖片預覽與清除

改進的生命週期管理：
1. 選擇圖片 → 即時預覽
2. 點擊發送 → **立即清除預覽**（而非等待回應）
3. 收到回應 → 展示 AI 訊息

優點：使用者明確知道圖片已發送

---

## 📝 開發最佳實踐

### 後端開發

1. **配置優先**: 新參數先在 Settings 中定義
2. **類型安全**: 所有函數必須有完整類型註解
3. **錯誤詳細**: 異常訊息包含原因和改善建議
4. **文檔清晰**: 公開函數必須有 docstring

### 前端開發

1. **設計系統遵守**: 使用已定義的顏色、字型、動畫
2. **組件職責單一**: 避免單一組件做過多事
3. **樣式隔離**: Tailwind 工具類，不寫全局 CSS
4. **性能優先**: 優先使用 transform/opacity（GPU 加速）
5. **無障礙考慮**: 保留 title、aria-label 等

### 通訊協議

1. **SSE 優於 WebSocket**: 簡單、標準、單向足夠
2. **明確終止信號**: `[DONE]` 和 `[ERROR]` 必須清晰
3. **Base64 圖片**: 避免複雜的多部分編碼邏輯
4. **超時管理**: 設置合理的請求超時

---

## 🚀 部署與維護

### 開發環境啟動

```bash
# 一鍵啟動（推薦）
./start_webapp.sh

# 手動啟動
# 終端 1：vLLM 服務
python main.py

# 終端 2：後端 API
cd webapp/backend && python main.py

# 終端 3：前端開發
cd webapp/frontend && npm run dev
```

### 生產部署注意

- 前端：使用 `npm run build` 生成靜態文件，由 Nginx 提供服務
- 後端：使用 Gunicorn + Uvicorn 多進程運行
- vLLM：配置 GPU 資源、記憶體限制、並發參數

### 監控與調試

- **前端**: 瀏覽器 DevTools（Network、Console、Performance）
- **後端**: 日誌輸出、API 響應時間
- **推論**: vLLM 內置監控（/metrics 端點）

---

## 📈 性能特徵

### 目標指標
| 指標 | 目標 | 備註 |
|------|------|------|
| TTFT | < 1s | 首 Token 時間 |
| TPOT | < 50ms | 每 Token 時間 |
| TPS | > 100 | Token 吞吐量 |
| 頁面載入 | < 3s | 含模型資訊查詢 |
| 動畫幀率 | ≥ 60fps | 使用 GPU 加速 CSS |

### 最佳化建議
1. 啟用 vLLM 的前綴快取 (`enable_prefix_caching`)
2. 調整 `max_num_batched_tokens` 以平衡延遲和吞吐
3. 使用 CSS transform 而非改變大小/位置
4. 考慮圖片預加載與懶加載

---

## 🔄 未來擴展方向

### 短期（下一版本）
- [ ] 多輪對話（可選保存）
- [ ] 模型切換器
- [ ] 對話匯出功能
- [ ] 代碼高亮展示

### 中期
- [ ] 語音輸入/輸出
- [ ] 主題切換（深色/淺色）
- [ ] 更多視覺模型支持
- [ ] 嵌入式分析儀表板

### 長期
- [ ] 行動應用版本
- [ ] 多語言界面
- [ ] 企業級權限管理
- [ ] API 限速與計費

---

## 📚 文檔索引

- **使用者指南**: [webapp/README.md](webapp/README.md)
- **快速開始**: [webapp/QUICKSTART.md](webapp/QUICKSTART.md)
- **功能演示**: [webapp/FEATURES.md](webapp/FEATURES.md)
- **更新日誌**: [webapp/CHANGELOG.md](webapp/CHANGELOG.md)
- **架構分析**: [docs/ARCHITECTURE_ANALYSIS.md](docs/ARCHITECTURE_ANALYSIS.md)
- **AI 協作指示**: [.github/copilot-instructions.md](.github/copilot-instructions.md)
- **專案概覽**: [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)

---

## 💡 核心洞察

### 設計理念
本專案體現了**關注點分離**和**漸進式增強**的設計理念：
- 後端嚴格分層：配置 → 核心 → API → 服務
- 前端模組化：殼層 → 互動層 → 展示層 → 效果層
- 通訊標準化：遵循 HTTP 和 SSE 標準，易於集成

### 使用者體驗
優先級順序：
1. **立即反應**: SSE 流式輸出，無等待感
2. **直觀互動**: 拖放、實時預覽、清晰反饋
3. **視覺愉悅**: 優雅設計、平滑動畫、專業感
4. **無學習曲線**: 一鍵啟動、開箱即用

### 開發體驗
- **清晰的錯誤訊息**: 快速定位問題
- **靈活的配置系統**: 易於定製參數
- **模組化的代碼**: 便於擴展功能
- **完整的文檔**: 降低維護成本

---

**最後更新**: 2026-02-23  
**版本**: v1.2  
**維護狀態**: 積極開發
