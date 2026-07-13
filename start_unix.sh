#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_CMD="python3"
command -v "$PYTHON_CMD" >/dev/null 2>&1 || PYTHON_CMD="python"

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  echo "未找到 Python，请先安装 Python 3.10 或更高版本。"
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "[1/3] 正在创建本地 Python 环境..."
  "$PYTHON_CMD" -m venv .venv
fi

source .venv/bin/activate
echo "[2/3] 正在检查运行依赖，第一次启动可能需要几分钟..."
python -m pip install -r requirements.txt

echo "[3/3] 正在启动末日菜园，浏览器会自动打开..."
python -m streamlit run app.py
