<#
.SYNOPSIS
  One-shot birdreport token refresh: update env var + rebuild cc-connect (so its claude
  picks up the new token) + pm2 save.
.DESCRIPTION
  birdreport login requires an image captcha, so token cannot be fully automated.
  Get the token manually: log in https://www.birdreport.cn/ -> F12 -> Network ->
  any api request -> copy request header X-Auth-Token. Then run this script.
.EXAMPLE
  powershell -File refresh_birdreport_token.ps1 -Token <YOUR_X_AUTH_TOKEN>
#>
param(
  [Parameter(Mandatory = $true)][string]$Token,
  [string]$CcConnectRunJs = "C:\Users\<user>\AppData\Roaming\npm\node_modules\cc-connect\run.js",
  [string]$CcConnectCwd   = "H:\your-project"
)

# 1) Persist token at User level
[Environment]::SetEnvironmentVariable("BIRDREPORT_TOKEN", $Token, "User")
Write-Host "[ok] BIRDREPORT_TOKEN updated (User scope)"

# 2) Load all related User vars into this session (pm2 start captures them -> full env for cc-connect)
$names = @("EBIRD_API_KEY","QWEATHER_API_HOST","QWEATHER_SUB","QWEATHER_KID","QWEATHER_PRIVATE_KEY",
  "BIRDREPORT_TOKEN","BIRDREPORT_MEMBER_ID","BIRDWATCH_VAULT",
  "ANTHROPIC_BASE_URL","ANTHROPIC_AUTH_TOKEN","ANTHROPIC_API_KEY","ANTHROPIC_MODEL")
foreach ($n in $names) {
  $v = [Environment]::GetEnvironmentVariable($n, "User")
  if ($v) { Set-Item "Env:$n" $v }
}

# 3) Rebuild cc-connect (pm2 --update-env is unreliable for child procs on Windows; use delete+start)
Write-Host "[..] rebuilding cc-connect"
pm2 delete cc-connect 2>$null | Out-Null
Start-Sleep -Seconds 2
pm2 start $CcConnectRunJs --name cc-connect --interpreter node --cwd $CcConnectCwd | Out-Null
pm2 save | Out-Null
Start-Sleep -Seconds 3

# 4) Verify the new token reached cc-connect's env
$ok = $false
pm2 env 0 2>$null | Select-String "BIRDREPORT_TOKEN" | ForEach-Object {
  if ($_.ToString() -match [Regex]::Escape($Token.Substring(0, 8))) { $ok = $true }
}
if ($ok) {
  Write-Host "[ok] cc-connect rebuilt; new token present in its env."
} else {
  Write-Host "[warn] rebuilt, but new token not confirmed in cc-connect env. Check 'pm2 status'."
}
Write-Host "Tip: wait a few seconds, then send /new in Feishu to start a fresh session."
