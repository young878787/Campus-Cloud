# AI Log Analytics Implementation Status

## 問題定義

這個服務要解決的核心問題不是單純「看 log」，而是：

- 從 Proxmox、操作紀錄、GPU、Token 等來源整理出可分析的運維訊號
- 把原始資料轉成 aggregation、feature、event
- 讓 AI 根據目前狀態、操作脈絡與建議候選，產出可讀的風險解釋
- 提供 dashboard 與 chat box，讓使用者直接查看分析結果與追問

## 目前已完成

### 基礎服務

- 已建立獨立服務 `ai-log-analytics`
- 已提供 FastAPI app、Swagger、靜態首頁
- 已支援 `python main.py` 與 `python app/main.py` 啟動

### 資料來源

- 已接 Proxmox 節點資料
- 已接 Proxmox VM/LXC 資源資料
- 已接 PostgreSQL `audit_logs` 查詢
- 已支援 `TOKEN_USAGE_SNAPSHOT_JSON`
- 已支援 `GPU_METRICS_SNAPSHOT_JSON`
- 已支援 `NODES_SNAPSHOT_JSON` 作為 fallback

### 分析流程

- 已有 source preview orchestration
- 已有 aggregation summary 計算
- 已有 feature 計算
- 已有 event generation
- 已有 recommendation generation
- 已有 rule-based summary
- 已加入 `AGGREGATION_STAIR_COEFFICIENT`

### AI 與介面

- 已提供 `GET /api/v1/analyze`
- 已提供 `GET /api/v1/sources/preview`
- 已提供 `POST /api/v1/explain`
- 已提供 `POST /api/v1/chat`
- 已接 vLLM 解釋層
- 已有 rule-based fallback，避免模型不可用時整體失效
- 已有 dashboard 與 chat box

## 目前分析得到的資訊

- 節點平均 CPU
- 節點平均記憶體
- 資源數量與執行狀態
- 高 CPU / 高記憶體風險
- VM/LXC 記憶體壓力與 OOM risk
- Token spike
- GPU idle waste
- Audit log 是否可用
- 根據事件整理出的建議與摘要

## 明確還沒做

### 歷史分析

- [ ] 還沒接 Proxmox RRD 歷史資料
- [ ] 還沒做真正的 7 天 baseline 比對
- [ ] 還沒做同類任務比較
- [ ] 還沒做趨勢預測或故障前兆分析

### 資料整合層

- [ ] 還沒把 raw metrics 寫入自己的時間序列表
- [ ] 還沒建立 `analytics_events` 之類的持久化事件表
- [ ] 還沒建立案例層 `case / insight`
- [ ] 還沒把分析結果持久化成 analysis record
- [ ] 還沒做排程 collector，現在多數是即時抓取或 env snapshot

### Audit Log

- [ ] 還沒確認所有環境都能穩定讀到 backend `audit_logs`
- [ ] 還沒處理 audit source 與 analytics 自身 DB 分離設定
- [ ] 還沒做 audit log 缺資料時的補償策略

### GPU / Token

- [ ] GPU 目前仍以 snapshot 為主，還沒接自動 collector
- [ ] Token 目前仍以 snapshot 為主，還沒從推論服務自動寫入
- [ ] 還沒把 GPU / Token 與 user、task、template 做完整關聯

### AI 解釋層

- [ ] 還沒做真正的案例檢索式解釋
- [ ] 還沒做長期記憶或歷史相似案例比對
- [ ] 還沒針對學生 / 老師 / 管理員做分角色 prompt 與輸出格式
- [ ] 還沒做 AI 回答持久化與可追蹤審計

### 前端

- [ ] 還沒做真正的 dashboard filter
- [ ] 還沒做 node / vm / user / 時間區間篩選
- [ ] 還沒做圖表型趨勢視覺化
- [ ] 還沒做 loading / error / empty state 的完整 UX
- [ ] 還沒做 chat 歷史保存

### 維運與部署

- [ ] 還沒建立資料表 migration
- [ ] 還沒做 DB auto-create
- [ ] 還沒補完整測試
- [ ] 還沒做 background job / scheduler
- [ ] 還沒做 production deployment 說明

## 目前已知限制

- 平均 CPU 目前是以節點 `cpu_ratio` 做直接平均，不是依 `maxcpu` 加權平均
- 當 `audit_logs` 不可用時，分析會退化成只看資源訊號
- Token 與 GPU 的資料品質目前取決於是否有提供 snapshot
- AI 解釋目前仍偏向「根據當下事件做說明」，不是完整預測型運維 AI

## 建議下一步

如果要把這個服務從 MVP 推到可實際使用，優先順序建議是：

1. 完成 audit log source 穩定接入
2. 補 RRD 歷史資料與 baseline 比對
3. 建立自己的 aggregation / event / case 持久化表
4. 把 GPU / Token 改成自動 collector
5. 再往上做案例檢索與更完整的 AI 解釋
