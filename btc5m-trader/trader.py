#!/usr/bin/env python3
"""
BTC 5M 自动交易机器人
策略: gap决定方向，价格可执行即入场
  1. gap≥阈值 → 正向买Up，负向买Down
  2. Token价格 0.01<p<0.99 → 可执行
  3. 入场窗口 T-25s 到 T-5s，满足条件立刻入场
支持模拟(sim)和实盘(live)
配置热加载: 修改 config.json 后10秒内生效
"""

import os
import sys
import json
import time
import threading
import requests
import re
import websocket
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

# ============================================================
# 初始化
# ============================================================

load_dotenv()

CN = timezone(timedelta(hours=8))
DATA_DIR = Path("/mnt/c/Users/yyq/Desktop/自动交易/btc5m数据")
TRADES_FILE = DATA_DIR / "trades.jsonl"
STATE_FILE = DATA_DIR / "trader_state.json"
CONFIG_FILE = Path(__file__).parent / "config.json"
SSR_BASE = "https://polymarket.com/event"

# 钱包配置（从 .env 读取，不可通过 WebUI 修改）
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
FUNDER_ADDRESS = os.getenv("FUNDER_ADDRESS", "0x5d1F53aAd4E3Cae642Ad125d02041A81E593CC3c")

# 浏览器执行器配置（Playwright Chrome 自动化）
# 浏览器执行器 URL（WSL→Windows 宿主机）
_WIN_HOST = os.popen("ip route 2>/dev/null | grep default | awk '{print $3}'").read().strip() or "172.18.16.1"
BROWSER_EXECUTOR_URL = f"http://{_WIN_HOST}:8789"
clob_client = None  # SDK 客户端（备用）
browser_executor_ok = False  # 浏览器执行器是否就绪

# ============================================================
# 可热加载的策略参数
# ============================================================

config = {
    "entry_second": 25,
    "gap_threshold": 10,
    "min_buy_price": 0.60,
    "bet_fraction": 1.0,
    "withdraw_mode": "none",
    "max_consecutive_losses": 1,
    "cooldown_seconds": 0,
    "mode": "sim",
    "initial_capital": 1.0,
    "paused": False,
}
config_mtime = 0

# 多策略管理
strategies = {
    "1": {"name": "策略一（默认）", "params": {"entry_second": 25, "gap_threshold": 10, "min_buy_price": 0.60, "bet_fraction": 1.0, "cooldown_seconds": 0}},
    "2": {"name": "策略二（回测最优）", "params": {"entry_second": 10, "gap_threshold": 50, "min_buy_price": 0.55, "bet_fraction": 0.50, "cooldown_seconds": 0}},
    "3": {"name": "策略三", "params": {"entry_second": 20, "gap_threshold": 20, "min_buy_price": 0.60, "bet_fraction": 0.25, "cooldown_seconds": 0}},
    "4": {"name": "策略四", "params": {"entry_second": 15, "gap_threshold": 30, "min_buy_price": 0.65, "bet_fraction": 0.25, "cooldown_seconds": 0}},
    "5": {"name": "策略五", "params": {"entry_second": 30, "gap_threshold": 15, "min_buy_price": 0.60, "bet_fraction": 0.50, "cooldown_seconds": 0}}
}
active_strategy_id = "1"

def load_config():
    """热加载配置文件（支持多策略）"""
    global config, config_mtime, strategies, active_strategy_id
    try:
        mt = CONFIG_FILE.stat().st_mtime
        if mt != config_mtime:
            with open(CONFIG_FILE) as f:
                new = json.load(f)
            
            # 检查是否是新格式（包含strategies）
            if "strategies" in new:
                strategies = new["strategies"]
                active_strategy_id = new.get("active_strategy", "1")
                
                # 获取当前活跃策略的参数
                active = strategies.get(active_strategy_id, {})
                params = active.get("params", {})
                
                # 更新config（兼容旧代码）
                old = config.copy()
                config["entry_second"] = max(5, min(60, int(params.get("entry_second", 25))))
                config["gap_threshold"] = max(0, min(100, int(params.get("gap_threshold", 10))))
                config["min_buy_price"] = max(0.50, min(0.95, float(params.get("min_buy_price", 0.60))))
                config["bet_fraction"] = float(params.get("bet_fraction", 1.0))
                if config["bet_fraction"] not in (1.0, 0.50, 0.25):
                    config["bet_fraction"] = 1.0
                config["cooldown_seconds"] = max(0, min(3600, int(params.get("cooldown_seconds", 0))))
                
                # 全局配置
                config["withdraw_mode"] = new.get("withdraw_mode", "none")
                if config["withdraw_mode"] not in ("none", "half", "all"):
                    config["withdraw_mode"] = "none"
                config["max_consecutive_losses"] = max(1, min(5, int(new.get("max_consecutive_losses", 1))))
                config["mode"] = new.get("mode", "sim")
                if config["mode"] not in ("sim", "live"):
                    config["mode"] = "sim"
                config["initial_capital"] = max(1, min(10000, float(new.get("initial_capital", 1.0))))
                config["paused"] = bool(new.get("paused", False))
                
                config_mtime = mt
                strategy_name = active.get("name", f"策略{active_strategy_id}")
                if config != old:
                    log(f"⚙️ 切换到 [{strategy_name}]: T-{config['entry_second']}s gap≥${config['gap_threshold']} 概率≥{config['min_buy_price']:.2f} bet={config['bet_fraction']*100:.0f}%")
            else:
                # 旧格式兼容
                old = config.copy()
                config["entry_second"] = max(5, min(60, int(new.get("entry_second", 25))))
                config["gap_threshold"] = max(0, min(100, int(new.get("gap_threshold", 10))))
                config["min_buy_price"] = max(0.50, min(0.95, float(new.get("min_buy_price", 0.60))))
                config["bet_fraction"] = float(new.get("bet_fraction", 1.0))
                if config["bet_fraction"] not in (1.0, 0.50, 0.25):
                    config["bet_fraction"] = 1.0
                config["withdraw_mode"] = new.get("withdraw_mode", "none")
                if config["withdraw_mode"] not in ("none", "half", "all"):
                    config["withdraw_mode"] = "none"
                config["max_consecutive_losses"] = max(1, min(5, int(new.get("max_consecutive_losses", 1))))
                config["cooldown_seconds"] = max(0, min(3600, int(new.get("cooldown_seconds", 0))))
                config["mode"] = new.get("mode", "sim")
                if config["mode"] not in ("sim", "live"):
                    config["mode"] = "sim"
                config["initial_capital"] = max(1, min(10000, float(new.get("initial_capital", 1.0))))
                config["paused"] = bool(new.get("paused", False))
                config_mtime = mt
                if config != old:
                    log(f"⚙️ 配置已更新: T-{config['entry_second']}s gap≥${config['gap_threshold']} 概率≥{config['min_buy_price']:.2f} bet={config['bet_fraction']*100:.0f}% 提利={config['withdraw_mode']} 模式={config['mode']}")
    except FileNotFoundError:
        save_config()
    except Exception as e:
        log(f"⚠️ 配置加载失败: {e}")

def save_config():
    """保存当前配置到文件（新格式）"""
    try:
        # 构建新格式配置
        save_data = {
            "strategies": strategies,
            "active_strategy": active_strategy_id,
            "withdraw_mode": config.get("withdraw_mode", "none"),
            "max_consecutive_losses": config.get("max_consecutive_losses", 1),
            "mode": config.get("mode", "sim"),
            "initial_capital": config.get("initial_capital", 1.0),
            "paused": config.get("paused", False)
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
        global config_mtime
        config_mtime = CONFIG_FILE.stat().st_mtime
    except Exception as e:
        log(f"⚠️ 配置保存失败: {e}")

def get_strategies_info():
    """获取所有策略信息（供API使用）"""
    result = {}
    for sid, s in strategies.items():
        result[sid] = {
            "name": s.get("name", f"策略{sid}"),
            "params": s.get("params", {})
        }
    return {
        "strategies": result,
        "active_strategy": active_strategy_id
    }

def switch_strategy(strategy_id):
    """切换活跃策略"""
    global active_strategy_id
    if strategy_id in strategies:
        active_strategy_id = strategy_id
        save_config()
        load_config()  # 重新加载以应用新策略参数
        return True
    return False

def update_strategy(strategy_id, name=None, params=None):
    """更新策略配置"""
    if strategy_id not in strategies:
        return False
    
    if name is not None:
        strategies[strategy_id]["name"] = name
    if params is not None:
        strategies[strategy_id]["params"].update(params)
    
    save_config()
    if strategy_id == active_strategy_id:
        load_config()  # 如果更新的是当前策略，重新加载
    return True

# ============================================================
# 全局状态
# ============================================================

clob_client = None

# ============================================================
# 双状态: 模拟盘 + 实盘各自独立的数据
# ============================================================
# 当前活跃状态的全局变量（运行时使用）
bankroll = 1.0
total_withdrawn = 0.0
trade_count = 0
win_count = 0
loss_count = 0
consecutive_losses = 0
cooldown_until = 0

# 模拟盘独立状态（持久化）
sim_bankroll = 1.0
sim_total_withdrawn = 0.0
sim_trade_count = 0
sim_win_count = 0
sim_loss_count = 0
sim_consecutive_losses = 0
sim_cooldown_until = 0

# 实盘独立状态（持久化）
live_bankroll = 1.0
live_total_withdrawn = 0.0
live_trade_count = 0
live_win_count = 0
live_loss_count = 0
live_consecutive_losses = 0
live_cooldown_until = 0

def sync_state_to_vars():
    """将当前模式的状态复制到运行时全局变量"""
    global bankroll, total_withdrawn, trade_count, win_count, loss_count, consecutive_losses, cooldown_until
    global sim_bankroll, sim_total_withdrawn, sim_trade_count, sim_win_count, sim_loss_count, sim_consecutive_losses, sim_cooldown_until
    global live_bankroll, live_total_withdrawn, live_trade_count, live_win_count, live_loss_count, live_consecutive_losses, live_cooldown_until
    if config.get("mode") == "live":
        bankroll = live_bankroll; total_withdrawn = live_total_withdrawn
        trade_count = live_trade_count; win_count = live_win_count
        loss_count = live_loss_count
        consecutive_losses = live_consecutive_losses; cooldown_until = live_cooldown_until
    else:
        bankroll = sim_bankroll; total_withdrawn = sim_total_withdrawn
        trade_count = sim_trade_count; win_count = sim_win_count
        loss_count = sim_loss_count
        consecutive_losses = sim_consecutive_losses; cooldown_until = sim_cooldown_until

def sync_vars_to_state():
    """将运行时全局变量保存到当前模式的持久化状态"""
    global live_bankroll, live_total_withdrawn, live_trade_count, live_win_count, live_loss_count, live_consecutive_losses, live_cooldown_until
    global sim_bankroll, sim_total_withdrawn, sim_trade_count, sim_win_count, sim_loss_count, sim_consecutive_losses, sim_cooldown_until
    if config.get("mode") == "live":
        live_bankroll = bankroll; live_total_withdrawn = total_withdrawn
        live_trade_count = trade_count; live_win_count = win_count
        live_loss_count = loss_count
        live_consecutive_losses = consecutive_losses; live_cooldown_until = cooldown_until
    else:
        sim_bankroll = bankroll; sim_total_withdrawn = total_withdrawn
        sim_trade_count = trade_count; sim_win_count = win_count
        sim_loss_count = loss_count
        sim_consecutive_losses = consecutive_losses; sim_cooldown_until = cooldown_until

def log(msg):
    ts = datetime.now(CN).strftime("%H:%M:%S")
    prefix = "🟢" if config["mode"] == "live" else "🔵"
    print(f"[{ts}] {prefix} {msg}", flush=True)

def notify(msg):
    notify_file = DATA_DIR / "trader_notify.txt"
    with open(notify_file, "a") as f:
        f.write(f"[{datetime.now(CN).strftime('%H:%M:%S')}] {msg}\n")
    log(f"📢 {msg}")

# ============================================================
# 加载/保存状态
# ============================================================

def load_state():
    global bankroll, total_withdrawn, trade_count, win_count, loss_count, consecutive_losses, cooldown_until
    global sim_bankroll, sim_total_withdrawn, sim_trade_count, sim_win_count, sim_loss_count, sim_consecutive_losses, sim_cooldown_until
    global live_bankroll, live_total_withdrawn, live_trade_count, live_win_count, live_loss_count, live_consecutive_losses, live_cooldown_until
    global sim_bankroll, sim_total_withdrawn, sim_trade_count, sim_win_count, sim_loss_count, sim_consecutive_losses, sim_cooldown_until
    global live_bankroll, live_total_withdrawn, live_trade_count, live_win_count, live_loss_count, live_consecutive_losses, live_cooldown_until
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            state = json.load(f)
            # 加载模拟盘状态
            sim_state = state.get("sim_state", {})
            sim_bankroll = sim_state.get("bankroll", config.get("initial_capital", 10.0))
            sim_total_withdrawn = sim_state.get("total_withdrawn", 0.0)
            sim_trade_count = sim_state.get("trade_count", 0)
            sim_win_count = sim_state.get("win_count", 0)
            sim_loss_count = sim_state.get("loss_count", 0)
            sim_consecutive_losses = sim_state.get("consecutive_losses", 0)
            sim_cooldown_until = sim_state.get("cooldown_until", 0)
            # 加载实盘状态
            live_state = state.get("live_state", {})
            live_bankroll = live_state.get("bankroll", 1.01)  # 实盘默认用真实余额
            live_total_withdrawn = live_state.get("total_withdrawn", 0.0)
            live_trade_count = live_state.get("trade_count", 0)
            live_win_count = live_state.get("win_count", 0)
            live_loss_count = live_state.get("loss_count", 0)
            live_consecutive_losses = live_state.get("consecutive_losses", 0)
            live_cooldown_until = live_state.get("cooldown_until", 0)
        # 把当前模式的状态复制到运行时全局变量
        sync_state_to_vars()
        log(f"状态已加载: 模拟${sim_bankroll:.2f}/{sim_trade_count}笔 | 实盘${live_bankroll:.2f}/{live_trade_count}笔")

def save_state():
    sync_vars_to_state()  # 先保存当前模式的运行时状态
    with open(STATE_FILE, "w") as f:
        json.dump({
            "last_update": datetime.now(CN).isoformat(),
            "config": config,
            "executor_mode": "browser" if browser_executor_ok else "sdk",
            "executor_available": browser_executor_ok,
            "sim_state": {
                "bankroll": sim_bankroll, "total_withdrawn": sim_total_withdrawn,
                "trade_count": sim_trade_count, "win_count": sim_win_count,
                "loss_count": sim_loss_count,
                "consecutive_losses": sim_consecutive_losses, "cooldown_until": sim_cooldown_until,
            },
            "live_state": {
                "bankroll": live_bankroll, "total_withdrawn": live_total_withdrawn,
                "trade_count": live_trade_count, "win_count": live_win_count,
                "loss_count": live_loss_count,
                "consecutive_losses": live_consecutive_losses, "cooldown_until": live_cooldown_until,
            },
        }, f)

def log_trade(record):
    with open(TRADES_FILE, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def cleanup_trades():
    """交易记录超100条时，保留最近100条（删最早）"""
    try:
        result = subprocess.run(
            ["wc", "-l", str(TRADES_FILE)], capture_output=True, text=True, timeout=2
        )
        count = int(result.stdout.strip().split()[0])
        if count > 100:
            result = subprocess.run(
                ["tail", "-n", "100", str(TRADES_FILE)], capture_output=True, text=True, timeout=2
            )
            with open(TRADES_FILE, "w") as f:
                f.write(result.stdout)
            log(f"🧹 交易记录已清理: {count}条 → 100条（删最早{count-100}条）")
    except:
        pass

# ============================================================
# 数据采集
# ============================================================

btc_price_latest = {"price": None, "ts": 0}
btc_lock = threading.Lock()

# Chainlink BTC/USD on Polygon
CHAINLINK_RPC = "https://polygon-bor-rpc.publicnode.com"
CHAINLINK_BTC = "0xc907E116054Ad103354f2D350FD2514433D57F6f"

def btc_price_loop():
    """每秒从 Chainlink 获取 BTC 价格（与 Polymarket 结算源一致）"""
    global btc_price_latest
    while True:
        try:
            resp = requests.post(CHAINLINK_RPC, json={
                "jsonrpc": "2.0", "method": "eth_call",
                "params": [{"to": CHAINLINK_BTC, "data": "0xfeaf968c"}, "latest"],
                "id": 1
            }, timeout=5)
            result = resp.json().get("result", "0x")
            if len(result) > 130:
                price = int(result[2:][64:128], 16) / 10**8
                if 50000 <= price <= 150000:
                    with btc_lock:
                        btc_price_latest["price"] = price
                        btc_price_latest["ts"] = time.time()
        except:
            pass
        time.sleep(1)

def get_btc():
    with btc_lock:
        return btc_price_latest["price"]

def get_btc_fresh(retries=3):
    """直接从Chainlink获取最新BTC价格，带重试（用于结算）"""
    for i in range(retries):
        try:
            resp = requests.post(CHAINLINK_RPC, json={
                "jsonrpc": "2.0", "method": "eth_call",
                "params": [{"to": CHAINLINK_BTC, "data": "0xfeaf968c"}, "latest"],
                "id": 1
            }, timeout=5)
            result = resp.json().get("result", "0x")
            if len(result) > 130:
                price = int(result[2:][64:128], 16) / 10**8
                if 50000 <= price <= 150000:
                    return price
        except:
            pass
        if i < retries - 1:
            time.sleep(1)
    # 最后尝试从缓存获取
    return get_btc()



# === Polymarket 平台官方价格接口 ===
POLYMARKET_CRYPTO_API = "https://polymarket.com/api/crypto/crypto-price"

def fetch_platform_crypto_price(window_start_ts: int, window_end_ts: int, max_retries: int = 300, retry_interval: float = 2.0) -> dict:
    """
    从 Polymarket 平台获取官方开盘价和结算价。
    
    返回:
        {
            "openPrice": float,  # 开盘价
            "closePrice": float, # 结算价（窗口结束后才有）
            "completed": bool,   # 窗口是否已完成
            "source": "polymarket_crypto_price_api"
        }
    """
    import datetime
    
    # 转换为 UTC ISO 格式
    start_dt = datetime.datetime.fromtimestamp(window_start_ts, tz=datetime.timezone.utc)
    end_dt = datetime.datetime.fromtimestamp(window_end_ts, tz=datetime.timezone.utc)
    
    params = {
        "symbol": "BTC",
        "eventStartTime": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "variant": "fiveminute",
        "endDate": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    
    for attempt in range(max_retries):
        try:
            r = requests.get(POLYMARKET_CRYPTO_API, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                open_price = data.get("openPrice")
                close_price = data.get("closePrice")
                completed = data.get("completed", False)
                
                # 如果需要 closePrice 但还没完成，继续重试
                if close_price is None and not completed:
                    if attempt < max_retries - 1:
                        time.sleep(retry_interval)
                        continue
                
                return {
                    "openPrice": float(open_price) if open_price else None,
                    "closePrice": float(close_price) if close_price else None,
                    "completed": completed,
                    "source": "polymarket_crypto_price_api"
                }
            else:
                if attempt < max_retries - 1:
                    time.sleep(retry_interval)
                    continue
                return {
                    "openPrice": None,
                    "closePrice": None,
                    "completed": False,
                    "source": "polymarket_crypto_price_api",
                    "error": f"HTTP {r.status_code}"
                }
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(retry_interval)
                continue
            return {
                "openPrice": None,
                "closePrice": None,
                "completed": False,
                "source": "polymarket_crypto_price_api",
                "error": str(e)
            }
    
    return {
        "openPrice": None,
        "closePrice": None,
        "completed": False,
        "source": "polymarket_crypto_price_api",
        "error": "max retries exceeded"
    }

def fetch_ptb(slug):
    """从采集器的 markets.jsonl 读取 PTB（权威数据源），带重试"""
    for attempt in range(3):
        try:
            with open(DATA_DIR / "markets.jsonl") as f:
                for line in f:
                    d = json.loads(line)
                    if d.get("slug") == slug and d.get("type") == "market_open":
                        ptb = d.get("price_to_beat", 0)
                        if ptb > 0:
                            return ptb
        except:
            pass
        if attempt < 2:
            time.sleep(2)  # 等待collector写入
    # 备用：从 btc_price.jsonl 读取
    try:
        with open(DATA_DIR / "btc_price.jsonl") as f:
            for line in f:
                d = json.loads(line)
                if d.get("slug") == slug:
                    ptb = d.get("price_to_beat", 0)
                    if ptb > 0:
                        return ptb
    except:
        pass
    # 最后备用：从 SSR 获取
    try:
        r = requests.get(f"{SSR_BASE}/{slug}", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            import re as re_mod
            m = re_mod.search(r'__NEXT_DATA__.*?>(.*?)</script>', r.text, re.DOTALL)
            if m:
                data = json.loads(m.group(1))
                queries = data.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])
                for q in queries:
                    qd = q.get("state", {}).get("data", {})
                    if isinstance(qd, dict) and "eventMetadata" in qd:
                        ptb = qd["eventMetadata"].get("priceToBeat", 0)
                        if ptb and 50000 <= float(ptb) <= 150000:
                            return float(ptb)
    except:
        pass
    return 0

def find_market(slug):
    try:
        r = requests.get(f"https://gamma-api.polymarket.com/markets?slug={slug}&limit=1", timeout=10)
        data = r.json()
        return data[0] if data else None
    except:
        return None

def extract_tokens(market):
    clob = market.get("clobTokenIds", "")
    if isinstance(clob, str):
        try: ids = json.loads(clob)
        except: return None, None
    elif isinstance(clob, list):
        ids = clob
    else:
        return None, None
    if len(ids) >= 2:
        return ids[0], ids[1]  # up, down (Polymarket: tokens[0]=Up, tokens[1]=Down)
    return None, None

# ============================================================
# Token 价格追踪
# ============================================================

class TokenTracker:
    def __init__(self):
        self.ws = None
        self.token_up = None
        self.token_down = None
        self.up_ask = None
        self.up_bid = None
        self.down_ask = None
        self.down_bid = None
        self.connected = False
        self._lock = threading.Lock()

    def start(self):
        def on_open(ws):
            self.connected = True
            log("CLOB WebSocket 已连接")
            # 重新订阅当前市场（WS断开后订阅丢失）
            with self._lock:
                tu, td = self.token_up, self.token_down
            if tu and td:
                try:
                    ws.send(json.dumps({
                        "assets_ids": [tu, td],
                        "type": "market", "operation": "subscribe"
                    }))
                    log(f"📡 已重新订阅 {tu[:10]}... {td[:10]}...")
                except Exception as e:
                    log(f"⚠️ 重新订阅失败: {e}")

        def on_message(ws, message):
            try:
                data = json.loads(message)
                events = data if isinstance(data, list) else [data]
                for ev in events:
                    for pc in ev.get("price_changes", []):
                        asset_id = pc.get("asset_id", "")
                        best_ask = pc.get("best_ask")
                        best_bid = pc.get("best_bid")
                        with self._lock:
                            if asset_id == self.token_up:
                                if best_ask: self.up_ask = float(best_ask)
                                if best_bid: self.up_bid = float(best_bid)
                            elif asset_id == self.token_down:
                                if best_ask: self.down_ask = float(best_ask)
                                if best_bid: self.down_bid = float(best_bid)
                    if "bids" in ev and "asks" in ev:
                        asset_id = ev.get("asset_id", "")
                        asks = ev.get("asks", [])
                        bids = ev.get("bids", [])
                        with self._lock:
                            if asks:
                                v = float(asks[0]["price"])
                                if asset_id == self.token_up: self.up_ask = v
                                elif asset_id == self.token_down: self.down_ask = v
                            if bids:
                                v = float(bids[0]["price"])
                                if asset_id == self.token_up: self.up_bid = v
                                elif asset_id == self.token_down: self.down_bid = v
            except:
                pass

        def on_error(ws, error):
            log(f"WS 错误: {error}")

        def on_close(ws, code, msg):
            self.connected = False
            # 断开时清除价格数据
            with self._lock:
                self.up_ask = self.up_bid = self.down_ask = self.down_bid = None
            log("WS 断开，重连...")
            time.sleep(2)
            self._connect()

        self.ws = websocket.WebSocketApp(
            "wss://ws-subscriptions-clob.polymarket.com/ws/market",
            on_open=on_open, on_message=on_message,
            on_error=on_error, on_close=on_close,
        )
        threading.Thread(target=self.ws.run_forever, kwargs={"ping_interval": 30, "ping_timeout": 10}, daemon=True).start()
        for _ in range(20):
            if self.connected: return True
            time.sleep(0.5)
        return False

    def _connect(self):
        try: self.ws.close()
        except: pass
        self.start()

    def subscribe(self, token_up, token_down):
        with self._lock:
            if self.token_up and self.ws and self.connected:
                try:
                    self.ws.send(json.dumps({
                        "assets_ids": [self.token_up, self.token_down],
                        "type": "market", "operation": "unsubscribe"
                    }))
                except: pass
            self.token_up = token_up
            self.token_down = token_down
            self.up_ask = self.up_bid = self.down_ask = self.down_bid = None
        if self.ws and self.connected:
            self.ws.send(json.dumps({
                "assets_ids": [token_up, token_down],
                "type": "market", "operation": "subscribe"
            }))

    def get_snapshot(self):
        with self._lock:
            return {
                "up_ask": self.up_ask, "up_bid": self.up_bid,
                "down_ask": self.down_ask, "down_bid": self.down_bid,
            }

# ============================================================
# 下单执行 — 浏览器自动化（主） + SDK（备用）
# ============================================================

# === 浏览器执行器（主执行层） ===
def init_browser_executor():
    """检查 Windows Playwright 执行器是否就绪"""
    global browser_executor_ok
    try:
        r = requests.get(f"{BROWSER_EXECUTOR_URL}/heartbeat", timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get("ready"):
                browser_executor_ok = True
                log(f"[Browser] ✅ 浏览器执行器就绪 ({BROWSER_EXECUTOR_URL})")
                return True
            else:
                log(f"[Browser] ⚠️ 浏览器已连接但未登录: {data.get('last_error', 'unknown')}")
                return False
        else:
            log(f"[Browser] ❌ 执行器返回异常: {r.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        log(f"[Browser] ❌ 无法连接执行器 {BROWSER_EXECUTOR_URL}")
        return False
    except Exception as e:
        log(f"[Browser] ❌ 执行器检查失败: {e}")
        return False


def place_order_browser(direction, amount, slug):
    """通过浏览器执行器下单。返回 {success, error, ...}"""
    try:
        r = requests.post(
            f"{BROWSER_EXECUTOR_URL}/execute",
            json={"direction": direction, "amount": amount, "slug": slug},
            timeout=30,
        )
        return r.json()
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "CONNECTION_REFUSED"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# === SDK 客户端（备用执行层） ===
def init_clob_client():
    global clob_client
    if not PRIVATE_KEY:
        log("[SDK] ⚠️ 未设置 PRIVATE_KEY，SDK 交易不可用")
        return False
    try:
        from py_clob_client_v2.client import ClobClient
        from py_clob_client_v2.clob_types import OrderType

        clob_client = ClobClient(
            host="https://clob.polymarket.com",
            key=PRIVATE_KEY,
            chain_id=137,
            signature_type=2,
            funder=FUNDER_ADDRESS,
        )
        clob_client.set_api_creds(clob_client.create_or_derive_api_key())
        log("[SDK] ✅ CLOB Client V2 初始化成功（备用）")
        return True
    except Exception as e:
        log(f"[SDK] ❌ CLOB Client V2 初始化失败: {e}")
        return False


def place_order_sdk(token_id, side, price, size):
    """通过 SDK 下单。返回 {success, ...} 或 {error: ...}"""
    if not clob_client:
        return {"error": "SDK_NOT_INITIALIZED"}
    try:
        from py_clob_client_v2.clob_types import OrderArgsV2, OrderType
        result = clob_client.create_and_post_order(
            OrderArgsV2(
                price=price, size=size, side=side, token_id=token_id
            ),
            order_type=OrderType.GTC,
        )
        log(f"[SDK] ✅ 下单返回: {type(result).__name__}")
        return result
    except Exception as e:
        log(f"[SDK] ❌ 下单异常: {e}")
        return {"error": str(e)}


def place_order(token_id, direction, buy_price, size, slug):
    """主下单分发：浏览器优先，SDK 备用"""
    if config["mode"] != "live":
        return {"simulated": True, "price": buy_price, "size": size}

    # 主路径：浏览器执行器
    if browser_executor_ok:
        log(f"[Browser] 🚀 下单: {direction} ${buy_price:.3f} x{size} 股 | {slug}")
        result = place_order_browser(direction, buy_price, slug)
        if result.get("success"):
            log(f"[Browser] ✅ 下单成功")
            return {"success": True, "orderID": f"browser_{int(time.time())}", "executor": "browser"}
        else:
            log(f"[Browser] ⚠️ 浏览器下单失败: {result.get('error', 'unknown')}")
            # 失败后降级到 SDK
            log("[SDK] ⏬ 降级到 SDK 备用路径...")

    # 备用路径：SDK
    if clob_client:
        log(f"[SDK] 🚀 下单: {direction} ${buy_price:.3f} x{size} 股 | token={token_id}")
        result = place_order_sdk(token_id, direction, buy_price, size)
        if result.get("error"):
            log(f"[SDK] ❌ 下单失败: {result['error']}")
            return {"error": result["error"]}
        return {"success": True, "orderID": f"sdk_{int(time.time())}", "executor": "sdk"}

    log(f"⚠️ 浏览器和SDK均不可用，跳过下单")
    return {"simulated": True, "price": buy_price, "size": size}

# ============================================================
# 主交易循环
# ============================================================

def main():
    global bankroll, total_withdrawn, trade_count, win_count, loss_count, consecutive_losses, cooldown_until
    global sim_bankroll, sim_total_withdrawn, sim_trade_count, sim_win_count, sim_loss_count, sim_consecutive_losses, sim_cooldown_until
    global live_bankroll, live_total_withdrawn, live_trade_count, live_win_count, live_loss_count, live_consecutive_losses, live_cooldown_until

    log("=" * 50)
    log("BTC 5M 自动交易机器人")
    log(f"模式: {'🔴 实盘' if config['mode'] == 'live' else '🔵 模拟'}")
    log(f"钱包: {FUNDER_ADDRESS[:10]}...{FUNDER_ADDRESS[-6:]}")
    log("执行层: 浏览器自动化(主) + SDK(备用)")
    log("配置热加载: 修改 config.json 后10秒内生效")
    log("=" * 50)

    # 初始化配置和状态
    load_config()  # 从 config.json 读取（如果存在）
    load_state()

    # 初始化执行层：浏览器优先
    init_browser_executor()

    if config["mode"] == "live":
        # 实盘模式：确保至少一个执行层可用
        if not browser_executor_ok:
            log("⚠️ 浏览器执行器不可用，尝试SDK备用...")
            if not init_clob_client():
                log("⚠️ 浏览器和SDK均不可用，切回模拟模式")
        else:
            # 浏览器可用时，SDK作为备用
            init_clob_client()

    threading.Thread(target=btc_price_loop, daemon=True).start()
    time.sleep(2)
    btc_price = get_btc()
    log(f"BTC 价格: ${btc_price:,.0f}" if btc_price else "BTC 价格: 等待获取...")

    tracker = TokenTracker()
    if not tracker.start():
        log("❌ WebSocket 连接失败!")
        return

    processed = set()
    cleanup_counter = 0

    while True:
        try:
            # 每次循环检查配置更新
            load_config()

            # 暂停检查
            if config.get("paused", False):
                time.sleep(5)
                continue

            # 每20个市场清理一次交易记录
            cleanup_counter += 1
            if cleanup_counter >= 20:
                cleanup_counter = 0
                cleanup_trades()

            now = int(time.time())
            current_5m = (now // 300) * 300
            slug = f"btc-updown-5m-{current_5m}"
            seconds_left = current_5m + 300 - now

            if slug in processed:
                next_start = current_5m + 300
                wait = next_start - time.time() + 3
                if wait > 0:
                    time.sleep(wait)
                continue

            if time.time() < cooldown_until:
                remaining = cooldown_until - time.time()
                log(f"⏸ 冷却中... ({remaining:.0f}s)")
                # 冷却期也记录订单，备注冷却中
                skip_record = {
                    "slug": slug,
                    "time": datetime.now(CN).isoformat(),
                    "mode": config["mode"],
                    "direction": "none",
                    "gap": 0,
                    "gap_pct": 0,
                    "btc_entry": 0,
                    "btc_final": 0,
                    "ptb": 0,
                    "buy_price": 0,
                    "buy_prob": 0,
                    "buy_amount": 0,
                    "size": 0,
                    "total_fee": 0,
                    "seconds_left": int(remaining),
                    "won": False,
                    "net_profit": 0,
                    "status": "skipped",
                    "skip_reason": f"冷却中({int(remaining)}s)",
                }
                log_trade(skip_record)
                processed.add(slug)
                time.sleep(min(remaining, 30))
                continue

            market = find_market(slug)
            if not market:
                if seconds_left < 10:
                    processed.add(slug)
                    continue
                time.sleep(10)
                continue

            token_up, token_down = extract_tokens(market)
            if not token_up:
                processed.add(slug)
                continue

            ptb = fetch_ptb(slug)
            if ptb <= 0:
                log(f"⚠️ PTB首次获取失败，将在监控中重试 {slug}")

            start_dt = datetime.fromtimestamp(current_5m, tz=CN).strftime("%H:%M")
            end_dt = datetime.fromtimestamp(current_5m + 300, tz=CN).strftime("%H:%M")
            ptb_str = f"PTB=${ptb:,.0f}" if ptb > 0 else "PTB获取中..."
            log(f"📊 市场 {slug} ({start_dt}-{end_dt}) {ptb_str}")

            tracker.subscribe(token_up, token_down)
            
            # 等待价格数据到达
            time.sleep(2)

            # ===== 动态入场策略 =====
            # 核心：gap决定方向，token价格确认
            # 1. gap≥阈值 → gap方向决定买Up还是买Down
            # 2. token价格≥min_prob → 市场确认方向
            # 3. 入场窗口 T-entry_second 到 T-5s
            entered = False
            last_log_sec = -1
            signal = False

            while True:
                now_inner = int(time.time())
                sec_left = current_5m + 300 - now_inner

                # 超过 T-5s 还没入场 → 跳过
                if sec_left <= 5:
                    break

                # T-entry_second 才开始监控
                if sec_left > config["entry_second"]:
                    time.sleep(1)
                    continue

                # 如果PTB还没获取到，重试
                if ptb <= 0:
                    ptb = fetch_ptb(slug)
                    if ptb <= 0:
                        time.sleep(2)
                        continue

                # 加载最新配置
                load_config()
                gap_th = config["gap_threshold"]
                min_prob = config["min_buy_price"]

                # 获取当前价格
                btc = get_btc()
                snap = tracker.get_snapshot()
                gap = (btc - ptb) if btc else 0
                gap_abs = abs(gap)

                # ===== 核心逻辑：gap决定方向，token价格确认 =====
                up_ask = snap["up_ask"]
                down_ask = snap["down_ask"]
                direction = None
                buy_price = None

                if gap_abs >= gap_th:
                    # gap满足阈值 → gap决定方向
                    if gap > 0:
                        direction = "up"
                        buy_price = up_ask
                        token_id = token_up
                    else:
                        direction = "down"
                        buy_price = down_ask
                        token_id = token_down

                # 每3秒记录一次状态
                if sec_left % 3 == 0 and sec_left != last_log_sec:
                    last_log_sec = sec_left
                    log(f"  T-{sec_left}s | BTC=${btc:,.0f} gap=${gap:+,.0f} | "
                        f"Up={up_ask} Down={down_ask}")

                # ===== 条件检查 =====
                signal = False
                reason = ""

                if not direction:
                    reason = f"价差${gap_abs:.0f}<${gap_th}(未达阈值)"
                elif not buy_price or buy_price <= 0:
                    reason = "无价格数据"
                elif buy_price < 0.01:
                    reason = f"价格{buy_price:.4f}太低"
                elif buy_price > 0.99:
                    reason = f"价格{buy_price:.3f}太高"
                elif buy_price < min_prob:
                    reason = f"概率{buy_price:.0%}<{min_prob:.0%}(不够高)"
                else:
                    signal = True

                if signal:
                    log(f"🎯 信号触发! T-{sec_left}s | gap=${gap:+,.0f} | {direction} @{buy_price:.3f}")
                    break

                time.sleep(1)

            if not signal:
                # 超时未触发，记录跳过
                reason_str = reason if reason else "超时未触发"
                log(f"⏭ {slug} 跳过: {reason_str}")

                skip_sec_left = current_5m + 300 - int(time.time())

                # 等待市场结算，获取结算价
                settle_time = current_5m + 300 + 5
                wait = settle_time - time.time()
                if wait > 0:
                    time.sleep(wait)
                skip_btc_final = get_btc_fresh(retries=2) or 0

                skip_record = {
                    "slug": slug,
                    "time": datetime.now(CN).isoformat(),
                    "mode": config["mode"],
                    "direction": direction or "none",
                    "gap": round(gap, 2),
                    "gap_pct": round(gap / ptb * 100, 4) if ptb else 0,
                    "btc_entry": btc or 0,
                    "btc_final": round(skip_btc_final, 2),
                    "ptb": ptb,
                    "buy_price": buy_price or 0,
                    "buy_prob": round(buy_price, 4) if buy_price else 0,
                    "buy_amount": 0,
                    "size": 0,
                    "total_fee": 0,
                    "seconds_left": skip_sec_left,
                    "won": False,
                    "net_profit": 0,
                    "status": "skipped",
                    "skip_reason": reason_str,
                }
                log_trade(skip_record)
                processed.add(slug)
                time.sleep(3)
                continue

            # ===== 信号触发! 下单 =====
            bet_size_usd = bankroll * config["bet_fraction"]
            size = round(bet_size_usd / buy_price, 2)
            # Polymarket Crypto 手续费: fee = 股数 × 0.07 × 价格 × (1-价格)
            fee_per_share = 0.07 * buy_price * (1 - buy_price)
            total_fee = round(size * fee_per_share, 4)
            # 记录下单时的剩余时间
            seconds_left = current_5m + 300 - int(time.time())

            notify(f"🚀 交易信号! {slug}\n"
                   f"方向: {direction.upper()}\n"
                   f"BTC: ${btc:,.0f} PTB: ${ptb:,.0f}\n"
                   f"价差: ${gap:+,.0f} ({gap/ptb*100:+.3f}%)\n"
                   f"买入价: ${buy_price:.3f} (概率{buy_price*100:.0f}%)\n"
                   f"下注: ${bet_size_usd:.2f} ({size} 股)\n"
                   f"手续费: ${total_fee:.4f}\n"
                   f"剩余: {seconds_left}s")

            result = place_order(token_id, direction, buy_price, size, slug)

            if config["mode"] == "sim" or result.get("simulated"):
                order_id = f"sim_{int(time.time())}"
                filled = True
            elif result.get("success"):
                order_id = result.get("orderID")
                filled = True
            else:
                log(f"❌ 下单失败: {result}")
                processed.add(slug)
                continue

            # 等待结算
            settle_time = current_5m + 300 + 5
            wait = settle_time - time.time()
            if wait > 0:
                log(f"⏳ 等待结算 ({wait:.0f}s)...")
                time.sleep(wait)

            # ===== 结算 =====
            # 从 Polymarket 平台获取官方结算价
            window_end_ts = current_5m + 300
            platform_price = fetch_platform_crypto_price(current_5m, window_end_ts, max_retries=300, retry_interval=2.0)
            
            btc_final = platform_price.get("closePrice")
            open_price = platform_price.get("openPrice") or ptb
            settle_source = platform_price.get("source", "unknown")
            
            if btc_final is None or btc_final <= 0:
                # 平台结算价未返回，标记为待结算
                log(f"⚠️ 平台结算价未返回，标记为 pending: {slug}")
                actual_winner = "unknown"
                won = False
                settlement_status = "pending"
                exclude_from_backtest = True
            else:
                # 正确的胜负判断规则：最终价 >= 开盘价则 Up 赢
                actual_winner = "Up" if btc_final >= open_price else "Down"
                won = (direction == actual_winner)
                settlement_status = "confirmed"
                exclude_from_backtest = False
                log(f"✅ 平台结算: {actual_winner} (btc_final=${btc_final:,.2f} vs open_price=${open_price:,.2f})")

            if won:
                net_profit = size * ((1 - buy_price) - fee_per_share)
                win_count += 1
                consecutive_losses = 0
            else:
                net_profit = -size * (buy_price + fee_per_share)
                loss_count += 1
                consecutive_losses += 1
                # 亏损时重置本金为初始资金
                ic = config.get("initial_capital", 1.0)
                if bankroll + net_profit < ic:
                    bankroll = ic
                    net_profit = 0
                    notify(f"🔄 亏损后本金重置为 ${ic}")

            bankroll += net_profit
            trade_count += 1

            # 提利检查
            withdrawn_this = 0
            wm = config["withdraw_mode"]
            ic = config.get("initial_capital", 10.0)
            if wm == "half" and bankroll >= ic * 2:
                profit = bankroll - ic
                take = profit / 2
                total_withdrawn += take
                withdrawn_this = take
                bankroll -= take
            elif wm == "all" and bankroll > ic:
                profit = bankroll - ic
                total_withdrawn += profit
                withdrawn_this = profit
                bankroll = ic

            save_state()

            record = {
                "slug": slug,
                "time": datetime.now(CN).isoformat(),
                "mode": config["mode"],
                "direction": direction,
                "market_slug": slug,
                "window_start_ts": current_5m,
                "window_end_ts": window_end_ts,
                "market_time": datetime.fromtimestamp(current_5m, CN).strftime("%Y/%m/%d %H:%M") + "-" + datetime.fromtimestamp(window_end_ts, CN).strftime("%H:%M"),
                "open_price": round(open_price, 2),
                "platform_open_price": round(open_price, 2),
                "btc_entry": round(btc, 2),
                "btc_final": round(btc_final, 2) if btc_final else None,
                "platform_close_price": round(btc_final, 2) if btc_final else None,
                "entry_gap": round(gap, 2),
                "settlement_gap": round(btc_final - open_price, 2) if btc_final else None,
                "probability": buy_price,
                "amount": round(bet_size_usd, 2),
                "pnl": round(net_profit, 2),
                "return": round(net_profit / bet_size_usd, 4) if bet_size_usd > 0 else 0,
                "settlement_status": settlement_status,
                "settle_source": settle_source,
                "settle_confirmed_at": datetime.now(CN).isoformat() if settlement_status == "confirmed" else None,
                "skip_reason": "" if settlement_status == "confirmed" else "platform_close_price_missing",
                "exclude_from_backtest": exclude_from_backtest,
                "actual_winner": actual_winner,
                "status": "won" if won else ("lost" if actual_winner != "unknown" else "pending"),
                "buy_price": buy_price,
                "buy_prob": round(buy_price, 4),
                "size": size,
                "fee_per_share": round(fee_per_share, 6),
                "total_fee": total_fee,
                "seconds_left": seconds_left,
                "won": won,
                "net_profit": round(net_profit, 2),
                "bankroll": round(bankroll, 2),
                "total_withdrawn": round(total_withdrawn, 2),
                "withdrawn_this": round(withdrawn_this, 2),
                "config_snapshot": config.copy(),
            }
            log_trade(record)

            emoji = "✅" if won else "❌"
            msg = (f"{emoji} 结算 {'赢' if won else '亏'} ${abs(net_profit):.2f}\n"
                   f"资金: ${bankroll:.2f} | 已提: ${total_withdrawn:.2f}\n"
                   f"战绩: {win_count}W/{loss_count}L ({win_count/trade_count*100:.0f}%)")
            if withdrawn_this > 0:
                msg += f"\n💰 提出利润 ${withdrawn_this:.2f}!"
            notify(msg)

            log(f"{'✅' if won else '❌'} {direction.upper()} → {actual_winner.upper()} | "
                f"{'赢' if won else '亏'} ${abs(net_profit):.2f} | "
                f"资金=${bankroll:.2f} 已提=${total_withdrawn:.2f}")

            processed.add(slug)
            time.sleep(3)

        except KeyboardInterrupt:
            log("用户中断，退出")
            save_state()
            break
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            log(f"❌ 错误: {e}")
            for line in tb.splitlines():
                if line.strip():
                    log(f"   {line.strip()}")
            time.sleep(10)

if __name__ == "__main__":
    main()
