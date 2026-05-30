@echo off
chcp 65001 >nul
title Polymarket Executor Launcher
echo ============================================
echo   Polymarket Browser Executor
echo   Launcher Mode: 自动保活 + 热重启
echo   Port: 8789
echo ============================================
echo   关闭此窗口 = 停止所有服务
echo ============================================
echo.
python C:\temp\executor_launcher.py
pause
