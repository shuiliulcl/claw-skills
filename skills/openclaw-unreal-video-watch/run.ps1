$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $root "runtime\python.exe"
$ytDlpExe = Join-Path $root "tools\yt-dlp.exe"
$scriptPath = Join-Path $root "scripts\unreal_video_watch.py"
$configPath = Join-Path $root "config\watch_config.json"
$secretsDir = Join-Path $root "secrets"
$persistDir = Join-Path $env:LOCALAPPDATA "OpenClawUnrealVideoWatch"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Portable Python not found. Run install.ps1 first."
}

if (-not (Test-Path -LiteralPath $ytDlpExe)) {
    throw "Bundled yt-dlp not found. Run install.ps1 first."
}

New-Item -ItemType Directory -Force -Path $secretsDir | Out-Null
New-Item -ItemType Directory -Force -Path $persistDir | Out-Null

& $pythonExe $scriptPath --skill-root $root --yt-dlp $ytDlpExe --config $configPath
