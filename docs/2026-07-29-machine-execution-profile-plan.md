# 機器執行環境手冊與 Template Command 資料表收斂計畫

## 1. 目標

將目前散落在 AI prompt、`Resource.os_info`、Teacher Judge template command catalog 與機器模板名稱中的環境資訊，收斂為一套簡單、可確認、可重用的資料庫契約。

本次目標不是讓 AI 自行辨識完整作業系統，也不是建立知識庫或自動化編排平台，而是：

1. 在資料庫保存一份簡短的「機器執行環境手冊」。
2. 明確記錄系統名稱、版本與基本操作方向。
3. 保存經管理者確認、可由系統引用的 template commands。
4. 讓 `pve_log`、`teacher_judge`、VM template 與後續 n8n template 共用同一份資料。
5. AI 只接收產生指令所需的少量資料，不直接讀取完整資料表或敏感內容。

## 2. 現況與問題

### 2.1 `pve_log`

`backend/app/ai/pve_log/chat.py` 使用固定 `_SYSTEM_PROMPT`，AI 知道可以透過 `ssh_exec` 進入 VM/LXC，但不知道目標機器的確切系統版本與建議指令。

資料庫現有 `resources` 已包含：

- `vmid`
- `environment_type`
- `os_info`
- `template_id`
- `service_template_slug`

但目前 SSH 執行路徑只取 IP 與 SSH key，沒有把已確認的系統操作資料提供給 AI。

### 2.2 `teacher_judge`

目前已有 `teacher_judge_template_commands`：

- `template_key`
- `command_key`
- `command_label`
- `category`
- `command_template`
- `description`
- `risk_level`
- `requires_confirmation`
- `enabled`

`backend/app/ai/teacher_judge/template_command_service.py` 也已支援：

```python
SUPPORTED_TEMPLATE_KEYS = {"linux", "python", "n8n"}
```

因此 n8n 並不是全新方向；現有資料模型已經有雛形。問題是表名與 service 都綁定 Teacher Judge，其他模組若要使用，容易再建立重複資料表或相容包裝。

### 2.3 VM template 與 Resource

`vm_templates` 表示 PVE 上的可克隆模板，`resources` 表示已建立的 VM/LXC。這兩張表負責機器生命週期，不應同時承擔完整指令 catalog。

現有 `Resource.os_info` 是自由文字，只適合顯示或舊資料相容，不適合作為唯一的 template command 關聯鍵。

## 3. 核心設計決策

### 3.1 使用「執行環境設定檔」作為共用邊界

新增共用概念 `ExecutionProfile`，代表一種已確認的執行環境，例如：

- `linux-debian-12`
- `ubuntu-22.04`
- `python-3.12`
- `n8n-1.x`

它不是實際 VM，也不是 PVE template；它只保存系統基本事實、簡短手冊與可引用指令。

### 3.2 手冊保持短小、人工確認

手冊只回答 AI 或 automation 執行前真正需要知道的事情：

- 這是什麼系統。
- 目前確認的版本。
- 預設 shell。
- 基本服務管理方向。
- 必要注意事項。

不保存：

- 套件百科或完整官方文件。
- 動態 CPU、RAM、IP、執行狀態。
- SSH key、密碼、token、環境變數。
- AI 推論出的猜測。
- 大量 prompt 文字或對話紀錄。

### 3.3 指令與手冊分表

一個 profile 對應多個 commands。不可把手冊文字重複存進每個 command，也不可為 `pve_log`、Teacher Judge、n8n 分別建立同內容的 command 表。

### 3.4 AI 不是資料來源

系統名稱、版本與 template command 均由管理者或模板建立流程寫入資料庫。AI 只負責根據已確認資料選擇指令或產生受控腳本。

資料不足時只提供：

```text
目前沒有已確認的系統手冊，請先使用通用唯讀查詢，或由管理者補齊模板設定。
```

不得要求 AI 猜測作業系統版本。

## 4. 收斂後資料模型

### 4.1 `execution_profiles`

保存一份簡短的系統手冊。

| 欄位 | 型別 | 用途 |
| --- | --- | --- |
| `id` | UUID PK | 內部識別 |
| `profile_key` | varchar(100), unique | 穩定引用鍵，例如 `n8n-1.x` |
| `display_name` | varchar(150) | 管理介面顯示名稱 |
| `system_name` | varchar(100) | Debian、Ubuntu、Python、n8n |
| `system_version` | varchar(50), nullable | 已確認版本；不確定時保持 null |
| `manual` | text | 簡短操作手冊，建議限制長度 |
| `enabled` | boolean | 是否可被新流程選用 |
| `created_at` | timestamptz | 建立時間 |
| `updated_at` | timestamptz | 更新時間 |

建議約束：

- `profile_key` 不隨顯示名稱變更。
- `system_version` 只存已確認值，不存 `latest`。
- `manual` 建議在 API 層限制為 2,000 字元。
- 第一版不加入 JSON metadata、標籤系統、版本歷史或 prompt override。

範例：

```json
{
  "profile_key": "n8n-1.x",
  "display_name": "n8n 1.x",
  "system_name": "n8n",
  "system_version": "1.x",
  "manual": "n8n 以 systemd service 運行。狀態檢查優先使用 systemctl status n8n；HTTP 健康檢查使用 localhost 服務端點。不要直接修改 workflow database。"
}
```

### 4.2 `execution_profile_commands`

由現有 `teacher_judge_template_commands` 收斂而來。

| 欄位 | 型別 | 用途 |
| --- | --- | --- |
| `id` | UUID PK | 內部識別 |
| `profile_id` | UUID FK | 對應 `execution_profiles.id` |
| `command_key` | varchar(100) | profile 內穩定 command ID |
| `command_label` | varchar(100) | 顯示名稱 |
| `category` | varchar(50) | service、port、process、http 等 |
| `command_template` | text | 實際模板指令 |
| `description` | text | 指令用途 |
| `risk_level` | varchar(30) | 第一版沿用 `read_only` 等既有值 |
| `requires_confirmation` | boolean | 執行前是否確認 |
| `enabled` | boolean | 是否可用 |
| `created_at` | timestamptz | 建立時間 |
| `updated_at` | timestamptz | 更新時間 |

唯一約束：

```text
UNIQUE(profile_id, command_key)
```

第一版不增加 `consumer_type`、`ai_enabled`、`n8n_enabled` 等欄位。同一條 command 是否適用，由 profile 與呼叫端安全規則決定，避免快速膨脹成多組旗標。

### 4.3 機器與 profile 的關聯

在 `vm_templates` 增加：

```text
execution_profile_id UUID NULL
```

用途是指定從此 VM template 建立的機器應使用哪份系統手冊。

在 `resources` 增加：

```text
execution_profile_id UUID NULL
```

建立資源時從 VM template 複製 profile 關聯。這是必要的執行快照：

- VM template 後續被停用或替換時，既有 Resource 仍知道應使用哪個 profile。
- `pve_log` 可由 VMID 直接取得 profile，不必反查不穩定的 template 名稱。
- n8n、快速模板或其他部署流程也能在建立 Resource 時明確指定 profile。

`Resource.os_info` 第一階段保留作顯示與舊資料 fallback，但新流程不再以自由文字作為 command catalog 主鍵。

## 5. 共用讀取服務

新增非 AI 專用 service：

```text
backend/app/services/execution_profile_service.py
```

主要介面：

```python
def get_resource_execution_profile(
    session: Session,
    vmid: int,
) -> ExecutionProfileContext | None:
    ...

def get_enabled_profile_commands(
    session: Session,
    profile_id: UUID,
) -> list[ExecutionProfileCommand]:
    ...
```

回傳給 AI 的 context 必須是白名單 DTO，不回傳 ORM model：

```python
class ExecutionProfileContext(BaseModel):
    profile_key: str
    system_name: str
    system_version: str | None
    manual: str
```

commands 依場景另外取得，避免每次對話都把所有 raw commands 塞入 prompt。

## 6. 各模組使用方式

### 6.1 `pve_log`

當 AI 已知目標 VMID 且準備產生 SSH 指令時：

1. route/service 先驗證使用者可操作該 VMID。
2. 由 `resources.execution_profile_id` 取得 profile。
3. 將簡短 context 加入本次 LLM request。
4. AI 根據手冊與可用 commands 選擇方向。
5. 後端仍執行 command policy 與使用者確認。

注入內容保持簡單：

```text
目標機器已確認資料：
- 系統：n8n
- 版本：1.x
- 簡要手冊：n8n 以 systemd service 運行；狀態檢查優先使用 systemctl status n8n。

以上內容只提供指令方向，不代表可以略過權限、安全檢查或執行確認。
```

不需要向 AI 提供：

- profile UUID。
- VM template UUID。
- 建立或更新時間。
- enabled 狀態。
- SSH key 與加密欄位。
- 完整 Resource row。
- 與本次操作無關的 command catalog。

### 6.2 `teacher_judge`

將 `template_key` 的查詢改由 execution profile service 處理：

```text
template_key
  → execution_profiles.profile_key
  → execution_profile_commands
```

Teacher Judge 仍只讓 LLM 輸出 `command_key`，不把 raw shell command 暴露在 rubric 分析 prompt。建立 managed script 時，後端再依 `command_key` 解析實際 command template。

既有 policy validator、quality validator、AI reviewer 與人工核准流程保持不變。

### 6.3 VM template

建立或編輯 VM template 時選擇一個 execution profile。建立 Resource 時，把關聯寫入 `resources.execution_profile_id`。

第一版不要求系統自動掃描 VM 判斷 profile；由模板管理者選擇即可。

### 6.4 n8n template

n8n 可作為一個 execution profile：

```text
profile_key = n8n-1.x
system_name = n8n
```

其 commands 可包含：

- 查詢 n8n service 狀態。
- 查詢 n8n process。
- 查詢 localhost HTTP endpoint。
- 查詢指定 port。
- 讀取非敏感版本資訊。

未來若 n8n workflow 需要執行機器操作，workflow 只保存或傳遞：

```json
{
  "vmid": 123,
  "profile_key": "n8n-1.x",
  "command_key": "service.status"
}
```

真正的 `command_template` 由後端根據 DB 解析、驗證與執行。不要把任意 shell command 直接交給 n8n，也不要讓 n8n 成為另一份 command source of truth。

## 7. 資料表遷移與收斂

採單次正式遷移，不長期保留兩套 model/service。

### 階段一：建立新表與搬移資料

1. 建立 `execution_profiles`。
2. 建立 `execution_profile_commands`。
3. 依現有 `template_key` 建立 `linux`、`python`、`n8n` profiles。
4. 將 `teacher_judge_template_commands` 搬移至對應 profile。
5. 驗證每個舊 `(template_key, command_key)` 都有唯一新資料。

### 階段二：切換讀取端

1. 新增共用 `execution_profile_service.py`。
2. `teacher_judge` 改用共用 service。
3. `pve_log` 改由 VMID 取得 profile context。
4. VM template／Resource 建立流程寫入 `execution_profile_id`。

### 階段三：移除舊結構

確認所有呼叫端與測試均已切換後：

1. 移除 `TeacherJudgeTemplateCommand` model。
2. 移除 `teacher_judge/template_command_service.py`，不保留一行轉呼叫 wrapper。
3. 刪除 `teacher_judge_template_commands` 舊表。
4. 將 Teacher Judge 中仍使用的 `template_key` 語意明確收斂為 `profile_key`；API 若需同版本完成切換，直接更新契約與前端，不永久保留兩個同義欄位。

若現有 production 資料尚無法一次切換，過渡期只允許 migration 內部資料搬移，不建立雙寫。

## 8. 安全邊界

系統手冊與正確版本只能改善指令方向，不能取代執行安全：

- VMID 必須先通過群組／資源權限驗證。
- AI、Teacher Judge 與 n8n 都不得直接取得 SSH private key。
- `command_key` 必須存在、enabled 且屬於該 profile。
- 執行時依 `risk_level` 決定拒絕或要求確認。
- 使用者覆寫 command 時必須重新執行安全檢查。
- profile manual 視為管理者資料，不允許一般使用者直接寫入。
- 不將 stdout 中的秘密、token 或完整環境變數傳回 AI。

其中 `pve_log /ssh/exec` 與 `/ssh/confirm` 的 VMID 授權必須在導入 profile 時一併補齊，不能只依賴 prompt 內的群組限制。

## 9. API 與管理介面範圍

第一版只需要基本 CRUD：

```text
GET    /api/v1/execution-profiles
POST   /api/v1/execution-profiles
PATCH  /api/v1/execution-profiles/{id}
GET    /api/v1/execution-profiles/{id}/commands
POST   /api/v1/execution-profiles/{id}/commands
PATCH  /api/v1/execution-profiles/{id}/commands/{command_id}
```

管理權限沿用系統管理員／模板管理權限。第一版不做：

- profile import/export。
- n8n workflow 編輯器。
- AI 自動產生並直接發布 commands。
- profile 版本歷史。
- command 執行歷史新表。
- 自動偵測 OS 並改寫 DB。

## 10. 實作順序

1. 新增 `ExecutionProfile`、`ExecutionProfileCommand` model 與 Alembic migration，搬移既有 Teacher Judge commands。
2. 新增共用 service 與白名單 DTO，完成 profile／command 查詢及管理 API。
3. 將 `teacher_judge` 切換至共用 profile service，維持既有 `command_key` 驗證與 managed script 安全流程。
4. 在 VM template 與 Resource 建立流程加入 `execution_profile_id`，並為既有資料做可確認的 backfill。
5. 在 `pve_log` 依 VMID 注入簡短系統手冊與相關 commands，同時補齊 SSH route 的資源授權。
6. 加入 n8n profile fixture，驗證 Teacher Judge、AI SSH 與未來 automation 都能解析同一 command。
7. 移除舊 Teacher Judge 專用 model、service 與資料表。

## 11. 驗證

### 資料遷移

- 舊資料筆數與新 command 筆數一致。
- 每個舊 `(template_key, command_key)` 可解析到唯一 `(profile_id, command_key)`。
- migration downgrade 或明確回退步驟可恢復舊資料。
- 無孤兒 command。

### 共用 service

- disabled profile 不提供給新操作使用。
- disabled command 不會出現在 AI、Teacher Judge 或 n8n 查詢結果。
- 不存在的 VMID、profile 或 command 回傳明確錯誤。
- 回傳 AI 的 DTO 不含 ORM 額外欄位與敏感資訊。

### `pve_log`

- Ubuntu、Debian、n8n 與無 profile 資源各有一個 focused test。
- vLLM request 只包含系統名稱、版本、manual 與必要 commands。
- 未授權 VMID 即使提供有效 command key 也不能執行。
- command 仍須通過既有 guard／確認流程。

### `teacher_judge`

- rubric 分析仍只引用 `command_key`，不暴露 raw command。
- managed script generation 能由新表解析 command。
- policy、quality、AI reviewer 與人工核准測試維持通過。
- `n8n` profile 能產生 service、port 或 localhost HTTP 的唯讀檢查腳本。

## 12. 完成判準

符合以下條件才算完成：

1. 系統手冊只有一個資料來源：`execution_profiles`。
2. template commands 只有一個資料來源：`execution_profile_commands`。
3. Teacher Judge 不再擁有專用 command model 或專用資料表。
4. `pve_log` 能依 VMID 取得正確 profile，但只把必要資料交給 AI。
5. VM template 與 Resource 能明確關聯 profile。
6. n8n 能以 `profile_key + command_key` 使用同一套資料，不保存第二份 shell command。
7. 權限、risk level 與確認仍由後端強制執行，不能被 prompt 或 workflow 繞過。

