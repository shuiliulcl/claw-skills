param(
    [string]$PythonVersion = "3.13.3",
    [string]$YtDlpVersion = "2025.03.31"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Join-Path $root "runtime"
$toolsDir = Join-Path $root "tools"
$tmpDir = Join-Path $root ".tmp"
$persistDir = Join-Path $env:LOCALAPPDATA "OpenClawUnrealVideoWatch"
$packageCookies = Join-Path $root "secrets\cookies.txt"
$persistCookies = Join-Path $persistDir "cookies.txt"

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
New-Item -ItemType Directory -Force -Path $persistDir | Out-Null

$pythonZip = Join-Path $tmpDir "python-embed.zip"
$pythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$pythonExe = Join-Path $runtimeDir "python.exe"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    Write-Host "Downloading portable Python from $pythonUrl"
    Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonZip
    Expand-Archive -LiteralPath $pythonZip -DestinationPath $runtimeDir -Force

    $pthFile = Get-ChildItem -LiteralPath $runtimeDir -Filter "python*._pth" | Select-Object -First 1
    if ($null -ne $pthFile) {
        $content = Get-Content -LiteralPath $pthFile.FullName
        $content = $content | ForEach-Object {
            if ($_ -eq "#import site") { "import site" } else { $_ }
        }
        Set-Content -LiteralPath $pthFile.FullName -Value $content -Encoding ascii
    }
}

$ytDlpExe = Join-Path $toolsDir "yt-dlp.exe"
$ytDlpUrl = "https://github.com/yt-dlp/yt-dlp/releases/download/$YtDlpVersion/yt-dlp.exe"
if (-not (Test-Path -LiteralPath $ytDlpExe)) {
    Write-Host "Downloading yt-dlp from $ytDlpUrl"
    Invoke-WebRequest -Uri $ytDlpUrl -OutFile $ytDlpExe
}

if ((Test-Path -LiteralPath $packageCookies) -and -not (Test-Path -LiteralPath $persistCookies)) {
    Copy-Item -LiteralPath $packageCookies -Destination $persistCookies
    Write-Host "Migrated package cookies to persistent path: $persistCookies"
}

Write-Host "Install complete."
Write-Host "Portable Python: $pythonExe"
Write-Host "Bundled yt-dlp:  $ytDlpExe"
Write-Host "Persistent data: $persistDir"
