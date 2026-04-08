param(
    [string]$TaskName = "",
    [string]$RunAt = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$configPath = Join-Path $root "config\watch_config.json"
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json

if (-not $TaskName) {
    $TaskName = [string]$config.task_name
}

if (-not $RunAt) {
    $RunAt = [string]$config.run_at
}

$runScript = Join-Path $root "run.ps1"
$command = "powershell -ExecutionPolicy Bypass -File `"$runScript`""

schtasks /Create /SC DAILY /TN $TaskName /TR $command /ST $RunAt /F
Write-Host "Created daily task '$TaskName' at $RunAt."
