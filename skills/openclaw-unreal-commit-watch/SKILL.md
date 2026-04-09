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
5. Writes a Chinese-first Markdown daily report and a JSON raw data file to `output/`.

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

The generated report is Chinese-first. Headings, labels, and summary lines are in Chinese. Commit subjects are rendered as `English subject (Chinese summary)` whenever a local summary can be inferred reliably, while file paths remain in their original English.

It contains these sections:

1. `虚幻引擎提交日报`
   - repo path
   - branch
   - time window
   - fetch / pull / analysis ref
2. `今日概览`
   - total commits in window
   - Animation / Gameplay / AI commit counts
3. `重点模块`
   - one section each for Animation, Gameplay, and AI
   - Chinese-first "what changed" bullets
   - commit subject plus Chinese summary
4. `其他提交`
   - commits outside the three focus areas
5. `提交明细`
   - compact per-commit list with Chinese labels and English subjects
6. `备注`
   - skipped pull reason
   - dirty working tree warning
   - missing upstream warning

## Safety behavior

- Fetch failure is treated as a hard failure. The skill does not generate a daily report from stale local data.
- Fetch uses configurable retry attempts and delay values from `config/watch_config.json`.
- Pull is skipped when the repository has local uncommitted changes, but the report still analyzes the latest fetched remote branch when an upstream exists.
- Pull is skipped when the current branch is detached or has no upstream.
- The skill never resets, rebases, or discards local work.
