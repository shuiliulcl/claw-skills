---
name: x6-game-log-analysis
description: X6Game log analysis workflow. Use when inspecting X6Game.log, UE runtime logs, crash/runtime errors, package streaming errors, patch pak issues, hot update logs, or encrypted X6 game logs that may need the local decrypt tool before rg-based analysis.
---

# X6 Game Log Analysis

## Workflow

Use this skill when analyzing X6Game runtime logs. Combine it with `$x6-search` when searching the workspace for code or asset references related to a log finding.

1. Locate the log file the user mentioned. Common decrypted log path: `F:/UnEncryptLogTool/X6Game.log`.
2. If the log looks encrypted, unreadable, or the user says it needs decryption, use the local decrypt tool:

```powershell
cmd /c 'F:\UnEncryptLogTool\RunUnEncrypt.bat < nul'
```

The batch file lives at `F:/UnEncryptLogTool/RunUnEncrypt.bat`. It runs `PaperEncryptTool.exe -ReplaceSource -ExecDecrypt -SavedLogs=%~dp0`, so it decrypts logs in `F:/UnEncryptLogTool` in place. The batch ends with `pause`; redirecting stdin from `nul` avoids a stuck non-interactive shell.

3. Search logs with narrow, literal `rg` first. Prefer exact class, asset path, map path, spawner ID, entity ID, or timestamp keywords.

```powershell
rg -n -F "BP_SomeActor_C" "F:/UnEncryptLogTool/X6Game.log"
rg -n -i "missing dependency|CreateExport|Failed|Error" "F:/UnEncryptLogTool/X6Game.log"
```

4. Build a timeline around the strongest hit with `rg -C` or line-numbered reads. Prioritize root-cause lines before downstream symptoms.

5. When a log points to Lua, config, package, map, BP, or UE source behavior, search the workspace using the X6 large-repo rules. Do not run unrestricted repo-wide `rg`.

## Report Style

When reporting findings, include:

- The concrete failing log lines or line numbers.
- Whether the actor/map/package was missing, failed to export, spawned then moved/hidden, or was later destroyed/unloaded.
- The likely cause and one or two validation steps.
- Any uncertainty, especially when the log proves a symptom but not the patch/cook cause.
