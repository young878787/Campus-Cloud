#!/bin/bash

# vLLM Web UI 啟動腳本

set -e

echo "==================================="
echo "  vLLM Web UI - 優雅夢幻助手"
echo "==================================="
echo ""

# 檢查 vLLM 服務是否運行
echo "🔍 檢查 vLLM 服務..."
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "❌ vLLM 服務未運行！"
    echo "請先啟動 vLLM 服務："
    echo "  python main.py"
    exit 1
fi
echo "✅ vLLM 服務運行中"
echo ""

# 安裝後端依賴
echo "📦 安裝後端依賴..."
if ! pip list | grep -q fastapi; then
    pip install fastapi uvicorn[standard] python-multipart
fi
echo "✅ 後端依賴已安裝"
echo ""

# 安裝前端依賴
echo "📦 安裝前端依賴..."
cd webapp/frontend
if [ ! -d "node_modules" ]; then
    npm install
fi
echo "✅ 前端依賴已安裝"
echo ""

# 啟動前端開發伺服器（背景）
echo "🚀 啟動前端開發伺服器..."
npm run dev &
FRONTEND_PID=$!
echo "✅ 前端運行在: http://localhost:5173"
echo ""

# 返回專案根目錄
cd ../..

# 啟動後端服務
echo "🚀 啟動後端 API 服務..."
echo "✅ 後端運行在: http://localhost:3000"
echo ""
echo "==================================="
echo "  全部啟動完成！"
echo "  請訪問: http://localhost:5173"
echo "==================================="
echo ""
echo "按 Ctrl+C 停止所有服務"
echo ""

# 啟動後端（前台）
python webapp/backend/main.py

# 清理：停止前端
kill $FRONTEND_PID 2>/dev/null || true
