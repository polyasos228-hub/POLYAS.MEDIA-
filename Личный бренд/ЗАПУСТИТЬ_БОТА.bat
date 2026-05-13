@echo off
cd /d "%~dp0"
title Polyas Media Bot

python --version >nul 2>&1
if %errorlevel% == 0 (
    python telegram_scheduler_bot.py
    pause
    exit
)

py --version >nul 2>&1
if %errorlevel% == 0 (
    py telegram_scheduler_bot.py
    pause
    exit
)

echo Python not found. Install from https://python.org
pause
