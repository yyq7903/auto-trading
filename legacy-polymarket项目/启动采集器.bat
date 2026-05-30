@echo off
chcp 65001 >nul
title BTC 5M 数据采集器
echo 启动数据采集器...
wsl -d Ubuntu -- bash -c "cd /home/yyq/workspace/btc5m-collector && python3 collect.py"
pause
