# AI PVE 共用 Tools Library 詳細分析與實作計畫

## 0. 2026-07-31 實作狀態

已完成三個資料庫 seed templates 的共用 Tools Library：

- 新增 code-owned check registry、template profile、動態 `check_key` enum、compact prompt
  catalog 與共用 executor。
- 已實作 `system.disk_usage`、`service.process_search`、`n8n.port_5678`、
  `n8n.local_http`。
- Python profile 已實作 `python.version`、`python.environment`、
  `python.processes`、`python.listening_ports`。
- PostgreSQL profile 已實作 `postgresql.version`、`postgresql.readiness`、
  `postgresql.service_status`、`postgresql.port_5432`；全部是 credential-free
  health checks，不執行 SQL，也不讀取資料內容。
- `run_guest_check` 經既有 `pve_log.ssh_exec` transport 執行，不建立第二套 SSH client；
  VMID scope、SSH guard、timeout、redaction 與輸出截斷沿用既有實作。
- template path 的自由 `ssh_exec` 已一律改為人工確認，並移除已無 runtime 使用者的
  `command_policy.py` regex auto-run 路徑。
- `ai_pve_templates` schema 與 template chat request/response 均未修改，沒有 migration
  或 CRUD API。

本次刻意未做：

- 將既有 PVE `_TOOLS` 全部搬檔：本次只由 `pve_tools.definitions` 組合 template 的
  動態 tools，原 PVE Log tool schema 保持原位與原行為，降低第一個切片的回歸面。
- provider token 結論：目前只有 deterministic schema/round 測試，尚無 live provider
  usage，因此不能宣稱實際節省多少 token。

## 1. 決策摘要

建議建立共用 tools library，但不要把它做成「每個模板各自註冊一整套 OpenAI
function tools」，也不要把可執行 shell command 放進 `ai_pve_templates.system_prompt`。

採用三層設計：

1. **共用能力工具**：所有模板共用少量、穩定的 tool schema。
2. **受控檢查目錄**：由後端以 `check_key` 對應固定 command builder、參數 schema、
   風險等級與結果解析器。
3. **模板選擇與少量 extension**：模板只選擇適用的 `check_key`；只有無法合理表示成
   共用檢查、且確實需要獨立 transport、credential 或結構化結果的能力，才新增模板專屬
   tool。

建議第一版保留既有 PVE read tools，新增一個共用 `run_guest_check`，並保留
`ssh_exec` 作為需要人工確認的 escape hatch：

```text
PVE read tools
  get_resources / get_nodes / get_storage / get_resource_detail / get_cluster

Guest 共用工具
  run_guest_check(vmid, check_key, params)

例外工具
  ssh_exec(vmid, command, reason)
```

這個方向比「每模板一套 tools」更穩定，也比目前讓 AI 自由生成已知檢查指令更節省
tool schema 與重試成本。

## 2. 現況與真正問題

### 2.1 現行 runtime

目前 `AI_PVE_template` 已完成以下資料流：

```text
/api/v1/ai/pve-template/chat
  -> 依 template_key 讀取 ai_pve_templates
  -> 驗證指定 VMID 的資源權限
  -> base safety prompt + DB system_prompt
  -> app.ai.pve_log.chat 的共用 agent loop
  -> PVE tools 或 ssh_exec
```

`ai_pve_templates.system_prompt` 保存機器角色與診斷順序，不保存 command。已知唯讀
command 則分散在 `app.ai.pve_template.command_policy` 的字串與 regex 判斷中。

現有 `_TOOLS` 每一個 LLM tool round 都完整送出五個 PVE read tools 與 `ssh_exec`。
模板只能以自然語言告訴模型「應檢查什麼」，模型仍須自行生成 shell command。

### 2.2 目前風險

- 相同任務可能產生不同 command、flag、quoting 或 service 名稱，成功率不穩定。
- AI 可能先嘗試無效 command，再根據錯誤重試，增加 completion token 與遠端執行次數。
- `is_known_read_command()` 以完整 command 字串判斷是否可直接執行；只要模型換一種
  等價寫法，就會從 auto-run 退回人工確認。
- 若把 N8N、Python、PostgreSQL 全部做成獨立 function tools，tool schema 會隨模板數量
  增長，且 executor、policy、測試容易重複。
- 若把 command 放入 DB prompt，AI 仍可能改寫 command，而且 prompt 不能成為真正的
  authorization 或安全來源。

### 2.3 Token 的精確邊界

共用 library 能降低兩類浪費：

1. 避免每個模板都送出大量重複 tool schema。
2. 避免模型自由生成錯誤 command 後進行額外 tool round。

但它不會自動消除所有 token：

- tool schema 仍會在每次 `/chat/completions` tool round 傳入。
- 模板可用的 `check_key` 與簡短說明仍需讓模型知道。
- tool result 若過大，仍會消耗後續 context。

因此要同時控制 tool 數量、模板 catalog 長度、tool result 大小與 agent round 上限，
不能只把 Python 檔案命名為 `tools_library` 就視為完成最佳化。

## 3. 方案比較

| 方案 | 優點 | 問題 | 結論 |
| --- | --- | --- | --- |
| 每個模板一套 tools | 模型容易看出模板能力；單一 tool 語意明確 | schema 數量快速膨脹；重複 executor/policy/test；跨模板能力難重用 | 不採用 |
| 保持 `ssh_exec`，只強化 prompt | 修改最少；可執行任何工作 | command 仍由 AI 自由生成；等價字串導致 policy 不穩；重試與確認偏多 | 只保留為 fallback |
| DB 保存每個模板的 command | 可由資料調整；看似容易擴充 | DB command 成為高風險執行內容；版本、審查、測試與 rollback 困難；prompt 仍可能改寫 | 不採用 |
| 共用 capability tool + 受控 check registry | schema 穩定；command deterministic；容易測試、重用與量測 | 新增正式 check 需要程式碼與測試 | 採用 |

## 4. 建議架構

### 4.1 三種物件必須分開

#### Tool schema

這是模型可呼叫的穩定 API，例如 `run_guest_check`。它只描述輸入輸出，不保存具體
shell command。

#### Check definition

這是後端受控 registry 中的一個檢查項目，例如：

```text
key: system.disk_usage
label: 磁碟使用量
risk: read_only
parameter_schema: {}
command_builder: 建立固定 command
result_parser: 轉換 bounded structured result
```

Check definition 是可測試的後端程式碼，不是 system prompt 文字。

#### Template profile

模板 profile 只選擇適用的 check keys 與簡短使用提示：

```text
n8n:
  common:
    - system.disk_usage
    - system.listening_ports
    - service.process_search
    - service.recent_logs
  extension:
    - n8n.port_5678
    - n8n.local_http
```

模板不複製 common check，也不擁有 SSH transport。

### 4.2 建議模組邊界

```text
backend/app/ai/pve_tools/
  schemas.py          # Tool input/output 與 check metadata 型別
  definitions.py      # 穩定 OpenAI tool schemas
  registry.py         # check_key -> CheckDefinition
  executor.py         # 參數驗證、command build、policy、執行與 result parsing
  prompt_context.py   # 將允許的 check keys 組成精簡 AI context
  checks/
    common.py         # OS、disk、memory、port、process、service、log
    n8n.py            # 只保留 N8N 真正特殊的檢查
    python.py         # Python runtime/venv 等特殊檢查
    postgresql.py     # pg_isready、唯讀 health 等特殊檢查
```

`pve_tools` 是 AI tool contract 與 deterministic checks 的 owner。
`pve_log/chat.py` 保留 agent loop；`pve_log/ssh_exec.py` 保留 transport、VMIP/key 解析、
timeout、redaction 與 confirmation；`pve_template` 保留模板讀取與 prompt orchestration。

第一版不建立 plugin framework、動態 module loader 或通用 workflow DSL。registry 使用
明確 Python mapping 即可。

### 4.3 共用 `run_guest_check`

建議輸入：

```json
{
  "vmid": 102,
  "check_key": "n8n.local_http",
  "params": {}
}
```

建議回傳穩定結構：

```json
{
  "check_key": "n8n.local_http",
  "status": "passed",
  "summary": "localhost:5678 回傳 HTTP 200",
  "exit_code": 0,
  "data": {
    "http_status": 200
  },
  "stderr": "",
  "truncated": false
}
```

契約原則：

- 模型只能選 `check_key` 與通過 schema 的有限參數，不直接提供 command。
- executor 根據 registry 建立 command；模型不能覆寫 command、host、SSH user 或 key。
- `read_only` check 可在通過 VMID authorization、SSH guard 後直接執行。
- `mutating` check 即使存在 registry 也一律進入人工確認；第一版先不新增 mutating
  checks。
- 未註冊或不屬於目前模板 profile 的 `check_key` 直接拒絕，不退回猜測執行。
- 回傳以摘要與結構化欄位為主；raw stdout/stderr 維持 redaction 與長度上限。

### 4.4 `ssh_exec` 的定位

`ssh_exec` 不移除，但契約改為清楚的 fallback：

- registry 沒有適合 check，且任務確實需要 guest shell 時才使用。
- 所有自由生成 command 預設人工確認。
- hard deny、VMID scope、requester scope、timeout、redaction 永遠保留。
- 不因 command 看起來像既有 read check 就用 regex 自動放行；已知檢查應改呼叫
  `run_guest_check`。

完成 migration 後，`is_known_read_command()` 不再是主要 auto-run 判斷來源。auto-run
應依 registry 中的 immutable metadata 與實際 `check_key` 判定。

## 5. 模板與 Prompt 組裝

### 5.1 Source of truth

| 內容 | Source of truth | 是否可由 DB 覆寫 |
| --- | --- | --- |
| VMID authorization、SSH guard、confirmation | 後端 policy/executor | 否 |
| Tool schema | `pve_tools/definitions.py` | 否 |
| Check command、參數、risk、parser | `pve_tools/registry.py` 與 `checks/` | 否 |
| 共用 safety/tool 使用規則 | code-owned base prompt | 否 |
| 機器角色、診斷優先順序 | `ai_pve_templates.system_prompt` | 是 |
| 模板可用 check keys | 第一版 code-owned profile mapping | 否 |

第一版不修改 `ai_pve_templates` schema。直接以 `template_key` 查 code-owned profile，
避免立即新增 JSON 欄位、關聯表與管理 UI。

只有後續出現「管理者必須不部署程式就能調整模板 check 組合」的真實需求，才考慮新增
`tool_profile_key` 或獨立 profile tables。即使未來 DB 可選 check keys，DB 也只能引用
registry 已存在的 key，不能保存 command。

### 5.2 組裝順序

```text
immutable base safety prompt
  + request VMID scope
  + DB machine-role system_prompt
  + template profile 的 compact check catalog
  + fallback 規則
```

Compact catalog 只提供當次模板可用項目，例如：

```text
可用 guest checks：
- system.disk_usage：檢查檔案系統容量
- service.recent_logs：讀取指定服務的近期日誌
- n8n.port_5678：檢查 n8n 預設監聽 port
- n8n.local_http：檢查本機 n8n HTTP readiness

優先使用 run_guest_check；沒有適合 check 時才使用需要確認的 ssh_exec。
```

不要把完整 command、長篇範例或其他模板的 checks 注入 prompt。

### 5.3 動態 tool schema

第一版 `run_guest_check.check_key` 可依目前 template profile 產生有限 enum，讓模型只能
選當次允許的 keys。這不是「每模板一套 tools」；tool 名稱、參數 shape 與 executor
仍然共用，只是 enum 隨 profile 收斂。

需要注意：

- tool schema builder 必須 deterministic，同一 profile 產生相同排序。
- enum 與 prompt catalog 必須來自同一份 resolved profile，避免兩份清單漂移。
- 若模型/provider 對大型 enum 表現不佳，保留字串型 `check_key` 並完全依 server-side
  validation；不要同時維護兩套 registry。

## 6. 哪些能力應共用，哪些可專屬

### 6.1 應優先做成共用 checks

- OS/version
- CPU、memory、disk
- process 搜尋
- listening ports
- service status
- bounded recent logs
- localhost HTTP probe
- container listing
- runtime version

這些能力跨 N8N、Python、PostgreSQL 都可能使用，只應參數化或用小型 variant，不應
複製成三套 template tools。

### 6.2 可保留模板 extension checks

- `n8n.local_http`：固定處理 5678 與 N8N readiness 語意。
- `python.environment`：辨識 venv/uv/Poetry 與 interpreter boundary。
- `postgresql.readiness`：使用 `pg_isready` 並解析 database readiness。

它們仍透過同一個 `run_guest_check` 呼叫，只是 definition 位於各模板 extension module。

### 6.3 何時才新增真正的專屬 function tool

必須至少符合其中一項：

- 使用不同 transport，例如 N8N REST API，而不是 SSH command。
- 需要後端專屬 credential injection，且 credential 絕不能進入模型 context。
- 有獨立 authorization 或 confirmation policy。
- 需要複雜、穩定的 typed input/output，塞進 `params` 會變得含糊。
- 有狀態性操作或多步交易，無法安全表示成單一 deterministic check。

只是 command 不同、port 不同或 service 名稱不同，不足以成立新 tool。

## 7. 分階段實作計畫

### 階段 1：固定現有契約與量測基線

1. 盤點 `_TOOLS`、tool round 數量、現有 N8N/Python/PostgreSQL 測試任務。
2. 建立三類基線案例：已知唯讀檢查、未知唯讀指令、寫入/危險指令。
3. 記錄每案的 tool calls、confirmation 次數、LLM rounds、輸入 tool schema 字元數與
   是否一次成功。
4. 不以 token 估算取代 provider usage；若 vLLM 未回 usage，至少固定記錄 payload
   字元數與 round count。

完成條件：能比較改造前後的穩定性與 token proxy，而不是只憑感覺宣稱節省。

### 階段 2：抽出共用 tool contract，保持行為不變

1. 將 `_TOOLS` 從 `pve_log/chat.py` 移到 `pve_tools/definitions.py`。
2. 將 tool dispatch 抽到明確 executor 入口；PVE snapshot 與 SSH transport 不搬家。
3. `pve_log/chat.py` 改為接收 resolved tool definitions/executor，預設仍提供現有工具。
4. 保留現行 API response 與 `pve-log` 行為，先用 regression test 證明外部契約不變。

完成條件：既有 PVE Log 與 template focused tests 全部通過，tool payload 與結果 shape
沒有未預期變動。

### 階段 3：建立 check registry 與 `run_guest_check`

1. 定義 `CheckDefinition` 的最小欄位：`key`、`label`、`description`、`risk`、
   `parameter_model`、`command_builder`、`result_parser`。
2. 先遷移目前 `command_policy.py` 中已有測試的 common/N8N/Python/PostgreSQL read
   commands。
3. 新增 deterministic profile resolver：`template_key -> ordered check keys`。
4. 新增 `run_guest_check` schema、server-side allowlist validation 與 executor。
5. 共用現有 SSH guard、scope、timeout、redaction；不得建立第二套 SSH client。

完成條件：已註冊 read check 不需 AI 生成 shell 且可直接執行；未知 key、錯誤 params、
跨模板 key、越權 VMID 都在到達 SSH client 前被拒絕。

### 階段 4：Prompt 組裝與 fallback 收斂

1. `compose_system_prompt()` 加入由 resolved profile 生成的 compact check catalog。
2. 對 template chat 只送出 PVE tools、`run_guest_check` 與 fallback `ssh_exec`。
3. 更新 base prompt：已知檢查優先 `run_guest_check`；只有 catalog 無適合項目才用
   `ssh_exec`。
4. 移除 template path 對等價 command regex auto-run 的依賴；自由 command 全部走
   confirmation。
5. PVE Log 非 template path 是否採用 registry，等 template path 驗證成功後再決定，
   本階段不強制改變其既有行為。

完成條件：N8N 常見檢查穩定命中 check key；相同輸入不再因 shell 寫法不同改變
confirmation 結果。

### 階段 5：擴充與清理

1. 依實際 smoke 結果補 Python、PostgreSQL extension checks。
2. 只有符合第 6.3 節標準的能力才新增專屬 function tool。
3. 當所有既有 known-read cases 已遷移後，移除 template path 無用途的 regex 與過渡
   wrapper。
4. 更新原 AI PVE template 計畫中「所有 SSH command 都確認」等已過時描述，讓文件與
   runtime 一致。

完成條件：common checks 沒有複製；模板 extension 只保存差異；沒有同一 command 同時由
registry、prompt 範例與 regex 三處維護。

## 8. 驗證矩陣

### Registry 與 schema

- duplicate `check_key` 在啟動或測試時立即失敗。
- profile 引用不存在的 key 時立即失敗。
- 同一 profile 的 tool enum 與 prompt catalog 順序固定。
- `params` 缺欄位、多欄位、錯誤型別時不執行。
- template A 不能呼叫只屬於 template B 的 extension key。

### 執行與安全

- `read_only` registry check 通過授權與 guard 後直接執行。
- fallback `ssh_exec` 即使內容等價於 read check，仍要求確認。
- mutating/unknown/hard-deny 三類狀態不可混為一類。
- VMID、requester、scope、confirm token 與 TTL 維持現有驗證。
- command、credential、private key 不出現在 prompt、API response 或一般 log。
- stdout/stderr redaction、truncate、timeout、非零 exit code 都保留結構化狀態。

### AI 行為

- N8N port/readiness 任務選 `run_guest_check`，不自由生成 `ss`/`curl`。
- Python 環境辨識使用 profile 提供的 check keys。
- PostgreSQL readiness 不輸出 credential 或任意 SQL 結果。
- catalog 無適合 check 時，AI 才呼叫 `ssh_exec` 並提供具體 reason。
- tool result 回到 AI 後，回答依 exit code 與 structured data 判斷，不只看 stdout。

### 回歸與量測

- `backend/tests/test_ai_pve_template.py`
- `backend/tests/api/routes/test_ai_pve_log_session_forwarding.py`
- AI PVE SSH scope、IP resolution、host key 與 collector focused tests
- 比較改造前後：
  - tool schema payload 字元數
  - 平均 tool rounds
  - 自由 shell command 次數
  - confirmation 次數
  - 首次成功率

只有實際 provider usage 可用時才回報 token 數；否則明確標示為 payload/round proxy。

## 9. 資料庫與 API 影響

第一版：

- 不新增 migration。
- 不修改 `ai_pve_templates`。
- 不新增 check CRUD API。
- 不把 registry 暴露成任意 command 管理介面。
- `POST /ai/pve-template/chat` request/response 可保持不變。

若 UI 需要預覽模板能力，可在既有 template read response 後續加入只讀
`capabilities`/`check_keys`，但要先確認真實 UI 需求；本次不預先擴張 public API。

## 10. 主要風險與控制

- **Registry 變成另一個巨大 catalog**：只收高頻、穩定、可驗證檢查；低頻工作留給
  confirmable `ssh_exec`。
- **過度參數化**：`params` 僅容納安全且有明確 schema 的變化；開始出現互斥欄位或大量
  condition 時拆成另一個 check。
- **Tool 過度合併**：只合併相同 execution semantics；不同 credential、authorization
  或 transaction 不硬塞進 `run_guest_check`。
- **Prompt 與 registry 漂移**：prompt catalog 必須由 resolved registry 自動生成，
  不手寫第二份 check 列表。
- **誤稱節省 token**：保留基線與 usage/proxy 指標，只有量測後才下結論。
- **行為一次改太大**：先抽 contract，再加入 registry，最後才改 template routing；
  每階段維持 focused regression。

## 11. 最短可行切片

先只完成 N8N 的四個 deterministic checks：

1. `system.disk_usage`
2. `service.process_search`，參數限制為受控 service selector
3. `n8n.port_5678`
4. `n8n.local_http`

驗證同一批 N8N 任務在改造後：

- 不再由 AI 組出 `df`、`ps`、`ss`、`curl` command。
- 四個 read checks 不需人工確認。
- 未收錄的 N8N 工作仍能安全退回 `ssh_exec + confirmation`。
- tool result 能正常回到 AI 形成最終答案。
- schema payload、round count 與 confirmation 次數相較基線沒有惡化。

這個切片能直接驗證共用 library 的價值，同時不需要先建立資料表、管理 UI、plugin
framework 或把所有模板一次遷移。
