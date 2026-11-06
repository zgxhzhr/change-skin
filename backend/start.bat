@echo off
REM ==========================================================================
REM  Change-skin backend launcher
REM
REM  This file is intentionally ASCII-only.
REM  cmd.exe parses .bat files using the system code page (GBK on zh-CN),
REM  NOT the code page set by chcp inside the file. Chinese text saved as
REM  UTF-8 therefore gets split into garbage "commands". All human-facing
REM  Chinese output lives in run.py, which forces UTF-8 on its own streams.
REM ==========================================================================

chcp 65001 >nul
title change-skin backend
cd /d "%~dp0"

set PYTHONIOENCODING=utf-8

where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python not found. Install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

python -u run.py %*

echo.
echo Server stopped.
pause
