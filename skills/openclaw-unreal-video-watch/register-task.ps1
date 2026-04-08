param(
    [string]$TaskName = "OpenClaw Unreal Video Watch",
    [string]$RunAt = "09:00",
    [switch]$Daily
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runScript = Join-Path $root "run.ps1"
if (-not (Test-Path -LiteralPath $runScript)) {
    throw "Missing run script: $runScript"
}

$parts = $RunAt.Split(":")
if ($parts.Count -ne 2) {
    throw "RunAt must look like HH:mm, for example 09:00"
}

$hour = [int]$parts[0]
$minute = [int]$parts[1]
$runDate = (Get-Date).Date.AddDays(1).AddHours($hour).AddMinutes($minute)
$taskCommand = "powershell -ExecutionPolicy Bypass -File `"$runScript`""

if ($Daily) {
    schtasks /Create /SC DAILY /TN $TaskName /TR $taskCommand /ST $RunAt /F
    Write-Host "Created daily task '$TaskName' at $RunAt."
}
else {
    schtasks /Create /SC ONCE /TN $TaskName /TR $taskCommand /ST $runDate.ToString("HH:mm") /SD $runDate.ToString("MM/dd/yyyy") /F
    Write-Host "Created one-time task '$TaskName' for $($runDate.ToString('yyyy-MM-dd HH:mm'))."
}
