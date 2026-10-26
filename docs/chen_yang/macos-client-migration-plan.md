# SkyLab Connect — macOS (Intel x64 / Apple Silicon arm64) 客戶端移植與相容性分析計劃

> **作者 / 整理目錄**：`docs/chen_yang/`
> **目標**：在不破壞現有 Windows 客戶端的前提下，為 `desktop-client` 新增 macOS（支援 Intel `x64` 與 Apple Silicon `arm64`）客戶端，並梳理本機 Mac 開發環境建置清單、架構共用性、必要修改項目、風險與分階段執行計劃。

---

## 目錄

1. [目前本機 Mac 環境健檢與必裝工具指南](#1-目前本機-mac-環境健檢與必裝工具指南)
2. [架構盤點：可共用項目 vs. 平台綁定項目](#2-架構盤點可共用項目-vs-平台綁定項目)
3. [核心技術決策：macOS 上的 WireGuard 實作方案比較](#3-核心技術決策macos-上的-wireguard-實作方案比較)
4. [必要修改項目清單（逐檔案深度分析）](#4-必要修改項目清單逐檔案深度分析)
5. [保持 Windows 相容性的重構計劃（Driver 抽象層設計）](#5-保持-windows-相容性的重構計劃driver-抽象層設計)
6. [潛在風險評估與應對策略](#6-潛在風險評估與應對策略)
7. [分階段實作里程碑與驗證清單](#7-分階段實作里程碑與驗證清單)
8. [待確認決策問題](#8-待確認決策問題)

---

## 1. 目前本機 Mac 環境健檢與必裝工具指南

由於您剛換到 Mac，我們已先對您目前的機器進行環境掃描，以下是**目前電腦的現況**與**後續開發需要補裝的工具**。

### 1.1 目前機器現況（已就緒項目）

| 項目 | 偵測結果 | 狀態與說明 |
| :--- | :--- | :--- |
| **CPU / 架構** | `Apple M1` (`arm64`) | Apple Silicon 原生架構，可透過交叉編譯同時產出 `arm64` 與 Intel `x64` 版本 |
| **作業系統** | `macOS 27.0.1` (`Build 26A434`) | 系統正常 |
| **C/C++ 編譯器 (Clang)** | `/Library/Developer/CommandLineTools` (`gcc`/`clang`/`make`) | **已安裝** Xcode Command Line Tools，不需額外安裝完整版 Xcode（數十 GB）即可編譯大部分工具 |
| **套件管理器** | Homebrew (`/opt/homebrew/bin/brew`) | **已安裝**（目前僅裝了 `gh`） |
| **Node.js / npm** | `Node v24.22.0` / `npm 11.19.1` (透過 `nvm`) | **已安裝**，符合 `desktop-client/package.json` 要求的 `node >= 22.12.0` |
| **Python 管理器** | `uv` (`/Users/owo/.local/bin/uv`) | **已安裝**，可隨時建立後端所需的 Python 3.11+ 環境 |
| **Git** | `git 2.54.0` | **已安裝** |

### 1.2 尚未安裝、需要補齊的工具與編譯器

在 macOS 上開發與打包 `SkyLab Connect`，以下工具尚未安裝：

#### A. 必裝：WireGuard 底層工具與編譯器（桌面端開發核心）

1. **`wireguard-tools` 與 `wireguard-go`**
   - **目前狀態**：未安裝（`wg`、`wg-quick`、`wireguard-go` 皆找不到）。
   - **用途**：macOS 核心（XNU）不像 Linux 內建 WireGuard kernel module，因此 macOS 是透過 Userspace 的 `wireguard-go` 建立虛擬網卡（`utun`），再搭配 `wg` 指令注入金鑰與路由。
2. **新版 `bash`（若使用 `wg-quick` 則必裝）**
   - **目前狀態**：系統內建 `/bin/bash` 為 `3.2.57`（Apple 因 GPLv3 授權因素自 2007 年後不再更新內建 bash）。
   - **重要坑點**：`wg-quick` 腳本第一行會強制檢查 `[[ $BASH_VERSINFO -ge 4 ]]`，在原生 Mac 上執行 `wg-quick` 會直接報錯 `wg-quick: bash 4+ required`。透過 Homebrew 安裝新版 `bash` (5.x) 可解決本機開發問題（針對一般學生使用者的免安裝解法見第 3 節）。
3. **Go 編譯器 (`go`)**
   - **目前狀態**：未安裝。
   - **用途**：若我們要像 Windows 版內嵌 `wireguard.msi` 一樣，在 macOS `.app` 內嵌（Bundle）免安裝的 `wireguard-go`，需要 Go 編譯器來編譯 `arm64` 與 `x86_64` 雙架構執行檔（Go 原生支援 `GOOS=darwin GOARCH=amd64` 與 `GOARCH=arm64` 跨架構編譯，再用 macOS 內建的 `lipo` 工具合成 Universal Binary）。
4. **Rosetta 2（Apple Silicon 轉譯層）**
   - **目前狀態**：尚未安裝。
   - **用途**：您的電腦是 M1 (`arm64`)。當我們打包出給舊款 Intel Mac 用的 `x64` 版 `.app` 時，若想在您的 M1 Mac 上直接雙擊測試 `x64` 版本，需要安裝 Rosetta 2。

**👉 一鍵安裝上述桌面端開發環境指令：**

```bash
# 1. 安裝 WireGuard 工具鏈、Go 編譯器與新版 Bash
brew install wireguard-tools wireguard-go go bash

# 2. 安裝 Rosetta 2（供本機測試 Intel x64 打包產物）
softwareupdate --install-rosetta --agree-to-license
```

#### B. 選裝：若您也需要在這台 Mac 跑 SkyLab 前後端（Web / Backend）

- **`bun`**：SkyLab 的 Web 前端 (`frontend/`) 使用 `bun` 作為套件管理與執行工具。
  ```bash
  brew install oven-sh/bun/bun
  ```
- **Docker 環境（`OrbStack` 或 `Docker Desktop`）**：若要在本機跑 `docker compose`（PostgreSQL、Redis、Backend），在 M1 Mac 上極力推薦安裝 **OrbStack**（比 Docker Desktop 省電、記憶體佔用極低、啟動只要 2 秒，且完全相容 `docker` 與 `docker compose` 指令）：
  ```bash
  brew install --cask orbstack
  ```

---

## 2. 架構盤點：可共用項目 vs. 平台綁定項目

`desktop-client` 採用 **Electron + Vue 3 + TypeScript + Pinia** 架構，分層非常乾淨。經完整檢視原始碼，約 **85%～90% 的程式碼可以直接雙平台共用**。

### 2.1 可 100% 直接共用的模組（不需修改或僅極少調整）

| 階層 | 檔案 / 目錄 | 為什麼可以直接共用 |
| :--- | :--- | :--- |
| **Renderer UI 層** | `src/views/**`、`src/components/**`、`src/styles/**`、`src/router/**` | 純 Vue 3 + Element Plus + Tailwind CSS，無綁定 Windows API |
| **多語系與狀態管理** | `src/lang/{zh-TW,en-US,ja}.ts`、`src/store/app.ts` | Pinia store、30 秒 Session 到期警告輪詢、1 分鐘資源刷新皆為跨平台邏輯 |
| **Preload 安全橋接** | `electron/preload/index.ts` | `contextBridge` IPC Channel 白名單與啟動動畫與作業系統無關 |
| **核心與依賴注入** | `electron/core/{BeanFactory,IpcRouter,BusinessError,GlobalConstant,Logger}.ts` | `electron-log` 在 macOS 會自動將日誌寫入 `~/Library/Logs/SkyLab Connect/main.log` |
| **本地資料庫與設定** | `electron/repository/{BaseRepository,SettingsRepository}.ts`、`electron/service/SettingsService.ts` | `@seald-io/nedb` 為純 JS 實作（**無原生 C++ addon `node-gyp` 重編譯問題**）；`app.getPath("userData")` 在 macOS 自動對應 `~/Library/Application Support/SkyLab Connect`；`app.setLoginItemSettings({ openAtLogin })` 在 Electron 44 同時支援 Windows 與 macOS |
| **後端 API 與認證** | `electron/service/{SkyLabService,AuthService}.ts` | Electron `net.request`、Device Code 瀏覽器登入輪詢、Refresh Token 旋轉機制完全跨平台 |
| **金鑰產生與加密儲存** | `WireGuardTunnelService.ts` 內的 `_createIdentity`、`_loadIdentity`、`_buildConfig` | Node 內建 `crypto.generateKeyPairSync("x25519")` 跨平台一致；Electron `safeStorage` 在 Windows 使用 DPAPI，在 macOS 自動切換為 **macOS Keychain（鑰匙圈）** |
| **圖示資產** | `public/logo/pack/icon.icns`、`public/logo/only/icon.icns` | 倉庫中**已經有準備好 `.icns` 圖示檔**，可直接供 macOS 打包使用！ |

### 2.2 與 Windows 深度綁定、必須修改的模組

| 模組 | 檔案路徑 | 目前的 Windows 專屬寫法 | macOS 對應需求 |
| :--- | :--- | :--- | :--- |
| **1. 套件與建置設定** | `desktop-client/package.json`<br>`desktop-client/electron-builder.json5` | `"os": ["win32"]`；只有 `win` 與 `nsis` 設定；`prepare-wireguard.ps1` 用 PowerShell | 加入 `"darwin"`；新增 `mac` (`dmg` / `zip`，`x64` + `arm64` / `universal`) 設定與 macOS 準備腳本 |
| **2. WireGuard 通道服務** | `electron/service/WireGuardTunnelService.ts`<br>`electron/utils/PathUtils.ts` | 寫死 `process.platform !== "win32"` 拋錯；尋找 `C:\Program Files\WireGuard\wireguard.exe`；用 `sc.exe query WireGuardTunnel$SkyLab` 查狀態；用 `powershell.exe Start-Process -Verb RunAs` 提權；用 `msiexec.exe` 裝 MSI | 實作 macOS 通道控制（`utun` 介面建立、`wg` 設定、路由設定、狀態查詢、管理員提權） |
| **3. 視窗、選單與 Dock 行為** | `electron/main/index.ts` | `Menu.setApplicationMenu(null)`；視窗 `icon` 指到 `.ico`；`minimize` 直接 `hide()`；`activate` 只 `focus()` 未 `show()`；Tray 只綁 `double-click` | macOS 必須有 Application Menu（否則 `Cmd+C/V` 複製貼上會壞掉）；修復 Dock 點擊喚醒與 Tray 行為 |
| **4. 外部 SSH / RDP 啟動** | `electron/service/SystemService.ts` | 已預留 `darwin` 分支（`osascript` 開 Terminal、`rdp://` URI），但有細節問題 | Terminal 需加 `activate` 帶到前景；RDP 需檢查是否已安裝 Microsoft `Windows App` 並給予友善錯誤提示 |
| **5. 更新檢查與下載分流** | `electron/service/UpdateService.ts`<br>`frontend/.../ResourcesPage.jsx`<br>`backend/.../desktop_client.py` | 寫死只找 `SkyLab-Connect-Setup.exe` | 根據 `process.platform` 與 `process.arch` 選擇對應的 `.exe` 或 `.dmg` |

---

## 3. 核心技術決策：macOS 上的 WireGuard 實作方案比較

這是從 Windows 移植到 macOS **最重要的一個架構差異**。

### 為什麼不能照搬 Windows 的做法？
在 Windows 上，官方的 `WireGuard for Windows` 安裝後會提供 `wireguard.exe /installtunnelservice <conf>` 指令，讓我們直接把它當成系統服務呼叫。
**但在 macOS 上，App Store 或官網下載的 GUI 版 `WireGuard.app` 並未提供任何 CLI 指令讓外部程式匯入並啟動連線**（它受限於 Apple App Sandbox 與 NetworkExtension 框架）。

因此在 macOS 上，我們有以下三種技術方案可選：

### 方案比較表

| 評估維度 | **方案一（強烈推薦）：App 內嵌 `wireguard-go` + `wg` 執行檔，直接控制 `utun` 與路由** | **方案二：呼叫系統/Homebrew 的 `wg-quick`** | **方案三：原生 Swift `NetworkExtension` (System Extension)** |
| :--- | :--- | :--- | :--- |
| **學生是否需額外裝軟體** | **完全不用**（開箱即用，與 Windows 版體驗一致） | 需要學生先裝 Homebrew + `wireguard-tools` + `bash >= 4`（或內嵌 bash 4） | 完全不用 |
| **Apple 付費開發者帳號門檻** | 可先用免費 Ad-hoc 簽章測試，後續再加一般 Developer ID 簽章 | 同左 | **強制要求**付費帳號並向 Apple 申請特殊 `NetworkExtension` Entitlement，否則連本機都無法跑 |
| **實作複雜度** | **中低**（TypeScript / Shell 即可完成，約 150 行程式碼） | 低，但相依性問題多（macOS 內建 Bash 3.2 不相容 `wg-quick`） | **極高**（需寫 Xcode Swift Helper App + XPC 通訊） |
| **Split-Tunnel 精準度** | **極高**（SkyLab 只需將 VM 子網如 `10.10.0.0/16` 導向 `utun`，不改動學生預設閘道與 DNS） | 高 | 高 |

### 推薦採用「方案一」的具體運作原理

SkyLab Connect 從後端取得的設定非常單純（只有 `PrivateKey`、`Address`、`Gateway PublicKey`、`Endpoint`、`AllowedIPs`、`PersistentKeepalive`，**不改系統 DNS、也沒有複雜的防火牆規則**）。

我們可以在打包時將編譯好的 `wireguard-go` 與 `wg`（Universal Binary，同時含 `x64` 與 `arm64`，僅約 4~5 MB）放進 `.app/Contents/Resources/wireguard/`。

#### macOS 啟動通道 (`installTunnel`) 流程：
1. Electron 產生暫存設定（只含 `wg setconf` 認得的 `[Interface] PrivateKey` 與 `[Peer]` 區段，權限 `0600`）。
2. 透過單次提權執行內建啟動腳本：
   ```sh
   mkdir -p /var/run/wireguard
   chmod 700 /var/run/wireguard
   # 1. 啟動 userspace WireGuard 並記錄實際分配到的 utun 介面名稱（例如 utun6）
   WG_TUN_NAME_FILE=/var/run/wireguard/SkyLab.name "$BUNDLED_WIREGUARD_GO" utun
   IFACE="$(cat /var/run/wireguard/SkyLab.name)"
   # 2. 套用 WireGuard 金鑰與 Peer 設定
   "$BUNDLED_WG" setconf "$IFACE" "$WG_CONF_PATH"
   # 3. 設定虛擬網卡 IP 並啟動介面（例如 10.250.0.3/16）
   /sbin/ifconfig "$IFACE" inet "$INTERFACE_CIDR" "$INTERFACE_IP" mtu 1420 up
   # 4. 為每個 AllowedIPs（例如 10.10.0.0/16）加入指向該 utun 介面的路由
   /sbin/route -q -n add -inet "$ALLOWED_CIDR" -interface "$IFACE"
   ```
3. 立即刪除明文設定檔（與 Windows 版安全規格一致）。

#### macOS 狀態檢查 (`isRunning` & `readLatestHandshake`) 流程：
- 檢查 `/var/run/wireguard/SkyLab.name` 對應的 socket `/var/run/wireguard/<utunX>.sock` 是否存在，以及 `/sbin/ifconfig <utunX>` 是否存在。
- 讀取握手時間：執行 `wg show <utunX> latest-handshakes`（若 socket 權限允許或透過 helper 讀取）。

#### macOS 停止通道 (`uninstallTunnel`) 流程：
- 刪除 `/var/run/wireguard/<utunX>.sock` 與 `/var/run/wireguard/SkyLab.name`（`wireguard-go` 偵測到控制 socket 被移除後會自動關閉 `utunX` 介面，macOS 核心也會自動清除綁在該 `utunX` 上的路由！）。

---

## 4. 必要修改項目清單（逐檔案深度分析）

以下列出程式碼庫中需要修改的每個檔案、行號與具體調整內容：

### 4.1 `desktop-client/package.json`
- **第 8–10 行**：
  - 現況：`"os": ["win32"]`（這會導致在 macOS 執行 `npm install` 時因平台不符報 `EBADPLATFORM`）。
  - 修改：改為 `"os": ["win32", "darwin"]`。
- **第 28–31 行 (`scripts`)**：
  - 現況：只有 `prepare:wireguard:win` 與 `build:electron:win`。
  - 修改：保留原 Windows 指令不動，新增 macOS 腳本：
    ```json
    "prepare:wireguard:mac": "bash scripts/prepare-wireguard-mac.sh",
    "build:electron:mac": "npm run prepare:wireguard:mac && npm run build && electron-builder --mac --x64 --arm64 -p never",
    "build:electron:mac:arm64": "npm run prepare:wireguard:mac && npm run build && electron-builder --mac --arm64 -p never --config.forceCodeSigning=false",
    "build:electron:mac:x64": "npm run prepare:wireguard:mac && npm run build && electron-builder --mac --x64 -p never --config.forceCodeSigning=false",
    "build:electron:mac:universal": "npm run prepare:wireguard:mac && npm run build && electron-builder --mac --universal -p never"
    ```

### 4.2 `desktop-client/electron-builder.json5`
- **新增 `mac` 與 `dmg` 區塊**（與既有 `win` / `nsis` 並存，互不影響）：
  ```json5
  mac: {
    icon: "./public/logo/pack/icon.icns",
    category: "public.app-category.developer-tools",
    darkModeSupport: true,
    hardenedRuntime: true,
    gatekeeperAssess: false,
    extraResources: [
      {
        from: "vendor/wireguard-mac",
        to: "wireguard",
        filter: ["wireguard-go", "wg", "THIRD_PARTY_NOTICES.txt"]
      },
      {
        from: "THIRD_PARTY_NOTICES.txt",
        to: "THIRD_PARTY_NOTICES.txt"
      }
    ],
    target: [
      {
        target: "dmg",
        arch: ["arm64", "x64", "universal"]
      },
      {
        target: "zip",
        arch: ["arm64", "x64"]
      }
    ]
  },
  dmg: {
    sign: false
  }
  ```

### 4.3 `desktop-client/electron/main/index.ts`（macOS 桌面體驗修正）
這支檔案有 5 個關鍵的 macOS 相容性問題必須修正：

1. **Application Menu 被設為 `null`（第 115 行）**
   - **問題**：`Menu.setApplicationMenu(null)` 在 Windows 只是隱藏視窗頂部選單列；但在 **macOS** 上，全系統的快捷鍵（`Cmd+C` 複製、`Cmd+V` 貼上、`Cmd+A` 全選、`Cmd+Q` 結束）都是由 Application Menu 的 Role 觸發的！設為 `null` 會導致學生在 Mac 上連網址都無法貼上。
   - **修正**：
     ```ts
     if (process.platform === "darwin") {
       Menu.setApplicationMenu(
         Menu.buildFromTemplate([
           { role: "appMenu" },
           { role: "editMenu" },
           { role: "windowMenu" }
         ])
       );
     } else {
       Menu.setApplicationMenu(null);
     }
     ```
2. **點擊 Dock 圖示無法喚醒隱藏視窗（第 206–210 行）**
   - **問題**：使用者點擊視窗關閉鈕（紅色 X）時，第 125 行執行了 `this._win?.hide()`。當使用者接著點擊 macOS 下方 Dock 圖示觸發 `app.on("activate")` 時，目前寫的是 `if (wins.length) wins[0].focus()`。在 macOS 上對一個 `hide()` 的視窗只呼叫 `focus()` **不會讓視窗重新顯示**！
   - **修正**：
     ```ts
     app.on("activate", () => {
       if (this._win) {
         this._win.show();
         this._win.focus();
       } else {
         void this.initializeWindow();
       }
     });
     ```
3. **視窗最小化事件攔截（第 117–120 行）**
   - **問題**：在 Windows 上攔截 `minimize` 並 `hide()` 到系統匣很常見；但在 macOS 上點擊黃色縮小鈕攔截 `minimize` 呼叫 `hide()` 會造成 macOS 視窗動畫卡死或異常。
   - **修正**：僅在 `process.platform !== "darwin"` 時將 `minimize` 轉為 `hide()`；在 macOS 上讓黃色按鈕正常縮小至 Dock，紅色關閉鈕則隱藏視窗。
4. **Menu Bar Tray 點擊行為（第 157–163 行）**
   - **問題**：macOS 的頂部 Menu Bar 圖示不支援 Windows 式的 `double-click` 事件。
   - **修正**：在 macOS 上透過 `setContextMenu` 即可左鍵/右鍵點擊展開選單；Windows 維持 `double-click` 顯示視窗。
5. **BrowserWindow `icon` 屬性（第 75 行）**
   - **問題**：目前傳入 `icon.ico`。macOS 視窗不吃 `.ico`。
   - **修正**：`process.platform === "win32"` 傳 `icon.ico`，其他平台傳 `512x512.png`。

### 4.4 `desktop-client/electron/service/SystemService.ts`（SSH 與 RDP 啟動）
- **`openSsh`（第 67–73 行）**：
  - 目前已有 `darwin` 分支使用 `osascript` 呼叫 `Terminal`，但：
    1. 缺少 `activate`，若 Terminal 原本沒開或在背景，視窗不會跳到最前面。
    2. 應對 `user` 與 `host` 做嚴格字元驗證，防止 AppleScript 字串注入。
  - **修正建議**：
    ```ts
    const script = `tell application "Terminal"
      activate
      do script "${sshCmd}"
    end tell`;
    ```
- **`openRdp`（第 87–89 行）**：
  - 目前呼叫 `await shell.openExternal("rdp://full%20address=s:${target}")`。
  - **風險點**：macOS **並沒有內建 RDP 客戶端**。學生必須從 Mac App Store 免費安裝微軟官方的 **Windows App**（舊稱 Microsoft Remote Desktop），系統才會註冊 `rdp://` 協定。若沒裝，點擊「RDP 連線」會毫無反應或跳出系統未知協定錯誤。
  - **修正建議**：在 macOS 呼叫 `openRdp` 前，先檢查 `/Applications/Windows App.app` 或 `/Applications/Microsoft Remote Desktop.app`（或透過 `lsregister` / `open -Ra` 檢查 handler），若未安裝則拋出清楚的多語系提示，引導學生安裝「Windows App (Microsoft Remote Desktop)」。

### 4.5 `desktop-client/electron/service/UpdateService.ts` 與下載連結
- **第 5 行**：目前固定找 `"SkyLab-Connect-Setup.exe"`。
- **修正建議**：依執行平台動態選擇 Asset：
  - `win32`：`SkyLab-Connect-Setup.exe`
  - `darwin` + `arm64`：優先找 `SkyLab-Connect-mac-arm64.dmg` 或 `SkyLab-Connect-mac-universal.dmg`
  - `darwin` + `x64`：優先找 `SkyLab-Connect-mac-x64.dmg` 或 `SkyLab-Connect-mac-universal.dmg`

---

## 5. 保持 Windows 相容性的重構計劃（Driver 抽象層設計）

為了**絕對不破壞現有 Windows 客戶端與既有單元測試 (`test-tunnel.mjs`)**，我們不應該在 `WireGuardTunnelService.ts` 的每個方法裡塞滿 `if (process.platform === "win32") ... else ...`，而是將「與作業系統打交道的那 5 個底層動作」抽成平台驅動介面（Platform Driver），或封裝在獨立的私有轉發層中。

### 5.1 架構分層圖

```text
┌───────────────────────────────────────────────────────────────────┐
│                    WireGuardTunnelService.ts                      │
│  （跨平台共用核心：100% 共用，不因平台分叉）                       │
│  - X25519 金鑰生成與 safeStorage 加解密 (_loadIdentity)           │
│  - 帳號/後端 Scope 隔離 (getConnectionScope)                      │
│  - WireGuard 設定驗證與組裝 (_buildConfig)                        │
│  - 操作序列鎖 (_serializeOperation) 與防競態 (_operationRevision)  │
│  - 5 分鐘租約自動續期 (_refreshTunnelLease)                        │
│  - 每秒狀態輪詢與斷線通知 (watchTunnel)                           │
└───────────────┬───────────────────────────────────┬───────────────┘
                │ process.platform === "win32"      │ process.platform === "darwin"
                ▼                                   ▼
┌───────────────────────────────┐   ┌───────────────────────────────┐
│     WindowsTunnelBackend      │   │      DarwinTunnelBackend      │
│  - 檢查 wireguard.exe         │   │  - 檢查內嵌 wireguard-go / wg │
│  - msiexec 安裝捆綁 MSI       │   │  - osascript / helper 提權    │
│  - sc.exe query 查服務狀態    │   │  - 建立 utun + wg setconf     │
│  - /installtunnelservice      │   │  - ifconfig + route add       │
│  - /uninstalltunnelservice    │   │  - 移除控制 socket 清理通道   │
│  - wg.exe 讀 latest-handshake │   │  - wg 讀 latest-handshakes    │
└───────────────────────────────┘   └───────────────────────────────┘
```

### 5.2 相容性保證清單
1. **Windows 程式碼路徑零行為變更**：在 `win32` 環境下，所有呼叫的指令（`sc.exe`、`powershell.exe`、`msiexec.exe`、`wireguard.exe`、`wg.exe`）與參數跳脫規則（`_windowsArgument`）完全保持原樣。
2. **既有測試 100% 原地通過**：`scripts/test-tunnel.mjs`、`test-auth.mjs`、`test-settings.mjs`、`test-resource-access.mjs`、`test-session-polling.mjs` 全部維持相容，並新增 macOS Driver 的單元測試。
3. **CI 雙平台守護**：`.github/workflows/desktop-client-tests.yml` 改為在 `windows-latest` 與 `macos-latest` 同時執行，確保任何修改都不會讓任一平台退化。

---

## 6. 潛在風險評估與應對策略

在新增 macOS 客戶端時，有 5 個實務上一定會遇到的系統層級風險，必須提前規劃：

### 風險 1：macOS 管理員提權（密碼彈窗頻率問題）⚠️ 高優先級
- **現象**：在 macOS 上建立虛擬網卡 `utun` 與新增路由需要 `root` 權限。如果我們用 `osascript -e 'do shell script "..." with administrator privileges'`：
  - 啟動連線時會跳一次 macOS 密碼/Touch ID 視窗。
  - **停止連線或關閉 App (`quitSafely`) 時**，若也要 `root` 才能砍掉 `/var/run/wireguard/<utun>.sock`，就會在關閉 App 時又跳一次密碼框；如果使用者按「取消」，通道就會殘留！
- **解決方案（兩階段設計）**：
  - **做法 A（巧思解法，免背景常駐 Daemon 也免斷線密碼）**：
    在「啟動連線」那一次提權腳本中，除了啟動 `wireguard-go` 與設定路由外，將控制用的關閉觸發機制或 pid/socket 清理設計為可由當前登入使用者（`$USER`）觸發，或者在初次安裝/首次連線時寫入一條嚴格受限的 `/etc/sudoers.d/skylab-connect` 規則（僅允許執行 `/Applications/SkyLab Connect.app/Contents/Resources/wireguard/skylab-wg-helper` 且該檔案必須為 `root:wheel` 擁有、`0755` 權限不可被一般使用者竄改）。
  - **好處**：使用者**只需要在第一次使用時輸入一次密碼**，之後日常每次點擊「開始連線」、「停止連線」或「關閉 App」都像 Windows 已安裝服務一樣流暢，不再跳密碼框！

### 風險 2：Apple Gatekeeper 攔截與程式碼簽章 (Code Signing & Notarization)
- **現象**：macOS（尤其是 Apple Silicon M1/M2/M3/M4）對從瀏覽器下載的 `.dmg` / `.app` 會貼上 `com.apple.quarantine` 標籤。若沒有 Apple Developer ID 簽章與公證（Notarization），學生打開時會顯示**「無法打開 SkyLab Connect，因為無法驗證開發者」**或**「檔案已損毀」**。
- **解決方案**：
  - **若有 Apple Developer Program 帳號（$99 USD/年，或學校教育專案申請）**：在 GitHub Actions 設定憑證與 `APPLE_ID` / `APPLE_APP_SPECIFIC_PASSWORD`，由 `electron-builder` 自動完成簽章與 Apple 公證，學生下載後直接雙擊即可使用。
  - **若暫無付費憑證（內部/課堂測試階段）**：
    1. 打包時執行 Ad-hoc 簽章：`codesign --force --deep --sign - "SkyLab Connect.app"`（避免 Apple Silicon 因無簽章直接拒絕載入 arm64 binary）。
    2. 在課程說明或下載頁面附上首次開啟教學：「按住 Control 點擊 App -> 打開」或終端機執行 `xattr -cr "/Applications/SkyLab Connect.app"`。

### 風險 3：Intel (`x64`) 與 Apple Silicon (`arm64`) 架構相容性
- **現象**：學生可能拿舊款 Intel MacBook 或新款 M1~M4 MacBook。若給錯架構，未裝 Rosetta 2 的 M 系列 Mac 無法執行 `x64` 程式，而 Intel Mac 絕對無法執行 `arm64` 程式。
- **解決方案**：
  - 我們內嵌的 `wireguard-go` 與 `wg` 執行檔，透過建置腳本同時編譯 `GOARCH=amd64` 與 `GOARCH=arm64`，再用 `lipo -create -output wireguard-go wireguard-go-amd64 wireguard-go-arm64` 合成 **Universal Binary**。
  - Electron 打包時可選擇：
    - 產出單一 `SkyLab-Connect-mac-universal.dmg`（一個安裝包通吃所有 Mac，學生不用分辨自己是 Intel 還是 M1，檔案約大 70MB）；**或**
    - 分別產出 `SkyLab-Connect-mac-arm64.dmg` 與 `SkyLab-Connect-mac-x64.dmg`。

### 風險 4：macOS Keychain (`safeStorage`) 授權提示
- **現象**：`SettingsRepository` 與 `WireGuardTunnelService` 使用 Electron `safeStorage` 加密 Token 與 WireGuard 私鑰。在 macOS 上這會存入「登入鑰匙圈 (login keychain)」。若未做正式簽章，每次重新打包新版 `.app` 時，macOS 視為新的執行檔雜湊，可能會跳出一次詢問「是否允許存取鑰匙圈」。
- **解決方案**：確保 `appId` (`edu.SkyLab.connect`) 固定，且儘可能維持一致的簽章身分。

### 風險 5：休眠喚醒與 Wi-Fi 切換
- **現象**：MacBook 闔蓋休眠非常頻繁。`index.ts` 第 186 行已有 `powerMonitor.on("resume", () => void tunnelService.refreshIfRunning("resume"))`。
- **解決方案**：`wireguard-go` 跑在 userspace UDP socket 上，漫遊（Roaming）能力極佳，換 Wi-Fi 或休眠喚醒後只要發出下一個封包就能自動跟 Gateway 更新漫遊端點，現有的 `refreshIfRunning` 與 `PersistentKeepalive = 25` 設計可直接無縫在 macOS 運作。

---

## 7. 分階段實作里程碑與驗證清單

建議分成 **4 個階段（Phases）** 推進，每個階段皆可獨立驗證：

### Phase 1：本機 Mac 開發環境初始化與基礎相容修正 ✅ 已完成
- [x] 1. 在 M1 Mac 安裝 `wireguard-tools`、`wireguard-go`、`go`、`bash`。
- [x] 2. 修改 `desktop-client/package.json` 的 `"os": ["win32", "darwin"]`。
- [x] 3. 在 `desktop-client/` 執行 `npm ci`，確認所有現有 5 個測試腳本（`test:auth`、`test:tunnel`、`test:resources`、`test:settings`、`test:polling`）與 `npm run build` 在 M1 Mac 上 100% 通過。
- [x] 4. 修正 `electron/main/index.ts` 的 macOS 視窗行為（Application Menu、Dock `activate` 喚醒、`minimize`、視窗圖示）。

### Phase 2：macOS WireGuard 工具打包腳本與 Driver 實作 ✅ 已完成
- [x] 1. 新增 `desktop-client/scripts/prepare-wireguard-mac.sh` 與 `desktop-client/vendor/wireguard-mac/skylab-wg-helper.sh`：
   - 自動建置或驗證 `vendor/wireguard-mac/wireguard-go` 與 `vendor/wireguard-mac/wg`（支援 `arm64` + `x64` Universal Binary）及 `THIRD_PARTY_NOTICES.txt`。
- [x] 2. 擴充 `WireGuardTunnelService.ts` 與 `PathUtils.ts`：
   - 保留 Windows 原有邏輯不動。
   - 新增 macOS (`darwin`) 實作：首次授權安裝 `skylab-wg-helper`、啟動 `wireguard-go`、`wg setconf`、`ifconfig`、`route add`、讀取 `latest-handshakes`、停止與清理孤兒通道。
- [x] 3. 擴充 `scripts/test-tunnel.mjs`：新增 macOS 平台狀態機、版本雜湊比對、免重複授權與指令參數跳脫測試。

### Phase 3：SSH / RDP 體驗優化與打包設定 ✅ 已完成
- [x] 1. 優化 `SystemService.ts` 在 macOS 的 `openSsh`（自動將 Terminal 帶到前景並驗證參數）與 `openRdp`（自動偵測 `rdp://` handler 與 `Windows App.app` / `Microsoft Remote Desktop.app`，未安裝時回傳多語系指引）。
- [x] 2. 更新 `UpdateService.ts`、前端下載按鈕 (`frontend/src/pages/personal/resources/ResourcesPage.jsx`) 與後端 `/api/v1/desktop-client/download` (`backend/app/api/routes/desktop_client.py`)，自動依作業系統支援 macOS `.dmg` 下載。
- [x] 3. 更新 `electron-builder.json5` 新增 `mac` 與 `dmg` 設定，在本機實測產出 `SkyLab-Connect-mac-universal.dmg`。

### Phase 4：CI/CD 自動化與文件更新 ✅ 已完成
- [x] 1. 更新 `.github/workflows/desktop-client-tests.yml`，加入 `windows-latest` 與 `macos-latest` 雙平台矩陣測試與建置驗證。
- [x] 2. 更新 `docs/wireguard-desktop-architecture.zh-TW.md`、`docs/wireguard-desktop-architecture.md` 與 `desktop-client/THIRD_PARTY_NOTICES.txt` 補充 macOS 架構與授權說明。

---

## 8. 已拍板決策與實作完成狀態

### 8.1 已確認之技術決策
1. **安裝包形式**：採用 **Universal 通用版 (`SkyLab-Connect-mac-universal.dmg`)**，單一安裝包同時支援 Intel (`x86_64`) 與 Apple Silicon (`arm64`)。
2. **程式碼簽章**：目前採用 **免憑證 Ad-hoc 簽章 (`identity: "-"`, `hardenedRuntime: false`)**，避免 Apple Silicon 因無簽章或 Library Validation 阻擋啟動；日後若有 Apple Developer ID 憑證可直接執行 `npm run build:electron:mac` 進行正式簽章與公證。
3. **WireGuard 提權模式**：採用 **首次連線授權一次、後續日常啟停免密 (`skylab-wg-helper`)**。
   - 首次連線時透過 `osascript`（支援 Touch ID / 管理員密碼）將受保護的 `wireguard-go`、`wg` 與 `skylab-wg-helper` 安裝至 `/Library/Application Support/SkyLabConnect/wireguard/`（`root:wheel` 擁有，一般使用者無法竄改），並經 `visudo -cf` 驗證寫入 `/etc/sudoers.d/skylab-connect`。
   - 後續啟動通道 (`up`)、中斷連線 (`down`)、App 關閉自動清理 (`quitSafely`) 與握手狀態查詢 (`status` / `handshake`) 皆透過 `sudo -n` 無縫執行，不再反覆跳出密碼視窗。

### 8.2 本機常用指令速查表（macOS）

```bash
cd desktop-client

# 1. 開發模式（熱更新啟動 Electron 視窗）
npm run dev

# 2. 執行程式碼檢查與全套單元測試
npm run lint
npm run test:auth
npm run test:tunnel
npm run test:resources
npm run test:settings
npm run test:polling

# 3. 建置 macOS Universal 通用版安裝包 (.dmg)
npm run build:electron:mac:unsigned
# 產出路徑：desktop-client/release/<version>/SkyLab-Connect-mac-universal.dmg
```

### 8.3 學生首次安裝未公證 (Ad-hoc) DMG 的開啟方式說明
若學生從瀏覽器下載未經 Apple 付費公證的 `.dmg`，拖入 `/Applications` 後首次開啟若遇到 macOS Gatekeeper 提示，可透過以下任一方式解除隔離標籤（僅首次需要）：
- **方式一（GUI）**：在 `/Applications/SkyLab Connect.app` 按右鍵（或按住 Control 點擊）→ 選擇「打開」；或至「系統設定 → 隱私權與安全性」點擊「仍要打開」。
- **方式二（終端機一行指令）**：
  ```bash
  xattr -cr "/Applications/SkyLab Connect.app"
  ```

