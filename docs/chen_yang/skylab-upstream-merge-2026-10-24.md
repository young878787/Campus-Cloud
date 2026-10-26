# Campus-Cloud 合併 SkyLab main 分析與驗證

日期：2026-10-24（Asia/Taipei）。分析對象固定為下列 commit；不是對未來上游版本的保證。

## 合併範圍

| 項目 | 固定版本／結果 |
| --- | --- |
| 本地儲存庫 | `young878787/Campus-Cloud` |
| 原本 main | `f826c912f9937860da97663761af0aef721e38da` |
| 上游來源 | <https://github.com/ntubclass/SkyLab>，預設分支 `main` |
| 上游版本 | `e627f3e1e484d79f5c75aeadf6e9867a2868b783`（合併 PR #415） |
| 共同祖先 | `8f64c81d6695ed3b054d0a8e01c49de276f930e3` |
| 雙方獨有提交數 | 本地 5、上游 78（包含 merge commits；不代表 83 個獨立功能） |
| 上游相對共同祖先 | 1,528 個檔案，+64,388／−24,319 行，包含大量文件及圖片 |
| 整合分支 | `codex/merge-skylab-20261024`；驗證完成後本地 `main` 快轉至同一 merge commit |
| 方法 | 以保留雙方歷史的 merge 整合，逐項解決衝突並執行測試 |

兩個儲存庫有共同歷史，無須使用 `--allow-unrelated-histories`，也不需要把整份 SkyLab 複製進另一層目錄。原本工作目錄沒有未提交修改。處理期間另外出現的 `SkyLab_PR415_Code_Review_2026-10-24.md` 不屬於本次產出，保留為未追蹤檔，不納入本次提交。

## 上游更新的實際影響

| 區域 | 更新 | 合併時的判斷 |
| --- | --- | --- |
| 前端讀取 | TanStack Query、React Compiler、TanStack Virtual | 不只增加套件；資料讀取、背景刷新、快取與失效時序也改變，採用上游對應測試與 hook |
| 表格 | TanStack Table v9 | 保留新欄位及元件結構，避免把舊 JSX 局部貼回造成狀態不一致 |
| AI 導師檢查 | 批次續跑、逾時恢復與新查詢層整合 | 本地相關後端實作已被上游納入；合併後這些後端檔案與上游一致 |
| 使用者／課程 | 管理員維護群組；老師可匯入群組學生 | 新增 API、模型、稽核與 migration；群組匯入是當下名單複製，後續群組異動不自動改課程名單 |
| 容量與佈建 | 已分配規格計算、跨節點放置、記憶體超賣倍率、CPU 預設倍率調整 | 涉及排程與容量判斷，不能僅以畫面成功建置當作驗證 |
| 登入 | Google 首次登入自動建帳有獨立開關 | 升級時從既有 `signup_enabled` 複製值，維持原有政策 |
| 文件 | 舊 `docs/`、部分 README 搬到 VitePress `website/` | macOS 架構內容併入新中英文頁；本地 `docs/chen_yang/` 保留 |
| 官網 | 新增 `site/` 宣傳網站 | 測試及建置獨立於管理前端；預設 SEO 網址仍是上游品牌網址 |
| 執行環境 | Python 3.15、Electron 45、TypeScript 6 與共用相依更新 | 使用鎖檔安裝並驗證；沒有自行改回舊依賴或重新解出任意版本 |
| 部署 | PgBouncer、監控映像更新；新增文件／官網 CI | 沒有在本次操作部署正式服務或推送遠端 |

## 六個衝突檔案與解法

1. `backend/tests/ai/teacher_judge/test_teacher_judge_sessions_routes_coverage.py`：採上游重整後版本。批次送出／續跑的實作及 focused tests 已在上游，不保留舊的重複測試段。
2. `frontend/src/locales/en/teaching.json`：保留上游新增的英文單數形式 `AiJudgePanel.batchCreated_one`。
3. `frontend/src/pages/course-operations/class-workspace/AiJudgePanel.batchExecution.test.jsx`：採用帶 QueryClient、fake timer 通知排程與清理的上游測試，保留逾時查回及避免重複 POST 等情境。
4. `frontend/src/pages/course-operations/class-workspace/AiJudgePanel.jsx`：採用 `trackedBatch`、Query 快取及取消舊讀取的上游流程。額外發現自動合併把 `newRunBatchId()` 放了兩次，移除重複後，此檔與固定上游版本一致。
5. `website/guides/wireguard-desktop-architecture.md`：保留上游搬移／更新的文件，同時保留本地 macOS Universal、helper 安裝與 Keychain 說明。
6. `website/zh-TW/guides/wireguard-desktop-architecture.md`：與英文版採同樣處理。

沒有整批套用 `ours`／`theirs`。處理衝突後另外比對上游，確認剩餘程式差異主要為原有 macOS 支援及本地開發埠設定。

## 保留的本地功能

- macOS Intel x64／Apple Silicon arm64 Universal 桌面端與 WireGuard 二進位檔。
- root-owned helper 的首次授權安裝、後續通道啟停、狀態與清理流程。
- macOS 選單、Dock 視窗恢復、SSH 開 Terminal、RDP 客戶端偵測。
- 更新服務的 macOS DMG 資產選擇；資源頁的 macOS 下載網址選擇。
- 後端本地下載資產的 DMG 搜尋模式。
- Windows／macOS 雙平台桌面 CI matrix。
- Vite 的 `FRONTEND_PORT`／`FRONTEND_HOST_PORT`、`BACKEND_PORT`／`BACKEND_HOST_PORT` 設定；同時保留上游 React Compiler。
- 原本的 macOS 移植計畫檔。

另修正一處上游檔尾空白，並將 VitePress 建置產生的 `.vitepress/.temp/` 加入 `website/.gitignore`，避免建置暫存被誤提交。

## 資料庫升級重點

新增 migration 是一條連續鏈，最後只有一個 head：`usrgrp01_user_groups`。

| Migration | 變更 | 升級注意事項 |
| --- | --- | --- |
| `cepubpfx01` | 網域 hostname 範本轉為普通前綴 | 移除 `{student}`／`{class}`、轉小寫、整理符號及長度；`downgrade()` 無法重建舊字串，需靠升級前備份回復原資料 |
| `memovc01` | 新增記憶體超賣倍率 | 非空欄位，預設 1.0 |
| `cpuovc01` | CPU 超賣預設由 2.0 改 5.0 | 修改資料庫欄位預設；不覆寫已有設定列的倍率 |
| `regpolicy02_google_signup` | Google 自動建帳獨立開關 | 從既有 `signup_enabled` 複製當前政策 |
| `usrgrp01_user_groups` | 群組與群組成員表 | 新增外鍵、索引及群組名稱唯一約束 |

正式升級應先備份資料庫，再建置及執行 prestart。程式碼 rollback 不會自動還原 hostname 前綴轉換的資料；要完整還原需對應的資料庫備份。本次驗證只操作新建的臨時測試資料庫。

## 驗證結果

PostgreSQL 18 的完整 `alembic upgrade head`、`alembic check` 及 `scripts/prestart.sh` 已通過；模型與 migration 沒有 schema drift。Python 3.15.0 全套後端測試為 **7,954 passed、12 skipped、0 failed、0 errors**（98.43 秒）；沒有排除 PostgreSQL 或 Redis 測試。

已確認通過：

- 前端：321 個測試檔，2,100 個測試；正式建置成功。
- 桌面：登入 9、通道 14、資源存取 6、設定 5、輪詢 4，共 38 個測試；ESLint、Vue／TypeScript 檢查、正式建置成功。
- 桌面依賴稽核：沒有未獲既有規則允許的 high／critical 項目。
- macOS Universal DMG：以 Electron 45.0.0／electron-builder 26.15.3 打包成功；主程式具有 x86_64／arm64，`codesign --verify --deep --strict` 通過。使用 ad-hoc 簽章，未做 Apple 公證，不等於正式發行驗證。
- 文件站：匯出 354 個 OpenAPI paths、VitePress 建置及 anchor 檢查通過。
- 官網：29 個測試與 build／三語 prerender 通過。首次與前端同時跑 Vitest 出現共用 cache 目錄競爭，改為依序執行即通過，未修改測試內容。
- AI service：122 passed、2 skipped（CPU-only suite）。
- Ruff lint：全部通過。全庫 `ruff format --check` 回報 489 個既有檔案格式差異，未藉此次合併重排整個後端。
- migration 離線 SQL 產生成功；單一 head 檢查通過。
- Git 衝突標記及 `git diff --check` 檢查通過。

首次 Python 3.15 全套驗證額外啟用全域 `REDIS_ENABLED=true`，得到 7,922 passed、12 skipped、4 failed、28 errors。失敗均可從 log 對應到共用測試帳號／IP 達到登入或 setup 的 Redis 限流，並非 migration 失敗。後續改用與 CI 預設一致的 `REDIS_ENABLED=false` 重跑，7,954 個測試通過；Redis 仍啟動在獨立埠，專用限流／token blacklist 測試直接連該實例，不取消或略過這些測試。沒有修改應用程式的正式限流設定。

測試環境安裝了 Homebrew `postgresql@18`、`redis` 及必要依賴；臨時服務只綁 loopback、使用獨立資料目錄與動態埠，不設定開機啟動；完整驗證結束後 PostgreSQL／Redis 均已停止。Python 3.15 驗證環境位於 `/tmp/campus-skylab-python315`，原本工作區 Python 環境仍為 3.12。

完整驗證腳本為 `/tmp/campus_skylab_full_validation.py`；它建立新的臨時 DB／Redis、執行 migration、prestart、全套 pytest，並在 `finally` 停止服務。

主要執行記錄位於 `/tmp/campus-skylab-*.log`；測試安裝包為 `/tmp/campus-skylab-merge-macos/SkyLab-Connect-mac-universal.dmg`。這些是本機驗證產物，不納入 Git。

## 合併後仍需區分的限制與觀察

以下不是此次合併造成的衝突，也不應把靜態觀察描述為已重現的資料外洩。

1. **正式 Linux 映像驗證**：本機 Python 3.15 測試仍不能取代 `python:3.15-slim` 的 Linux Docker build、worker 與實際 PVE／Gateway 整合測試。現有 Backend CI matrix 仍只有 3.11；建議後續加入 3.15，且在 `uv sync` 明確指定 matrix 版本。
2. **SSH 明文快取生命週期**：`frontend/src/queries/resourceDetail.js` 的 `useSshKeyQuery` 未像 `queries/aiApi.js` 的完整 AI key 查詢指定 `gcTime: 0`，service 也未接取消訊號。這是敏感資料在瀏覽器記憶體中的生命週期差異；此次沒有證明跨帳號外洩。
3. **憑證畫面的一致性**：`setCredentials()` 直接 `setQueryData`，未先取消同 key 的在途讀取；較早 GET 晚到時可能覆蓋較新畫面。需要 deferred-response 情境測試才可確認具體重現。
4. **群組名稱大小寫競爭**：服務以 `lower(name)` 預查，但資料庫為普通 `UNIQUE(name)`。並行建立大小寫不同的名稱，仍可能通過各自預查；目前並未加入 functional unique index 或改變上游 schema。
5. **macOS 下載端點限制**：本地原有後端修改僅增加 DMG 搜尋模式，`/desktop-client/download` 仍優先使用單一 `DESKTOP_CLIENT_DOWNLOAD_URL`，不依用戶端平台分流。前端資源頁自行選 macOS URL；不能把「有 DMG pattern」說成後端已具備完整平台選擇。
6. **實機連線與發行**：沒有在此流程連線真實 PVE、變更系統 WireGuard 路由、安裝 root helper、執行 Windows 實機測試，或發布 DMG。macOS 通道測試使用 mock；安裝包可建置不代表實際 Gateway 連線已驗證。
7. **站台品牌設定**：官網、文件站預設 canonical／SEO 網址及品牌仍屬 SkyLab；若 Campus-Cloud 要公開獨立部署，需另行確認網域與品牌設定。

上述上游行為保留在合併結果中，沒有暗中改變憑證政策、名稱唯一性或部署版本。正式部署前應依使用情境處理，而不是把本機合併通過當成已上線。
