#!/usr/bin/env python3
"""检查交易通知文件并输出"""
import json
from pathlib import Path

f = Path("/mnt/c/Users/yyq/Desktop/自动交易/btc5m数据/trader_notify.txt")
if f.exists():
    content = f.read_text().strip()
    if content:
        print(content)
        f.unlink()
