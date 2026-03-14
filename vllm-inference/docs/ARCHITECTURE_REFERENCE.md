# Web 架構快速參考

## 🏠 系統架構圖

```
┌─────────────────────────────────────────────────────────────┐
│                     用戶瀏覽器層                              │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │         React App (Vite 開發伺服器: 5173)              │ │
│  │                                                         │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │           App.jsx (應用殼層)                      │ │ │
│  │  │  - 背景效果 (星空、光球)                         │ │ │
│  │  │  - 標題和模型狀態                                │ │ │
│  │  └────────────┬─────────────┬──────────────────────┘ │ │
│  │               │             │                         │ │
│  │  ┌────────────▼──┐  ┌──────▼──────────────────────┐ │ │
│  │  │   ChatBox.jsx │  │   MessageBubble.jsx        │ │ │
│  │  │  (互動層)      │  │   (展示層)                  │ │ │
│  │  │ - 文字輸入     │  │ - 訊息氣泡                 │ │ │
│  │  │ - 圖片上傳     │  │ - 進入動畫                 │ │ │
│  │  │ - 拖放支援     │  │ - 視覺效果                 │ │ │
│  │  │ - SSE 接收     │  │                            │ │ │
│  │  └────────────┬──┘  └──────┬───────────────────────┘ │ │
│  │               │             │                         │ │
│  │  ┌────────────▼─────────────▼──────────────────────┐ │ │
│  │  │         樣式系統 (Tailwind + CSS)                │ │ │
│  │  │  - 玻璃質感 | 星空 | 光暈 | 動畫                │ │ │
│  │  └─────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────┘ │
│                      ▼ HTTP POST / SSE                      │
└─────────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              後端服務層 (FastAPI: 3000)                      │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  main.py (7 個 REST 端點)                              │ │
│  │                                                         │ │
│  │  POST /api/model-info           → 模型資訊查詢        │ │
│  │  POST /api/chat                 → 文字對話 (非流式)  │ │
│  │  POST /api/chat/stream          → 文字對話 (流式)    │ │
│  │  POST /api/chat/vision          → 圖片分析 (非流式)  │ │
│  │  POST /api/chat/vision/stream   → 圖片分析 (流式)    │ │
│  │  GET  /api/health               → 健康檢查            │ │
│  │  POST /api/reset                → 狀態重置            │ │
│  │                                                         │ │
│  └────────────────────────────────────────────────────────┘ │
│                      ▼ OpenAI SDK                           │
└─────────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│         推論核心層 (vLLM 服務: 8000)                        │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  ModelClient (config/core/api)                        │ │
│  │  - 智能客戶端                                         │ │
│  │  - 流式和非流式支援                                   │ │
│  │  - 視覺模型自動檢測                                   │ │
│  │  - Base64 圖片編碼                                    │ │
│  └──────────┬────────────────────────────────────────────┘ │
│             │                                               │ │
│  ┌──────────▼────────────────────────────────────────────┐ │
│  │  vLLM 推論引擎                                        │ │
│  │  - Continuous Batching                               │ │
│  │  - PagedAttention                                     │ │
│  │  - 多 GPU 並行                                        │ │
│  │  - 高併發 (64+ 序列)                                 │ │
│  └───────────────────────────────────────────────────────┘ │
│             │                                               │ │
│  ┌──────────▼────────────────────────────────────────────┐ │
│  │  GPU 推論                                             │ │
│  │  - 文字生成                                           │ │
│  │  - 視覺理解                                           │ │
│  │  - 實時回應                                           │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 📡 通訊協議詳解

### 1. 非流式對話 (普通 HTTP)

```
請求流程:
客戶端
  │
  ├─ POST /api/chat
  │  Content-Type: application/json
  │  {
  │    "message": "你好",
  │    "max_tokens": 512,
  │    "temperature": 0.7
  │  }
  │
  └─ 等待完整回應 (5-30s)
      ↓
    200 OK
    {
      "content": "完整的 AI 回應...",
      "total_tokens": 123
    }
```

### 2. 流式對話 (SSE)

```
請求流程:
客戶端 (建立 EventSource)
  │
  ├─ POST /api/chat/stream
  │  Content-Type: application/json
  │  {
  │    "message": "你好",
  │    ...
  │  }
  │
  └─ 實時接收事件流
      ↓
    200 OK
    Content-Type: text/event-stream
    
    data: 你\n\n
    data: 好\n\n
    data: ，\n\n
    data: 有\n\n
    ...
    data: [DONE]\n\n
```

### 3. 圖片上傳 (FormData)

```
請求流程:
客戶端 (檔案選擇或拖放)
  │
  ├─ 讀取圖片檔案 → FileReader API
  │  convertToBase64(file)
  │
  ├─ POST /api/chat/vision/stream
  │  Content-Type: multipart/form-data
  │  
  │  Form Data:
  │  ├─ message: "這是什麼？"
  │  ├─ image: <base64 圖片>
  │  ├─ max_tokens: 512
  │  └─ temperature: 0.7
  │
  └─ 接收 SSE 視覺分析結果
      ↓
    data: 這\n\n
    data: 是\n\n
    ... (視覺分析結果)
    data: [DONE]\n\n
```

---

## 🗄️ 檔案結構詳解

```
docs/
├─ ARCHITECTURE_ANALYSIS.md     # 原有架構文檔
├─ SHAREGPT_QUICKSTART.md       # ShareGPT 基準測試指南
└─ VISION_UPDATE_NOTES.md       # 視覺模型更新說明

webapp/
├─ backend/
│  ├─ main.py                   # 7 個 FastAPI 端點
│  ├─ test_api.py               # API 功能測試
│  └─ requirements.txt           # 後端依賴 (可選)
│
├─ frontend/
│  ├─ public/                    # 靜態資源
│  ├─ src/
│  │  ├─ App.jsx                # 主應用殼層 (94 行)
│  │  ├─ main.jsx               # React 入口
│  │  ├─ index.css              # 全局樣式 (150+ 行)
│  │  │                         # - 玻璃效果
│  │  │                         # - 動畫定義
│  │  │                         # - 星空背景
│  │  │                         # - 全局類別
│  │  │
│  │  └─ components/
│  │     ├─ ChatBox.jsx         # 互動容器 (300+ 行)
│  │     │                      # - 文字輸入
│  │     │                      # - 拖放上傳
│  │     │                      # - 圖片預覽
│  │     │                      # - SSE 接收
│  │     │                      # - 訊息容器
│  │     │
│  │     └─ MessageBubble.jsx   # 訊息展示 (60 行)
│  │                            # - 使用者氣泡
│  │                            # - AI 氣泡
│  │                            # - 進入動畫
│  │
│  ├─ index.html                # HTML 模板
│  ├─ package.json              # 依賴清單 (React, Vite, Tailwind)
│  ├─ vite.config.js            # Vite 配置 (API 代理)
│  ├─ tailwind.config.js        # Tailwind 配置 (顏色、動畫)
│  └─ postcss.config.js         # PostCSS 配置
│
├─ README.md                     # 完整使用指南
├─ QUICKSTART.md                # 快速開始指南
├─ FEATURES.md                  # 功能演示
├─ CHANGELOG.md                 # v1.1 更新日誌
└─ package.json                 # 前端根依賴 (可選)

config/
├─ __init__.py
├─ settings.py                  # Pydantic 配置類
└─ __pycache__/

core/
├─ __init__.py
├─ engine.py                    # vLLM 子進程管理
└─ __pycache__/

api/
├─ __init__.py
├─ client.py                    # OpenAI 客戶端包裝
└─ __pycache__/

utils/
├─ __init__.py
├─ health_utils.py              # 健康檢查
├─ image_utils.py               # 圖片處理 (新增 Base64 函數)
├─ logging_utils.py             # 日誌系統
├─ model_utils.py               # 模型檢測
└─ __pycache__/

benchmark/
├─ __init__.py
├─ async_bench.py               # 異步壓力測試
├─ enhanced_bench.py            # 增強版測試
├─ sharegpt_bench.py            # ShareGPT 基準
├─ sharegpt_dataset.py          # 數據集管理
└─ __pycache__/

.github/
└─ copilot-instructions.md      # AI 開發指示 (已更新 v1.1)

.env                            # 環境變數 (模型、API 等)
.env.example                    # 環境變數範本
main.py                         # vLLM 服務啟動
start_webapp.sh                 # 🆕 一鍵啟動腳本
PROJECT_OVERVIEW.md             # 專案概覽 (已更新)
DEVELOPMENT_SUMMARY.md          # 🆕 開發歷程總結
ARCHITECTURE_REFERENCE.md       # 🆕 本檔案
```

---

## 🚀 啟動流程

### 一鍵啟動 (推薦)

```bash
./start_webapp.sh
```

**內部流程**:
1. 檢查 vLLM 服務是否運行 (http://localhost:8000)
2. 安裝 Python 依賴 (如需要)
3. 安裝 Node.js 依賴 (如需要)
4. 啟動後端 FastAPI (port 3000)
5. 啟動前端開發伺服器 (port 5173)
6. 自動開啟瀏覽器

### 手動啟動

```bash
# 終端 1: vLLM 服務 (必須先起)
python main.py

# 終端 2: 後端 API
cd webapp/backend && python main.py

# 終端 3: 前端開發 (有熱重載)
cd webapp/frontend && npm run dev
```

### 生產構建

```bash
# 前端構建 (輸出到 dist/)
cd webapp/frontend && npm run build

# 後端使用 Gunicorn + Uvicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
```

---

## 📝 API 端點參考

### 1. `/api/model-info` - 模型資訊

```
POST /api/model-info

請求:
{
  "model_name": "Qwen3-VL-30B"  (可選, 不提供則使用配置模型)
}

回應:
{
  "model_name": "qwen/Qwen3-VL-30B-A3B-Thinking-FP8",
  "is_vision": true,
  "context_length": 32768,
  "max_tokens": 512,
  "temperature": 0.7
}
```

### 2. `/api/chat` - 純文字 (非流式)

```
POST /api/chat

請求:
{
  "message": "人工智慧有什麼應用？",
  "max_tokens": 1024,
  "temperature": 0.7
}

回應:
{
  "content": "人工智慧的應用非常廣泛...",
  "total_tokens": 287
}
```

### 3. `/api/chat/stream` - 純文字 (流式)

```
POST /api/chat/stream

請求: (同上)

回應: (SSE 流)
data: 人\n\n
data: 工\n\n
data: 智\n\n
...
data: [DONE]\n\n
```

### 4. `/api/chat/vision` - 圖片分析 (非流式)

```
POST /api/chat/vision

請求 (FormData):
- message: "這是什麼動物？"
- image: <file or base64>
- max_tokens: 512
- temperature: 0.7

回應:
{
  "content": "這是一隻貓咪...",
  "total_tokens": 145
}
```

### 5. `/api/chat/vision/stream` - 圖片分析 (流式)

```
POST /api/chat/vision/stream

請求: (FormData 同上)

回應: (SSE 流)
data: 這\n\n
data: 是\n\n
...
data: [DONE]\n\n
```

### 6. `/api/health` - 健康檢查

```
GET /api/health

回應:
{
  "status": "healthy",
  "vllm_service": "running",
  "timestamp": "2026-02-16T12:00:00"
}
```

### 7. `/api/reset` - 重設狀態

```
POST /api/reset

回應:
{
  "message": "Application state reset successfully"
}
```

---

## 🎨 Tailwind 配置要點

### 自訂配色

```javascript
colors: {
  primary: {
    600: '#7C3AED',  // 主紫
    400: '#A78BFA',  // 淡紫
    900: '#3F0F6B'   // 深紫
  },
  cyan: {
    500: '#06B6D4'   // 按鈕青
  }
}
```

### 自訂動畫

```javascript
animation: {
  'in': 'fadeIn 0.5s ease-in-out',
  'bounce-slow': 'bounce 3s infinite'
}

keyframes: {
  fadeIn: {
    '0%': { opacity: '0', transform: 'translateY(10px)' },
    '100%': { opacity: '1', transform: 'translateY(0)' }
  }
}
```

### Backdrop 效果

```javascript
backdropBlur: {
  'sm': '4px',
  'md': '12px',
  'lg': '20px'
}
```

---

## 🔍 除錯提示

### 前端問題排查

| 症狀 | 原因 | 解決方案 |
|------|------|---------|
| 訊息不更新 | SSE 未連接 | 檢查後端 API 運行狀況 |
| 圖片不預覽 | FileReader 失敗 | 檢查檔案格式和大小 |
| 拖放無反應 | 事件未綁定 | 檢查 dragover 的 preventDefault |
| 樣式不應用 | Tailwind 編譯失敗 | 執行 `npm run dev` 重新構建 |

### 後端問題排查

| 症狀 | 原因 | 解決方案 |
|------|------|---------|
| 404 錯誤 | 端點不存在 | 檢查 main.py 路由定義 |
| CORS 錯誤 | 跨域設定 | 檢查 FastAPI CORS 中間件 |
| 超時 | vLLM 推論慢 | 降低 max_tokens 或並發數 |
| 圖片錯誤 | Base64 不合法 | 檢查圖片編碼和格式 |

---

## 📊 性能調優

### Tailwind 構建優化

```bash
# 生產構建 (自動 tree-shake 未用樣式)
npm run build

# 開發構建 (包含所有樣式，便於調試)
npm run dev
```

### CSS 動畫優化

```css
/* ✅ GPU 加速 (使用 transform) */
.button {
  transition: transform 300ms ease-in-out;
}
.button:hover {
  transform: scale(1.05);
}

/* ❌ 避免 (引發重排) */
.button:hover {
  width: 110%;
  height: 110%;
}
```

---

**版本**: v1.1  
**最後更新**: 2026-02-16  
**用途**: 開發參考和快速查詢
