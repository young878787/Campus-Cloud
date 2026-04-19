#!/usr/bin/env bash
# ============================================================
# ShareGPT Benchmark 快速啟動腳本
# 使用 ShareGPT 數據集進行性能測試
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 顏色定義
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# 載入 .env
if [[ -f .env ]]; then
    if ! ENV_SYNTAX_ERROR=$(bash -n .env 2>&1); then
        echo -e "${YELLOW}⚠${NC} .env 語法錯誤，無法載入環境變數"
        echo ""
        echo "bash -n .env 輸出:"
        echo "$ENV_SYNTAX_ERROR"
        echo ""
        echo "常見修正: 含空白的 JSON 值請加引號，例如"
        echo "  LIMIT_MM_PER_PROMPT='{\"image\":5,\"video\":1,\"audio\":0}'"
        echo ""
        exit 1
    fi

    set -a
    if ! source .env; then
        set +a
        echo -e "${YELLOW}⚠${NC} 載入 .env 失敗，請檢查變數格式"
        echo "提示: 變數值若包含空白、逗號或 JSON，請使用單引號或雙引號包住"
        exit 1
    fi
    set +a
fi

# 啟用虛擬環境
if [[ -f .venv/bin/activate ]]; then
    source .venv/bin/activate
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}🚀 ShareGPT vLLM Benchmark${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# 預設設定
DEFAULT_DATASET="test_datasets/ShareGPT_V3_unfiltered_cleaned_split.json"
DATASET_URL="https://huggingface.co/datasets/anon8231489123/ShareGPT_Vicuna_unfiltered/resolve/main/ShareGPT_V3_unfiltered_cleaned_split.json"

# 檢查參數
if [[ $# -eq 0 ]]; then
    echo -e "${YELLOW}使用方式:${NC}"
    echo "  $0 [選項]"
    echo ""
    echo -e "${YELLOW}選項:${NC}"
    echo "  -d, --dataset PATH      ShareGPT 數據集路徑 (默認: ${DEFAULT_DATASET})"
    echo "  -n, --num-samples N     採樣數量 (不指定則使用全部)"
    echo "  -c, --concurrency N     併發數"
    echo "  -m, --max-tokens N      每次最大生成 token 數"
    echo "  -t, --temperature T     溫度參數 (默認: 0.7)"
    echo "  --seed N                隨機種子 (默認: 42)"
    echo "  --no-save               不儲存報告"
    echo "  --download              下載 ShareGPT_V3 數據集"
    echo "  -h, --help              顯示此幫助訊息"
    echo ""
    echo -e "${YELLOW}範例:${NC}"
    echo ""
    echo "  # 下載 ShareGPT 數據集"
    echo "  $0 --download"
    echo ""
    echo "  # 快速測試 (100 個樣本)"
    echo "  $0 -n 100 -c 20"
    echo ""
    echo "  # 完整測試 (預設採樣 1000 個)"
    echo "  $0 -n 1000 -c 50"
    echo ""
    echo "  # 大規模測試 (5000 個樣本，高併發)"
    echo "  $0 -n 5000 -c 100"
    echo ""
    echo "  # 自定義數據集"
    echo "  $0 -d /path/to/custom_sharegpt.json -n 500"
    echo ""
    exit 0
fi

# 解析參數
DATASET=""
NUM_SAMPLES=""
CONCURRENCY=""
MAX_TOKENS=""
TEMPERATURE="0.7"
SEED="42"
NO_SAVE=""
DOWNLOAD_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--dataset)
            DATASET="$2"
            shift 2
            ;;
        -n|--num-samples)
            NUM_SAMPLES="$2"
            shift 2
            ;;
        -c|--concurrency)
            CONCURRENCY="$2"
            shift 2
            ;;
        -m|--max-tokens)
            MAX_TOKENS="$2"
            shift 2
            ;;
        -t|--temperature)
            TEMPERATURE="$2"
            shift 2
            ;;
        --seed)
            SEED="$2"
            shift 2
            ;;
        --no-save)
            NO_SAVE="--no-save"
            shift
            ;;
        --download)
            DOWNLOAD_ONLY=true
            shift
            ;;
        -h|--help)
            $0
            exit 0
            ;;
        *)
            echo -e "${YELLOW}未知選項: $1${NC}"
            exit 1
            ;;
    esac
done

# 如果只是下載數據集
if [[ "$DOWNLOAD_ONLY" = true ]]; then
    echo -e "${CYAN}▶${NC} 下載 ShareGPT_V3 數據集..."
    echo ""
    
    if [[ -f "$DEFAULT_DATASET" ]]; then
        echo -e "${GREEN}✓${NC} 數據集已存在: $DEFAULT_DATASET"
        SIZE=$(du -h "$DEFAULT_DATASET" | cut -f1)
        echo "  大小: $SIZE"
    else
        echo "  URL: $DATASET_URL"
        echo "  輸出: $DEFAULT_DATASET"
        echo ""
        
        if command -v wget &> /dev/null; then
            wget -O "$DEFAULT_DATASET" "$DATASET_URL"
        elif command -v curl &> /dev/null; then
            curl -L -o "$DEFAULT_DATASET" "$DATASET_URL"
        else
            echo -e "${YELLOW}⚠${NC} 需要 wget 或 curl 來下載數據集"
            exit 1
        fi
        
        echo ""
        echo -e "${GREEN}✓${NC} 下載完成"
        SIZE=$(du -h "$DEFAULT_DATASET" | cut -f1)
        echo "  大小: $SIZE"
    fi
    
    echo ""
    echo "使用此數據集運行 benchmark:"
    echo "  $0 -d $DEFAULT_DATASET -n 100 -c 20"
    echo ""
    exit 0
fi

# 設定默認數據集
if [[ -z "$DATASET" ]]; then
    DATASET="$DEFAULT_DATASET"
fi

# 檢查數據集是否存在
if [[ ! -f "$DATASET" ]]; then
    echo -e "${YELLOW}⚠${NC} 數據集不存在: $DATASET"
    echo ""
    echo "下載 ShareGPT_V3 數據集:"
    echo "  $0 --download"
    echo ""
    exit 1
fi

# 顯示配置
echo -e "${CYAN}▶${NC} 配置:"
echo "  數據集:         $DATASET"
[[ -n "$NUM_SAMPLES" ]] && echo "  採樣數量:       $NUM_SAMPLES"
[[ -n "$CONCURRENCY" ]] && echo "  併發數:         $CONCURRENCY"
[[ -n "$MAX_TOKENS" ]] && echo "  最大 Token:     $MAX_TOKENS"
echo "  溫度:           $TEMPERATURE"
echo "  隨機種子:       $SEED"
echo ""

# 構建命令
CMD="python3 run_sharegpt_benchmark.py \"$DATASET\""
[[ -n "$NUM_SAMPLES" ]] && CMD="$CMD -n $NUM_SAMPLES"
[[ -n "$CONCURRENCY" ]] && CMD="$CMD -c $CONCURRENCY"
[[ -n "$MAX_TOKENS" ]] && CMD="$CMD -m $MAX_TOKENS"
CMD="$CMD -t $TEMPERATURE --seed $SEED $NO_SAVE"

# 執行
echo -e "${CYAN}▶${NC} 啟動 Benchmark..."
echo ""

eval $CMD

echo ""
echo -e "${GREEN}✓${NC} Benchmark 完成"
echo ""
