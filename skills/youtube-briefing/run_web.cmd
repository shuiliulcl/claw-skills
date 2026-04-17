@echo off
title YouTube Briefing UI
cd /d "%~dp0"
python "%~dp0youtube_briefing_web.py"
if errorlevel 1 (
  echo.
  echo YouTube Briefing UI failed to start.
  pause
)
