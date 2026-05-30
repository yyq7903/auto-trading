#!/usr/bin/env python3
"""
BTC 5M Live Trader — browser Magic-session execution
完全隔离：独立 config / state / trades / logs
"""
import os, sys, json, time, threading, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

from shared.utils import log, log_trade, CN
from shared.config import Config
from shared.btc_price import get_btc, get_btc_fresh, btc_price_loop, fetch_ptb, extract_tokens, find_market, latest_market_snapshot, fetch_platform_crypto_price
import browser_executor

load_dotenv()

# === 路径 ===
MODE = "live"
TRADER_DIR = Path(__file__).parent
DATA_DIR = Path(f"/mnt/c/Users/yyq/Desktop/自动交易/btc5m数据/{MODE}")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# WebUI 读取的根目录 trades.jsonl
ROOT_TRADES = Path("/mnt/c/Users/yyq/Desktop/自动交易/btc5m数据/trades.jsonl")

STATE_FILE = DATA_DIR / "state.json"
NOTIFY_FILE = DATA_DIR / "notify.txt"

# === 钱包（从共享 .env 读取） ===
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
FUNDER_ADDRESS = os.getenv("FUNDER_ADDRESS", "0x23D779628967Db6D8896031a8Cdf739A9273d201")

# === 数据目录（共享，只读） ===
COLLECTOR_DATA = Path("/mnt/c/Users/yyq/Desktop/自动交易/btc5m数据/shared")
MARKETS_FILE = COLLECTOR_DATA / "markets.jsonl"
BTC_PRICE_FILE = COLLECTOR_DATA / "btc_price.jsonl"

# === 运行时状态 ===
config = Config(str(TRADER_DIR))
cfg = config.data  # 快捷引用
bankroll = 1.01
trade_count = 0
win_count = 0
loss_count = 0
total_withdrawn = 0.0
consecutive_losses = 0
cooldown_until = 0
btc_price = 0.0

executor_ready = False


def load_state():
    global bankroll, trade_count, win_count, loss_count, total_withdrawn, consecutive_losses, cooldown_until
    state = config.load_state()
    bankroll = state.get("bankroll", 1.01)
    trade_count = state.get("trade_count", 0)
    win_count = state.get("win_count", 0)
    loss_count = state.get("loss_count", 0)
    total_withdrawn = state.get("total_withdrawn", 0.0)
    consecutive_losses = state.get("consecutive_losses", 0)
    cooldown_until = state.get("cooldown_until", 0)
    log(f"状态已加载: ${bankroll:.2f}/{trade_count}笔 ({win_count}W/{loss_count}L)", MODE)


def record_skip(slug, reason, remaining=0):
    """记录跳过事件到 trades.jsonl（WebUI 可见）"""
    record = {
        "slug": slug,
        "time": datetime.now(CN).isoformat(),
        "mode": "live",
        "direction": "none",
        "gap": 0,
        "btc_entry": round(btc_price, 2) if btc_price else 0,
        "ptb": 0,
        "buy_price": 0,
        "buy_amount": 0,
        "seconds_left": remaining,
        "won": False,
        "net_profit": 0,
        "status": "skipped",
        "skip_reason": reason,
    }
    try:
        with open(ROOT_TRADES, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except:
        pass


def save_state():
    state = {
        "bankroll": bankroll, "trade_count": trade_count,
        "win_count": win_count, "loss_count": loss_count,
        "total_withdrawn": total_withdrawn,
        "consecutive_losses": consecutive_losses,
        "cooldown_until": cooldown_until,
        "executor_ready": executor_ready,
    }
    config.save_state(state)
    # 同时写入根目录 trader_state.json 供 WebUI 读取
    try:
        root_state = Path("/mnt/c/Users/yyq/Desktop/自动交易/btc5m数据/trader_state.json")
        with open(root_state, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except:
        pass


# === BTC 价格 ===
def btc_update_loop():
    global btc_price
    while True:
        try:
            p = get_btc_fresh(retries=1)
            if p > 0:
                btc_price = p
        except:
            pass
        time.sleep(1)


def load_markets() -> list:
    try:
        if MARKETS_FILE.exists():
            with open(MARKETS_FILE) as f:
                return [json.loads(l) for l in f if l.strip()]
    except:
        pass
    return []


def markets_reader():
    """每5秒加载一次市场数据"""
    while True:
        yield load_markets()
        time.sleep(5)


# === 通知 ===
def notify(msg):
    with open(NOTIFY_FILE, "a") as f:
        f.write(f"[{datetime.now(CN).strftime('%H:%M:%S')}] {msg}\n")
    log(f"📢 {msg}", MODE)


# === 信号检测 ===
def check_signal(markets, slug, now, current_5m):
    """检测交易信号。返回 (direction, buy_price, token_id, gap) 或 None"""
    global btc_price

    ptb = fetch_ptb(slug)
    if ptb <= 0:
        return None

    snap = latest_market_snapshot(slug)
    snap_ts = snap.get("timestamp", "")
    try:
        snap_time = datetime.fromisoformat(snap_ts.replace("Z", "+00:00"))
        snap_age = time.time() - snap_time.timestamp()
    except:
        snap_age = 999
    if snap_age > 30:
        r = current_5m + 300 - now
        record_skip(slug, f"数据太旧{snap_age:.0f}s", r)
        return None

    if snap.get("chainlink_price", 0) > 0:
        btc_price = float(snap["chainlink_price"])
    elif btc_price <= 0:
        btc_price = get_btc_fresh()
    if btc_price <= 0:
        return None

    gap = btc_price - ptb

    # 检查gap阈值
    if abs(gap) < cfg["gap_threshold"]:
        return None

    direction = "Up" if gap > 0 else "Down"
    m = find_market(markets, slug)
    tid_up, tid_down = extract_tokens(m)
    buy_price = 0
    token_id = ""

    remaining = current_5m + 300 - now
    if remaining < 5:
        return None  # 太晚了

    up_p = float(snap.get("up_ask") or snap.get("up_price") or 0)
    down_p = float(snap.get("down_ask") or snap.get("down_price") or 0)
    if direction == "Up":
        buy_price = up_p if 0 < up_p < 1 else 0
        token_id = tid_up
    else:
        buy_price = down_p if 0 < down_p < 1 else 0
        token_id = tid_down

    if buy_price <= 0 or buy_price > 0.99:
        return None
    if buy_price < cfg["min_buy_price"]:
        return None

    return {
        "direction": direction,
        "buy_price": buy_price,
        "token_id": token_id,
        "gap": gap,
        "ptb": ptb,
        "btc_price": btc_price,
        "remaining": remaining,
        "data_age": snap_age,
        "market_data_source": snap.get("market_data_source", ""),
    }


def live_ready_to_trade() -> tuple[bool, str]:
    """Hard gate for real-money execution."""
    global executor_ready
    if cfg.get("paused", True):
        return False, "live 配置已暂停"
    if not cfg.get("armed", False):
        return False, "live 未人工武装"
    executor_ready = browser_executor.check_ready()
    if not executor_ready:
        return False, "浏览器 Magic 执行器未就绪"
    return True, "ready"


# ===== 主循环 =====
def main():
    global executor_ready, btc_price, bankroll, trade_count, win_count, loss_count
    global consecutive_losses, cooldown_until

    log("=" * 50, MODE)
    log("BTC 5M LIVE TRADER", MODE)
    log(f"钱包: {FUNDER_ADDRESS[:10]}...{FUNDER_ADDRESS[-6:]}", MODE)
    log("执行层: Browser Magic Session", MODE)
    log("=" * 50, MODE)

    # 加载配置和状态
    config.load()
    load_state()

    # 检查浏览器 Magic 登录态执行器
    executor_ready = browser_executor.check_ready()
    if not executor_ready:
        log("⚠️ 浏览器 Magic 执行器不可用！继续运行，但不会真实下单", MODE)

    # 启动价格线程
    threading.Thread(target=btc_update_loop, daemon=True).start()

    # 首次等待BTC价格
    time.sleep(3)
    btc_price = get_btc()

    # 主循环
    processed = set()
    market_gen = markets_reader()

    while True:
        try:
            config.load()
            now = int(time.time())
            current_5m = (now // 300) * 300
            slug = f"btc-updown-5m-{current_5m}"
            remaining = current_5m + 300 - now

            # 检查暂停
            if cfg.get("paused", False):
                time.sleep(5)
                continue

            if not cfg.get("armed", False):
                time.sleep(5)
                continue

            # 检查冷却
            if cooldown_until > now:
                time.sleep(3)
                continue

            # 跳过已处理市场
            if slug in processed:
                time.sleep(3)
                continue

            # 策略一窗口：T-entry_second 到 T-5s 持续监听。
            if remaining > cfg["entry_second"]:
                time.sleep(min(remaining - cfg["entry_second"], 5))
                continue

            if remaining <= 5:
                if slug not in processed:
                    record_skip(slug, "T-5 前无策略一信号", remaining)
                    processed.add(slug)
                time.sleep(3)
                continue

            # 加载市场数据
            markets = load_markets()

            # 检查信号
            sig = check_signal(markets, slug, now, current_5m)
            if not sig:
                if remaining % 5 == 0:
                    snap = latest_market_snapshot(slug)
                    ptb = fetch_ptb(slug)
                    cur = float(snap.get("chainlink_price") or btc_price or 0)
                    gap = cur - ptb if ptb > 0 and cur > 0 else 0
                    log(f"监听 {slug} T-{remaining}s gap=${gap:+,.0f} Up={snap.get('up_ask') or snap.get('up_price', 0)} Down={snap.get('down_ask') or snap.get('down_price', 0)}", MODE, tag="LIVE")
                time.sleep(1)
                continue

            direction = sig["direction"]
            buy_price = sig["buy_price"]
            gap = sig["gap"]

            # 计算下注
            min_order_amount = 1.0  # Market order minimum on the Polymarket UI.
            max_live_amount = float(cfg.get("max_live_amount", 1.0))
            bet_size = max(bankroll * cfg["bet_fraction"], min_order_amount)
            bet_size = min(bet_size, max_live_amount)
            if bet_size < min_order_amount:
                log(f"⏭ 最低下单金额${min_order_amount:.2f} > 单笔上限${max_live_amount:.2f}", MODE, tag="LIVE")
                record_skip(slug, f"最低下单金额${min_order_amount:.2f}>上限${max_live_amount:.2f}", remaining)
                processed.add(slug)
                time.sleep(3)
                continue
            size = round(bet_size / buy_price, 2)

            log(f"🎯 信号触发! {slug} gap=${gap:+,.0f} {direction} @{buy_price:.3f} 下注${bet_size:.2f}", MODE, tag="LIVE")

            # ===== 执行下单 =====
            ready, ready_reason = live_ready_to_trade()
            result = {}
            if ready:
                log(f"[Browser] 🚀 市价下单: {direction} ${bet_size:.2f} token={sig['token_id'][:10]}...", MODE)
                result = browser_executor.place_order(direction, bet_size, slug)
                if result.get("success"):
                    log(f"[Browser] ✅ 下单成功: {result.get('status', '')} {result.get('orderID', '')}", MODE)
                else:
                    log(f"[Browser] ❌ 下单失败: {result.get('error', 'unknown')}", MODE)
            else:
                log(f"⏭ {ready_reason}，跳过真实下单", MODE)
                record_skip(slug, ready_reason, remaining)

            # 记录交易
            record = {
                "slug": slug,
                "time": datetime.now(CN).isoformat(),
                "mode": "live",
                "direction": direction,
                "gap": round(gap, 2),
                "btc_entry": round(btc_price, 2),
                "ptb": round(sig["ptb"], 2),
                "buy_price": buy_price,
                "buy_amount": round(bet_size, 2),
                "size": size,
                "data_age": round(sig.get("data_age", 0), 3),
                "market_data_source": sig.get("market_data_source", ""),
                "orderID": result.get("orderID", ""),
                "status": (result.get("status") or "placed") if result.get("success") else ("failed" if ready else "skipped"),
                "executor": "browser_magic" if ready else "none",
                "skip_reason": "" if result.get("success") else (result.get("error") or result.get("errorMsg") or ready_reason),
                "executor_result": result,
            }
            log_trade(record, MODE)
            # 同时写入根目录 trades.jsonl 供 WebUI 读取
            try:
                with open(ROOT_TRADES, "a") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except:
                pass
            processed.add(slug)
            if not result.get("success"):
                save_state()
                time.sleep(3)
                continue

            # 等待结算
            settle_time = current_5m + 300 + 5
            wait = settle_time - time.time()
            if wait > 0:
                log(f"⏳ 等待结算 ({wait:.0f}s)...", MODE)
                time.sleep(wait)

            # ===== 结算 =====
            window_end_ts = current_5m + 300
            platform_price = fetch_platform_crypto_price(current_5m, window_end_ts, max_retries=300, retry_interval=2.0)
            
            btc_final = platform_price.get("closePrice")
            open_price = platform_price.get("openPrice") or sig["ptb"]
            settle_source = platform_price.get("source", "unknown")
            
            if btc_final is None or btc_final <= 0:
                # 平台结算价未返回，标记为待结算
                log(f"⚠️ 平台结算价未返回，标记为 pending: {slug}", MODE, tag="LIVE")
                # 更新交易记录为 pending 状态
                record["settlement_status"] = "pending"
                record["settle_source"] = settle_source
                record["platform_close_price"] = None
                record["btc_final"] = None
                record["exclude_from_backtest"] = True
                try:
                    with open(ROOT_TRADES, "a") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                except:
                    pass
                processed.add(slug)
                continue
            
            # 正确的胜负判断规则：最终价 >= 开盘价则 Up 赢
            actual_winner = "Up" if btc_final >= open_price else "Down"
            won = (direction == actual_winner)
            
            # 更新交易记录
            record["btc_final"] = round(btc_final, 2)
            record["platform_close_price"] = round(btc_final, 2)
            record["settlement_gap"] = round(btc_final - open_price, 2)
            record["actual_winner"] = actual_winner
            record["settlement_status"] = "confirmed"
            record["settle_source"] = settle_source
            record["settle_confirmed_at"] = datetime.now(CN).isoformat()
            record["exclude_from_backtest"] = False
            
            if won:
                profit = bet_size * (1 - buy_price) / buy_price
                bankroll += profit
                win_count += 1
                consecutive_losses = 0
                log(f"✅ 获胜! 利润+${profit:.2f} 余额=${bankroll:.2f}", MODE, tag="LIVE")
            else:
                loss = bet_size
                bankroll -= loss
                loss_count += 1
                consecutive_losses += 1
                log(f"❌ 亏损! -${loss:.2f} 余额=${bankroll:.2f}", MODE, tag="LIVE")

            trade_count += 1
            save_state()

        except KeyboardInterrupt:
            log("🛑 停止", MODE)
            break
        except Exception as e:
            log(f"⚠️ 异常: {e}", MODE)
            time.sleep(5)


if __name__ == "__main__":
    main()
