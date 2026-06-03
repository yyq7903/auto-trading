"""
BTC 价格获取 — Chainlink RPC
"""
import time, json, requests, threading, os, os, os, os, os
from collections import OrderedDict
from pathlib import Path

CHAINLINK_RPC = "https://polygon-bor-rpc.publicnode.com"
CHAINLINK_CONTRACT = "0xc907E116054Ad103354f2D350FD2514433D57F6f"
CHAINLINK_SIG = "0xfeaf968c"
GAMMA_API = "https://gamma-api.polymarket.com"
DATA_DIR = Path("C:/Users/yyq/Desktop/自动交易/btc5m数据/shared") if os.name == "nt" else Path("C:/Users/yyq/Desktop/自动交易/btc5m数据/shared" if os.name == "nt" else "C:/Users/yyq/Desktop/自动交易/btc5m数据/shared" if os.name == "nt" else "C:/Users/yyq/Desktop/自动交易/btc5m数据/shared" if os.name == "nt" else "C:/Users/yyq/Desktop/自动交易/btc5m数据/shared" if os.name == "nt" else "/mnt/c/Users/yyq/Desktop/自动交易/btc5m数据/shared")
MARKETS_FILE = DATA_DIR / "markets.jsonl"
BTC_PRICE_FILE = DATA_DIR / "btc_price.jsonl"
TRUE_DIR = Path("C:/Users/yyq/Desktop/自动交易/btc5m数据/true_market") if os.name == "nt" else Path("C:/Users/yyq/Desktop/自动交易/btc5m数据/true_market" if os.name == "nt" else "C:/Users/yyq/Desktop/自动交易/btc5m数据/true_market" if os.name == "nt" else "C:/Users/yyq/Desktop/自动交易/btc5m数据/true_market" if os.name == "nt" else "C:/Users/yyq/Desktop/自动交易/btc5m数据/true_market" if os.name == "nt" else "/mnt/c/Users/yyq/Desktop/自动交易/btc5m数据/true_market")

_btc_cache = None
_btc_lock = threading.Lock()

# 每个窗口的 ptb 缓存（slug → price）
_ptb_cache = OrderedDict()
_PTB_CACHE_MAX = 50


def get_btc() -> float:
    """获取离线BTC价格（读缓存）"""
    global _btc_cache
    return _btc_cache or 0.0


def get_btc_fresh(retries=3) -> float:
    """从Chainlink获取实时BTC价格；RPC受限时回退到Coinbase现货价。"""
    for i in range(retries):
        try:
            r = requests.post(CHAINLINK_RPC, json={
                "jsonrpc": "2.0", "method": "eth_call",
                "params": [{"to": CHAINLINK_CONTRACT, "data": CHAINLINK_SIG}, "latest"], "id": 1
            }, timeout=10)
            if r.status_code == 200:
                hex_str = r.json()["result"][2:]
                price = int(hex_str[64:128], 16) / 1e8
                if price > 0:
                    global _btc_cache
                    with _btc_lock:
                        _btc_cache = price
                    return price
        except Exception as e:
            if i < retries - 1:
                time.sleep(1)
    for url, parser in (
        ("https://api.exchange.coinbase.com/products/BTC-USD/ticker", lambda data: data.get("price")),
        ("https://api.coinbase.com/v2/prices/BTC-USD/spot", lambda data: (data.get("data") or {}).get("amount")),
    ):
        try:
            r = requests.get(url, timeout=3)
            if r.status_code != 200:
                continue
            price = float(parser(r.json()) or 0)
            if price > 0:
                with _btc_lock:
                    _btc_cache = price
                return price
        except Exception:
            pass
    try:
        r = requests.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=3)
        if r.status_code == 200:
            amount = ((r.json().get("data") or {}).get("amount"))
            price = float(amount or 0)
            if price > 0:
                with _btc_lock:
                    _btc_cache = price
                return price
    except Exception:
        pass
    return _btc_cache or 0.0


def btc_price_loop():
    """后台线程：每秒更新BTC价格"""
    while True:
        try:
            get_btc_fresh(retries=1)
        except:
            pass
        time.sleep(1)


def fetch_ptb(slug: str) -> float:
    """Fetch the fixed price-to-beat for a market from collector files."""
    global _ptb_cache

    if slug in _ptb_cache:
        return _ptb_cache[slug]

    ptb = 0.0
    for row in reversed(read_jsonl_tail(MARKETS_FILE, 600)):
        if row.get("slug") == slug and row.get("type") == "market_open":
            ptb = float(row.get("price_to_beat", 0) or 0)
            break

    if ptb <= 0:
        for row in reversed(read_jsonl_tail(BTC_PRICE_FILE, 900)):
            if row.get("slug") == slug:
                ptb = float(row.get("price_to_beat", 0) or 0)
                if ptb > 0:
                    break

    if ptb <= 0:
        for row in reversed(read_jsonl_tail(TRUE_DIR / "windows.jsonl", 600)):
            if row.get("slug") != slug:
                continue
            if row.get("source") == "platform_validation":
                ptb = float(row.get("platform_ptb", 0) or 0)
                if ptb > 0:
                    break
            if row.get("source") == "polymarket_gamma":
                ptb = float(row.get("ptb", 0) or 0)
                if ptb > 0:
                    break

    if ptb <= 0:
        return 0.0

    _ptb_cache[slug] = ptb
    while len(_ptb_cache) > _PTB_CACHE_MAX:
        _ptb_cache.popitem(last=False)

    return ptb


def read_jsonl_tail(path: Path, limit: int = 500) -> list:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        out = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except:
                pass
        return out
    except:
        return []


def latest_market_snapshot(slug: str) -> dict:
    """Latest collector snapshot for BTC/market probabilities.

    Priority: orderbook_ticks.jsonl (best bid/ask) > price_change_ticks.jsonl > price_ticks.jsonl
    """
    # 1) BTC price from price_ticks
    price_row = {}
    for row in reversed(read_jsonl_tail(TRUE_DIR / "price_ticks.jsonl", 1200)):
        if row.get("slug") == slug:
            price_row = row
            break

    # 2) Orderbook from orderbook_ticks (most reliable source with nested up/down)
    ob_row = {}
    for row in reversed(read_jsonl_tail(TRUE_DIR / "orderbook_ticks.jsonl", 200)):
        if row.get("slug") == slug and isinstance(row.get("up"), dict) and isinstance(row.get("down"), dict):
            ob_row = row
            break

    # 3) If orderbook has data, use it directly
    if ob_row and ob_row.get("up") and ob_row.get("down"):
        up_data = ob_row["up"]
        down_data = ob_row["down"]
        up_bid = float(up_data.get("bid1_price", 0) or 0)
        up_ask = float(up_data.get("ask1_price", 0) or 0)
        down_bid = float(down_data.get("bid1_price", 0) or 0)
        down_ask = float(down_data.get("ask1_price", 0) or 0)
        value = float(price_row.get("value", 0) or 0) if price_row else 0
        return {
            "chainlink_price": value,
            "up_price": round((up_bid + up_ask) / 2, 4) if up_bid > 0 else up_ask,
            "down_price": round((down_bid + down_ask) / 2, 4) if down_bid > 0 else down_ask,
            "up_bid": up_bid,
            "up_ask": up_ask,
            "down_bid": down_bid,
            "down_ask": down_ask,
            "market_data_source": "orderbook_ticks",
            "timestamp": ob_row.get("received_at") or ob_row.get("server_ts") or "",
            "value": value,
        }

    # 4) Fallback to price_change_ticks
    changes = {}
    for row in reversed(read_jsonl_tail(TRUE_DIR / "price_change_ticks.jsonl", 1600)):
        if row.get("slug") != slug:
            continue
        side = str(row.get("side", "")).lower()
        if side in ("up", "down") and side not in changes:
            changes[side] = {
                "bid1_price": float(row.get("best_bid", 0) or 0),
                "ask1_price": float(row.get("best_ask", 0) or 0),
                "received_at": row.get("received_at", ""),
            }
        if "up" in changes and "down" in changes:
            break

    if not changes:
        return price_row or {}

    def side_prices(side_data: dict) -> dict:
        bid = float(side_data.get("bid1_price", 0) or 0)
        ask = float(side_data.get("ask1_price", 0) or 0)
        mid = round((bid + ask) / 2, 4) if bid > 0 and ask > 0 else ask or bid or 0
        return {"bid": bid, "ask": ask, "mid": mid}

    up = side_prices(changes.get("up", {}))
    down = side_prices(changes.get("down", {}))
    value = float(price_row.get("value", 0) or 0)
    return {
        **price_row,
        "chainlink_price": value,
        "up_price": up["mid"],
        "down_price": down["mid"],
        "up_bid": up["bid"],
        "up_ask": up["ask"],
        "down_bid": down["bid"],
        "down_ask": down["ask"],
        "market_data_source": "true_market",
        "timestamp": price_row.get("received_at") or price_row.get("server_ts") or "",
    }


def extract_tokens(market):
    """解析token ID"""
    if not market:
        return "", ""
    if market.get("token_up") or market.get("token_down"):
        return market.get("token_up", ""), market.get("token_down", "")
    tid_up, tid_down = "", ""
    tokens = market.get("tokens", [])
    for t in tokens:
        tid = t.get("token_id", "")
        ot = t.get("outcome", "")
        if ot.lower() == "up":
            tid_up = tid
        elif ot.lower() == "down":
            tid_down = tid
    if not tid_up or not tid_down:
        for t in tokens:
            tid = t.get("token_id", "")
            if not tid_up:
                tid_up = tid
            elif not tid_down:
                tid_down = tid
    return tid_up, tid_down


def find_market(markets, slug: str) -> dict:
    """在市场列表中查找指定slug，回退到 true_market/windows.jsonl"""
    for m in markets:
        if m.get("slug") == slug:
            return m
    # 回退：从 true_market/windows.jsonl 获取 token 信息
    for row in reversed(read_jsonl_tail(TRUE_DIR / "windows.jsonl", 200)):
        if row.get("slug") == slug and row.get("source") == "polymarket_gamma":
            return row
    return {}


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
    
    如果获取失败返回:
        {
            "openPrice": None,
            "closePrice": None,
            "completed": False,
            "source": "polymarket_crypto_price_api",
            "error": str
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
