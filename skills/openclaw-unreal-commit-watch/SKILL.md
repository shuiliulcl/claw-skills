---
name: openclaw-unreal-commit-watch
description: Pull updates for a locally cloned Unreal Engine repository, analyze commits from the last 24 hours, and generate a daily Markdown report with focus sections for Animation, Gameplay, and AI related modules. Use this when OpenClaw needs a recurring Unreal source update digest from a local git repository.
---

# OpenClaw Unreal Commit Watch

Use this skill when the goal is to watch a local Unreal Engine source repository, pull the newest changes, and generate a daily report that highlights Animation, Gameplay, and AI work.

## What this skill does

1. Reads a local git repository path from `config/watch_config.json` or from the command line.
2. Runs `git fetch` and tries a safe `git pull --ff-only` when the working tree is clean and the current branch tracks a remote branch.
3. Collects commits from the last 24 hours by default.
4. Classifies commits and changed files into focus buckets:
   - Animation
   - Gameplay
   - AI
5. Writes a Markdown daily report and a JSON raw data file to `output/`.

## Default setup

Edit `config/watch_config.json` and set `repo_path` to your local Unreal repository.

## Run once

```powershell
powershell -ExecutionPolicy Bypass -File ".\run.ps1"
```

Or override the repository path:

```powershell
powershell -ExecutionPolicy Bypass -File ".\run.ps1" -RepoPath "F:\UnrealEngine"
```

## Register daily task

```powershell
powershell -ExecutionPolicy Bypass -File ".\register-task.ps1"
```

## Daily report format

The generated report is a Markdown file with these sections:

1. `Daily Unreal Commit Watch`
   - repo path
   - branch
   - time window
   - fetch / pull result
2. `Topline`
   - total commits in window
   - total authors
   - Animation / Gameplay / AI commit counts
3. `Focus Highlights`
   - one section each for Animation, Gameplay, and AI
   - top commits
   - hotspot files
4. `Other Commits`
   - commits outside the three focus areas
5. `Commit Ledger`
   - compact per-commit list with author, time, subject, and tags
6. `Notes`
   - skipped pull reason
   - dirty working tree warning
   - missing upstream warning

## Safety behavior

- Pull is skipped when the repository has local uncommitted changes.
- Pull is skipped when the current branch is detached or has no upstream.
- The skill never resets, rebases, or discards local work.
