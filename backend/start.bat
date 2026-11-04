@echo off
chcp 65001 >nul
title 异世界商城 · 后端

cd /d "%~dp0"

echo ============================================
echo   正在启动异世界商城后端
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [X] 找不到 python，请先安装 Python 3.10+ 并加入 PATH
    pause
    exit /b 1
)

python run.py %*

echo.
echo 服务已停止。
pause
