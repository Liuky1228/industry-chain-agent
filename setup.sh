#!/usr/bin/env bash
# 手动安装脚本（macOS / Linux）：建虚拟环境 + 装依赖 + 生成 .env
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

python3 -m venv .venv
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
else
  echo "虚拟环境创建失败"; exit 1
fi

pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "已生成 .env，请编辑填入你的 DEEPSEEK_API_KEY 后重新运行本脚本或手动启动"
fi

echo "安装完成。启动后端: uvicorn app.main:app --host 0.0.0.0 --port 8004"
