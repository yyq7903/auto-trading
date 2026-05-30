@echo off
chcp 65001 >nul
title BTC 5M 交易机器人
echo 启动交易机器人（模拟模式）...
wsl -d Ubuntu -- bash -c "cd /home/yyq/workspace/btc5m-trader && python3 trader.py"
pause
