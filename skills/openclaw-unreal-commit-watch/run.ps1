param(
    [string]$RepoPath = "",
    [int]$LookbackHours = 0
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath = Join-Path $root "scripts\generate-report.ps1"
$configPath = Join-Path $root "config\watch_config.json"

if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Missing script: $scriptPath"
}

& $scriptPath -SkillRoot $root -ConfigPath $configPath -RepoPath $RepoPath -LookbackHours $LookbackHours
