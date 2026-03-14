# vLLM 高併發模型部署

基於 vLLM 官方最新版本的 **乾淨架構** 高併發模型推論部署方案。

## 架構總覽

```
vllm_single/
├── .env                  # 環境變數 (最高優先級)
├── .env.example          # 環境變數範本
├── config/               # 設定層 - 統一參數管理
│   ├── __init__.py
│   └── settings.py       # Pydantic Settings (.env > 預設值)
├── core/                 # 核心層 - vLLM 引擎管理
│   ├── __init__.py
│   └── engine.py         # 伺服器啟停與健康檢查
├── api/                  # 介面層 - API 客戶端
│   ├── __init__.py
│   └── client.py         # 同步/異步 OpenAI 客戶端
├── benchmark/            # 測試層 - 異步壓力測試
│   ├── __init__.py
│   ├── async_bench.py    # Benchmark (總請求/總Token/吞吐量)
│   ├── enhanced_bench.py # 增強版 Benchmark (支援自定義 JSON 格式)
│   ├── sharegpt_bench.py # ShareGPT Benchmark (使用 ShareGPT 數據集)
│   ├── dataset.py        # 自定義測試數據集
│   └── sharegpt_dataset.py # ShareGPT 數據集解析
├── scripts/              # 腳本
│   ├── start_server.sh   # 啟動伺服器
│   └── run_benchmark.sh  # 執行 Benchmark
├── main.py               # 伺服器入口
├── call_model.py         # API 呼叫範例
├── run_benchmark.py      # Benchmark 入口
└── requirements.txt      # 依賴清單
```

## 設計原則

| 原則 | 實現 |
|------|------|
| **參數優先級** | `.env` 環境變數 > `config/settings.py` 預設值 |
| **關注點分離** | config / core / api / benchmark 各層獨立 |
| **高併發** | vLLM 原生 continuous batching + async API |
| **可觀測** | Benchmark 報告含延遲分位數、TTFT、吞吐量 |

## 快速開始

### 1. 啟用虛擬環境 & 安裝依賴

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 修改設定

編輯 `.env` 設定模型和參數：

```env
MODEL_NAME=nvidia/Qwen3-235B-A22B-NVFP4
HF_CACHE_DIR=/raid/hf-cache/hub
API_PORT=8000
MAX_MODEL_LEN=4096
GPU_MEMORY_UTILIZATION=0.95
MAX_NUM_SEQS=64
```

可用模型 (已快取)：
- `nvidia/Qwen3-235B-A22B-NVFP4`
- `Qwen/Qwen3-Next-80B-A3B-Thinking-FP8`
- `hugging-quants/Meta-Llama-3.1-405B-Instruct-AWQ-INT4`
- `openai/gpt-oss-120b`

### 3. 啟動伺服器

```bash
# 方式一: Python 入口
python main.py

# 方式二: Shell 腳本
bash scripts/start_server.sh
```

### 4. 呼叫模型 API

```bash
# 同步呼叫範例
python call_model.py

# 異步呼叫範例
python call_model.py async

# 全部範例
python call_model.py all
```

#### Python 程式碼呼叫

```python
from api.client import ModelClient, quick_chat

# 一行快速呼叫
answer = quick_chat("什麼是機器學習？")

# 完整客戶端
client = ModelClient()

# 同步
response = client.chat_simple("介紹 vLLM", max_tokens=256)

# 流式
for chunk in client.chat_stream("什麼是 LLM？"):
    print(chunk, end="")

# 異步
import asyncio
answer = asyncio.run(client.achat_simple("解釋 GPU 推論"))
```

#### cURL 呼叫

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer vllm-secret-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nvidia/Qwen3-235B-A22B-NVFP4",
    "messages": [{"role": "user", "content": "你好"}],
    "max_tokens": 256
  }'
```

### 5. 執行 Benchmark

#### A. 簡單 Benchmark（async_bench）

```bash
# 使用 .env 預設值
python run_benchmark.py

# 自訂參數
python run_benchmark.py -n 100 -c 20 -t 512

# 完整參數
python run_benchmark.py \
  --requests 200 \
  --concurrency 30 \
  --max-tokens 256 \
  --prompt "請介紹深度學習"
```

#### B. 增強版 Benchmark（自定義測試集）

```bash
# 使用自定義 JSON 格式測試集
python run_enhanced_benchmark.py test_datasets/chinese_qa_standard.json -c 20

# 只測試特定類別
python run_enhanced_benchmark.py test_datasets/chinese_qa_standard.json --category 技術問答
```

#### C. ShareGPT Benchmark（推薦使用）⭐

使用業界標準 ShareGPT 數據集進行測試：

```bash
# 1. 下載 ShareGPT 數據集
./run_sharegpt_benchmark.sh --download

# 2. 快速測試（100 個樣本）
./run_sharegpt_benchmark.sh -n 100 -c 20

# 3. 標準測試（1000 個樣本）
./run_sharegpt_benchmark.sh -n 1000 -c 50

# 4. 大規模壓力測試（5000 個樣本）
./run_sharegpt_benchmark.sh -n 5000 -c 100

# 5. 使用 Python 直接調用
python run_sharegpt_benchmark.py ShareGPT_V3_unfiltered_cleaned_split.json \
    -n 1000 -c 50 -m 512 -t 0.7
```

**ShareGPT Benchmark 特點：**
- ✅ 使用業界標準 ShareGPT 數據集
- ✅ 支援靈活的採樣與併發配置
- ✅ 完整的性能指標（吞吐量、延遲、TTFT、TPOT）
- ✅ 與 enhanced_bench 相同的架構和調用方式
- ✅ 測試流程穩定性和可複現性

**測試指標包括：**
- 請求吞吐量 (req/s)
- Token 吞吐量 (tok/s)
- 端到端延遲統計 (平均/P50/P90/P95/P99)
- TTFT - Time To First Token
- TPOT - Time Per Output Token
- Token 長度統計

📖 詳細文檔：[docs/SHAREGPT_BENCHMARK_GUIDE.md](docs/SHAREGPT_BENCHMARK_GUIDE.md)

Benchmark 報告自動儲存到 `benchmark_results/` 目錄。

## .env 參數說明

| 變數 | 說明 | 預設值 |
|------|------|--------|
| `MODEL_NAME` | 模型名稱 | `nvidia/Qwen3-235B-A22B-NVFP4` |
| `HF_CACHE_DIR` | HF 快取目錄 | `/raid/hf-cache/hub` |
| `API_HOST` | 監聽地址 | `0.0.0.0` |
| `API_PORT` | 監聽埠 | `8000` |
| `API_KEY` | API 金鑰 | `vllm-secret-key-change-me` |
| `DTYPE` | 資料類型 | `auto` |
| `MAX_MODEL_LEN` | 最大上下文長度 | `4096` |
| `GPU_MEMORY_UTILIZATION` | GPU 記憶體利用率 | `0.95` |
| `MAX_NUM_SEQS` | 最大併發序列 | `64` |
| `TENSOR_PARALLEL_SIZE` | 張量並行 | `1` |
| `ENFORCE_EAGER` | 強制 eager 模式 | `false` |
| `ENABLE_PREFIX_CACHING` | 前綴快取 | `true` |
| `BENCH_TOTAL_REQUESTS` | Benchmark 總請求 | `50` |
| `BENCH_CONCURRENCY` | Benchmark 併發 | `10` |
| `BENCH_MAX_TOKENS` | Benchmark 最大 token | `256` |
