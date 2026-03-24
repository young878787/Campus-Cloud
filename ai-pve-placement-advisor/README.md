# PVE Placement Advisor

這是一個獨立的 FastAPI 服務，用於 Proxmox VE（PVE）資源配置建議。

主要目標：

- 讀取目前 PVE 節點與 VM/LXC 的資源狀態
- 提供節點容量與叢集健康度可視化
- 接收類似 backend VM/LXC 申請表的輸入規格
- 依據 CPU、記憶體、磁碟、Guest 密度、GPU 與使用者壓力進行配置判斷
- 輸出可解釋的分配原因與風險訊號

## 主要 API

- `GET /api/v1/analyze`
  - 回傳叢集摘要、節點容量、事件與建議
- `POST /api/v1/placement/recommend`
  - 輸入需求規格，回傳配置結果
- `GET /api/v1/sources/preview`
  - 預覽原始資料來源（Proxmox / snapshot / backend traffic）
- `GET /api/v1/metrics`
  - 回傳服務執行指標（請求數、錯誤數、平均延遲、來源失敗計數）

## Placement 輸入欄位

- `machine_name`
- `resource_type`
- `cores`
- `memory_mb`
- `disk_gb`
- `gpu_required`
- `instance_count`
- `estimated_users_per_instance`

## AI 分析根據與判斷方式

本服務的「AI 分析」是**規則 + 權重評分 + 可解釋輸出**，不是黑箱分類器。

### 1) 分析根據（資料來源）

1. **Proxmox 即時資料**
   - 節點：CPU、記憶體、磁碟、狀態、uptime、GPU 映射
   - 資源：VM/LXC 的狀態與資源占用
2. **Snapshot 後備資料**（Proxmox 失效時）
   - `NODES_SNAPSHOT_JSON`
   - `TOKEN_USAGE_SNAPSHOT_JSON`
   - `GPU_METRICS_SNAPSHOT_JSON`
3. **Backend 需求流量訊號（可選）**
   - 讀取 `vm-requests` 近期資料
   - 指標包含：近期新增申請、pending 數、核准數、申請資源總量

### 2) 核心判斷邏輯

1. **安全餘裕計算（Safe Headroom）**
   - 不直接用滿節點容量，而是先保留 `PLACEMENT_HEADROOM_RATIO`。
   - 可配置量 = 原始可用量 - 保留量。
2. **Running-only Guest 密度**
   - Guest 壓力僅計算 `running` VM/LXC，避免 `stopped` 造成誤判。
3. **使用者壓力修正**
   - 若有 `estimated_users_per_instance`，會用 `SAFE_USERS_PER_CPU`、`SAFE_USERS_PER_GIB` 推導更保守的有效 CPU / 記憶體需求。
4. **GPU 約束（硬條件）**
   - `gpu_required > 0` 時，僅選擇 `gpu_count >= gpu_required` 的節點。
5. **加權評分選點（Weighted Headroom Score）**
   - 候選節點先通過可放置檢查（CPU/記憶體/磁碟/GPU/Guest 上限）。
   - 再以加權分數排序：
     - `PLACEMENT_WEIGHT_CPU`
     - `PLACEMENT_WEIGHT_MEMORY`
     - `PLACEMENT_WEIGHT_DISK`
     - `PLACEMENT_WEIGHT_GUEST`
   - 分數越高，代表在放入需求後仍保有較佳安全餘裕。

### 3) 事件與建議輸出

- 事件（`events`）會標示風險類型與嚴重度，例如：
  - `high_cpu` / `high_memory` / `high_disk`
  - `guest_overload`
  - `partial_fit` / `placement_blocked`
  - `backend_pending_high`
- 建議（`recommendations`）會把判斷轉成可執行語句，說明：
  - 為何選某些節點
  - 為何跳過某些節點
  - 哪些需求造成目前無法完全配置

## 效能與可靠性設計

- 來源資料 TTL 快取：`SOURCE_CACHE_TTL_SECONDS`
- Proxmox / vLLM 重試與退避：`SOURCE_RETRY_ATTEMPTS`、`SOURCE_RETRY_BACKOFF_SECONDS`
- async 路由中的阻塞 I/O 轉 thread 執行（避免卡住 event loop）
- 內建輕量 metrics（請求量、錯誤率、延遲、來源失敗次數）

## Backend 流量串接（可選）

設定以下環境變數即可啟用：

- `BACKEND_API_BASE_URL`
- `BACKEND_API_TOKEN`
- `BACKEND_API_TIMEOUT`
- `BACKEND_TRAFFIC_WINDOW_MINUTES`
- `BACKEND_TRAFFIC_SAMPLE_LIMIT`
- `BACKEND_PENDING_HIGH_THRESHOLD`

啟用後，流量訊號會出現在 `analyze` / `sources/preview` 回應，並影響需求壓力相關建議。

## 快速啟動

```bash
cd ai-pve-placement-advisor
copy .env.example .env
pip install -r requirements.txt
python main.py
```

預設網址：

```text
http://localhost:8011
```

Swagger 文件：

```text
http://localhost:8011/docs
```

## UI

`static/index.html` 目前包含：

- placement 輸入表單
- 叢集摘要
- 節點容量卡片
- 推薦與未選節點原因
- 使用者壓力考量說明

## 命名說明

本服務原名為 `ai-log-analytics`，目前已更聚焦於 PVE 配置建議，因此改名為 `ai-pve-placement-advisor`。
