# 手动安装脚本（Windows）：建虚拟环境 + 装依赖 + 生成 .env
$root = $PSScriptRoot
Set-Location $root

if (-not (Test-Path .venv)) {
  python -m venv .venv
}

# 激活并安装依赖
& ".\.venv\Scripts\Activate.ps1"
pip install --upgrade pip
pip install -r requirements.txt

if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  Write-Host "已生成 .env，请编辑填入你的 DEEPSEEK_API_KEY"
}

Write-Host "安装完成。启动后端: uvicorn app.main:app --host 0.0.0.0 --port 8004"
