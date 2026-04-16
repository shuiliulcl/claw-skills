@echo off
title Feishu ChatGPT Bot

echo ================================================
echo   Feishu x ChatGPT Bot - Restarting...
echo ================================================
echo.

for /f "usebackq delims=" %%i in (`python -c "import os; from app_config import settings; workspace = settings.agents_path if getattr(settings, 'agents_path', '') and os.path.isdir(settings.agents_path) else os.path.dirname(os.path.abspath(r'%~dp0bot.py')); print(os.path.join(workspace, 'runtime_data', 'bot.pid'))" 2^>nul`) do set PID_FILE=%%i
if not defined PID_FILE set PID_FILE=%~dp0runtime_data\bot.pid

if exist "%PID_FILE%" (
    set /p OLD_PID=<"%PID_FILE%"
    echo [1/3] Killing old process PID %OLD_PID%...
    taskkill /PID %OLD_PID% /F >nul 2>&1
    del "%PID_FILE%" >nul 2>&1
    timeout /t 1 /nobreak >nul
    echo Done.
) else (
    echo [1/3] No running bot found.
)

echo.
echo [2/3] Starting bot...
echo       Close this window to stop.
echo.

cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0start.ps1" -LocalChat

echo.
echo [3/3] Bot stopped.
pause
