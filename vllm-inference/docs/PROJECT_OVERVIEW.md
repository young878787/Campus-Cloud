# 專案概覽

這是一個基於 vLLM 的高併發模型部署方案，現已整合**優雅夢幻風格的 Web UI**，支持流式對話、圖片辨識與**影片分析**。

## 📦 核心特性

### 後端服務
- **vLLM 推論引擎**: 高併發推論（Continuous Batching + PagedAttention）
- **OpenAI 兼容 API**: 標準 API 接口，易於集成
- **視覺模型支持**: 支援文字、圖片、影片多模態輸入
- **異步優先**: AsyncOpenAI + asyncio，高效併發

### Web UI 應用
- **優雅夢幻風格**: 紫色漸變、玻璃質感、星空背景
- **流式輸出**: Server-Sent Events (SSE) 實時響應
- **拖放上傳**: 支援拖放圖片、影片上傳辨識
- **多媒體支援**: 文字 / 圖片 / 影片 / 文件四種輸入模式
- **單次對話**: 無狀態設計，不保存歷史記錄

## 🏗️ 專案結構

```
vllm_single/
├── config/              # 配置層 (Settings)
├── core/                # 核心層 (vLLM Engine)
├── api/                 # API 層 (OpenAI Client)
├── benchmark/           # 測試層 (壓力測試)
├── utils/               # 工具層 (模型檢測、圖片、影片處理)
├── webapp/              # Web UI 應用
│   ├── backend/         # FastAPI 後端
│   │   ├── main.py      # API 服務（含影片端點）
│   │   └── test_api.py  # 測試腳本
│   ├── frontend/        # React 前端
│   │   ├── src/         # 組件和樣式
│   │   └── package.json # 依賴管理
│   ├── README.md        # 完整文檔
│   └── QUICKSTART.md    # 快速開始
├── start_webapp.sh      # 一鍵啟動腳本
└── main.py              # vLLM 服務入口
```

## 🚀 快速開始

### 前置需求
- Python 3.10+ 和 CUDA 環境
- Node.js 18+ (前端)
- vLLM 服務已配置

### 啟動步驟

1. **啟動 vLLM 服務**:
```bash
python main.py
```

2. **啟動 Web UI**:
```bash
./start_webapp.sh
```

3. **訪問應用**:
打開瀏覽器訪問 `http://localhost:5173`

## ✨ 主要功能

### 文字聊天
- 實時流式輸出
- 支援長文本生成
- 可調節溫度和 token 限制

### 圖片辨識
- 上傳圖片（JPG、PNG、WebP）
- 流式分析結果
- 支援 Base64 編碼

### 影片分析 (v1.2 新增)
- 上傳影片（MP4、MOV、AVI 等）
- 自動分段推論（超過 64 幀自動切片）
- 即時顯示影片元資料（時長、幀數、分段數）
- 支援拖放上傳

### 視覺優化 (v1.1)
- 玻璃質感效果
- 多層光暈和陰影
- 按鈕光澤動畫
- 訊息進入動畫

## 📊 技術棧

| 層級 | 技術 | 說明 |
|------|------|------|
| **推論** | vLLM | 高併發推論引擎 |
| **後端 API** | FastAPI | Web 服務框架 |
| **客戶端** | AsyncOpenAI | 非同步 API 客戶端 |
| **前端框架** | React 18 | UI 庫 |
| **打包工具** | Vite | 現代化構建工具 |
| **樣式系統** | Tailwind CSS | 實用優先的 CSS |
| **圖片處理** | PIL/Pillow | 圖片編碼與調整 |
| **影片處理** | OpenCV | 影格提取與分段 |
| **配置管理** | Pydantic | 類型安全配置 |

## 🎨 設計系統

### 配色方案
- **主紫色**: #7C3AED (Indigo-600)
- **淡紫色**: #A78BFA (Indigo-400)
- **青色**: #06B6D4 (Cyan-500)
- **背景**: 深紫漸變 (Primary-900 to Purple-900)

### 視覺效果
- **玻璃質感**: backdrop-blur + 半透明 + 多層陰影
- **星空背景**: 動態移動的星點
- **光暈效果**: 浮動彩色球體 + 脈衝動畫
- **動畫時長**: 300-500ms (ease-in-out)

### 字型
- **標題**: Noto Serif JP
- **內文**: Noto Sans JP

## 📈 性能指標

| 指標 | 目標值 | 說明 |
|------|-------|------|
| **TTFT** | < 1s | 首 Token 延遲 |
| **TPOT** | < 50ms | 每 Token 延遲 |
| **TPS** | > 100 | Token 吞吐量 |
| **RPS** | > 10 | 請求吞吐量 |
| **併發** | 64+ | 最大序列數 |

## 🔧 配置與部署

### 環境變數 (.env)
```
MODEL_NAME              # 使用的模型
API_PORT=8000          # API 埠號
GPU_MEMORY_UTILIZATION # GPU 記憶體使用率
MAX_NUM_SEQS           # 最大併發序列數
```

### 開發模式
```bash
# 開發前端（熱重載）
npm run dev

# 開發後端（自動重載）
python main.py
```

### 生產部署
```bash
# 構建前端
npm run build

# 使用 Nginx 反向代理
# 啟動後端服務
```

## 📚 文檔資源

- [webapp/README.md](webapp/README.md) - Web UI 完整指南
- [webapp/QUICKSTART.md](webapp/QUICKSTART.md) - 快速開始
- [webapp/FEATURES.md](webapp/FEATURES.md) - 功能演示
- [webapp/CHANGELOG.md](webapp/CHANGELOG.md) - 更新日誌
- [.github/copilot-instructions.md](.github/copilot-instructions.md) - AI 協作指示

## 🐛 故障排除

### Web UI 無法啟動
- 確認 vLLM 服務運行在 localhost:8000
- 檢查 Node.js 版本 (需 18+)
- 查看終端輸出的錯誤訊息

### 影片分析不支援
- 確認 MODEL_NAME 是支援影片的視覺模型（如 Qwen3-VL）
- 確認 OpenCV (`cv2`) 已安裝：`pip install opencv-python-headless`
- 影片過大時推論較慢，可降低 `VIDEO_FPS` 設定

### 圖片分析不支援
- 確認 MODEL_NAME 是視覺模型 (如 Qwen-VL)
- 檢查模型是否正確加載

### 流式輸出中斷
- 增加 request_timeout
- 降低併發數量
- 檢查網路連接

## 📈 未來計劃

- [ ] 多輪對話記憶（可選）
- [ ] 語音輸入/輸出
- [ ] 主題切換（深色/淺色）
- [ ] 對話匯出功能
- [ ] 多模型切換器
- [ ] 自定義主題顏色

## 👥 貢獻指南

1. 遵循現有架構層次
2. 關注點分離，單一職責
3. 完整類型註解和文檔
4. 提供清晰錯誤訊息

## 📄 授權

MIT License

---

**版本**: v1.2 with Video Support  
**最後更新**: 2026-02-23  
**維護者**: vLLM Team
