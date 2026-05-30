@echo off
chcp 65001 >nul
title BTC 5M WebUI
echo 启动 WebUI...
echo 打开浏览器访问: http://localhost:8877
wsl -d Ubuntu -- bash -c "cd /home/yyq/workspace/btc5m-webui && python3 -m http.server 8877 --bind 0.0.0.0"
pause
