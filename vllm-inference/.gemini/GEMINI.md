# vLLM 高併發模型部署 - AI 協作指示

## 專案概覽

基於 vLLM 的乾淨架構高併發推論部署方案，支持文字與視覺多模態模型。

### 核心技術棧
- **推論引擎**: vLLM (Continuous Batching + PagedAttention)
- **API 標準**: OpenAI Compatible API
- **配置管理**: Pydantic Settings (.env 優先)
- **異步處理**: AsyncOpenAI + asyncio
- **圖片處理**: PIL/Pillow (視覺模型)

---

## 架構層次

### 後端核心層次
```
config/     → 設定層 (統一參數管理)
core/       → 核心層 (vLLM 引擎生命週期)
api/        → 介面層 (OpenAI 客戶端封裝)
benchmark/  → 測試層 (異步壓力測試)
utils/      → 工具層 (模型檢測、圖片處理)
docs/       → 文檔層 (僅當用戶要求時產出)
```

### Web 應用層次（v1.1 新增）
```
webapp/
├── backend/     → API 代理層 (FastAPI 服務)
│   ├── main.py  → vLLM API 轉發 + SSE 流式推送
│   └── test_api.py → 後端功能測試
├── frontend/    → 使用者介面層 (React + Vite)
│   ├── src/
│   │   ├── App.jsx → 主應用殼層 (背景、標題、配置)
│   │   ├── components/
│   │   │   ├── ChatBox.jsx → 聊天容器 (流式、拖放、圖片)
│   │   │   └── MessageBubble.jsx → 訊息氣泡 (樣式、動畫)
│   │   └── index.css → 全局樣式 (玻璃、發光、動畫)
│   └── package.json → 依賴管理
└── README.md → 使用指南

分層原則: 關注點分離，單一職責，依賴倒置
```

**Web UI 特點**:
- 獨立靜態伺服器啟動，可脫離官方 vLLM UI
- 優雅夢幻動漫風格（紫色系漸變、玻璃質感、星空背景）
- 支援流式輸出（Server-Sent Events）和拖放上傳
- 無狀態設計（單次對話，不保存歷史）

---

## 開發規範

### 1. 程式碼風格

- **類型註解**: 必須使用 `from __future__ import annotations` 和完整類型提示
- **文檔字串**: 所有公開函數、類必須有清晰的 docstring
- **命名規範**: 
  - 函數/變數: snake_case
  - 類名: PascalCase
  - 常數: UPPER_SNAKE_CASE
- **註解原則**: 解釋「為什麼」而非「做什麼」，複雜邏輯必註解

### 2. 設定管理

- **優先級**: `.env` > `settings.py` 預設值
- **新增參數**: 
  1. 在 `Settings` 類中定義 (使用 `Field` 描述)
  2. 更新 `.env.example` 範本
  3. 相關方法自動適配新參數
- **環境變數**: 關鍵變數通過 `inject_env_vars()` 注入子進程

### 3. 引擎層

- **啟動邏輯**: 使用 `subprocess.Popen` 管理 vLLM 子進程
- **健康檢查**: 啟動後必須等待 `/health` 端點就緒
- **錯誤處理**: 區分進程異常退出與超時，提供明確錯誤訊息
- **生命週期**: 支持正常終止 (SIGTERM) 與強制終止 (SIGKILL)

### 4. API 客戶端

- **雙模式**: 提供同步與異步方法（函數名以 `async_` 開頭）
- **流式支援**: `stream=True` 時返回迭代器，必須正確處理流式響應
- **視覺模型**: 
  - 自動檢測模型類型 (`is_vision_model` 屬性)
  - 圖片通過 Base64 編碼傳遞
  - 使用 `image_utils` 處理圖片調整與編碼
- **錯誤重試**: 重要場景使用指數退避重試策略

### 5. 基準測試

- **數據集**: 優先使用 ShareGPT 格式，支持自定義 JSON
- **並發控制**: 使用 `asyncio.Semaphore` 限制並發數
- **指標收集**: 
  - **延遲**: TTFT (首 Token 時間), TPOT (每 Token 時間), 總延遲
  - **吞吐量**: RPS (請求/秒), TPS (Token/秒)
  - **分位數**: P50, P90, P95, P99
- **結果輸出**: JSON 格式存入 `benchmark_results/`，檔名含時間戳

### 6. 工具函數

- **模型檢測** (`model_utils.py`):
  - `detect_model_type()`: 根據關鍵字判斷視覺/文字模型
  - `is_vision_model()`: 布林判斷
  - 維護 `VISION_KEYWORDS` 列表，新模型加入關鍵字
- **圖片處理** (`image_utils.py`):
  - `image_to_base64()`: 編碼為 Base64
  - `resize_image()`: 智能調整尺寸，保持長寬比
  - `create_multimodal_content()`: 建立 OpenAI 多模態格式

### 7. Web 前端開發規範

**設計系統**:
- **配色方案**: AI/Chatbot 紫色系（主紫 #7C3AED、淡紫 #A78BFA、青色 #06B6D4）
- **視覺效果**: 玻璃質感、多層陰影、星空背景、浮動光球
- **字型**: Noto Serif JP (標題) 與 Noto Sans JP (內文)
- **動畫速度**: 300-500ms ease-in-out (平滑過渡)

**元件開發**:
- **獨立職責**: 每個組件只負責一個視覺或邏輯部分
- **樣式隔離**: 使用 Tailwind 工具類，避免全局污染
- **響應式**: 支援 375px 到 1440px 的各種設備
- **無障礙**: 保留 title、aria-label，語義化標籤

**互動設計**:
- **即時反饋**: 所有按鈕都有 hover、active、disabled 狀態
- **載入指示**: 使用旋轉圖標或骨架屏表示進行中
- **動畫進入**: 訊息從底部淡入滑入（500ms）
- **拖放體驗**: 視覺高亮 + 覆蓋層提示

**性能優化**:
- **CSS 動畫**: 優先使用 transform 和 opacity（GPU 加速）
- **避免重排**: 使用 will-change 提示瀏覽器
- **懶加載**: 大型資源延遲加載
- **事件委託**: 減少事件監聽器數量

---

## 工作流程

### 新增功能

1. **理解需求**: 若不清楚，詢問用戶或提出更優方案
2. **選擇層次**: 確定修改涉及哪些層（config/core/api/benchmark/utils/webapp）
3. **更新設定**: 新參數先加入 `Settings`
4. **實現邏輯**: 遵循現有模式，保持乾淨架構（後端遵守分層，前端遵守設計系統）
5. **錯誤處理**: 提供明確錯誤訊息，避免靜默失敗；前端使用 try-catch + 使用者提示
6. **測試驗證**: 檢查語法錯誤 (`get_errors`)，必要時運行測試
7. **直接說明**: 完成後簡要說明改動，**不產出總結文檔**（除非用戶要求）

**前端特殊流程** (如涉及)：
1. 查看設計系統 (`webapp/frontend/tailwind.config.js`)
2. 使用已有的工具類（glass、button-shine、animate-in 等）
3. 保持動畫時間一致（300-500ms）
4. 測試拖放、流式輸出、圖片上傳等功能
5. 檢查響應式設計（多種解析度）

### 修復錯誤

1. **查看錯誤**: 使用 `get_errors` 或查看終端輸出
2. **定位原因**: 閱讀相關檔案，理解上下文
3. **查詢文檔**: 
   - **vLLM**: 查閱最新 vLLM 官方文檔（版本更新快）
   - **OpenAI API**: 參考 OpenAI Python SDK 文檔
   - **Pydantic**: 查詢 Pydantic v2 文檔
   - **React/Tailwind**: 參考官方文檔和最佳實踐
4. **實施修復**: 直接修改，**不使用後退機制**，確保使用最新方案
5. **驗證修復**: 再次檢查錯誤是否消失

**前端特殊修復**:
- 流式輸出問題：檢查 SSE 事件解析
- 拖放問題：檢查拖放事件處理
- 樣式問題：使用瀏覽器開發者工具檢查 Tailwind 是否正確編譯

### 重構優化

1. **保持向後兼容**: 除非明確要求破壞性變更
2. **漸進式改進**: 小步快跑，避免大規模重寫
3. **保留測試**: 確保現有功能不受影響

**前端優化指南**:
- 優先優化視覺深度和互動反饋（玻璃效果、陰影、動畫）
- 注重使用者體驗（載入狀態、錯誤提示、拖放反饋）
- 避免添加過多動畫導致性能下降

---

## 常見場景

### 添加新模型支持

1. 確認模型類型（文字 or 視覺）
2. 視覺模型：更新 `VISION_KEYWORDS`（若需要）
3. 測試 vLLM 是否支持該模型架構
4. 更新 `.env` 中的 `MODEL_NAME`

### 調整性能參數

- **記憶體不足**: 降低 `gpu_memory_utilization` 或 `max_num_seqs`
- **延遲過高**: 減少 `concurrency` 或增加 GPU 數量（`tensor_parallel_size`）
- **吞吐量低**: 啟用 `enable_prefix_caching`，調整 `max_num_batched_tokens`

### 擴展 API 功能

1. 在後端 `ModelClient` 類中添加方法
2. 同時提供同步與異步版本
3. 在 FastAPI 服務中暴露新端點
4. 在前端 `ChatBox` 中調用新端點

### 自定義基準測試

1. 繼承 `ShareGPTBenchmark` 或創建新類
2. 遵循 `TestResult` → `BenchmarkReport` 數據流
3. 實現 `_run_single_test()` 與 `_calculate_statistics()`

### 優化前端視覺效果

1. 查看 `tailwind.config.js` 中已有配色和動畫定義
2. 使用已有工具類（`.glass`, `.button-shine` 等）
3. 新增效果應遵循設計系統（紫色系、300-500ms 動畫）
4. 測試玻璃效果、陰影、光澤、發光等在各瀏覽器的表現

### 新增前端互動功能

1. 在相應組件中添加狀態管理
2. 添加使用者交互處理函數
3. 提供清晰的載入和錯誤反饋
4. 測試拖放、按鈕點擊、輸入等互動

---

## 重要提醒

### 必須遵守

- ✅ **最新方案**: 遇到錯誤先查最新文檔，不猜測過時方法
- ✅ **類型安全**: 所有函數參數與返回值必須有類型註解
- ✅ **錯誤處理**: 不捕獲過於寬泛的異常，提供具體錯誤訊息
- ✅ **資源清理**: 使用 context manager 或明確釋放資源
- ✅ **並行優化**: 獨立操作使用並行工具呼叫

### 絕不要做

- ❌ **不產生不必要的文檔**: 除非用戶明確要求總結
- ❌ **不使用過時 API**: vLLM/OpenAI SDK 更新快，避免使用已棄用方法
- ❌ **不硬編碼路徑**: 使用 `Settings` 管理所有配置
- ❌ **不忽略錯誤**: 即使是「不太重要」的警告也應處理
- ❌ **不破壞分層**: 例如 `benchmark/` 不應直接導入 `core/engine.py`

### 灰色地帶處理

- **需求模糊**: 向用戶詢問，或提供 2-3 個方案讓用戶選擇
- **技術選型**: 優先選擇與現有架構一致的方案
- **性能權衡**: 說明不同選項的利弊，由用戶決定

---

## 參考資源

- **vLLM 官方**: https://docs.vllm.ai/
- **OpenAI API**: https://platform.openai.com/docs/api-reference
- **Pydantic**: https://docs.pydantic.dev/latest/
- **專案文檔**: `/docs/` 目錄（架構分析、實現總結、使用指南）

---

## 版本資訊

- **vLLM**: 追蹤最新穩定版本
- **Python**: 3.10+
- **CUDA**: 13.0
- **Node.js**: 18+ (Web UI)
- **React**: 18.3+ (前端框架)
- **架構更新**: 2026-02-16

### 更新歷史

**v1.1 (2026-02-16)**: Web UI 完整上線
- ✅ FastAPI 後端服務層
- ✅ React 前端應用層
- ✅ 優雅夢幻動漫風格設計
- ✅ 流式輸出 (SSE)
- ✅ 拖放上傳功能
- ✅ 玻璃質感視覺效果
- ✅ 多層陰影與發光效果

**v1.0**: 後端核心完成
- ✅ vLLM 高併發推論
- ✅ OpenAI 兼容 API
- ✅ 視覺模型支持
- ✅ 異步基準測試
