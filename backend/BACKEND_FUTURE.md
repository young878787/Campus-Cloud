# Backend 未來方向與維護注意事項

這份文件的目的不是描述「現在有哪些功能」，而是說明：

- 目前後端架構已經收斂到什麼程度
- 接下來應該優先處理哪些方向
- 未來新增功能時，哪些邊界不要再打破
- 哪些技術債可以接受，哪些不應再繼續累積

---

## 1. 目前架構定位

目前後端已經從早期的平鋪式 service 結構，整理成較清楚的分層：

- `api/`
  - HTTP / WebSocket 入口
- `core/`
  - 設定、權限、security、db session、例外等基礎能力
- `domain/`
  - 純規則與協調模型
- `services/`
  - 應用協調層，串接 domain / repository / infrastructure
- `repositories/`
  - DB 存取
- `infrastructure/`
  - Proxmox / Redis / SSH / worker / 外部 AI client 等外部系統 adapter

這個方向是正確的，之後不要再退回「把規則、外部呼叫、HTTP 邏輯都塞回 service」的做法。

---

## 2. 未來架構主軸

未來應維持以下原則：

### 2.1 API 只做入口，不做業務判斷

`api/routes/*` 和 `api/websocket/*` 應只負責：

- 驗證輸入
- 取得當前使用者 / session
- 呼叫 service
- 回傳 response

不要在 route 內加入大量：

- 排程判斷
- placement/migration 規則
- Proxmox 流程控制
- 跨資源授權判斷細節

這些應該留在 `services/` 或 `core/authorizers.py`。

### 2.2 Domain 保持純規則

`domain/placement`、`domain/migration`、`domain/scheduling` 的設計目標應是：

- 不依賴 FastAPI
- 不依賴 route schema
- 不直接操作 Proxmox client
- 不直接操作 DB session

如果某段邏輯未來可能需要：

- 單元測試
- 替換演算法
- 比較不同策略
- 在 CLI / worker / API 共用

那就應該優先放入 `domain/`。

### 2.3 Services 只做協調，不做「巨型上帝物件」

`services/` 的責任是流程協調，不應繼續膨脹成千行單檔。

目前已經開始拆：

- `services/scheduling/coordinator.py`
- `services/vm/placement_service.py`

未來延續這個方向：

- 主檔保留公開入口
- 大量 helper 下沉到 support / runtime / policy / solver / task module

### 2.4 Infrastructure 必須是外部依賴 owner

凡是涉及以下內容，應優先放進 `infrastructure/`：

- Proxmox API
- Redis
- SSH / Paramiko
- worker backend
- 外部 AI / LLM HTTP client

不要再把：

- 連線建立
- 重試策略
- sleep 輪詢
- 外部 API payload 細節

混回 route 或 service。

---

## 3. 未來最重要的技術方向

## 3.1 正式推動 async 化

目前 async 化只完成第一輪止血：

- WebSocket 熱點已避免直接阻塞 event loop
- Google 外部驗證已 async
- Proxmox task wait 已有 async wrapper

但整體仍然是 sync-first。

### 下一步建議順序

1. 導入 `AsyncSession`
2. 補 `core/db_async.py`
3. 新增 async repository 熱點
4. 先讓 scheduler / websocket / 外部整合優先使用 async
5. 最後才考慮一般 CRUD 是否需要全面 async

### 優先 async 化的區域

- scheduler
- websocket
- proxmox polling / 長任務等待
- 外部 HTTP client
- 高 I/O repository 查詢

### 暫時可接受的過渡手法

- `asyncio.to_thread(...)`

這不是最終型，但在全面導入 `AsyncSession` 前，是可接受的中繼方案。

---

## 3.2 權限控制要繼續集中，不要回到散落式 `if`

目前權限已開始收斂到：

- `core/permissions.py`
- `core/authorizers.py`

未來原則：

- route 不直接散寫 `is_admin()` / `is_teacher()` / `has_permission()`
- service 不直接複製 ownership 判斷
- WebSocket 權限要與 HTTP 共用同一套 authorizer/policy

新增功能時，先問：

- 這是新的 permission rule 嗎？
- 這是 ownership rule 嗎？
- 這是否應該進 authorizer，而不是在 route/service 多寫一次？

如果答案是「會重複使用」，就應抽進 authorizer。

---

## 3.3 Scheduler 與 placement 要持續拆小

目前最大的複雜度來源仍是：

- `services/scheduling/coordinator.py`
- `services/vm/placement_service.py`

後續建議進一步拆：

### scheduling

- `runtime.py`
- `migration_jobs.py`
- `reconcile.py`
- `stop_tasks.py`
- `start_tasks.py`

### placement

- `plan_builder.py`
- `reservation_solver.py`
- `rebalance_solver.py`
- `preview.py`
- `storage_selection.py`

拆分原則：

- 不改既有 service 公開函式名
- 先抽 helper，再決定是否移動 owner
- 先保留 facade，再逐步調整測試匯入

---

## 3.4 舊相容層最終要退役

目前為了降低風險，仍保留一些相容層，例如：

- `domain/pve_*` 與 `domain/{placement,migration,scheduling}` 並存
- `services/ai` / `services/infra` 這類兼容 package

這是合理的過渡，但不應永久保留。

### 退役順序建議

1. 新程式碼只使用新路徑
2. 測試全部改到新 owner
3. `rg` 確認 repo 內沒有實際使用舊路徑
4. 再刪除舊 package

避免直接刪 compatibility 層，否則容易讓 monkeypatch、測試與隱性 import 一次爆掉。

---

## 4. 未來新增功能時的規則

新增功能請先判斷它屬於哪一層：

### 如果是業務規則

放 `domain/`

例子：

- placement 評分規則
- migration eligibility
- scheduling window 決策
- quota / balance policy

### 如果是流程協調

放 `services/`

例子：

- 接到 VM request 後的 provision 流程
- 審核後重建 reservation
- active request 的 runtime reconcile

### 如果是外部系統對接

放 `infrastructure/`

例子：

- PVE API 呼叫
- Redis cache / rate limit
- SSH 執行指令
- 外部 AI inference gateway

### 如果只是 request/response DTO

放 `schemas/`

不要把 schema 誤當成 domain model。

---

## 5. 測試策略未來要補強的地方

目前已有關鍵 workflow regression 與權限測試，但仍有幾個缺口：

- scheduler integration 測試覆蓋率仍不夠
- websocket 路徑缺少完整行為測試
- async 路徑需要新增對應測試
- infrastructure adapter 缺少更細的 isolation test

### 建議補的測試類型

1. `domain` 單元測試
2. `services` workflow regression
3. `api` contract 測試
4. `infrastructure` adapter mock test
5. scheduler / migration queue 狀態機測試

未來每次重構前，應先補足該區域最少一條 regression 測試，再動手。

---

## 6. 目前仍存在的風險

這些不是立即阻塞，但要持續注意：

### 6.1 sync DB 仍是最大限制

即使外部 I/O 開始 async 化，只要 DB 還是 sync-first：

- scheduler 吞吐仍有限
- websocket 在高併發時仍可能受限
- 背景任務會持續依賴 thread offload

### 6.2 核心 service 仍偏大

雖然已拆出 support module，但主檔仍不算小。  
之後如果再繼續把新邏輯塞進主檔，會很快重新膨脹。

### 6.3 舊新命名並存是過渡，不是完成

`domain/pve_*` 與 `domain/*` 並存是目前刻意保守的做法。  
若長期不清理，會造成新的閱讀成本。

---

## 7. 建議的下一階段路線

### Phase 1：穩定化

- 繼續補 scheduler / placement regression
- 讓新程式碼只引用新 `domain/*`
- 減少相容層新使用者

### Phase 2：async 深化

- 導入 `AsyncSession`
- 補 async repository
- 改善長時間 Proxmox / resource polling

### Phase 3：相容層退役

- 移除 `domain/pve_*`
- 移除不再需要的 package shim
- 清理舊 import 與 monkeypatch 路徑

### Phase 4：精修

- 再做 package 命名與文件整理
- 視需要補 `features/` 邊界，或反過來繼續簡化

---

## 8. 維護者簡短原則

後續維護時，請盡量遵守：

1. 不要把外部連線細節寫回 service
2. 不要把業務規則寫回 route
3. 不要在多個地方複製權限判斷
4. 不要讓單一 service 再次長成上帝物件
5. 新增 async 時，先處理高 I/O 熱點，不要一次全 async 化
6. 重構優先保留 facade，相容層最後再刪

---

## 9. 結論

目前 backend 架構已經進入可持續演進的狀態。  
接下來真正重要的，不是再做一次大搬家，而是：

- 穩定新邊界
- 把 async 做深
- 繼續拆大模組
- 最後才退役舊相容層

只要持續守住 `api / domain / services / infrastructure` 這四條邊界，後續不論是排程、遷移、Proxmox 擴充、外部 AI 整合，成本都會明顯低很多。
