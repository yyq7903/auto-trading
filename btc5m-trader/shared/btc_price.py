"""
BTC 价格获取 — Chainlink RPC
"""
import time, json, requests, threading
from collections import OrderedDict
from pathlib import Path

CHAINLINK_RPC = "https://polygon-bor-rpc.publicnode.com"
CHAINLINK_CONTRACT = "0xc907E116054Ad103354f2D350FD2514433D57F6f"
CHAINLINK_SIG = "0xfeaf968c"
GAMMA_API = "https://gamma-api.polymarket.com"
DATA_DIR = Path("/mnt/c/Users/yyq/Desktop/自动交易/btc5m数据/shared")
MARKETS_FILE = DATA_DIR / "markets.jsonl"
BTC_PRICE_FILE = DATA_DIR / "btc_price.jsonl"

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
    """从Chainlink获取实时BTC价格"""
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
    return 0.0


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
    """Latest collector snapshot for BTC/market probabilities."""
    for row in reversed(read_jsonl_tail(BTC_PRICE_FILE, 900)):
        if row.get("slug") == slug:
            return row
    return {}


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
    """在市场列表中查找指定slug"""
    for m in markets:
        if m.get("slug") == slug:
            return m
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
