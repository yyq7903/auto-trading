"""
BTC 5M 共享工具
"""
import json, time
from datetime import datetime, timezone, timedelta

CN = timezone(timedelta(hours=8))
DATA_BASE = "C:/Users/yyq/Desktop/自动交易/btc5m数据"


def log(msg, mode="sim", tag=""):
    ts = datetime.now(CN).strftime("%H:%M:%S")
    prefix = "🟡" if mode == "live" else "🔵"
    tag_str = f"[{tag}] " if tag else ""
    print(f"[{ts}] {prefix} {tag_str}{msg}", flush=True)


def notify(msg, mode="sim"):
    notify_dir = f"{DATA_BASE}/{mode}"
    with open(f"{notify_dir}/notify.txt", "a") as f:
        f.write(f"[{datetime.now(CN).strftime('%H:%M:%S')}] {msg}\n")
    log(f"📢 {msg}", mode)


def log_trade(record, mode="sim"):
    trades_file = f"{DATA_BASE}/{mode}/trades.jsonl"
    with open(trades_file, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
