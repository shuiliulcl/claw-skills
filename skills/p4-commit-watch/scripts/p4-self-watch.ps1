# p4-self-watch.ps1
# 监控指定 p4 用户在多个 stream 的提交，生成带 diff 分析的报告
# 用法: powershell -File p4-self-watch.ps1 -ConfigFile <path> [-HoursBack 12]

param(
    [string]$ConfigFile = "$PSScriptRoot\..\p4-watch-config.json",
    [int]$HoursBack = 0  # 0 = 从配置文件读取
)

# ---------- 加载配置 ----------
if (-not (Test-Path $ConfigFile)) {
    Write-Host "[ERROR] Config file not found: $ConfigFile"
    Write-Host "  Copy references/config-example.json to p4-watch-config.json and edit it."
    exit 1
}

$config = Get-Content $ConfigFile -Encoding UTF8 | ConvertFrom-Json
$p4User  = $config.self_watch.p4_user
$repos   = $config.repos
$hoursBack = if ($HoursBack -gt 0) { $HoursBack } else { $config.self_watch.hours_back }

if (-not $config.self_watch.enabled) {
    Write-Host "[INFO] self_watch disabled in config."
    exit 0
}

if ($repos.Count -eq 0) {
    Write-Host "[ERROR] No repos configured."
    exit 1
}

# ---------- 逐仓库拉取提交 ----------
$since = (Get-Date).AddHours(-$hoursBack).ToString("yyyy/MM/dd:HH:mm:ss")
$allRepoCommits = @()

foreach ($repo in $repos) {
    $stream = $repo.stream
    $label  = if ($repo.label) { $repo.label } else { $repo.name }

    $rawChanges = @(p4 changes -s submitted -t -u $p4User "$stream@$since,@now" 2>&1)
    $changes = @($rawChanges | Where-Object { $_ -match "^Change" })

    if ($changes.Count -eq 0) { continue }

    foreach ($line in $changes) {
        if ($line -notmatch "^Change (\d+) on (\d{4}/\d{2}/\d{2}) (\d{2}:\d{2}:\d{2}) by (\S+) '(.+)") { continue }
        $clNum  = $Matches[1]
        $clDate = $Matches[2]
        $clTime = $Matches[3]

        # 完整描述
        $descLines = @(p4 describe -s $clNum 2>&1)
        $fullDesc = ($descLines | Select-Object -Skip 1 | Where-Object { $_ -match "^\t" } |
                     Select-Object -First 5 | ForEach-Object { $_.TrimStart("`t") }) -join " | "

        # 文件列表
        $fileSection = $false
        $files = @()
        foreach ($dl in $descLines) {
            if ($dl -match "^Affected files") { $fileSection = $true; continue }
            if ($dl -match "^Differences") { break }
            if ($fileSection -and $dl -match "^\.\.\. (//\S+)#(\d+) (\w+)") {
                $files += [PSCustomObject]@{ Path=$Matches[1]; Rev=$Matches[2]; Action=$Matches[3] }
            }
        }

        $fileCount = $files.Count
        $cpp   = @($files | Where-Object { $_.Path -match "\.(cpp|h|inl)$" }).Count
        $bp    = @($files | Where-Object { $_.Path -match "\.(uasset|umap)$" }).Count
        $lua   = @($files | Where-Object { $_.Path -match "\.lua$" }).Count
        $other = $fileCount - $cpp - $bp - $lua

        $tags = [regex]::Matches($fullDesc, '\[([^\]]+)\]') | ForEach-Object { $_.Groups[1].Value }
        $tagStr = if ($tags.Count -gt 0) { $tags -join ", " } else { "none" }

        # diff 临时文件（仅代码文件）
        $diffTmpFile = ""
        $codeFiles = @($files | Where-Object { $_.Path -match "\.(cpp|h|inl|lua)$" })
        if ($codeFiles.Count -gt 0) {
            $rawDiff = @(p4 describe -du $clNum 2>&1)
            $diffStart = ($rawDiff | Select-String -Pattern "^Differences" | Select-Object -First 1).LineNumber
            $diffContent = if ($diffStart) {
                ($rawDiff | Select-Object -Skip $diffStart | Select-Object -First 300) -join "`n"
            } else {
                ($rawDiff | Select-Object -First 300) -join "`n"
            }

            # 对 [add] 操作的 Lua 文件，p4 describe -du 不会展开内容，用 p4 print 补充
            $addedLuaFiles = @($codeFiles | Where-Object { $_.Path -match "\.lua$" -and $_.Action -eq "add" })
            if ($addedLuaFiles.Count -gt 0) {
                $extraContent = @()
                foreach ($lf in $addedLuaFiles) {
                    $fileRef = "$($lf.Path)#$($lf.Rev)"
                    $extraContent += "`n==== $fileRef (text/new) ===="
                    $printLines = @(p4 print -q $fileRef 2>&1 | Select-Object -First 200)
                    $extraContent += ($printLines -join "`n")
                }
                $diffContent += "`n" + ($extraContent -join "`n")
            }

            $diffTmpFile = [System.IO.Path]::GetTempFileName() + ".txt"
            [System.IO.File]::WriteAllText($diffTmpFile, $diffContent, [System.Text.Encoding]::UTF8)
        }

        $allRepoCommits += [PSCustomObject]@{
            Repo        = $label
            CL          = $clNum
            DateTime    = "$clDate $clTime"
            FullDesc    = $fullDesc
            Tags        = $tagStr
            FileCount   = $fileCount
            CPP         = $cpp
            BP          = $bp
            Lua         = $lua
            Other       = $other
            Files       = $files
            DiffTmpFile = $diffTmpFile
        }
    }
}

# ---------- 生成报告 ----------
$period = "$((Get-Date).AddHours(-$hoursBack).ToString('MM/dd HH:mm')) ~ $((Get-Date).ToString('MM/dd HH:mm'))"
$repoLabels = ($repos | ForEach-Object { if ($_.label) { $_.label } else { $_.name } }) -join ", "

$lines = @()
$lines += "[$p4User] P4 Commit Report"
$lines += "Repos: $repoLabels"
$lines += "Period: $period"
$lines += "Total: $($allRepoCommits.Count) commit(s)"
$lines += ""

if ($allRepoCommits.Count -eq 0) {
    $lines += "(no commits in this period)"
}

foreach ($c in $allRepoCommits) {
    $lines += "===================="
    $lines += "[$($c.Repo)] CL $($c.CL)  $($c.DateTime)"
    $lines += "DESC: $($c.FullDesc)"
    $lines += "TAGS: $($c.Tags)"
    $lines += "FILES: $($c.FileCount) total (C++/H: $($c.CPP) | BP: $($c.BP) | Lua: $($c.Lua) | Other: $($c.Other))"
    $lines += "CHANGED:"
    foreach ($f in ($c.Files | Select-Object -First 8)) {
        $short = $f.Path -replace [regex]::Escape($stream.TrimEnd(".")), ""
        $lines += "  [$($f.Action)] $short"
    }
    if ($c.Files.Count -gt 8) { $lines += "  ... +$($c.Files.Count - 8) more" }
    if ($c.DiffTmpFile) { $lines += "DIFF_FILE: $($c.DiffTmpFile)" }
    $lines += ""
}

$report = $lines -join "`n"
Write-Host $report

# diff 路径列表供外层使用
$diffPaths = @($allRepoCommits | Where-Object { $_.DiffTmpFile } | ForEach-Object { $_.DiffTmpFile })
if ($diffPaths.Count -gt 0) {
    Write-Host "DIFF_PATHS:$($diffPaths -join ',')"
}