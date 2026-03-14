# vLLM Web UI - 優雅夢幻助手

基於 vLLM 的現代化 Web UI，支援**流式輸出**和**圖片辨識**，採用優雅夢幻的動漫風格設計。

## ✨ 特色

- 🎨 **優雅夢幻風格**: 紫色系漸變、玻璃質感、星空背景
- 🌊 **流式輸出**: 實時顯示 AI 回應，提升互動體驗  
- 🖼️ **圖片辨識**: 支援視覺模型，上傳圖片進行分析
- 💬 **單次對話**: 不保存歷史記錄，專注當前問題
- ⚡ **高效能**: FastAPI + React，異步處理，響應迅速

## 🏗️ 技術架構

```
webapp/
├── backend/          # FastAPI 後端
│   └── main.py      # API 服務 (流式代理)
└── frontend/        # React 前端
    ├── src/
    │   ├── App.jsx           # 主應用
    │   ├── components/
    │   │   ├── ChatBox.jsx   # 聊天容器
    │   │   └── MessageBubble.jsx  # 訊息氣泡
    │   └── index.css         # 夢幻風格樣式
    └── package.json
```

### 後端 API

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/model-info` | GET | 獲取模型資訊 |
| `/api/chat` | POST | 文字聊天（非流式） |
| `/api/chat/stream` | POST | 文字聊天（流式 SSE） |
| `/api/chat/vision` | POST | 視覺聊天（非流式） |
| `/api/chat/vision/stream` | POST | 視覺聊天（流式 SSE） |

## 🚀 快速開始

### 前置需求

1. **vLLM 服務已啟動**:
   ```bash
   python main.py
   ```

2. **Node.js** (v18+):
   ```bash
   node --version
   ```

### 一鍵啟動

```bash
# 賦予執行權限
chmod +x start_webapp.sh

# 啟動全部服務
./start_webapp.sh
```

腳本會自動：
1. ✅ 檢查 vLLM 服務狀態
2. 📦 安裝 Python 依賴 (FastAPI, uvicorn)
3. 📦 安裝 Node.js 依賴 (React, Vite)
4. 🚀 啟動前端開發伺服器 (http://localhost:5173)
5. 🚀 啟動後端 API 服務 (http://localhost:3000)

### 手動啟動

#### 方法 1: 開發模式（推薦）

**終端 1 - 啟動後端**:
```bash
cd webapp/backend
pip install fastapi uvicorn[standard] python-multipart
python main.py
```

**終端 2 - 啟動前端**:
```bash
cd webapp/frontend
npm install
npm run dev
```

訪問: http://localhost:5173

#### 方法 2: 生產模式

```bash
# 建置前端
cd webapp/frontend
npm install
npm run build

# 啟動後端（會自動提供前端靜態檔案）
cd ../backend
python main.py
```

訪問: http://localhost:3000

## 🎨 設計系統

### 配色方案

採用 **AI/Chatbot Platform** 配色（來自 UI/UX Pro Max）:

| 角色 | 顏色 | 說明 |
|------|------|------|
| Primary | `#7C3AED` | 主要紫色 |
| Secondary | `#A78BFA` | 淡紫色 |
| CTA | `#06B6D4` | 青色按鈕 |
| Background | `#FAF5FF` | 淺紫背景 |
| Text | `#1E1B4B` | 深紫文字 |

### 視覺效果

- **玻璃質感** (Glassmorphism): `backdrop-blur` + 半透明背景
- **星空背景**: 動態移動的星點
- **漸變光暈**: 浮動動畫的彩色光球
- **文字發光**: 紫色發光效果
- **流暢過渡**: 300ms ease-in-out

### 字型

- **標題**: Noto Serif JP (優雅日系)
- **內文**: Noto Sans JP (清晰易讀)

## 📸 使用指南

### 文字對話

1. 在輸入框輸入訊息
2. 按 Enter 或點擊發送按鈕
3. 實時查看 AI 流式回應
4. 點擊「開始新對話」重新開始

### 圖片辨識

（需要視覺模型，如 Qwen-VL）

1. 點擊「上傳圖片」按鈕
2. 選擇圖片檔案（支援 JPG, PNG, WebP 等）
3. 圖片會顯示預覽
4. 輸入關於圖片的問題
5. 發送後實時查看 AI 分析結果

## 🔧 配置選項

### 後端配置

編輯 `webapp/backend/main.py`:

```python
# 伺服器設定
host="0.0.0.0"    # 監聽地址
port=3000          # 埠號

# 模型參數（在請求中設定）
max_tokens=512     # 最大生成長度
temperature=0.7    # 溫度參數
```

### 前端配置

編輯 `webapp/frontend/vite.config.js`:

```javascript
server: {
  port: 5173,      // 前端埠
  proxy: {
    '/api': {
      target: 'http://localhost:3000',  // 後端地址
      changeOrigin: true,
    }
  }
}
```

## 🐛 故障排除

### 問題 1: 無法連接到 vLLM 服務

```
❌ vLLM 服務未運行！
```

**解決方案**:
```bash
# 啟動 vLLM 服務
python main.py

# 檢查服務狀態
curl http://localhost:8000/health
```

### 問題 2: 圖片上傳失敗

```
當前模型不支援視覺輸入
```

**解決方案**:
- 確認 `.env` 中的 `MODEL_NAME` 是視覺模型（如 Qwen-VL, LLaVA）
- 檢查 `utils/model_utils.py` 的 `VISION_KEYWORDS`

### 問題 3: 流式輸出中斷

**可能原因**:
- 網路超時
- vLLM 服務過載

**解決方案**:
- 降低併發請求數
- 調整 `config/settings.py` 的 `request_timeout`

## 📊 性能建議

### 開發環境

- 使用 `npm run dev` 啟用 HMR（熱更新）
- 後端使用 `reload=True` 自動重載

### 生產環境

- 建置前端: `npm run build`
- 使用 Nginx 反向代理
- 啟用 Gzip 壓縮
- 使用 CDN 加速靜態資源

## 🎯 未來擴展

- [ ] 多輪對話記憶（可選）
- [ ] 語音輸入/輸出
- [ ] 深色/淺色主題切換
- [ ] 匯出對話為 Markdown
- [ ] 多模型切換
- [ ] 自定義主題顏色

## 📄 授權

本專案遵循 MIT 授權。

---

**Powered by vLLM** | **Designed with UI/UX Pro Max** | **Built with ❤️**
