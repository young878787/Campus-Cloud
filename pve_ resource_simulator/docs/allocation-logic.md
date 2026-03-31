# PVE Resource Simulator Allocation Logic

## 目的

`pve_ resource_simulator` 用來模擬「如果現在要把一批 VM 放進叢集，系統大概會怎麼選 host」。

它不是在做理論上的全域最佳化，而是在做一個夠實用、夠容易理解、也夠接近真實 PVE 管理情境的 placement 模型。

這份文件分成兩層說明：

- 規則層：程式實際怎麼算
- 白話層：為什麼要這樣算

## 整體流程

每個小時的模擬大致分成這幾步：

1. 先找出這個時段有哪些 VM reservation 真的在啟用
2. 如果有歷史資料，就把 request 規格換成較接近真實使用量的 effective demand
3. 依序嘗試把 VM 放到最適合的 server
4. 如果沒有直接可放的 host，而且允許 rebalance，就嘗試做少量搬移
5. placement 完成後，再額外評估 peak risk

白話講：

- 不是只看表單寫幾顆 CPU、幾 GB RAM
- 也不是只看現在哪台最空
- 而是先估這台 VM「通常真的會吃多少」，再看「放上去之後哪台最不容易變糟」

## 歷史訊號

monthly analytics 會整理三類訊號：

- `average_*`: 整個月的加權平均
- `trend_*`: 最近一段時間的趨勢值，使用 EWMA
- `peak_*`: 高峰值，使用加權 P95

另外還有每小時的 `hourly[*]`：

- `hourly[*].cpu_ratio`
- `hourly[*].memory_ratio`
- `hourly[*].disk_ratio`
- `hourly[*].peak_cpu_ratio`
- `hourly[*].peak_memory_ratio`
- `hourly[*].peak_disk_ratio`
- `hourly[*].loadavg_1`

白話講：

- `average_*` 是「平常大概這樣」
- `trend_*` 是「最近有沒有變忙」
- `peak_*` 是「忙起來最容易衝到哪」
- `hourly[*]` 是「上午 9 點跟晚上 11 點，其實可能完全不是同一種負載」

## Effective Demand

### CPU / RAM baseline

如果某個 VM type 有對應的歷史 profile，系統不會直接拿 request 值去算，而是先估一個 baseline。

CPU：

```text
effective_cpu = min(requested_cpu, max(requested_cpu * cpu_ratio * 1.4, requested_cpu * 0.35))
```

RAM：

```text
effective_ram = min(requested_ram, max(requested_ram * memory_ratio * 1.15, requested_ram * 0.5))
```

目前 `cpu_ratio` / `memory_ratio` 的選法是：

```text
max(hourly_ratio, trend_ratio, average_ratio)
```

也就是：

- 優先吃到這個時段的歷史行為
- 同時考慮最近有沒有升溫
- 避免只看 average 對近期變化太遲鈍

白話講：

- 如果歷史上這類 VM 通常只吃 30% CPU，就不用每台都當成滿載去算
- 但也不能太樂觀，所以還是會乘上一點 margin
- 同時設 floor，避免把「很少用」誤判成「幾乎不用」

### Peak guard

placement 完之後，還會再估這台 VM 如果碰到高峰，大概會到哪裡。

CPU：

```text
peak_cpu = min(requested_cpu, max(requested_cpu * peak_cpu_ratio * 1.1, effective_cpu))
```

RAM：

```text
peak_ram = min(requested_ram, max(requested_ram * peak_memory_ratio * 1.05, effective_ram))
```

白話講：

- baseline 是拿來決定「平常放不放得下」
- peak guard 是拿來提醒「平常放得下，不代表尖峰也舒服」

### Disk / GPU

目前 disk 與 GPU 仍直接使用 request 值，不做歷史縮放。

白話講：

- CPU / RAM 比較像彈性使用量
- Disk / GPU 更像明確配額，所以先不要縮

## Hard Fit

一台 host 必須先通過 hard fit，才會進入 scoring。

條件如下：

- CPU 用 overcommit 後的 schedulable capacity 判斷
- RAM 用 safety buffer 後的 schedulable capacity 判斷
- Disk 不能超過實體剩餘
- GPU 不能超過實體剩餘

公式：

```text
cpu_schedulable_capacity = total_cpu * CPU_OVERCOMMIT_RATIO
memory_schedulable_capacity = total_memory * RAM_USABLE_RATIO
```

預設：

- `CPU_OVERCOMMIT_RATIO = 4.0`
- `RAM_USABLE_RATIO = 0.9`

白話講：

- CPU 允許超賣，因為大多數 VM 不會同時滿載
- RAM 比較保守，因為記憶體爆掉的代價比 CPU contention 更難受

## Placement Score

通過 hard fit 的 host，會再用 score 排序。分數越低越好。

排序核心：

1. `projected_dominant_share + resource_penalty + migration_cost`
2. projected average weighted share
3. projected physical CPU share
4. 目前已放 VM 數量
5. server name

### Weighted dominant share

先算放上去之後的各種 share：

- CPU share = `(used_cpu + vm_cpu) / cpu_schedulable_capacity`
- RAM share = `(used_memory + vm_memory) / memory_schedulable_capacity`
- Disk share = `(used_disk + vm_disk) / total_disk`
- GPU share = `(used_gpu + vm_gpu) / total_gpu`

再套權重：

- `CPU_SHARE_WEIGHT = 1.0`
- `MEMORY_SHARE_WEIGHT = 1.2`
- `DISK_SHARE_WEIGHT = 1.5`
- `GPU_SHARE_WEIGHT = 3.0`

最後取最大值：

```text
dominant_share = max(weighted_cpu, weighted_memory, weighted_disk, weighted_gpu)
```

白話講：

- 不是看平均空不空
- 是看「最痛的那個資源」痛到什麼程度
- 哪台放上去後最不容易出現單點瓶頸，就先選哪台

## Resource Penalty

### CPU contention penalty

CPU 另外會看實體核心壓力：

- `CPU_SAFE_SHARE = 0.7`
- `CPU_MAX_SHARE = 1.2`
- `CPU_CONTENTION_WEIGHT = 2.0`

意思是：

- 小於 `0.7` 幾乎不罰
- 大於 `1.2` 罰滿
- 中間線性增加

白話講：

- 即使 policy 上允許 CPU overcommit
- 也不代表實體 CPU 已經很擠時還要繼續無腦堆

### RAM overflow penalty

- `MEMORY_OVERFLOW_WEIGHT = 5.0`

如果 RAM policy share 超過 `1.0`，就直接給很重的 penalty。

白話講：

- CPU 擠一點，通常只是變慢
- RAM 爆掉，體感通常更差，所以這邊故意比較兇

### Disk contention penalty

- `DISK_SAFE_SHARE = 0.75`
- `DISK_MAX_SHARE = 0.95`
- `DISK_CONTENTION_WEIGHT = 1.5`

白話講：

- 磁碟快滿時，延遲和維運壓力都會上來
- 所以不是等到 100% 才覺得危險

### Loadavg soft penalty

loadavg 不做 hard reject，而是 soft penalty。

目前使用：

- `LOADAVG_WARN_PER_CORE = 0.8`
- `LOADAVG_MAX_PER_CORE = 1.5`
- `LOADAVG_PENALTY_WEIGHT = 0.9`

系統會先算：

```text
loadavg_per_core = max(current_loadavg_1, average_loadavg_1) / total_cpu
```

再把這個值轉成 penalty。

白話講：

- 某台 host 規格看起來夠，不代表它現在就適合再塞新東西
- loadavg 是在補足「當下這台真的很忙」這種 average 不一定看得出的情況
- 但它只是降權，不是一票否決

## Local Rebalance

如果沒有 host 能直接放下來，而且 `allow_rebalance = true`，系統會嘗試做少量搬移。

目前上限：

- `LOCAL_REBALANCE_MAX_MOVES = 2`
- `MIGRATION_COST = 0.15`

做法是：

1. 先找最值得搬的 VM
2. 找搬過去分數最好的目標 host
3. 看搬 1 台或 2 台後，是否能把新 VM 放進來

白話講：

- 這不是在做複雜的全域最佳化
- 只是想模擬管理者常做的那種「挪一兩台，就能把新申請塞進來」的操作

## Peak Risk

placement 完成後，每筆 calculation row 會再標記 peak risk：

- `safe`
- `guarded`
- `high`

判斷門檻：

- CPU warning/high: `0.7 / 1.2`
- RAM warning/high: `0.8 / 0.85`

白話講：

- 這不是 admission hard reject
- 是在提醒「平常 OK，但高峰時可能開始不舒服」

## 參數怎麼看

這些常數不要全部當成需要 AI 訓練的超參數。

比較好的分類方式是：

### 1. 幾乎固定的工程常數

這類先不要亂調：

- `EPSILON`
- `CPU_MARGIN`
- `RAM_MARGIN`
- `CPU_FLOOR_RATIO`
- `RAM_FLOOR_RATIO`
- `CPU_PEAK_MARGIN`
- `RAM_PEAK_MARGIN`
- `LOCAL_REBALANCE_MAX_MOVES`
- `MIGRATION_COST`

白話講：

- 這些比較像「模型骨架」
- 調了會影響整體邏輯風格，不是一般營運微調

### 2. 值得校準的 policy 參數

這類才值得之後慢慢調：

- `CPU_OVERCOMMIT_RATIO`
- `RAM_USABLE_RATIO`
- `CPU_SAFE_SHARE`
- `CPU_MAX_SHARE`
- `DISK_SAFE_SHARE`
- `DISK_MAX_SHARE`
- `LOADAVG_WARN_PER_CORE`
- `LOADAVG_PENALTY_WEIGHT`
- `CPU_SHARE_WEIGHT`
- `MEMORY_SHARE_WEIGHT`
- `DISK_SHARE_WEIGHT`
- `GPU_SHARE_WEIGHT`

白話講：

- 這些比較像營運 policy
- 學校環境、host 等級、使用習慣不同，合理值也可能不同

## 要不要用 AI 訓練這些參數

目前不建議直接用 AI 去「訓練」這些常數。

原因很簡單：

- 這些大多是 rule-based policy，不是語言模型擅長直接學的東西
- 如果沒有明確標註目標，例如「placement 後是否卡頓」、「是否爆 RAM」、「是否使用者抱怨」，模型其實不知道該往哪裡調
- 太早讓 AI 直接優化，很容易只是 overfit 模擬器

比較務實的做法是：

1. 先把高影響參數做成 config
2. 收集真實營運資料
3. 用 replay 或 simulator 做離線評估
4. 再用 grid search 或 Bayesian optimization 微調少數 policy 參數

白話講：

- 先別急著讓 AI 幫你調數字
- 先知道哪些數字真的會影響結果
- 等有真實資料，再去校準，會比現在直接訓練更可靠

## 總結

這套 simulator 的核心精神是：

- CPU 可以超賣，但不能假裝實體壓力不存在
- RAM 要保守，避免 placement 看起來成功、實際體感很差
- average、trend、peak 要一起看，不能只看單一指標
- loadavg 用來補足「這台 host 現在其實很忙」的現場資訊
- rebalance 只做小範圍，追求實用而不是數學上的最優解

一句話版：

「先用歷史資料把 request 變得比較像真實需求，再挑那台放上去後最不容易變成瓶頸的 host；如果 host 當下很忙，就降權，但不急著直接拒絕。」
