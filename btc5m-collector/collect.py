"""
collect.py — BTC 5M 数据采集器 v4
数据源:
  - Polymarket SSR (__NEXT_DATA__): PTB + 历史结算结果
  - Polymarket CLOB REST: 初始/保底盘口快照
  - Chainlink RPC (Polygon): 实时 BTC 价格（每秒）
  - Polymarket CLOB WebSocket: Up/Down token 价格增量
数据保存到 Windows 桌面 btc5m数据 文件夹。
"""

import json
import time
import datetime
import threading
import re
import requests
import websocket
from pathlib import Path

# ── 配置 ──
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

# Chainlink BTC/USD on Polygon (Polymarket 结算源)
CHAINLINK_RPC = "https://polygon-bor-rpc.publicnode.com"
CHAINLINK_BTC = "0xc907E116054Ad103354f2D350FD2514433D57F6f"

DATA_DIR = Path("/mnt/c/Users/yyq/Desktop/自动交易/btc5m数据")
DATA_DIR.mkdir(parents=True, exist_ok=True)

ALL_EVENTS = DATA_DIR / "all_events.jsonl"
BTC_PRICE = DATA_DIR / "btc_price.jsonl"
MARKETS = DATA_DIR / "markets.jsonl"

# ── 全局状态 ──
asset_to_side = {}
current_slug = ""
current_tokens = []
current_ptb = 0
last_chainlink_price = 0
last_up_price = 0      # 最新 Up token 价格
last_down_price = 0    # 最新 Down token 价格
last_up_bid = 0
last_up_ask = 0
last_down_bid = 0
last_down_ask = 0
market_count = 0
event_count = 0
btc_count = 0
rest_count = 0
start_time = time.time()
ws_initialized = False
price_lock = threading.Lock()
last_ws_price_at = 0.0


def log(msg):
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_current_slug():
    now = datetime.datetime.now(datetime.timezone.utc)
    minutes = now.minute - (now.minute % 5)
    floored = now.replace(minute=minutes, second=0, microsecond=0)
    ts = int(floored.timestamp())
    return f"btc-updown-5m-{ts}", ts


def write_jsonl(path, entry):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Chainlink 价格（实时，每秒） ──
def get_chainlink_price():
    """从 Polygon RPC 获取 Chainlink BTC/USD 价格"""
    global last_chainlink_price
    try:
        resp = requests.post(CHAINLINK_RPC, json={
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{"to": CHAINLINK_BTC, "data": "0xfeaf968c"}, "latest"],
            "id": 1
        }, timeout=5)
        result = resp.json().get("result", "0x")
        if len(result) > 130:
            hex_data = result[2:]
            answer = int(hex_data[64:128], 16) / 10**8
            if 50000 <= answer <= 150000:
                last_chainlink_price = answer
                return answer
    except:
        pass
    return last_chainlink_price


# ── SSR 数据（PTB + 历史结果） ──
def fetch_ssr_data(slug):
    """从 Polymarket SSR 获取 PTB 和历史结算结果"""
    try:
        r = requests.get(
            f"https://polymarket.com/event/{slug}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )
        if r.status_code != 200:
            return None

        m = re.search(r'__NEXT_DATA__.*?>(.*?)</script>', r.text, re.DOTALL)
        if not m:
            return None

        data = json.loads(m.group(1))
        queries = data.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])

        result = {"ptb": 0, "history": [], "current": {}}

        for q in queries:
            qk = q.get("queryKey", [])
            qd = q.get("state", {}).get("data", {})
            if not qd:
                continue

            # 当前市场的 PTB
            if isinstance(qd, dict) and "eventMetadata" in qd:
                em = qd["eventMetadata"]
                if "priceToBeat" in em:
                    result["ptb"] = float(em["priceToBeat"])

            # 历史结算结果
            if isinstance(qk, list) and "past-results" in str(qk):
                if isinstance(qd, dict) and "data" in qd:
                    results = qd["data"].get("results", [])
                    for hr in results:
                        result["history"].append({
                            "start": hr.get("startTime", ""),
                            "end": hr.get("endTime", ""),
                            "open": float(hr.get("openPrice") or 0),
                            "close": float(hr.get("closePrice") or 0),
                            "outcome": hr.get("outcome", ""),
                            "change_pct": float(hr.get("percentChange", 0)),
                        })

            # 当前实时价格（缓存的）
            if isinstance(qk, list) and "crypto-prices" in str(qk):
                if isinstance(qd, dict):
                    result["current"] = {
                        "open": float(qd.get("openPrice") or 0),
                        "close": float(qd.get("closePrice") or 0),
                    }

        return result if result["ptb"] > 0 else None
    except Exception as e:
        log(f"SSR 错误: {e}")
        return None


# ── 市场元数据（Gamma API） ──
def fetch_market(slug):
    try:
        r = requests.get(f"{GAMMA_API}/markets", params={"slug": slug, "limit": 1}, timeout=10)
        if r.status_code == 200 and r.json():
            m = r.json()[0]
            tokens = json.loads(m.get("clobTokenIds", "[]"))
            if len(tokens) >= 2:
                return {
                    "market_id": m["id"],
                    "question": m.get("question", ""),
                    "token_up": tokens[0],
                    "token_down": tokens[1],
                    "volume": float(m.get("volume24hr", 0) or 0),
                    "liquidity": float(m.get("liquidityNum", 0) or 0),
                }
    except:
        pass
    return None


def _best_book_prices(book):
    bids = []
    asks = []
    for row in book.get("bids", []) or []:
        try:
            bids.append(float(row.get("price", 0) or 0))
        except:
            pass
    for row in book.get("asks", []) or []:
        try:
            asks.append(float(row.get("price", 0) or 0))
        except:
            pass
    return (max(bids) if bids else 0.0), (min(asks) if asks else 0.0)


def fetch_clob_book(token_id):
    """从 CLOB REST 拉取单个 token 的盘口，返回 best bid/ask。"""
    try:
        r = requests.get(f"{CLOB_API}/book", params={"token_id": token_id}, timeout=5)
        if r.status_code != 200:
            return None
        bid, ask = _best_book_prices(r.json())
        if 0 < bid < 1 or 0 < ask < 1:
            return {"bid": bid, "ask": ask}
    except Exception as e:
        log(f"CLOB REST 盘口错误: {e}")
    return None


def apply_price_snapshot(up_bid=None, up_ask=None, down_bid=None, down_ask=None):
    """统一更新可执行买价，买入用 best_ask，不用 UI 展示价或最后成交价。"""
    global last_up_price, last_down_price, last_up_bid, last_up_ask, last_down_bid, last_down_ask
    with price_lock:
        if up_bid:
            last_up_bid = float(up_bid)
        if up_ask:
            last_up_ask = float(up_ask)
            last_up_price = last_up_ask
        if down_bid:
            last_down_bid = float(down_bid)
        if down_ask:
            last_down_ask = float(down_ask)
            last_down_price = last_down_ask


def refresh_clob_snapshot(reason="rest"):
    """用 CLOB REST 做当前市场盘口快照，弥补 WS 首包/断线/延迟。"""
    global rest_count
    if len(current_tokens) < 2 or not current_slug:
        return False
    if reason == "periodic" and time.time() - last_ws_price_at < 3:
        return False
    up = fetch_clob_book(current_tokens[0])
    down = fetch_clob_book(current_tokens[1])
    if not up and not down:
        return False
    apply_price_snapshot(
        up_bid=(up or {}).get("bid"),
        up_ask=(up or {}).get("ask"),
        down_bid=(down or {}).get("bid"),
        down_ask=(down or {}).get("ask"),
    )
    rest_count += 1
    write_jsonl(ALL_EVENTS, {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "slug": current_slug,
        "type": "clob_rest_snapshot",
        "source": reason,
        "up_bid": last_up_bid,
        "up_ask": last_up_ask,
        "down_bid": last_down_bid,
        "down_ask": last_down_ask,
    })
    return True


# ── BTC 价格采集（每秒 Chainlink） ──
_last_btc_entry = {}  # 上次写入btc_price.jsonl的记录
_last_btc_write = 0   # 上次写入时间

def btc_price_loop():
    """每秒从 Chainlink 获取 BTC 价格，但只在价格变化时写入btc_price.jsonl"""
    global btc_count, current_ptb, last_chainlink_price, _last_btc_entry, _last_btc_write

    while True:
        try:
            cl_price = get_chainlink_price()
            if cl_price > 0:
                now = time.time()
                gap = round(cl_price - current_ptb, 2) if current_ptb > 0 else 0
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                with price_lock:
                    up_price = last_up_price
                    down_price = last_down_price
                    up_bid = last_up_bid
                    up_ask = last_up_ask
                    down_bid = last_down_bid
                    down_ask = last_down_ask

                entry = {
                    "timestamp": now_iso,
                    "chainlink_price": cl_price,
                    "price_to_beat": current_ptb,
                    "gap": gap,
                    "slug": current_slug,
                    "up_price": up_price,
                    "down_price": down_price,
                    "up_bid": up_bid,
                    "up_ask": up_ask,
                    "down_bid": down_bid,
                    "down_ask": down_ask,
                    "market_data_source": "clob_book_ws",
                }

                # 写入条件：
                # 1. up/down价格有变化（与上次写入不同）
                # 2. BTC价格有明显变化（>$1）
                # 3. 每5秒强制写一次（保底，确保BTC价格连续）
                should_write = False
                if _last_btc_entry:
                    up_changed = entry["up_price"] != _last_btc_entry.get("up_price")
                    down_changed = entry["down_price"] != _last_btc_entry.get("down_price")
                    btc_changed = abs(entry["chainlink_price"] - _last_btc_entry.get("chainlink_price", 0)) > 1
                    if up_changed or down_changed:
                        entry["fresh"] = True
                        should_write = True
                    elif btc_changed or (now - _last_btc_write >= 5):
                        entry["fresh"] = False
                        should_write = True
                else:
                    entry["fresh"] = True
                    should_write = True

                if should_write:
                    write_jsonl(BTC_PRICE, entry)
                    _last_btc_entry = entry
                    _last_btc_write = now
                    btc_count += 1
        except:
            pass

        time.sleep(max(0, 1.0 - (time.time() % 1)))


# ── WebSocket 事件处理 ──
def switch_market(ws, slug):
    global current_slug, current_tokens, current_ptb, asset_to_side, market_count
    global last_up_price, last_down_price, last_up_bid, last_up_ask, last_down_bid, last_down_ask

    # 同一市场不重复处理
    if slug == current_slug and current_ptb > 0:
        return True

    # Gamma API 获取 token ID
    info = fetch_market(slug)
    if not info:
        return False

    # SSR 获取 PTB + 历史
    ssr = fetch_ssr_data(slug)
    if ssr and ssr["ptb"] > 0:
        ptb = ssr["ptb"]
        # 保存历史结算结果
        for h in ssr["history"]:
            write_jsonl(MARKETS, {
                "type": "history",
                "start": h["start"],
                "end": h["end"],
                "open_price": h["open"],
                "close_price": h["close"],
                "outcome": h["outcome"],
                "change_pct": h["change_pct"],
            })
    else:
        # SSR 失败，用 Chainlink 当前价格作为 PTB
        ptb = get_chainlink_price()
        if ptb <= 0:
            return False

    current_slug = slug
    current_tokens = [info["token_up"], info["token_down"]]
    current_ptb = ptb
    asset_to_side = {info["token_up"]: "up", info["token_down"]: "down"}
    with price_lock:
        last_up_price = last_down_price = 0
        last_up_bid = last_up_ask = last_down_bid = last_down_ask = 0

    write_jsonl(MARKETS, {
        "type": "market_open",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "slug": slug,
        "market_id": info["market_id"],
        "question": info["question"],
        "token_up": info["token_up"],
        "token_down": info["token_down"],
        "price_to_beat": ptb,
        "volume": info["volume"],
        "liquidity": info["liquidity"],
    })

    refresh_clob_snapshot("market_switch")

    try:
        ws.send(json.dumps({
            "assets_ids": current_tokens,
            "type": "market",
            "operation": "subscribe",
            "custom_feature_enabled": True,
        }))
        market_count += 1
        log(f"市场 #{market_count}: {slug} | PTB=${ptb:,.2f} (Chainlink)")
        return True
    except:
        return False


def on_message(ws, message):
    global event_count, last_ws_price_at
    if not message or message.isspace() or message == "pong":
        return
    if "INVALID" in message.upper():
        ws.close()
        return

    try:
        data = json.loads(message)
        events = data if isinstance(data, list) else [data]
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for event in events:
            entry = {"timestamp": now_iso, "slug": current_slug}

            if "price_changes" in event:
                for pc in event["price_changes"]:
                    aid = pc.get("asset_id") or pc.get("asset") or event.get("asset_id") or event.get("asset") or ""
                    side = asset_to_side.get(aid, "unknown")
                    price = pc.get("price")
                    bid = pc.get("best_bid")
                    ask = pc.get("best_ask")
                    
                    # 买入价用 best_ask，不用 last trade price 或 1 - opposite。
                    try:
                        if side == "up":
                            apply_price_snapshot(up_bid=bid, up_ask=ask)
                            last_ws_price_at = time.time()
                        elif side == "down":
                            apply_price_snapshot(down_bid=bid, down_ask=ask)
                            last_ws_price_at = time.time()
                    except:
                        pass
                    
                    write_jsonl(ALL_EVENTS, {
                        **entry, "type": "price_change", "side": side,
                        "price": price, "size": pc.get("size"),
                        "trade_side": pc.get("side"),
                        "best_bid": bid, "best_ask": ask,
                    })
                    event_count += 1
                continue

            if "bids" in event or "asks" in event:
                aid = event.get("asset_id", "")
                side = asset_to_side.get(aid, "unknown")
                bid, ask = _best_book_prices(event)
                if side == "up":
                    apply_price_snapshot(up_bid=bid, up_ask=ask)
                    last_ws_price_at = time.time()
                elif side == "down":
                    apply_price_snapshot(down_bid=bid, down_ask=ask)
                    last_ws_price_at = time.time()
                write_jsonl(ALL_EVENTS, {
                    **entry, "type": "orderbook", "side": side,
                    "bids": event.get("bids", []), "asks": event.get("asks", []),
                })
                event_count += 1
                continue

            if event.get("event_type") == "last_trade_price":
                aid = event.get("asset_id", "")
                side = asset_to_side.get(aid, "unknown")
                write_jsonl(ALL_EVENTS, {
                    **entry, "type": "trade", "side": side,
                    "price": event.get("price"), "size": event.get("size"),
                    "trade_side": event.get("side"),
                })
                event_count += 1
                continue

            write_jsonl(ALL_EVENTS, {**entry, "type": "unknown", "raw": event})
            event_count += 1
    except:
        pass


def on_open(ws):
    global ws_initialized
    log("WebSocket 已连接")

    if not ws_initialized:
        slug, _ = get_current_slug()
        switch_market(ws, slug)
        ws_initialized = True
        threading.Thread(target=lambda: ping_loop(ws), daemon=True).start()
        threading.Thread(target=lambda: check_loop(ws), daemon=True).start()
    else:
        if current_tokens:
            try:
                ws.send(json.dumps({
                    "assets_ids": current_tokens,
                    "type": "market",
                    "operation": "subscribe",
                }))
            except:
                pass


def on_error(ws, error):
    log(f"WS 错误: {error}")


def on_close(ws, code, msg):
    log(f"WS 断开 ({code})")


def ping_loop(ws):
    while ws.sock and ws.sock.connected:
        try:
            ws.send("PING")
        except:
            break
        time.sleep(10)


def check_loop(ws):
    while True:
        time.sleep(15)
        if ws.sock and ws.sock.connected:
            slug, _ = get_current_slug()
            if slug != current_slug:
                switch_market(ws, slug)


def clob_rest_loop():
    while True:
        time.sleep(3)
        try:
            refresh_clob_snapshot("periodic")
        except:
            pass


def stats_loop():
    while True:
        time.sleep(60)
        elapsed = (time.time() - start_time) / 3600
        ev_size = ALL_EVENTS.stat().st_size / 1024 / 1024 if ALL_EVENTS.exists() else 0
        btc_size = BTC_PRICE.stat().st_size / 1024 if BTC_PRICE.exists() else 0
        log(f"[{elapsed:.1f}h] WS事件:{event_count} | REST盘口:{rest_count} | BTC价格:{btc_count} | "
            f"Chainlink=${last_chainlink_price:,.0f} | 文件:{ev_size:.0f}MB+{btc_size:.0f}KB")


def main():
    log("=" * 50)
    log("BTC 5M 数据采集器 v4")
    log(f"数据目录: {DATA_DIR}")
    log(f"价格源: Chainlink RPC (Polygon)")
    log(f"PTB源: Polymarket SSR (__NEXT_DATA__)")
    log("=" * 50)

    threading.Thread(target=btc_price_loop, daemon=True).start()
    log("Chainlink 价格采集线程已启动 (每秒)")

    threading.Thread(target=stats_loop, daemon=True).start()
    threading.Thread(target=clob_rest_loop, daemon=True).start()

    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.run_forever(ping_interval=0, reconnect=True)


if __name__ == "__main__":
    main()
