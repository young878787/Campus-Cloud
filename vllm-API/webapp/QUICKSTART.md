# Web UI 快速啟動指南

## 🚀 啟動步驟

### 1. 確保 vLLM 服務運行

```bash
# 啟動 vLLM 服務（如未啟動）
python main.py
```

### 2. 一鍵啟動 Web UI

```bash
# 執行啟動腳本
./start_webapp.sh
```

### 3. 訪問應用

開啟瀏覽器訪問: **http://localhost:5173**

---

## 📝 手動啟動（開發模式）

### 終端 1 - 後端

```bash
cd webapp/backend
pip install fastapi uvicorn[standard] python-multipart
python main.py
```

### 終端 2 - 前端

```bash
cd webapp/frontend
npm install
npm run dev
```

---

## 🎨 功能展示

### ✅ 文字聊天（流式輸出）

1. 在輸入框輸入訊息
2. 觀察實時流式回應
3. 每次對話獨立，不保存歷史

### ✅ 圖片辨識（視覺模型）

1. 點擊「上傳圖片」
2. 選擇圖片檔案
3. 輸入問題
4. 實時查看分析結果

---

## 🐛 常見問題

### Q: 無法連接到後端？

**A**: 確認 vLLM 服務運行在 `http://localhost:8000`

```bash
curl http://localhost:8000/health
```

### Q: 圖片上傳不支援？

**A**: 當前模型必須是視覺模型（如 Qwen-VL）

檢查 `.env` 文件中的 `MODEL_NAME`

### Q: 前端無法啟動？

**A**: 確認 Node.js 版本

```bash
node --version  # 需要 v18+
```

---

## 📦 專案結構

```
webapp/
├── backend/
│   └── main.py          # FastAPI 服務
├── frontend/
│   ├── src/
│   │   ├── App.jsx      # 主應用
│   │   ├── components/  # React 組件
│   │   └── index.css    # 樣式
│   ├── package.json
│   └── vite.config.js
├── README.md            # 完整文檔
└── QUICKSTART.md        # 本文件
```

---

**享受優雅的 AI 對話體驗！✨**
