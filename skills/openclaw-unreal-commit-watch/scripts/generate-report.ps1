param(
    [Parameter(Mandatory = $true)][string]$SkillRoot,
    [Parameter(Mandatory = $true)][string]$ConfigPath,
    [string]$RepoPath = "",
    [int]$LookbackHours = 0
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

function UText {
    param([int[]]$Codes)
    return -join ($Codes | ForEach-Object { [char]$_ })
}

function Get-Text {
    param([string]$Key)

    switch ($Key) {
        "report_title" { return UText 0x865A,0x5E7B,0x5F15,0x64CE,0x63D0,0x4EA4,0x65E5,0x62A5 }
        "repo" { return UText 0x4ED3,0x5E93 }
        "branch" { return UText 0x5206,0x652F }
        "window" { return UText 0x65F6,0x95F4,0x7A97,0x53E3 }
        "generated_at" { return UText 0x751F,0x6210,0x65F6,0x95F4 }
        "fetch_status" { return "Fetch " + (UText 0x72B6,0x6001) }
        "pull_status" { return "Pull " + (UText 0x72B6,0x6001) }
        "head_change" { return "HEAD " + (UText 0x53D8,0x5316) }
        "topline" { return UText 0x4ECA,0x65E5,0x6982,0x89C8 }
        "total_commits" { return UText 0x63D0,0x4EA4,0x603B,0x6570 }
        "total_authors" { return UText 0x4F5C,0x8005,0x603B,0x6570 }
        "animation_commits" { return UText 0x52A8,0x753B,0x76F8,0x5173,0x63D0,0x4EA4 }
        "gameplay_commits" { return "Gameplay " + (UText 0x76F8,0x5173,0x63D0,0x4EA4) }
        "ai_commits" { return "AI " + (UText 0x76F8,0x5173,0x63D0,0x4EA4) }
        "focus" { return UText 0x91CD,0x70B9,0x6A21,0x5757 }
        "other" { return UText 0x5176,0x4ED6,0x63D0,0x4EA4 }
        "ledger" { return UText 0x63D0,0x4EA4,0x660E,0x7EC6 }
        "notes" { return UText 0x5907,0x6CE8 }
        "animation" { return UText 0x52A8,0x753B }
        "gameplay" { return "Gameplay" }
        "ai" { return "AI" }
        "recent_none_prefix" { return UText 0x6700,0x8FD1,0x65F6,0x95F4,0x7A97,0x53E3,0x5185,0x6CA1,0x6709,0x53D1,0x73B0,0x4E0E }
        "recent_none_suffix" { return UText 0x76F8,0x5173,0x7684,0x63D0,0x4EA4,0x3002 }
        "related_commits" { return UText 0x76F8,0x5173,0x63D0,0x4EA4,0x6570 }
        "related_authors" { return UText 0x76F8,0x5173,0x4F5C,0x8005,0x6570 }
        "top_files" { return UText 0x70ED,0x70B9,0x6587,0x4EF6 }
        "highlights" { return UText 0x91CD,0x70B9,0x63D0,0x4EA4 }
        "none" { return UText 0x65E0 }
        "other_none" { return UText 0x672C,0x65F6,0x95F4,0x7A97,0x53E3,0x5185,0x6CA1,0x6709,0x843D,0x5728,0x91CD,0x70B9,0x6A21,0x5757,0x4E4B,0x5916,0x7684,0x63D0,0x4EA4,0x3002 }
        "commit_none" { return UText 0x672C,0x65F6,0x95F4,0x7A97,0x53E3,0x5185,0x6CA1,0x6709,0x53D1,0x73B0,0x65B0,0x7684,0x63D0,0x4EA4,0x3002 }
        "author" { return UText 0x4F5C,0x8005 }
        "time" { return UText 0x65F6,0x95F4 }
        "files" { return UText 0x6587,0x4EF6 }
        "no_notes" { return UText 0x65E0,0x989D,0x5916,0x5907,0x6CE8,0x3002 }
        "last_hours_prefix" { return UText 0x6700,0x8FD1 }
        "last_hours_suffix" { return UText 0x5C0F,0x65F6 }
        default { return $Key }
    }
}

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

function Get-FocusDefinitions {
    return [ordered]@{
        Animation = @{
            PathPatterns = @(
                "/plugins/animation/",
                "/controlrig/",
                "/animgraph",
                "/animationblueprint",
                "/skeletalmeshmodelingtools/",
                "/posesearch/",
                "/sequencer/",
                "/moviesceneanimmixer/"
            )
            SubjectPatterns = @(
                "(?i)\banimation\b",
                "(?i)\banimgraph\b",
                "(?i)\bcontrol rig\b",
                "(?i)\bskeletal\b",
                "(?i)\bretarget\b",
                "(?i)\bmontage\b",
                "(?i)\bpose\b",
                "(?i)\bmotion matching\b",
                "(?i)\bsequencer\b"
            )
        }
        Gameplay = @{
            PathPatterns = @(
                "/gameplayabilities/",
                "/gameplaytasks/",
                "/gamefeatures/",
                "/enhancedinput/",
                "/input/",
                "/character",
                "/gameframework/",
                "/player",
                "/pawn",
                "/gamemode",
                "/gamestate"
            )
            SubjectPatterns = @(
                "(?i)\bgameplay\b",
                "(?i)\bability\b",
                "(?i)\babilities\b",
                "(?i)\bcharacter\b",
                "(?i)\bcombat\b",
                "(?i)\bweapon\b",
                "(?i)\binput\b",
                "(?i)\bmovement\b",
                "(?i)\bplayer\b",
                "(?i)\bpawn\b"
            )
        }
        AI = @{
            PathPatterns = @(
                "/aimodule/",
                "/behaviortree/",
                "/blackboard/",
                "/statetree/",
                "/navigation",
                "/navmesh",
                "/smartobject",
                "/massai",
                "/perception",
                "/eqs",
                "/pcg/"
            )
            SubjectPatterns = @(
                "(?i)\bai\b",
                "(?i)\bbehavior tree\b",
                "(?i)\bbehaviortree\b",
                "(?i)\bblackboard\b",
                "(?i)\bstate tree\b",
                "(?i)\bstatetree\b",
                "(?i)\bnavigation\b",
                "(?i)\bnavmesh\b",
                "(?i)\bsmart object\b",
                "(?i)\bmassai\b",
                "(?i)\bperception\b",
                "(?i)\beqs\b",
                "(?i)\bpcg\b"
            )
        }
    }
}

function Get-FocusLabel {
    param([string]$Name)
    switch ($Name) {
        "Animation" { return (Get-Text "animation") }
        "Gameplay" { return (Get-Text "gameplay") }
        "AI" { return (Get-Text "ai") }
        default { return $Name }
    }
}

function Get-GlossaryPairs {
    return @(
        @("fix", (UText 0x4FEE,0x590D)),
        @("improve", (UText 0x6539,0x8FDB)),
        @("update", (UText 0x66F4,0x65B0)),
        @("add", (UText 0x65B0,0x589E)),
        @("remove", (UText 0x79FB,0x9664)),
        @("refactor", (UText 0x91CD,0x6784)),
        @("optimize", (UText 0x4F18,0x5316)),
        @("rename", (UText 0x91CD,0x547D,0x540D)),
        @("revert", (UText 0x56DE,0x9000)),
        @("cleanup", (UText 0x6E05,0x7406)),
        @("clean up", (UText 0x6E05,0x7406)),
        @("support", (UText 0x652F,0x6301)),
        @("enable", (UText 0x542F,0x7528)),
        @("disable", (UText 0x7981,0x7528)),
        @("implement", (UText 0x5B9E,0x73B0)),
        @("animation", (Get-Text "animation")),
        @("animgraph", "AnimGraph"),
        @("control rig", "Control Rig"),
        @("montage", "Montage"),
        @("pose", (UText 0x59FF,0x6001)),
        @("retarget", (UText 0x91CD,0x5B9A,0x5411)),
        @("gameplay ability system", "Gameplay Ability System"),
        @("ability", (UText 0x80FD,0x529B)),
        @("abilities", (UText 0x80FD,0x529B,0x7CFB,0x7EDF)),
        @("character", (UText 0x89D2,0x8272)),
        @("combat", (UText 0x6218,0x6597)),
        @("movement", (UText 0x79FB,0x52A8)),
        @("input", (UText 0x8F93,0x5165)),
        @("behavior tree", "Behavior Tree"),
        @("blackboard", "Blackboard"),
        @("state tree", "StateTree"),
        @("statetree", "StateTree"),
        @("navigation", (UText 0x5BFC,0x822A)),
        @("navmesh", "NavMesh"),
        @("perception", (UText 0x611F,0x77E5)),
        @("ai", "AI"),
        @("logging", (UText 0x65E5,0x5FD7)),
        @("crash", (UText 0x5D29,0x6E83)),
        @("editor", (UText 0x7F16,0x8F91,0x5668)),
        @("plugin", (UText 0x63D2,0x4EF6)),
        @("build", (UText 0x6784,0x5EFA)),
        @("compile", (UText 0x7F16,0x8BD1))
    )
}

function Get-CommitSummaryZh {
    param(
        [string]$Subject,
        [string[]]$Tags
    )

    if (-not $Subject) {
        return ""
    }

    $summary = $Subject
    foreach ($pair in (Get-GlossaryPairs)) {
        $pattern = [regex]::Escape($pair[0])
        $replacement = [string]$pair[1]
        $summary = [regex]::Replace($summary, "(?i)\b$pattern\b", $replacement)
    }

    $summary = $summary -replace "\s+", " "
    $summary = $summary.Trim(" ", "-", "_", "(", ")")

    if ($summary -eq $Subject) {
        if ($Tags.Count -gt 0) {
            $labels = ($Tags | ForEach-Object { Get-FocusLabel -Name $_ }) -join "/"
            return "$labels " + (UText 0x76F8,0x5173,0x6539,0x52A8)
        }
        return UText 0x63D0,0x4EA4,0x5185,0x5BB9,0x6458,0x8981
    }

    return $summary
}

function Format-SubjectWithZh {
    param(
        [string]$Subject,
        [string[]]$Tags
    )

    $zh = Get-CommitSummaryZh -Subject $Subject -Tags $Tags
    if (-not $zh) {
        return $Subject
    }
    return "$Subject ($zh)"
}

function Get-TagsForCommit {
    param(
        [string]$Subject,
        [string[]]$Files
    )

    $filteredFiles = @(Get-ClassificationFiles -Files $Files)
    $normalizedFiles = @($filteredFiles | ForEach-Object { $_.Replace('\', '/').ToLowerInvariant() })
    $subjectText = [string]$Subject
    $tags = New-Object System.Collections.Generic.List[string]
    foreach ($entry in (Get-FocusDefinitions).GetEnumerator()) {
        $matched = $false
        foreach ($pathPattern in $entry.Value.PathPatterns) {
            if ($normalizedFiles | Where-Object { $_ -like "*$pathPattern*" }) {
                $matched = $true
                break
            }
        }
        if (-not $matched) {
            foreach ($subjectPattern in $entry.Value.SubjectPatterns) {
                if ($subjectText -match $subjectPattern) {
                    $matched = $true
                    break
                }
            }
        }
        if ($matched) {
            $tags.Add($entry.Key)
        }
    }
    return $tags | Select-Object -Unique
}

function Get-ClassificationFiles {
    param([string[]]$Files)

    $result = @()
    foreach ($file in $Files) {
        if (-not $file) { continue }
        if (Is-NoiseFileForClassification -FilePath $file) {
            continue
        }
        $result += $file
    }
    return $result
}

function Is-NoiseFileForClassification {
    param([string]$FilePath)

    $name = [System.IO.Path]::GetFileName($FilePath).ToLowerInvariant()
    if ($name -in @("commit.gitdeps.xml", "build.version", "metadata.csv")) {
        return $true
    }
    if ($name.EndsWith(".csproj") -or $name.EndsWith(".sln") -or $name.EndsWith(".vcxproj") -or $name.EndsWith(".props") -or $name.EndsWith(".targets")) {
        return $true
    }
    if ($name -like "*.uplugin" -or $name -like "*.uproject") {
        return $true
    }
    return $false
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

function Get-DisplayFileNames {
    param([string[]]$Files)

    $names = @()
    foreach ($file in $Files) {
        if (-not $file) { continue }
        $name = [System.IO.Path]::GetFileName($file)
        if ($name) {
            $names += $name
        }
    }
    return @($names | Select-Object -Unique)
}

function Format-CommitDate {
    param([string]$DateText)

    if (-not $DateText) {
        return ""
    }

    try {
        $dto = [DateTimeOffset]::Parse($DateText)
        return $dto.ToLocalTime().ToString("yyyy-MM-dd HH:mm")
    }
    catch {
        return $DateText
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
    $label = Get-FocusLabel -Name $Name
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("## $label")
    $lines.Add("")

    if ($list.Count -eq 0) {
        $lines.Add("- " + (Get-Text "recent_none_prefix") + $label + (Get-Text "recent_none_suffix"))
        $lines.Add("")
        return $lines
    }

    $lines.Add("- " + (Get-Text "related_commits") + ": $($list.Count)")
    $lines.Add("- " + (Get-Text "highlights") + ":")
    foreach ($commit in ($list | Select-Object -First $TopCommitCount)) {
        $lines.Add("  - $(Format-SubjectWithZh -Subject $commit.subject -Tags $commit.tags)")
        $lines.Add("    - SHA: $($commit.short_sha)")
        $lines.Add("    - " + (Get-Text "time") + ": $(Format-CommitDate -DateText $commit.date)")
        if ($commit.files.Count -gt 0) {
            $previewFiles = Get-DisplayFileNames -Files ($commit.files | Select-Object -First 3)
            $lines.Add("    - " + (Get-Text "files") + ": $($previewFiles -join '; ')")
        }
    }
    $lines.Add("")
    return $lines
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
$analysisRef = "HEAD"
if ($upstream) {
    $analysisRef = $upstream
    if ($isDirty) {
        $notes.Add("Commit analysis uses fetched upstream reference $upstream because local changes prevented pull.")
    }
}
$logFormat = "%H%x1f%an%x1f%ad%x1f%s"
$logResult = Invoke-Git -Repo $resolvedRepo -Arguments @("log", $analysisRef, "--since=$sinceSpec", "--date=iso-strict", "--pretty=format:$logFormat")
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

$authors = @($commits | Select-Object -ExpandProperty author -Unique)
$timestamp = $generatedAt.ToString("yyyyMMdd_HHmmss")
$reportPath = Join-Path $outputRoot "unreal_commit_watch_$timestamp.md"
$jsonPath = Join-Path $outputRoot "unreal_commit_watch_$timestamp.json"

$report = New-Object System.Collections.Generic.List[string]
$report.Add("# " + (Get-Text "report_title"))
$report.Add("")
$report.Add("- " + (Get-Text "generated_at") + ": $($generatedAt.ToString("yyyy-MM-dd HH:mm:ss"))")
$report.Add("- " + (Get-Text "fetch_status") + ": $fetchStatus")
$report.Add("")
$report.Add("## " + (Get-Text "topline"))
$report.Add("")
$report.Add("- " + (Get-Text "total_commits") + ": $($commits.Count)")
$report.Add("- " + (Get-Text "animation_commits") + ": $($focusBuckets.Animation.Count)")
$report.Add("- " + (Get-Text "gameplay_commits") + ": $($focusBuckets.Gameplay.Count)")
$report.Add("- " + (Get-Text "ai_commits") + ": $($focusBuckets.AI.Count)")
$report.Add("")
$report.Add("## " + (Get-Text "focus"))
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
$report.Add("## " + (Get-Text "other"))
$report.Add("")
if ($otherCommits.Count -eq 0) {
    $report.Add("- " + (Get-Text "other_none"))
}
else {
    foreach ($commit in $otherCommits) {
        $report.Add("- $(Format-SubjectWithZh -Subject $commit.subject -Tags $commit.tags)")
        $report.Add("  - SHA: $($commit.short_sha)")
        $report.Add("  - " + (Get-Text "time") + ": $(Format-CommitDate -DateText $commit.date)")
    }
}
$report.Add("")
$report.Add("## " + (Get-Text "ledger"))
$report.Add("")
if ($commits.Count -eq 0) {
    $report.Add("- " + (Get-Text "commit_none"))
}
else {
    foreach ($commit in $commits) {
        $tagText = if ($commit.tags.Count -gt 0) { (($commit.tags | ForEach-Object { Get-FocusLabel -Name $_ }) -join ", ") } else { (Get-Text "other") }
        $report.Add("- [$($commit.short_sha)] [$tagText] $(Format-SubjectWithZh -Subject $commit.subject -Tags $commit.tags)")
        $report.Add("  - " + (Get-Text "time") + ": $(Format-CommitDate -DateText $commit.date)")
        if ($commit.files.Count -gt 0) {
            $previewFiles = Get-DisplayFileNames -Files ($commit.files | Select-Object -First 6)
            $report.Add("  - " + (Get-Text "files") + ": $($previewFiles -join '; ')")
        }
    }
}
$report.Add("")
$report.Add("## " + (Get-Text "notes"))
$report.Add("")
if ($notes.Count -eq 0) {
    $report.Add("- " + (Get-Text "no_notes"))
}
else {
    foreach ($note in $notes) {
        $report.Add("- $note")
    }
}
$report.Add("- " + (Get-Text "repo") + ": $repoRoot")
$report.Add("- " + (Get-Text "branch") + ": $branch")
$report.Add("- " + (Get-Text "window") + ": " + (Get-Text "last_hours_prefix") + " $hours " + (Get-Text "last_hours_suffix"))
$report.Add("- " + (Get-Text "pull_status") + ": $pullStatus")
$report.Add("- " + (Get-Text "head_change") + ": $beforeHead -> $afterHead")
$report.Add("- Analysis ref: $analysisRef")
$report.Add("")

[System.IO.File]::WriteAllText($reportPath, ($report -join "`r`n"), [System.Text.Encoding]::UTF8)

$payload = @{
    generated_at = $generatedAt.ToString("o")
    repo_root = $repoRoot
    branch = $branch
    before_head = $beforeHead
    after_head = $afterHead
    pull = $pullStatus
    analysis_ref = $analysisRef
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
