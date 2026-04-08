param(
    [Parameter(Mandatory = $true)][string]$SkillRoot,
    [Parameter(Mandatory = $true)][string]$ConfigPath,
    [string]$RepoPath = "",
    [int]$LookbackHours = 0
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

function Join-ProcessArgs {
    param([string[]]$Values)

    $quoted = foreach ($value in $Values) {
        if ($null -eq $value) { continue }
        '"' + ($value.Replace('"', '\"')) + '"'
    }
    return ($quoted -join ' ')
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)][string]$Repo,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "git"
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.Arguments = Join-ProcessArgs -Values (@("-C", $Repo) + $Arguments)

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    $exitCode = $process.ExitCode
    $output = @($stdout.Trim(), $stderr.Trim()) | Where-Object { $_ }

    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "git $($Arguments -join ' ') failed: $($output -join "`n")"
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output   = ($output -join "`n").Trim()
    }
}

function Get-FocusDefinitions {
    return [ordered]@{
        Animation = @(
            "animation", "anim", "animgraph", "controlrig", "rig", "skeletal", "retarget", "ik", "pose", "motionmatching", "montage"
        )
        Gameplay = @(
            "gameplay", "ability", "abilities", "character", "combat", "weapon", "player", "pawn", "gamemode", "gamestate", "input", "movement"
        )
        AI = @(
            "ai", "behavior", "behaviortree", "blackboard", "statetree", "eqs", "perception", "navigation", "navmesh", "smartobject", "crowd", "massai"
        )
    }
}

function Get-TagsForCommit {
    param(
        [string]$Subject,
        [string[]]$Files
    )

    $text = (($Subject + "`n" + ($Files -join "`n")).ToLowerInvariant())
    $tags = New-Object System.Collections.Generic.List[string]
    foreach ($entry in (Get-FocusDefinitions).GetEnumerator()) {
        foreach ($keyword in $entry.Value) {
            if ($text -like "*$keyword*") {
                $tags.Add($entry.Key)
                break
            }
        }
    }
    return $tags | Select-Object -Unique
}

function Get-ShortSha {
    param([string]$Sha)
    if ($Sha.Length -le 8) { return $Sha }
    return $Sha.Substring(0, 8)
}

function Add-FileHotspots {
    param(
        [hashtable]$Table,
        [string[]]$Files
    )

    foreach ($file in $Files) {
        if (-not $file) { continue }
        if ($Table.ContainsKey($file)) {
            $Table[$file] += 1
        }
        else {
            $Table[$file] = 1
        }
    }
}

function Format-FocusSection {
    param(
        [string]$Name,
        [System.Collections.IEnumerable]$Commits,
        [int]$TopCommitCount,
        [int]$TopFileCount
    )

    $list = @($Commits)
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("## $Name")
    $lines.Add("")

    if ($list.Count -eq 0) {
        $lines.Add("- No $Name related commits found in this window.")
        $lines.Add("")
        return $lines
    }

    $authors = $list | Select-Object -ExpandProperty author | Sort-Object -Unique
    $fileCounts = @{}
    foreach ($commit in $list) {
        Add-FileHotspots -Table $fileCounts -Files $commit.files
    }
    $topFiles = $fileCounts.GetEnumerator() | Sort-Object -Property @{ Expression = "Value"; Descending = $true }, @{ Expression = "Name"; Descending = $false } | Select-Object -First $TopFileCount

    $lines.Add("- Commits: $($list.Count)")
    $lines.Add("- Authors: $($authors.Count)")
    $lines.Add("- Top files:")
    if ($topFiles.Count -eq 0) {
        $lines.Add("  - none")
    }
    else {
        foreach ($item in $topFiles) {
            $lines.Add("  - $($item.Name) ($($item.Value))")
        }
    }
    $lines.Add("- Commit highlights:")
    foreach ($commit in ($list | Select-Object -First $TopCommitCount)) {
        $lines.Add("  - [$($commit.short_sha)] $($commit.subject) | $($commit.author) | $($commit.date)")
    }
    $lines.Add("")
    return $lines
}

function Resolve-RepoPath {
    param(
        [string]$ConfigRepoPath,
        [string]$OverrideRepoPath
    )

    $selected = if ($OverrideRepoPath) { $OverrideRepoPath } else { $ConfigRepoPath }
    if (-not $selected) {
        throw "repo_path is empty. Set it in config/watch_config.json or pass -RepoPath."
    }
    return [System.IO.Path]::GetFullPath($selected)
}

function Invoke-GitWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Repo,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [int]$RetryCount = 1,
        [int]$DelaySeconds = 0
    )

    $attempt = 0
    $lastResult = $null
    while ($attempt -lt $RetryCount) {
        $attempt += 1
        $lastResult = Invoke-Git -Repo $Repo -Arguments $Arguments -AllowFailure
        if ($lastResult.ExitCode -eq 0) {
            return [pscustomobject]@{
                ExitCode = 0
                Output = $lastResult.Output
                Attempts = $attempt
            }
        }
        if ($attempt -lt $RetryCount -and $DelaySeconds -gt 0) {
            Start-Sleep -Seconds $DelaySeconds
        }
    }

    return [pscustomobject]@{
        ExitCode = if ($null -ne $lastResult) { $lastResult.ExitCode } else { 1 }
        Output = if ($null -ne $lastResult) { $lastResult.Output } else { "" }
        Attempts = $attempt
    }
}

$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$resolvedRepo = Resolve-RepoPath -ConfigRepoPath ([string]$config.repo_path) -OverrideRepoPath $RepoPath
$hours = if ($LookbackHours -gt 0) { $LookbackHours } else { [int]$config.lookback_hours }
$outputRoot = Join-Path $SkillRoot ([string]$config.output_dir)
$fetchRetryCount = [Math]::Max(1, [int]$config.fetch_retry_count)
$fetchRetryDelaySeconds = [Math]::Max(0, [int]$config.fetch_retry_delay_seconds)
$topCommitCount = [int]$config.top_commit_count_per_focus
$topFileCount = [int]$config.top_file_count_per_focus

if (-not (Test-Path -LiteralPath $resolvedRepo)) {
    throw "Repository path does not exist: $resolvedRepo"
}

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

$repoCheck = Invoke-Git -Repo $resolvedRepo -Arguments @("rev-parse", "--show-toplevel")
$repoRoot = $repoCheck.Output
$generatedAt = Get-Date
$sinceTime = $generatedAt.AddHours(-1 * $hours)
$sinceSpec = $sinceTime.ToString("yyyy-MM-dd HH:mm:ss")
$notes = New-Object System.Collections.Generic.List[string]

$branchResult = Invoke-Git -Repo $resolvedRepo -Arguments @("rev-parse", "--abbrev-ref", "HEAD")
$branch = $branchResult.Output
$beforeHead = (Invoke-Git -Repo $resolvedRepo -Arguments @("rev-parse", "--short", "HEAD")).Output
$statusResult = Invoke-Git -Repo $resolvedRepo -Arguments @("status", "--porcelain")
$isDirty = [bool]$statusResult.Output
$upstreamResult = Invoke-Git -Repo $resolvedRepo -Arguments @("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") -AllowFailure
$upstream = if ($upstreamResult.ExitCode -eq 0) { $upstreamResult.Output } else { "" }

$fetchResult = Invoke-GitWithRetry -Repo $resolvedRepo -Arguments @("fetch", "--all", "--prune") -RetryCount $fetchRetryCount -DelaySeconds $fetchRetryDelaySeconds
$pullStatus = "skipped"
$fetchStatus = "completed"

if ($fetchResult.ExitCode -ne 0) {
    throw "git fetch failed after $($fetchResult.Attempts) attempt(s). Details: $($fetchResult.Output)"
}

if ($branch -eq "HEAD") {
    $notes.Add("Pull skipped because the repository is in detached HEAD state.")
}
elseif (-not $upstream) {
    $notes.Add("Pull skipped because the current branch has no upstream.")
}
elseif ($isDirty) {
    $notes.Add("Pull skipped because the working tree has local changes.")
}
else {
    $pullResult = Invoke-Git -Repo $resolvedRepo -Arguments @("pull", "--ff-only")
    if ($pullResult.ExitCode -eq 0) {
        $pullStatus = if ($pullResult.Output) { $pullResult.Output } else { "Already up to date." }
    }
}

$afterHead = (Invoke-Git -Repo $resolvedRepo -Arguments @("rev-parse", "--short", "HEAD")).Output
$logFormat = "%H%x1f%an%x1f%ad%x1f%s"
$logResult = Invoke-Git -Repo $resolvedRepo -Arguments @("log", "--since=$sinceSpec", "--date=iso-strict", "--pretty=format:$logFormat")
$commitLines = @()
if ($logResult.Output) {
    $commitLines = $logResult.Output -split "`n"
}

$commits = New-Object System.Collections.Generic.List[object]
foreach ($line in $commitLines) {
    if (-not $line.Trim()) { continue }
    $parts = $line -split [char]0x1f
    if ($parts.Count -lt 4) { continue }
    $sha = $parts[0]
    $author = $parts[1]
    $date = $parts[2]
    $subject = $parts[3]
    $fileResult = Invoke-Git -Repo $resolvedRepo -Arguments @("show", "--pretty=format:", "--name-only", "--no-renames", $sha)
    $files = @()
    if ($fileResult.Output) {
        $files = @($fileResult.Output -split "`n" | Where-Object { $_.Trim() })
    }
    $tags = @(Get-TagsForCommit -Subject $subject -Files $files)
    $commits.Add([pscustomobject]@{
        sha       = $sha
        short_sha = Get-ShortSha -Sha $sha
        author    = $author
        date      = $date
        subject   = $subject
        files     = $files
        tags      = $tags
    })
}

$focusBuckets = [ordered]@{
    Animation = New-Object System.Collections.Generic.List[object]
    Gameplay  = New-Object System.Collections.Generic.List[object]
    AI        = New-Object System.Collections.Generic.List[object]
}
$otherCommits = New-Object System.Collections.Generic.List[object]

foreach ($commit in $commits) {
    $matched = $false
    foreach ($tag in $commit.tags) {
        if ($focusBuckets.Contains($tag)) {
            $focusBuckets[$tag].Add($commit)
            $matched = $true
        }
    }
    if (-not $matched) {
        $otherCommits.Add($commit)
    }
}

$authors = $commits | Select-Object -ExpandProperty author -Unique
$timestamp = $generatedAt.ToString("yyyyMMdd_HHmmss")
$reportPath = Join-Path $outputRoot "unreal_commit_watch_$timestamp.md"
$jsonPath = Join-Path $outputRoot "unreal_commit_watch_$timestamp.json"

$report = New-Object System.Collections.Generic.List[string]
$report.Add("# Daily Unreal Commit Watch")
$report.Add("")
$report.Add("- Repo: $repoRoot")
$report.Add("- Branch: $branch")
$report.Add("- Window: last $hours hours")
$report.Add("- Generated at: $($generatedAt.ToString("yyyy-MM-dd HH:mm:ss"))")
$report.Add("- Fetch: $fetchStatus")
$report.Add("- Pull: $pullStatus")
$report.Add("- HEAD: $beforeHead -> $afterHead")
$report.Add("")
$report.Add("## Topline")
$report.Add("")
$report.Add("- Total commits: $($commits.Count)")
$report.Add("- Total authors: $($authors.Count)")
$report.Add("- Animation commits: $($focusBuckets.Animation.Count)")
$report.Add("- Gameplay commits: $($focusBuckets.Gameplay.Count)")
$report.Add("- AI commits: $($focusBuckets.AI.Count)")
$report.Add("")
$report.Add("## Focus Highlights")
$report.Add("")
foreach ($line in (Format-FocusSection -Name "Animation" -Commits $focusBuckets.Animation -TopCommitCount $topCommitCount -TopFileCount $topFileCount)) {
    $report.Add([string]$line)
}
foreach ($line in (Format-FocusSection -Name "Gameplay" -Commits $focusBuckets.Gameplay -TopCommitCount $topCommitCount -TopFileCount $topFileCount)) {
    $report.Add([string]$line)
}
foreach ($line in (Format-FocusSection -Name "AI" -Commits $focusBuckets.AI -TopCommitCount $topCommitCount -TopFileCount $topFileCount)) {
    $report.Add([string]$line)
}
$report.Add("## Other Commits")
$report.Add("")
if ($otherCommits.Count -eq 0) {
    $report.Add("- No non-focus commits in this window.")
}
else {
    foreach ($commit in $otherCommits) {
        $report.Add("- [$($commit.short_sha)] $($commit.subject) | $($commit.author) | $($commit.date)")
    }
}
$report.Add("")
$report.Add("## Commit Ledger")
$report.Add("")
if ($commits.Count -eq 0) {
    $report.Add("- No commits found in this time window.")
}
else {
    foreach ($commit in $commits) {
        $tagText = if ($commit.tags.Count -gt 0) { ($commit.tags -join ", ") } else { "Other" }
        $report.Add("- [$($commit.short_sha)] [$tagText] $($commit.subject)")
        $report.Add("  - Author: $($commit.author)")
        $report.Add("  - Date: $($commit.date)")
        if ($commit.files.Count -gt 0) {
            $previewFiles = $commit.files | Select-Object -First 6
            $report.Add("  - Files: $($previewFiles -join '; ')")
        }
    }
}
$report.Add("")
$report.Add("## Notes")
$report.Add("")
if ($notes.Count -eq 0) {
    $report.Add("- No additional notes.")
}
else {
    foreach ($note in $notes) {
        $report.Add("- $note")
    }
}
$report.Add("")

[System.IO.File]::WriteAllText($reportPath, ($report -join "`r`n"), [System.Text.Encoding]::UTF8)

$payload = @{
    generated_at = $generatedAt.ToString("o")
    repo_root = $repoRoot
    branch = $branch
    before_head = $beforeHead
    after_head = $afterHead
    pull = $pullStatus
    lookback_hours = $hours
    commit_count = $commits.Count
    authors = @($authors | ForEach-Object { $_ })
    notes = @($notes | ForEach-Object { $_ })
    commits = @($commits | ForEach-Object { $_ })
}
$payload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

Write-Host "Report: $reportPath"
Write-Host "Data:   $jsonPath"
Write-Host "Commits in window: $($commits.Count)"
