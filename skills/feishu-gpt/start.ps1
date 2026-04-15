# 飞书 × ChatGPT 机器人 快速启动脚本
$Host.UI.RawUI.WindowTitle = "飞书 × ChatGPT 机器人"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  飞书 × ChatGPT 机器人 启动中..." -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[错误] 未找到 Python，请先安装：https://www.python.org/downloads/" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}
Write-Host "[OK] Python 已就绪" -ForegroundColor Green

# 检查并安装依赖
$depsInstalled = python -c "import lark_oapi; import openai; import mcp; import httpx" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[*] 正在安装依赖 lark-oapi / openai / mcp..." -ForegroundColor Yellow
    pip install lark-oapi openai mcp
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[错误] 依赖安装失败，请检查网络" -ForegroundColor Red
        Read-Host "按回车退出"
        exit 1
    }
}
Write-Host "[OK] 依赖已就绪" -ForegroundColor Green

# 检查 config.py 是否存在
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$configPath = Join-Path $scriptDir "config.py"
$botPath = Join-Path $scriptDir "bot.py"

if (-not (Test-Path $configPath)) {
    Write-Host "[错误] 未找到 config.py，请和 start.ps1 放在同一文件夹" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

# 检查 APP_ID 是否已填写
$configContent = Get-Content $configPath -Raw
if ($configContent -match 'cli_xxxxxx') {
    Write-Host ""
    Write-Host "[提示] config.py 中的 APP_ID 还未修改！" -ForegroundColor Yellow
    Write-Host "       请用记事本打开 config.py 填写飞书 APP_ID / APP_SECRET / OPENAI_API_KEY" -ForegroundColor Yellow
    Read-Host "按回车退出"
    exit 1
}

Write-Host ""
if ($configContent -match 'sk-xxxxxxxx') {
    Write-Host ""
    Write-Host "[提示] config.py 中的 OPENAI_API_KEY 还未修改！" -ForegroundColor Yellow
    Read-Host "按回车退出"
    exit 1
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  所有检查通过，启动机器人！" -ForegroundColor Green
Write-Host "  将同时启动飞书机器人和本地对话" -ForegroundColor Gray
Write-Host "  关闭此窗口即可停止机器人" -ForegroundColor Gray
Write-Host "  仅本地对话可运行: python bot.py --local-chat" -ForegroundColor Gray
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

python $botPath

Write-Host ""
Write-Host "[机器人已停止]" -ForegroundColor Yellow
Read-Host "按回车退出"
