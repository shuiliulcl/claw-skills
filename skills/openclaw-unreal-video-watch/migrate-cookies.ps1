$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$packageCookies = Join-Path $root "secrets\cookies.txt"
$persistDir = Join-Path $env:LOCALAPPDATA "OpenClawUnrealVideoWatch"
$persistCookies = Join-Path $persistDir "cookies.txt"

New-Item -ItemType Directory -Force -Path $persistDir | Out-Null

if (-not (Test-Path -LiteralPath $packageCookies)) {
    Write-Host "No package-local cookies file found at: $packageCookies"
    Write-Host "Nothing to migrate."
    exit 0
}

if (Test-Path -LiteralPath $persistCookies) {
    Write-Host "Persistent cookies file already exists at: $persistCookies"
    Write-Host "Leaving the existing file unchanged."
    exit 0
}

Copy-Item -LiteralPath $packageCookies -Destination $persistCookies
Write-Host "Migrated cookies to: $persistCookies"
