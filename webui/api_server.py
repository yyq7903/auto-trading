#!/usr/bin/env python3
import json, time, sys, subprocess, requests, os, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from urllib.parse import parse_qs, urlparse

try:
    import market_integrity
except Exception:
    market_integrity = None

BASE = Path(r"/mnt/c/Users/yyq/Desktop/自动交易")
if os.name == "nt":
    BASE = Path(r"C:\Users\yyq\Desktop\自动交易")
else:
    candidate_base = Path(r"/mnt/c/Users/yyq/Desktop/自动交易")
    if candidate_base.exists():
        BASE = candidate_base

if os.name == "nt":
    BASE = Path.home() / "Desktop" / "\u81ea\u52a8\u4ea4\u6613"

W = BASE / "webui"
STATIC_DIR = W / "dist"
if not STATIC_DIR.exists():
    STATIC_DIR = W
T = BASE / "btc5m-trader"
D = BASE / "btc5m数据"
if os.name == "nt":
    D = BASE / "btc5m数据"
if os.name == "nt":
    D = BASE / "btc5m\u6570\u636e"
TRUE_DIR = D / "true_market"
RUNTIME = BASE / "runtime"
EVENTS_FILE = RUNTIME / "backend_events.jsonl"
CN = timezone(timedelta(hours=8))
LC = T / "live" / "config.json"
SC = T / "sim" / "config.json"
POLYGON_RPC = os.getenv("POLYGON_RPC_URL", "https://polygon-bor-rpc.publicnode.com")
POLYGONSCAN = "https://polygonscan.com"
PUSD_TOKEN = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
if str(T) not in sys.path: sys.path.insert(0, str(T))
LH = {"ok": False}; LH_at = 0.0
PRICE_CACHE = {"value": 0.0, "at": 0.0, "source": ""}
PLATFORM_PRICE_CACHE = {}
TICK_DATA_CACHE = {}
TRADES_CACHE = {}
WINDOWS_CACHE = {}
RESOLUTION_CACHE = {}
LINE_COUNT_CACHE = {}
WALLET_CACHE = {"at": 0.0, "data": None}
SERVICE_CACHE = {}
SAFETY_CACHE = {"at": 0.0, "data": None}
BRIDGE_CACHE = {"at": 0.0, "ok": False}
INTEGRITY_REFRESH = {"running": False, "last_started": 0.0}

def maybe_refresh_integrity(max_age_seconds=300):
    if market_integrity is None:
        return False
    try:
        path = market_integrity.SUMMARY_PATH
        stale = (not path.exists()) or (time.time() - path.stat().st_mtime > max_age_seconds)
    except Exception:
        stale = True
    if not stale or INTEGRITY_REFRESH.get("running"):
        return False
    if time.time() - INTEGRITY_REFRESH.get("last_started", 0) < 60:
        return False

    def _run():
        try:
            market_integrity.generate()
        except Exception:
            pass
        finally:
            INTEGRITY_REFRESH["running"] = False

    INTEGRITY_REFRESH["running"] = True
    INTEGRITY_REFRESH["last_started"] = time.time()
    threading.Thread(target=_run, daemon=True).start()
    return True

def rj(p):
    if not p.exists(): return {}
    try:
        return json.load(open(p, encoding="utf-8-sig"))
    except Exception:
        return {}
def wj(p, d): json.dump(d, open(p,"w",encoding="utf-8"), indent=2, ensure_ascii=False)
def tail_lines(path, n=200, block_size=65536):
    if not path.exists() or n <= 0:
        return []
    try:
        data = b""
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            while pos > 0 and data.count(b"\n") <= n:
                read_size = min(block_size, pos)
                pos -= read_size
                f.seek(pos)
                data = f.read(read_size) + data
        return data.decode("utf-8-sig", errors="ignore").splitlines()[-n:]
    except Exception:
        return []

def tail_jsonl(path, n=200):
    rows = []
    for line in tail_lines(path, n):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows

def file_sig(path):
    try:
        st = path.stat()
        return (st.st_size, getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
    except Exception:
        return (0, 0)

def last_jsonl(p):
    rows = tail_jsonl(p, 1)
    return rows[-1] if rows else {}

def count_lines(p):
    if not p.exists(): return 0
    now = time.time()
    key = str(p)
    cached = LINE_COUNT_CACHE.get(key)
    try:
        stat = p.stat()
    except Exception:
        return 0
    if cached and cached.get("size") == stat.st_size and now - cached.get("at", 0) < 300:
        return cached.get("count", 0)
    try:
        count = 0
        start_time = time.time()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                count += chunk.count(b"\n")
                if time.time() - start_time > 2:  # 2s timeout for counting
                    break
        LINE_COUNT_CACHE[key] = {"at": now, "size": stat.st_size, "count": count}
        return count
    except Exception:
        return cached.get("count", 0) if cached else 0

def data_quality_state():
    q = last_jsonl(TRUE_DIR / "data_quality.jsonl")
    price = last_jsonl(TRUE_DIR / "price_ticks.jsonl")
    book = last_jsonl(TRUE_DIR / "orderbook_ticks.jsonl")
    stats = q.get("stats", {}) if isinstance(q.get("stats"), dict) else {}
    if not q:
        return {
            "collector_running": svc("btc5m-collector"),
            "current_window_quality": "missing",
            "message": "暂未发现真实数据采集状态",
            "stats": {},
        }
    try:
        updated = datetime.fromisoformat(str(q.get("received_at","")).replace("Z","+00:00"))
        age_ms = max(0, int((datetime.now(timezone.utc) - updated).total_seconds() * 1000))
    except Exception:
        age_ms = None
    quality = q.get("current_window_quality","missing")
    remaining = int(q.get("remaining_seconds") or 0)
    official_price_age = iso_age_seconds(price.get("received_at"))
    if age_ms is not None and age_ms > 120_000:
        quality = "stale"
    elif remaining < -30:
        quality = "stale"
    elif official_price_age is not None and official_price_age > 15 and quality == "good":
        quality = "degraded"
    display_price = latest_display_price()
    return {
        **q,
        "collector_running": bool(q.get("collector_running")) and (svc("btc5m-collector") or age_ms is None or age_ms < 90_000),
        "current_window_quality": quality,
        "rtds_degraded": bool(q.get("rtds_degraded")) or (official_price_age is not None and official_price_age > 15),
        "status_age_ms": age_ms,
        "price_last_value": display_price.get("value", price.get("value", 0)),
        "price_last_source": display_price.get("source", price.get("source", "")),
        "official_price_age_seconds": round(official_price_age, 1) if official_price_age is not None else None,
        "display_price_fallback": bool(display_price.get("display_fallback")),
        "orderbook_last_reason": book.get("reason", book.get("event_type", "")),
        "line_counts": {
            "data_quality": stats.get("data_quality", 0),
            "price_ticks": stats.get("price_ticks", 0),
            "orderbook_ticks": stats.get("orderbook_ticks", 0),
            "trade_ticks": stats.get("trade_ticks", 0),
            "market_meta": stats.get("market_meta", 0),
            "resolutions": stats.get("resolutions", 0),
        },
        "stats": stats,
    }

def latest_quality_snapshot():
    q = last_jsonl(TRUE_DIR / "data_quality.jsonl")
    if not q:
        return {}
    try:
        updated = datetime.fromisoformat(str(q.get("received_at","")).replace("Z","+00:00"))
        q["status_age_ms"] = max(0, int((datetime.now(timezone.utc) - updated).total_seconds() * 1000))
    except Exception:
        q["status_age_ms"] = None
    return q

def parse_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default

def iso_age_seconds(value):
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z","+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        return None

def iso_utc(ts):
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""

def latest_true_window():
    for row in reversed(tail_jsonl(TRUE_DIR / "windows.jsonl", 300)):
        if row.get("source") == "polymarket_gamma" and row.get("window_start_ts"):
            return row
    return {}

def latest_platform_validation(slug):
    for row in reversed(tail_jsonl(TRUE_DIR / "windows.jsonl", 300)):
        if row.get("source") == "platform_validation" and row.get("slug") == slug:
            return row
    return {}

def latest_orderbook(slug):
    changes = {}
    for row in reversed(tail_jsonl(TRUE_DIR / "price_change_ticks.jsonl", 800)):
        if slug and row.get("slug") != slug:
            continue
        side = str(row.get("side","")).lower()
        if side in ("up", "down") and side not in changes:
            changes[side] = {
                "bid1_price": parse_float(row.get("best_bid",0)),
                "ask1_price": parse_float(row.get("best_ask",0)),
                "bids": [{"price": parse_float(row.get("best_bid",0)), "size": 0}],
                "asks": [{"price": parse_float(row.get("best_ask",0)), "size": 0}],
                "received_at": row.get("received_at",""),
            }
        if "up" in changes and "down" in changes:
            return {"source": "polymarket_clob_ws", "reason": "price_change", "slug": slug, **changes}

    fallback = {}
    for row in reversed(tail_jsonl(TRUE_DIR / "orderbook_ticks.jsonl", 500)):
        if slug and row.get("slug") != slug:
            continue
        fallback = fallback or row
        up = row.get("up", {}) if isinstance(row.get("up"), dict) else {}
        down = row.get("down", {}) if isinstance(row.get("down"), dict) else {}
        if up.get("bids") or up.get("asks") or down.get("bids") or down.get("asks"):
            return row
    return fallback

def side_prices(side):
    bids = side.get("bids", []) if isinstance(side, dict) else []
    asks = side.get("asks", []) if isinstance(side, dict) else []
    bid = parse_float(side.get("bid1_price",0)) if isinstance(side, dict) else 0
    ask = parse_float(side.get("ask1_price",0)) if isinstance(side, dict) else 0
    if bid <= 0 and bids:
        bid = parse_float((bids[0] or {}).get("price",0))
    if ask <= 0 and asks:
        ask = parse_float((asks[0] or {}).get("price",0))
    mid = round((bid + ask) / 2, 4) if bid > 0 and ask > 0 else ask or bid or 0
    return {"bid": bid, "ask": ask, "mid": mid}

def latest_display_price():
    global PRICE_CACHE
    price = last_jsonl(TRUE_DIR / "price_ticks.jsonl")
    value = parse_float(price.get("value",0))
    official_age = iso_age_seconds(price.get("received_at"))
    if value and official_age is not None and official_age <= 10:
        return {**price, "value": value, "age_seconds": round(official_age, 1), "display_fallback": False}

    now = time.time()
    if PRICE_CACHE.get("value") and now - PRICE_CACHE.get("at", 0) <= 2:
        return {
            "value": PRICE_CACHE["value"],
            "source": PRICE_CACHE["source"],
            "age_seconds": round(now - PRICE_CACHE["at"], 1),
            "official_age_seconds": round(official_age, 1) if official_age is not None else None,
            "display_fallback": True,
        }

    for url, source in [
        ("https://api.coinbase.com/v2/prices/BTC-USD/spot", "coinbase_display_fallback"),
    ]:
        try:
            r = requests.get(url, timeout=1)
            data = r.json()
            if source.startswith("coinbase"):
                v = parse_float(((data.get("data") or {}).get("amount")))
            else:
                ticker = ((data.get("result") or {}).get("XXBTZUSD") or {})
                v = parse_float((ticker.get("c") or [0])[0])
            if v:
                PRICE_CACHE = {"value": v, "at": now, "source": source}
                return {
                    "value": v,
                    "source": source,
                    "age_seconds": 0.0,
                    "official_age_seconds": round(official_age, 1) if official_age is not None else None,
                    "display_fallback": True,
                }
        except Exception:
            pass
    if PRICE_CACHE.get("value"):
        return {
            "value": PRICE_CACHE["value"],
            "source": PRICE_CACHE.get("source", "coinbase_display_fallback"),
            "age_seconds": round(now - PRICE_CACHE.get("at", now), 1),
            "official_age_seconds": round(official_age, 1) if official_age is not None else None,
            "display_fallback": True,
            "warning": "coinbase_refresh_failed_using_cached_value",
        }
    return {
        "value": 0,
        "source": "coinbase_unavailable",
        "age_seconds": None,
        "official_age_seconds": round(official_age, 1) if official_age is not None else None,
        "display_fallback": True,
        "warning": "coinbase_refresh_failed_no_cache",
    }

def platform_crypto_price(symbol, start_ts, end_ts, variant="fiveminute"):
    """Read the same crypto open/close price endpoint used by the Polymarket page."""
    global PLATFORM_PRICE_CACHE
    if not start_ts or not end_ts:
        return {}
    key = (symbol.upper(), int(start_ts), int(end_ts), variant)
    now = time.time()
    cached = PLATFORM_PRICE_CACHE.get(key)
    if cached and now - cached.get("at", 0) < 30:
        return cached.get("data", {})
    try:
        params = {
            "symbol": symbol.upper(),
            "eventStartTime": iso_utc(start_ts),
            "variant": variant,
            "endDate": iso_utc(end_ts),
        }
        r = requests.get(
            "https://polymarket.com/api/crypto/crypto-price",
            params=params,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=2,
        )
        if r.status_code != 200:
            return cached.get("data", {}) if cached else {}
        data = r.json()
        result = {
            "open_price": parse_float(data.get("openPrice", 0)),
            "close_price": parse_float(data.get("closePrice", 0), None),
            "timestamp": data.get("timestamp"),
            "completed": bool(data.get("completed")),
            "incomplete": bool(data.get("incomplete")),
            "cached": bool(data.get("cached")),
            "source": "polymarket_crypto_price_api",
        }
        PLATFORM_PRICE_CACHE[key] = {"at": now, "data": result}
        return result
    except Exception:
        return cached.get("data", {}) if cached else {}

def true_market_snapshot():
    w = latest_true_window()
    if not w: return {}
    slug = w.get("slug","")
    price = latest_display_price()
    q = latest_quality_snapshot()
    ob = latest_orderbook(slug)
    up = side_prices(ob.get("up", {}) if isinstance(ob.get("up"), dict) else {})
    down = side_prices(ob.get("down", {}) if isinstance(ob.get("down"), dict) else {})
    val = latest_platform_validation(slug)
    start = int(w.get("window_start_ts") or 0)
    end = int(w.get("window_end_ts") or 0)
    now = int(time.time())
    price_value = parse_float(price.get("value",0))
    platform_price = platform_crypto_price("BTC", start, end)
    platform_open = parse_float(platform_price.get("open_price",0))
    validated_platform_open = parse_float(val.get("platform_ptb", w.get("platform_ptb", 0)))
    raw_ptb = parse_float(w.get("ptb",0))
    raw_quality = str(w.get("ptb_quality","") or "")
    official_age = price.get("official_age_seconds")
    if platform_open or validated_platform_open:
        ptb = platform_open or validated_platform_open
        ptb_source = platform_price.get("source","polymarket_crypto_price_api")
        ptb_quality = "platform"
        exclude_from_backtest = False
    elif raw_ptb and raw_quality in ("exact", "close"):
        ptb = raw_ptb
        ptb_source = w.get("ptb_source","")
        ptb_quality = raw_quality
        exclude_from_backtest = bool(w.get("exclude_from_backtest", False))
    else:
        ptb = 0
        ptb_source = "missing_platform_open_price"
        ptb_quality = "missing"
        exclude_from_backtest = True
    return {
        "slug": slug,
        "window_start_ts": start,
        "window_end_ts": end,
        "seconds_left": max(0, end - now) if end else 0,
        "ptb": ptb,
        "open_price": ptb,
        "raw_collector_ptb": raw_ptb,
        "ptb_source": ptb_source,
        "ptb_quality": ptb_quality,
        "platform_ptb": platform_open or validated_platform_open,
        "platform_close_price": platform_price.get("close_price"),
        "ptb_diff": round(abs(raw_ptb - platform_open), 2) if raw_ptb and platform_open else parse_float(val.get("diff", 0)),
        "exclude_from_backtest": exclude_from_backtest,
        "btc_price": price_value,
        "chainlink_price": price_value,
        "gap": round(price_value - ptb, 2) if price_value and ptb else 0,
        "up_price": up["mid"],
        "down_price": down["mid"],
        "up_bid": up["bid"],
        "up_ask": up["ask"],
        "down_bid": down["bid"],
        "down_ask": down["ask"],
        "source": price.get("source",""),
        "data_age_seconds": price.get("age_seconds", round((q.get("status_age_ms") or 0) / 1000, 1)),
        "official_price_age_seconds": price.get("official_age_seconds"),
        "display_fallback": bool(price.get("display_fallback")),
    }
def mask(a):
    return f"{a[:8]}...{a[-6:]}" if isinstance(a,str) and len(a)>14 else (a or "")

def env_file():
    out = {}
    fp = T / ".env"
    if not fp.exists(): return out
    for line in fp.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out

def rpc(method, params):
    try:
        r = requests.post(POLYGON_RPC, json={"jsonrpc":"2.0","id":1,"method":method,"params":params}, timeout=2)
        data = r.json()
        if "error" in data: return None
        return data.get("result")
    except Exception:
        return None

def erc20_balance(token, owner):
    if not owner or not owner.startswith("0x") or len(owner) != 42: return None
    data = "0x70a08231" + owner[2:].lower().rjust(64, "0")
    res = rpc("eth_call", [{"to": token, "data": data}, "latest"])
    try: return int(res or "0x0", 16)
    except Exception: return None

def native_balance(owner):
    res = rpc("eth_getBalance", [owner, "latest"]) if owner else None
    try: return int(res or "0x0", 16)
    except Exception: return None

def contract_deployed(owner):
    code = rpc("eth_getCode", [owner, "latest"]) if owner else None
    return bool(code and code != "0x")

def usd6(v):
    try: return round(int(v) / 1_000_000, 6)
    except Exception: return 0.0

def poly_tx(tx):
    return f"{POLYGONSCAN}/tx/{tx}" if isinstance(tx, str) and tx.startswith("0x") and len(tx) == 66 else ""

def poly_addr(addr):
    return f"{POLYGONSCAN}/address/{addr}" if isinstance(addr, str) and addr.startswith("0x") and len(addr) == 42 else ""

def backend_events(limit=50):
    if not EVENTS_FILE.exists(): return []
    rows = []
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                item = json.loads(line)
                item["tx_url"] = poly_tx(item.get("tx_hash",""))
                rows.append(item)
            except Exception:
                pass
    rows.reverse()
    return rows[:limit]

def wallet_state():
    if WALLET_CACHE.get("data") and time.time() - WALLET_CACHE.get("at", 0) < 30:
        return WALLET_CACHE["data"]
    env = env_file()
    ch = clh()
    funder = env.get("FUNDER_ADDRESS") or env.get("POLYMARKET_FUNDER_ADDRESS") or ""
    bal = ch.get("balance_allowance", {}) if isinstance(ch.get("balance_allowance"), dict) else {}
    allowances = bal.get("allowances", {}) if isinstance(bal.get("allowances"), dict) else {}
    allowance_ready = bool(allowances) and all(str(v) != "0" for v in allowances.values())
    pbal = erc20_balance(PUSD_TOKEN, funder)
    nbal = native_balance(funder)
    last_order = next((e for e in backend_events(20) if e.get("type") == "order"), None)
    return {
        "route": "后端自动下单（不用浏览器）",
        "network": "Polygon",
        "chain_id": 137,
        "polygonscan": POLYGONSCAN,
        "pUSD_token": PUSD_TOKEN,
        "pUSD_token_url": poly_addr(PUSD_TOKEN),
        "deposit_wallet": funder,
        "deposit_wallet_short": mask(funder),
        "deposit_wallet_url": poly_addr(funder),
        "signer": ch.get("address", ""),
        "signature_type": ch.get("signature_type"),
        "builder_key_present": bool(env.get("BUILDER_API_KEY")),
        "clob_ok": bool(ch.get("ok")),
        "clob_balance": usd6(bal.get("balance", 0)),
        "allowance_ready": allowance_ready,
        "allowance_count": len(allowances),
        "chain_pUSD_balance": usd6(pbal or 0),
        "native_pol": round((nbal or 0) / 10**18, 8),
        "wallet_deployed": contract_deployed(funder),
        "last_order": last_order,
        "events": backend_events(12),
    }

_wallet_state_uncached = wallet_state
def wallet_state():
    now = time.time()
    if WALLET_CACHE.get("data") and now - WALLET_CACHE.get("at", 0) < 30:
        return WALLET_CACHE["data"]
    # 如果有缓存但过期，先返回旧缓存（避免阻塞）
    if WALLET_CACHE.get("data") and now - WALLET_CACHE.get("at", 0) < 300:
        return WALLET_CACHE["data"]
    data = _wallet_state_uncached()
    WALLET_CACHE.update({"at": now, "data": data})
    return data

def svc(n):
    now = time.time()
    cached = SERVICE_CACHE.get(n)
    if cached and now - cached.get("at", 0) < 5:
        return cached.get("ok", False)
    try:
        if os.name == "nt":
            r = subprocess.run(["wsl","systemctl","--user","is-active",n],capture_output=True,text=True,encoding="utf-8",errors="ignore",timeout=1)
            if r.stdout.strip()=="active":
                SERVICE_CACHE[n] = {"at": now, "ok": True}
                return True
            hint = {
                "btc5m-sim":"sim/trader.py", "btc5m-sim.service":"sim/trader.py",
                "btc5m-live":"live/trader.py", "btc5m-live.service":"live/trader.py",
                "btc5m-collector":"true_market_collector.py", "btc5m-collector.service":"true_market_collector.py",
            }.get(n, n)
            r = subprocess.run(["wsl","bash","-lc",f"ps -ef | grep -F '{hint}' | grep -v grep"],capture_output=True,text=True,encoding="utf-8",errors="ignore",timeout=1)
            ok = bool(r.stdout.strip())
            SERVICE_CACHE[n] = {"at": now, "ok": ok}
            return ok
        r = subprocess.run(["systemctl","--user","is-active",n],capture_output=True,text=True,timeout=1)
        if r.stdout.strip()=="active":
            SERVICE_CACHE[n] = {"at": now, "ok": True}
            return True
        p = subprocess.run(["bash","-lc",f"ps -ef | grep -F '{n}' | grep -v grep"],capture_output=True,text=True,timeout=1)
        ok = bool(p.stdout.strip())
        SERVICE_CACHE[n] = {"at": now, "ok": ok}
        return ok
    except:
        SERVICE_CACHE[n] = {"at": now, "ok": False}
        return False

def brd():
    now = time.time()
    if now - BRIDGE_CACHE.get("at", 0) < 30:
        return BRIDGE_CACHE.get("ok", False)
    for h in ["http://172.18.16.1:8789/status","http://localhost:8789/status"]:
        try:
            r = requests.get(h, timeout=0.8)
            if r.status_code==200 and r.json().get("ready"):
                BRIDGE_CACHE.update({"at": now, "ok": True})
                return True
        except: pass
    BRIDGE_CACHE.update({"at": now, "ok": False})
    return False

def clh():
    global LH, LH_at
    now = time.time()
    if now-LH_at<60: return LH
    def _wsl_health():
        if os.name != "nt":
            return None
        cmd = "cd /mnt/c/Users/yyq/Desktop/自动交易/btc5m-trader && python3 -m clob_executor health"
        try:
            r = subprocess.run(["wsl", "bash", "-lc", cmd], capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=6)
            out = (r.stdout or "").strip()
            start = out.find("{")
            if start >= 0:
                return json.loads(out[start:])
            return {"executor":"clob_sdk","ok":False,"error":(r.stderr or out or "wsl_health_empty")[:300]}
        except Exception as e:
            return {"executor":"clob_sdk","ok":False,"error":str(e)[:300]}
    try:
        import clob_executor
        import threading
        result = [LH]
        def _run():
            try:
                result[0] = clob_executor.health(check_auth=True)
            except Exception as e:
                result[0] = {"executor":"clob_sdk","ok":False,"error":str(e)[:300]}
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=4)
        if t.is_alive():
            LH = {"executor":"clob_sdk","ok":False,"error":"health_check_timeout"}; LH_at=now; return LH
        LH = result[0]; LH_at=now; return LH
    except Exception as e:
        LH = _wsl_health() or {"executor":"clob_sdk","ok":False,"error":str(e)[:300]}; LH_at=now; return LH

def read_trades():
    fp = D / "trades.jsonl"
    if not fp.exists(): return []
    now = time.time()
    sig = file_sig(fp)
    cached = TRADES_CACHE.get("data")
    if cached is not None and TRADES_CACHE.get("sig") == sig and now - TRADES_CACHE.get("at", 0) < 3:
        return list(cached)
    trades = []
    with open(fp,"r",encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                try: trades.append(json.loads(line))
                except: pass
    TRADES_CACHE.update({"at": now, "sig": sig, "data": trades})
    return list(trades)

def num_or_none(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None

def trade_amount(t):
    return float(num_or_none(t.get("amount", t.get("buy_amount", 0))) or 0)

def trade_pnl(t):
    return float(num_or_none(t.get("pnl", t.get("net_profit", 0))) or 0)

def trade_prob(t):
    return float(num_or_none(t.get("probability", t.get("buy_prob", 0))) or 0)

def trade_open(t):
    return num_or_none(t.get("open_price", t.get("platform_open_price", t.get("ptb", None))))

def trade_final(t):
    return num_or_none(t.get("btc_final", t.get("platform_close_price", None)))

def trade_settle_gap(t):
    return num_or_none(t.get("settlement_gap", t.get("settle_gap", t.get("gap", None))))

def trade_return_pct(t, amt=None, pnl=None):
    ret = t.get("return_pct")
    if ret is not None:
        return float(ret or 0)
    if t.get("return") is not None:
        return float(t.get("return") or 0) * 100
    amt = trade_amount(t) if amt is None else amt
    pnl = trade_pnl(t) if pnl is None else pnl
    return round(pnl / amt * 100, 2) if amt > 0 else 0.0

def display_status(t):
    st = t.get("status", "")
    settlement_status = t.get("settlement_status", "")
    won = t.get("won", False)
    if st == "skipped":
        return "skipped"
    if st == "failed":
        return "failed"
    if st == "pending" or settlement_status == "pending":
        return "pending"
    if st == "won" or (st != "" and won):
        return "won"
    if st == "lost" or (st != "" and not won):
        return "lost"
    if won:
        return "won"
    return "matched_lost"

def row_ts(row):
    value = row.get("server_ts") or row.get("received_at") or row.get("time") or ""
    try:
        return datetime.fromisoformat(str(value).replace("Z","+00:00")).timestamp()
    except Exception:
        pass
    for key in ("rtds_timestamp_ms", "timestamp_ms", "actual_entry_ts"):
        v = num_or_none(row.get(key))
        if v:
            return v / 1000 if v > 1_000_000_000_000 else v
    return 0

def market_window_label(start_ts, end_ts=None):
    try:
        s = datetime.fromtimestamp(int(start_ts), CN)
        e = datetime.fromtimestamp(int(end_ts or int(start_ts) + 300), CN)
        return f"{s.strftime('%m-%d %H:%M')}-{e.strftime('%H:%M')}"
    except Exception:
        return ""

def load_windows(limit=200):
    fp = TRUE_DIR / "windows.jsonl"
    now = time.time()
    sig = file_sig(fp)
    key = int(limit)
    cached = WINDOWS_CACHE.get(key)
    if cached and cached.get("sig") == sig and now - cached.get("at", 0) < 5:
        return list(cached.get("data", []))
    rows_by_slug = {}
    for row in tail_jsonl(fp, max(limit * 8, 600)):
        slug = row.get("slug")
        start = row.get("window_start_ts")
        if not slug or not start:
            continue
        current = rows_by_slug.get(slug, {})
        merged = {**current, **row}
        rows_by_slug[slug] = merged
    rows = list(rows_by_slug.values())
    rows.sort(key=lambda r: int(r.get("window_start_ts") or 0), reverse=True)
    result = rows[:limit]
    WINDOWS_CACHE[key] = {"at": now, "sig": sig, "data": result}
    return list(result)

def resolution_by_slug(limit=5000):
    fp = TRUE_DIR / "resolutions.jsonl"
    now = time.time()
    sig = file_sig(fp)
    key = int(limit)
    cached = RESOLUTION_CACHE.get(key)
    if cached and cached.get("sig") == sig and now - cached.get("at", 0) < 60:
        return dict(cached.get("data", {}))
    out = {}
    for row in tail_jsonl(fp, limit):
        slug = row.get("slug")
        if slug:
            out[slug] = row
    RESOLUTION_CACHE[key] = {"at": now, "sig": sig, "data": out}
    return dict(out)

def resolution_final(row):
    row = row if isinstance(row, dict) else {}
    return num_or_none(row.get("closePrice", row.get("close_price", row.get("final_price"))))

def best_open_price(window, trades):
    """Prefer platform/trade open prices over known-bad collector PTB estimates."""
    quality = str(window.get("ptb_quality") or "").lower()
    platform = num_or_none(window.get("platform_ptb"))
    if platform is not None:
        return platform
    if quality in {"platform", "exact", "good"}:
        ptb = num_or_none(window.get("ptb"))
        if ptb is not None:
            return ptb
    for t in trades:
        v = trade_open(t)
        if v is not None:
            return v
    if quality in {"platform", "exact", "good", "close"}:
        return num_or_none(window.get("ptb"))
    return None

def price_rows_for_window(start, end, max_rows=20000):
    path = TRUE_DIR / "price_ticks.jsonl"
    if not path.exists() or not start or not end:
        return []
    rows = []
    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                ts = row_ts(row)
                if start <= ts <= end:
                    rows.append(row)
                    if len(rows) > max_rows:
                        rows = rows[-max_rows:]
    except Exception:
        pass
    return rows

def market_rows_for_slug(path, slug, max_rows=12000):
    if not path.exists():
        return []
    rows = []
    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            for line in f:
                if slug not in line:
                    continue
                try:
                    rows.append(json.loads(line))
                    if len(rows) > max_rows:
                        rows = rows[-max_rows:]
                except Exception:
                    pass
    except Exception:
        pass
    return rows

def side_book_point(book, sim):
    book = book if isinstance(book, dict) else {}
    sim = sim if isinstance(sim, dict) else {}
    return {
        "bid": num_or_none(book.get("bid1_price")),
        "ask": num_or_none(book.get("ask1_price")),
        "bid_size": num_or_none(book.get("bid1_size")),
        "ask_size": num_or_none(book.get("ask1_size")),
        "avg_fill": num_or_none(sim.get("simulated_avg_fill_price")),
        "shares": num_or_none(sim.get("simulated_shares")),
        "liquidity": num_or_none(sim.get("available_liquidity_at_entry")),
        "fill_quality": sim.get("fill_quality", ""),
    }

def market_detail(slug):
    windows = load_windows(500)
    window = next((w for w in windows if w.get("slug") == slug), {})
    trades = [t for t in read_trades() if t.get("slug") == slug or t.get("market_slug") == slug]
    start = int(window.get("window_start_ts") or (trades[0].get("window_start_ts") if trades else 0) or 0)
    end = int(window.get("window_end_ts") or (start + 300 if start else 0))
    open_price = best_open_price(window, trades)
    price_rows = market_rows_for_slug(TRUE_DIR / "price_ticks.jsonl", slug, 20000)
    if not price_rows:
        price_rows = price_rows_for_window(start, end, 20000)
    book_rows = market_rows_for_slug(TRUE_DIR / "orderbook_ticks.jsonl", slug, 20000)

    prices = []
    for r in price_rows:
        ts = row_ts(r)
        value = num_or_none(r.get("value", r.get("price")))
        if not ts or value is None:
            continue
        prices.append({
            "ts": int(ts * 1000),
            "time": datetime.fromtimestamp(ts, CN).strftime("%H:%M:%S"),
            "price": round(value, 4),
            "gap": round(value - open_price, 4) if open_price else None,
            "source": r.get("source", ""),
            "lag_ms": num_or_none(r.get("received_lag_ms")),
        })
    prices.sort(key=lambda x: x["ts"])

    orderbook = []
    for r in book_rows:
        if not isinstance(r.get("up"), dict) and not isinstance(r.get("down"), dict):
            continue
        ts = row_ts(r)
        if not ts:
            continue
        up = side_book_point(r.get("up"), r.get("up_sim"))
        down = side_book_point(r.get("down"), r.get("down_sim"))
        orderbook.append({
            "ts": int(ts * 1000),
            "time": datetime.fromtimestamp(ts, CN).strftime("%H:%M:%S"),
            "reason": r.get("reason") or r.get("event_type") or "",
            "up": up,
            "down": down,
            "up_prob": up.get("avg_fill") or up.get("ask"),
            "down_prob": down.get("avg_fill") or down.get("ask"),
        })
    orderbook.sort(key=lambda x: x["ts"])

    final_price = None
    for t in trades:
        final_price = final_price or trade_final(t)
    if final_price is None:
        final_price = resolution_final(resolution_by_slug(5000).get(slug))

    gaps = [p["gap"] for p in prices if p.get("gap") is not None]
    trade_gaps = []
    for t in trades:
        for v in (t.get("buy_gap"), t.get("entry_gap"), t.get("settlement_gap")):
            n = num_or_none(v)
            if n is not None:
                trade_gaps.append(n)
    all_gaps = gaps or trade_gaps
    crossed = bool(all_gaps and min(all_gaps) < 0 < max(all_gaps))
    final_gap = round(final_price - open_price, 4) if final_price is not None and open_price else None

    return {
        "slug": slug,
        "window": {
            **window,
            "window_start_ts": start,
            "window_end_ts": end,
            "market_time": market_window_label(start, end),
            "open_price": open_price,
            "final_price": final_price,
            "final_gap": final_gap,
            "winner": "Up" if final_gap is not None and final_gap >= 0 else "Down" if final_gap is not None else "",
        },
        "summary": {
            "price_points": len(prices),
            "orderbook_points": len(orderbook),
            "trades": len(trades),
            "reversal": crossed,
            "max_gap": round(max(all_gaps), 4) if all_gaps else None,
            "min_gap": round(min(all_gaps), 4) if all_gaps else None,
            "final_gap": final_gap,
        },
        "prices": prices,
        "orderbook": orderbook,
        "trades": trades,
    }

def normalize_stats(d):
    d = d if isinstance(d, dict) else {}
    trades = int(d.get("trade_count") or 0)
    wins = int(d.get("win_count") or 0)
    losses = int(d.get("loss_count") or 0)
    return {
        "bankroll": float(d.get("bankroll") or 0),
        "trade_count": trades,
        "win_count": wins,
        "loss_count": losses,
        "total_withdrawn": float(d.get("total_withdrawn") or 0),
        "win_rate": round((wins / trades) * 100, 2) if trades else 0.0,
    }

def trading_stats():
    state = rj(D / "sim" / "state.json")
    legacy = rj(D / "trader_state.json")
    sim = normalize_stats(state.get("sim_state") or legacy)
    live = normalize_stats(state.get("live_state") or rj(D / "live" / "state.json"))
    total_trades = sim["trade_count"] + live["trade_count"]
    total_wins = sim["win_count"] + live["win_count"]
    total_losses = sim["loss_count"] + live["loss_count"]
    total = {
        "bankroll": round(sim["bankroll"] + live["bankroll"], 6),
        "trade_count": total_trades,
        "win_count": total_wins,
        "loss_count": total_losses,
        "total_withdrawn": round(sim["total_withdrawn"] + live["total_withdrawn"], 6),
        "win_rate": round((total_wins / total_trades) * 100, 2) if total_trades else 0.0,
    }
    return {"sim": sim, "live": live, "total": total}

def daily_summary(trades):
    daily = defaultdict(lambda: {"trades":0,"confirmed":0,"pending":0,"excluded":0,
                                 "pnl":0.0,"wins":0,"losses":0,"skipped":0,"volume":0.0,
                                 "markets":set()})
    for t in trades:
        ts = t.get("time","")
        try:
            dt = datetime.fromisoformat(ts).astimezone(CN); day = dt.strftime("%m-%d")
        except: day = "unknown"
        d = daily[day]; d["trades"]+=1
        # 记录唯一市场
        slug = t.get("slug") or t.get("market_slug")
        if slug:
            d["markets"].add(slug)
        
        # 统计各类状态
        settlement_status = t.get("settlement_status","")
        exclude = t.get("exclude_from_backtest", False)
        if exclude:
            d["excluded"] += 1
        
        if settlement_status == "pending":
            d["pending"] += 1
        elif settlement_status == "confirmed":
            d["confirmed"] += 1
            # 只有 confirmed 且未排除的记录才计入盈亏和胜负
            d["volume"] += abs(trade_amount(t))
            pnl = trade_pnl(t)
            d["pnl"] += pnl
            if t.get("status")=="won" or t.get("won"):
                d["wins"]+=1
            elif t.get("status")=="lost" or (not t.get("won") and t.get("status")!="won"):
                d["losses"]+=1
        
        if t.get("status")=="skipped": d["skipped"]+=1
    
    return [{"date":k,"trades":v["trades"],"confirmed":v["confirmed"],"pending":v["pending"],
             "excluded":v["excluded"],"pnl":round(v["pnl"],2),
             "wins":v["wins"],"losses":v["losses"],"skipped":v["skipped"],
             "volume":round(v["volume"],2),"markets":len(v["markets"])}
            for k,v in sorted(daily.items(),reverse=True)]

class H(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):
        super().__init__(*a,directory=str(STATIC_DIR),**kw)
    def j(self,d,s=200):
        b = json.dumps(d,ensure_ascii=False).encode("utf-8")
        self.send_response(s)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)))
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        try: self.wfile.write(b)
        except BrokenPipeError: pass
    def do_GET(self):
        p = self.path
        if p=="/api/config": self.j(rj(T/"config.json"))
        elif p=="/api/trader": self.j(rj(D/"trader_state.json"))
        elif p=="/api/safety": self.do_safety()
        elif p=="/api/status": self.do_status()
        elif p=="/api/summary": self.do_summary()
        elif p=="/api/performance": self.do_summary()
        elif p=="/api/live": self.j(rj(LC))
        elif p=="/api/sim": self.j(rj(SC))
        elif p=="/api/clob-health": self.j(clh())
        elif p=="/api/wallet": self.j(wallet_state())
        elif p=="/api/data-quality": self.j(data_quality_state())
        elif p.startswith("/api/backend-events"): self.j({"events": backend_events(50)})
        elif p=="/api/strategies":
            cfg = rj(T/"config.json")
            strategies = cfg.get("strategies",{})
            # Clean strategy names - remove parenthetical suffixes
            for sid, s in strategies.items():
                if isinstance(s, dict) and "name" in s:
                    name = s["name"]
                    # Remove （xxx） or (xxx) suffixes
                    import re
                    name = re.sub(r'[（\(][^）\)]*[）\)]', '', name).strip()
                    s["name"] = name
            self.j({"active_strategy": cfg.get("active_strategy","1"), "strategies": strategies})
        elif p=="/api/markets": self.do_markets()
        elif p.startswith("/api/market-windows"): self.do_market_windows()
        elif p.startswith("/api/market-detail"): self.do_market_detail()
        elif p.startswith("/api/trades"): self.do_trades()
        elif p=="/api/daily-detail": self.do_daily_detail()
        elif p=="/api/fund-trend": self.do_fund_trend()
        elif p=="/api/skip-reasons": self.do_skip_reasons()
        elif p.startswith("/api/market-tick-data"): self.do_market_tick_data()
        elif p.startswith("/api/market-integrity"): self.do_market_integrity()
        elif p=="/api/missing-markets": self.do_missing_markets()
        else:
            if "." not in Path(p.split("?",1)[0]).name:
                self.path = "/index.html"
            super().do_GET()
    def do_POST(self):
        p = self.path
        try: b = json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))))
        except: b={}
        if p=="/api/config": self.up_config(b)
        elif p=="/api/toggle": self.toggle(b)
        elif p=="/api/live/arm": self.arm(b)
        elif p=="/api/strategies/switch": self.switch_strat(b)
        elif p=="/api/strategies/update": self.up_strat(b)
        elif p=="/api/sim/funds": self.set_sim_funds(b)
        elif p=="/api/reset": self.reset()
        elif p=="/api/refresh": self.refresh()
        else: self.j({"error":"not found"},404)
    def do_safety(self):
        br=brd(); sa=svc("btc5m-live"); ss=svc("btc5m-sim")
        lc=rj(LC); pa=lc.get("paused",True); ar=lc.get("armed",False)
        sc=rj(SC); sp=sc.get("paused",False)
        cfg=rj(T/"config.json"); md=cfg.get("mode","sim")
        ch=clh()
        bal = ch.get("balance_allowance", {}) if isinstance(ch.get("balance_allowance"), dict) else {}
        route_ready = bool(ch.get("ok") and ch.get("signature_type")==3 and usd6(bal.get("balance",0)) >= 1)
        self.j({"asset_scope":["BTC 5M"],"executor":"backend_deposit_wallet" if route_ready else "clob_sdk",
            "confirm_text":"BTC5M-LIVE","service_active":sa,"sim_active":ss,
            "browser_ready":br,"clob_ready":ch.get("ok",False),
            "clob_health":ch,"armed":ar,"paused":pa,"sim_paused":sp,
            "mode":md,"ready_to_trade":ar and not pa and route_ready and sa,
            "live_connected":route_ready,"route_ready":route_ready,
            "sim_trading":not sp and ss,"max_live_amount":1.0,
            "checks":[
                {"name":"实盘服务","ok":sa},
                {"name":"模拟服务","ok":ss},
                {"name":"实盘钱包可下单","ok":route_ready},
                {"name":"交易接口可用","ok":ch.get("ok",False)}]})
    def do_status(self):
        cfg=rj(T/"config.json"); md=cfg.get("mode","sim")
        lsa=svc("btc5m-live"); ssa=svc("btc5m-sim"); ca=svc("btc5m-collector")
        ticker={}; market={}

        true_snap = true_market_snapshot()
        if true_snap:
            market = {
                "slug": true_snap.get("slug",""),
                "window_start_ts": true_snap.get("window_start_ts",0),
                "window_end_ts": true_snap.get("window_end_ts",0),
                "seconds_left": true_snap.get("seconds_left",0),
                "ptb_quality": true_snap.get("ptb_quality",""),
                "ptb_diff": true_snap.get("ptb_diff",0),
                "exclude_from_backtest": true_snap.get("exclude_from_backtest",False),
            }
            ticker = {
                "btc_price": true_snap.get("btc_price",0),
                "chainlink_price": true_snap.get("chainlink_price",0),
                "ptb": true_snap.get("ptb",0),
                "open_price": true_snap.get("open_price",0),
                "platform_ptb": true_snap.get("platform_ptb",0),
                "gap": true_snap.get("gap",0),
                "up_price": true_snap.get("up_price",0),
                "down_price": true_snap.get("down_price",0),
                "up_bid": true_snap.get("up_bid",0),
                "up_ask": true_snap.get("up_ask",0),
                "down_bid": true_snap.get("down_bid",0),
                "down_ask": true_snap.get("down_ask",0),
                "source": true_snap.get("source",""),
                "ptb_source": true_snap.get("ptb_source",""),
                "ptb_quality": true_snap.get("ptb_quality",""),
                "data_age_seconds": true_snap.get("data_age_seconds",0),
                "official_price_age_seconds": true_snap.get("official_price_age_seconds"),
                "display_fallback": true_snap.get("display_fallback", False),
            }

        # 回退：从旧文件读取
        if not ticker.get("btc_price"):
            try:
                ts=rj(D/"trader_state.json")
                if ts.get("current_market"): market.update(ts["current_market"])
                if ts.get("ticker"): ticker.update(ts["ticker"])
            except: pass
        if not ticker.get("btc_price"):
            try:
                tail=subprocess.run(["tail","-n","1",str(D/"btc_price.jsonl")],capture_output=True,text=True,timeout=2)
                if tail.stdout.strip():
                    tp=json.loads(tail.stdout.strip())
                    ticker["btc_price"]=tp.get("btc_price",0)
                    ticker["chainlink_price"]=tp.get("chainlink_price",0)
                    ticker["ptb"]=tp.get("ptb",tp.get("price_to_beat",0)); ticker["gap"]=tp.get("gap",0)
                    ticker["up_price"]=tp.get("up_price",0); ticker["down_price"]=tp.get("down_price",0)
                    ticker["source"]=tp.get("market_data_source",""); ticker["data_age_seconds"]=tp.get("age",99)
            except: pass
        if not market.get("slug"):
            try:
                ev=subprocess.run(["tail","-n","1",str(D/"all_events.jsonl")],capture_output=True,text=True,timeout=2)
                if ev.stdout.strip():
                    e=json.loads(ev.stdout.strip())
                    market["slug"]=e.get("slug",""); market["seconds_left"]=e.get("seconds_left",300)
                    market["close_time"]=e.get("close_time","")
            except: pass
        stats = trading_stats()
        ts = stats["sim"] or rj(D/"trader_state.json")
        self.j({"sim":{"service_active":ssa},"live":{"service_active":lsa},"collector":{"service_active":ca},
            "current_market":market,"ticker":ticker,"executor_mode":md,
            "stats": stats,
            "trader_state":{"bankroll":ts.get("bankroll",0),"trade_count":ts.get("trade_count",0),
                "win_count":ts.get("win_count",0),"loss_count":ts.get("loss_count",0),
                "total_withdrawn":ts.get("total_withdrawn",0)}})
    def do_summary(self):
        trades=read_trades()
        
        # 只统计 confirmed 且未排除的记录
        confirmed_trades = [t for t in trades 
                          if t.get("settlement_status") == "confirmed" 
                          and not t.get("exclude_from_backtest", False)]
        
        # 统计各类状态
        total=len(trades)
        confirmed=len(confirmed_trades)
        pending=sum(1 for t in trades if t.get("settlement_status")=="pending")
        excluded=sum(1 for t in trades if t.get("exclude_from_backtest", False))
        
        # 胜负统计只计算 confirmed 记录
        won=sum(1 for t in confirmed_trades if t.get("status")=="won" or t.get("won"))
        lost=sum(1 for t in confirmed_trades if t.get("status")=="lost" or (not t.get("won") and t.get("status")!="won"))
        skipped=sum(1 for t in trades if t.get("status")=="skipped")
        failed=sum(1 for t in trades if t.get("status")=="failed")
        
        # 盈亏统计只计算 confirmed 记录
        total_pnl=round(sum(trade_pnl(t) for t in confirmed_trades),2)
        total_amount=round(sum(trade_amount(t) for t in confirmed_trades),2)
        
        # 胜率
        win_rate=round(won/confirmed*100,2) if confirmed>0 else 0

        # 获取资金信息
        stats = trading_stats()
        sim_bankroll = round(stats.get("sim", {}).get("bankroll", 0), 6)
        live_bankroll = round(stats.get("live", {}).get("bankroll", 0), 6)
        sim_win_rate = stats.get("sim", {}).get("win_rate", 0)
        live_win_rate = stats.get("live", {}).get("win_rate", 0)

        self.j({
            "total":total,
            "confirmed":confirmed,
            "pending":pending,
            "excluded":excluded,
            "won":won,
            "lost":lost,
            "skipped":skipped,
            "failed":failed,
            "win_rate":win_rate,
            "total_pnl":total_pnl,
            "total_amount":total_amount,
            "sim_bankroll":sim_bankroll,
            "live_bankroll":live_bankroll,
            "sim_win_rate":sim_win_rate,
            "live_win_rate":live_win_rate,
            "daily_summary":daily_summary(trades)
        })
    def do_trades(self):
        p=self.path; page=1; pp=20
        if "?" in p:
            qs=p.split("?",1)[1]
            for kv in qs.split("&"):
                if "=" in kv:
                    k,v=kv.split("=",1)
                    if k=="p": page=max(1,int(v))
                    elif k=="ps": pp=min(100,max(1,int(v)))
        def displayable_trade(t):
            if t.get("probability_source") == "market_open_fallback":
                return False
            st = str(t.get("status", "")).lower()
            if t.get("mode") == "sim" and st in ("won", "lost", "matched_lost"):
                if t.get("fill_quality") != "full":
                    return False
                op = num_or_none(t.get("open_price", t.get("platform_open_price", t.get("ptb"))))
                en = num_or_none(t.get("btc_entry"))
                bg = num_or_none(t.get("buy_gap", t.get("entry_gap", t.get("gap"))))
                if op and en and bg is not None and abs((en - op) - bg) > 2:
                    return False
            return True
        all_trades=[t for t in read_trades() if displayable_trade(t)]; all_trades.reverse()
        actual_total=len(all_trades)
        pages=max(1,(actual_total+pp-1)//pp)
        if page>pages: page=pages
        start=(page-1)*pp; end=min(start+pp,actual_total)
        page_trades=all_trades[start:end]
        fmt=[]
        for t in page_trades:
            # 兼容新旧字段
            st=t.get("status","")
            settlement_status=t.get("settlement_status","")
            won=t.get("won",False)
            
            # 状态映射
            if st=="skipped": ds="skipped"
            elif st=="failed": ds="failed"
            elif st=="pending" or settlement_status=="pending": ds="pending"
            elif st=="won" or (st!="" and won): ds="won"
            elif st=="lost" or (st!="" and not won): ds="lost"
            elif won: ds="won"
            else: ds="matched_lost"
            
            d=str(t.get("direction","none")).lower()
            if d not in ("up","down"): d="none"
            
            # 兼容新旧字段
            amt=trade_amount(t)
            pnl=trade_pnl(t)
            btc_open=t.get("open_price",t.get("platform_open_price",t.get("ptb",0)))
            btc_entry=num_or_none(t.get("btc_entry")) or 0
            btc_final=t.get("btc_final",t.get("platform_close_price",None))
            if btc_final is not None:
                btc_final=float(btc_final)
            eg=t.get("buy_gap", t.get("entry_gap",t.get("gap",0)))
            sg=t.get("settlement_gap", t.get("close_gap", t.get("settle_gap")))
            if sg is not None:
                sg=float(sg)
            if btc_open and btc_entry:
                eg=btc_entry-float(btc_open)
            prob_val=t.get("probability",t.get("buy_prob",0)); prob=float(prob_val) if prob_val is not None else 0.0
            if ds=="skipped" and t.get("fill_quality") in ("none", None, ""):
                prob=0.0
            
            # 计算收益率
            return_pct=t.get("return_pct")
            if return_pct is None and t.get("return") is not None:
                return_pct=float(t["return"])*100
            elif return_pct is None and amt>0:
                return_pct=round(pnl/amt*100,2)
            elif return_pct is None:
                return_pct=0.0
            
            actual_winner = t.get("actual_winner","")
            
            fmt.append({
                "status":ds,
                "time":t.get("time",""),
                "entry_time":t.get("actual_entry_ts", t.get("entry_time", t.get("time",""))),
                "entry_seconds_before":t.get("entry_seconds_before"),
                "direction":d,
                "settlement_direction":t.get("actual_winner", t.get("settlement_direction","")),
                "mode":t.get("mode",""),
                "slug":t.get("slug",""),
                "market_slug":t.get("market_slug",t.get("slug","")),
                "window_start_ts":t.get("window_start_ts"),
                "window_end_ts":t.get("window_end_ts"),
                "market_time":t.get("market_time_short", t.get("market_time","")),
                "btc_open":float(btc_open) if btc_open else 0,
                "platform_open_price":float(t.get("platform_open_price",0)) if t.get("platform_open_price") else None,
                "btc_entry":btc_entry,
                "btc_final":btc_final,
                "platform_close_price":float(t.get("platform_close_price",0)) if t.get("platform_close_price") else None,
                "entry_gap":round(float(eg),2) if eg else 0,
                "buy_gap":round(float(eg),2) if eg else 0,
                "settle_gap":round(float(sg),2) if sg else None,
                "settlement_gap":round(float(sg),2) if sg else None,
                "close_gap":round(float(sg),2) if sg else None,
                "buy_prob":prob,
                "entry_probability":prob,
                "probability_source":t.get("probability_source",""),
                "probability_age_seconds":t.get("probability_age_seconds"),
                "best_bid":num_or_none(t.get("best_bid")),
                "best_ask":num_or_none(t.get("best_ask")),
                "avg_fill_price":num_or_none(t.get("avg_fill_price")),
                "fill_quality":t.get("fill_quality",""),
                "buy_amount":amt,
                "fee":num_or_none(t.get("fee", t.get("fees", t.get("clob_fee")))),
                "amount":amt,
                "net_profit":pnl,
                "pnl":pnl,
                "return_pct":return_pct,
                "settlement_status":settlement_status,
                "settle_source":t.get("settle_source",""),
                "settle_confirmed_at":t.get("settle_confirmed_at"),
                "exclude_from_backtest":t.get("exclude_from_backtest",False),
                "skip_reason":t.get("skip_reason",""),
            })

        self.j({"trades":fmt,"total":actual_total,"page":page,"pages":pages,"per_page":pp})
    def do_daily_detail(self):
        trades=read_trades()
        daily=defaultdict(list)
        for t in trades:
            ts=t.get("time","")
            try: dt=datetime.fromisoformat(ts).astimezone(CN); day=dt.strftime("%Y-%m-%d")
            except: day="unknown"
            d=str(t.get("direction","none")).lower()
            if d not in ("up","down"): d="none"
            ds=display_status(t)
            amt=trade_amount(t); pnl=trade_pnl(t)
            eg=num_or_none(t.get("entry_gap",t.get("gap",0))) or 0
            sg=trade_settle_gap(t)
            ret=trade_return_pct(t, amt, pnl)
            tx = t.get("tx_hash",t.get("transaction_hash",t.get("hash","")))
            daily[day].append({"status":ds,"time":t.get("time",""),"direction":d,
                "slug":t.get("slug",""),"market_slug":t.get("market_slug",t.get("slug","")),
                "window_start_ts":t.get("window_start_ts"),"window_end_ts":t.get("window_end_ts"),
                "market_time":t.get("market_time",""),
                "btc_open":trade_open(t),"platform_open_price":num_or_none(t.get("platform_open_price")),
                "btc_entry":num_or_none(t.get("btc_entry")) or 0,
                "btc_final":trade_final(t),
                "platform_close_price":num_or_none(t.get("platform_close_price")),
                "entry_gap":round(float(eg),2),"settle_gap":round(float(sg),2) if sg is not None else None,
                "buy_gap":round(float(eg),2),"settlement_gap":round(float(sg),2) if sg is not None else None,
                "close_gap":round(float(sg),2) if sg is not None else None,
                "buy_prob":trade_prob(t),"buy_amount":amt,"amount":amt,
                "net_profit":pnl,"pnl":pnl,"return_pct":ret,
                "settlement_status":t.get("settlement_status",""),"settle_source":t.get("settle_source",""),
                "exclude_from_backtest":t.get("exclude_from_backtest",False),
                "skip_reason":t.get("skip_reason",""),
                "executor":t.get("executor",""),"order_id":t.get("orderID",t.get("order_id","")),
                "tx_hash":tx,"tx_url":poly_tx(tx)})
        result=[{"date":k,"trades":v} for k,v in sorted(daily.items(),reverse=True)]
        self.j(result)
    def do_fund_trend(self):
        """返回资金变化趋势数据"""
        trades = read_trades()
        # 按时间排序
        trades.sort(key=lambda t: t.get("time", ""))
        
        # 构建资金曲线数据
        fund_data = []
        # 从 state.json 读取初始资金
        state_data = rj(D / "sim" / "state.json")
        sim_state = state_data.get("sim_state", {}) if isinstance(state_data, dict) else {}
        cfg_data = state_data.get("config", {}) if isinstance(state_data, dict) else {}
        current_bankroll = float(sim_state.get("bankroll") or cfg_data.get("initial_capital") or 1.0)
        
        for t in trades:
            if t.get("settlement_status") == "confirmed":
                pnl = float(t.get("pnl", t.get("net_profit", 0)) or 0)
                current_bankroll += pnl
                fund_data.append({
                    "time": t.get("time", ""),
                    "bankroll": round(current_bankroll, 2),
                    "pnl": round(pnl, 2),
                    "slug": t.get("slug", "")
                })
        
        # 如果没有确认的交易，返回初始状态
        if not fund_data:
            fund_data.append({
                "time": datetime.now(CN).isoformat(),
                "bankroll": current_bankroll,
                "pnl": 0,
                "slug": "initial"
            })
        
        self.j({"data": fund_data, "initial": 100.0})

    def do_skip_reasons(self):
        """返回跳过原因分布数据"""
        trades = read_trades()
        
        # 统计跳过原因
        reasons = {}
        for t in trades:
            if t.get("status") == "skipped" or t.get("settlement_status") == "skipped":
                reason = t.get("skip_reason", "unknown")
                if reason:
                    # 简化原因描述
                    if "概率" in reason:
                        short = "概率不足"
                    elif "gap" in reason:
                        short = "价差太小"
                    elif "PTB" in reason:
                        short = "开盘价缺失"
                    elif "价格" in reason:
                        short = "价格不可执行"
                    else:
                        short = reason[:20]
                    reasons[short] = reasons.get(short, 0) + 1
        
        # 转换为饼图数据格式
        pie_data = [{"name": k, "value": v} for k, v in reasons.items()]
        
        self.j({"data": pie_data, "total": sum(reasons.values())})

    def do_market_tick_data(self):
        """返回指定市场的回放tick数据（带缓存）"""
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        slug = (qs.get("slug") or [""])[0]
        if not slug:
            self.j({"error": "missing slug"}, 400)
            return

        # 检查缓存（60秒有效）
        now = time.time()
        cached = TICK_DATA_CACHE.get(slug)
        if cached and now - cached.get("at", 0) < 60:
            self.j(cached["data"])
            return

        windows = load_windows(500)
        window = next((w for w in windows if w.get("slug") == slug), {})
        trades = [t for t in read_trades() if t.get("slug") == slug or t.get("market_slug") == slug]
        start_ts = int(window.get("window_start_ts") or (trades[0].get("window_start_ts") if trades else 0) or 0)
        end_ts = int(window.get("window_end_ts") or (start_ts + 300 if start_ts else 0))

        # 读取可靠开盘价和结算价。坏的 RTDS/PTB 估算不再回退显示，避免误导回放和交易判断。
        open_price = best_open_price(window, trades)
        platform_price = platform_crypto_price("BTC", start_ts, end_ts)
        platform_open = num_or_none(platform_price.get("open_price"))
        if platform_open is not None:
            open_price = platform_open
        final_price = None

        # 从 resolutions 读取结算价
        resolutions = resolution_by_slug(5000)
        if slug in resolutions:
            final_price = resolution_final(resolutions[slug])
        if final_price is None:
            final_price = num_or_none(platform_price.get("close_price"))
        if final_price is None:
            for t in trades:
                final_price = final_price or trade_final(t)

        # 读取价格数据（优先 slug，其次窗口时间范围；仅使用真实采集到的点）
        prices = {}
        try:
            for row in tail_jsonl(TRUE_DIR / "price_ticks.jsonl", 50000):
                ts = 0
                rtds_ms = parse_float(row.get("rtds_timestamp_ms", 0))
                if rtds_ms:
                    ts = int(rtds_ms / 1000)
                else:
                    ts = int(row_ts(row) or 0)
                if not ts:
                    continue
                row_slug = row.get("slug")
                in_window = bool(start_ts and end_ts and start_ts <= ts <= end_ts)
                if row_slug and row_slug != slug:
                    continue
                if not row_slug and not in_window:
                    continue
                value = parse_float(row.get("value", 0))
                if value:
                    prices[ts] = value
        except Exception:
            pass

        # 读取盘口数据（up/down 是对象，不是行）
        up_probs = {}
        down_probs = {}
        try:
            for row in tail_jsonl(TRUE_DIR / "orderbook_ticks.jsonl", 10000):
                if row.get("slug") != slug:
                    continue
                ts = row_ts(row)
                if not ts:
                    continue
                ts_key = int(ts)

                # up 对象
                up_obj = row.get("up", {})
                if isinstance(up_obj, dict):
                    up_bid = parse_float(up_obj.get("bid1_price", 0))
                    up_ask = parse_float(up_obj.get("ask1_price", 0))
                    if up_bid and up_ask:
                        up_probs[ts_key] = round((up_bid + up_ask) / 2, 4)

                # down 对象
                down_obj = row.get("down", {})
                if isinstance(down_obj, dict):
                    down_bid = parse_float(down_obj.get("bid1_price", 0))
                    down_ask = parse_float(down_obj.get("ask1_price", 0))
                    if down_bid and down_ask:
                        down_probs[ts_key] = round((down_bid + down_ask) / 2, 4)
        except Exception:
            pass

        # 合并所有时间戳
        all_ts = sorted(set(list(prices.keys()) + list(up_probs.keys()) + list(down_probs.keys())))

        ticks = []
        last_price = None
        last_up = None
        last_down = None
        for ts in all_ts:
            if ts in prices:
                last_price = prices.get(ts)
            if ts in up_probs:
                last_up = up_probs.get(ts)
            if ts in down_probs:
                last_down = down_probs.get(ts)
            price = last_price
            up = last_up
            down = last_down
            gap = round(price - open_price, 2) if price is not None and open_price else None
            ticks.append({
                "ts": ts,
                "price": round(price, 2) if price is not None else None,
                "gap": gap,
                "up_prob": round(up, 4) if up is not None else None,
                "down_prob": round(down, 4) if down is not None else None,
                "volume": 0,
            })

        result = {
            "slug": slug,
            "open_price": open_price,
            "final_price": final_price,
            "ticks": ticks,
            "data_points": {
                "price": len(prices),
                "orderbook_up": len(up_probs),
                "orderbook_down": len(down_probs),
            },
        }

        # 写入缓存
        TICK_DATA_CACHE[slug] = {"at": now, "data": result}
        self.j(result)

    def do_market_integrity(self):
        if market_integrity is None:
            self.j({
                "summary": {},
                "rows": [],
                "total": 0,
                "page": 1,
                "pages": 1,
                "per_page": 100,
                "error": "market_integrity_module_unavailable",
            })
            return
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        try:
            page = max(1, int((qs.get("p") or ["1"])[0]))
        except Exception:
            page = 1
        try:
            per_page = min(500, max(1, int((qs.get("ps") or ["100"])[0])))
        except Exception:
            per_page = 100
        status = (qs.get("status") or [""])[0]
        refreshing = maybe_refresh_integrity()
        summary = market_integrity.read_summary()
        rows = market_integrity.read_rows(per_page, status, page)
        self.j({"summary": summary, "refreshing": refreshing or INTEGRITY_REFRESH.get("running", False), **rows})

    def do_missing_markets(self):
        if market_integrity is not None:
            refreshing = maybe_refresh_integrity()
            summary = market_integrity.read_summary()
            if summary:
                self.j({
                    "total_expected": summary.get("total_expected", 0),
                    "total_actual": summary.get("total_actual", 0),
                    "total_missing": summary.get("total_missing", 0),
                    "today_expected": summary.get("today_expected", 0),
                    "today_actual": summary.get("today_actual", 0),
                    "today_missing": summary.get("today_missing", 0),
                    "first_window_ts": summary.get("first_window_ts"),
                    "latest_window_ts": summary.get("latest_window_ts"),
                    "complete": summary.get("complete", 0),
                    "partial": summary.get("partial", 0),
                    "abnormal": summary.get("abnormal", 0),
                    "unsettled": summary.get("unsettled", 0),
                    "usable_for_backtest": summary.get("usable_for_backtest", 0),
                    "today_complete": summary.get("today_complete", 0),
                    "today_partial": summary.get("today_partial", 0),
                    "today_abnormal": summary.get("today_abnormal", 0),
                    "today_unsettled": summary.get("today_unsettled", 0),
                    "generated_at": summary.get("generated_at", ""),
                    "refreshing": refreshing or INTEGRITY_REFRESH.get("running", False),
                })
                return
        """计算缺失市场数：从第一条记录开始，每5分钟一个窗口，减去实际记录数"""
        # 加载所有窗口（去重）
        rows_by_slug = {}
        for row in tail_jsonl(TRUE_DIR / "windows.jsonl", 5000):
            slug = row.get("slug")
            start = row.get("window_start_ts")
            if not slug or not start:
                continue
            rows_by_slug[slug] = {**rows_by_slug.get(slug, {}), **row}

        if not rows_by_slug:
            self.j({"total_expected": 0, "total_actual": 0, "total_missing": 0,
                    "today_expected": 0, "today_actual": 0, "today_missing": 0})
            return

        # 获取所有窗口的时间戳
        all_starts = []
        for row in rows_by_slug.values():
            ts = int(row.get("window_start_ts") or 0)
            if ts:
                all_starts.append(ts)

        if not all_starts:
            self.j({"total_expected": 0, "total_actual": 0, "total_missing": 0,
                    "today_expected": 0, "today_actual": 0, "today_missing": 0})
            return

        min_ts = min(all_starts)
        max_ts = max(all_starts)
        now_ts = int(time.time())

        # 总预期：从第一条记录到现在，每5分钟一个窗口
        total_expected = (now_ts - min_ts) // 300 + 1
        total_actual = len(rows_by_slug)
        total_missing = max(0, total_expected - total_actual)

        # 今日预期：从今天00:00到现在
        today_start = datetime.now(CN).replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = int(today_start.timestamp())
        today_expected = (now_ts - today_ts) // 300 + 1

        # 今日实际
        today_actual = sum(1 for ts in all_starts if ts >= today_ts)
        today_missing = max(0, today_expected - today_actual)

        self.j({
            "total_expected": total_expected,
            "total_actual": total_actual,
            "total_missing": total_missing,
            "today_expected": today_expected,
            "today_actual": today_actual,
            "today_missing": today_missing,
            "first_window_ts": min_ts,
            "latest_window_ts": max_ts,
        })

    def up_config(self,b):
        cfg=rj(T/"config.json")
        if "mode" in b: cfg["mode"]=b["mode"]
        if "paused" in b: cfg["paused"]=b["paused"]
        wj(T/"config.json",cfg); self.j({"ok":True})
    def toggle(self,b):
        import subprocess
        act=b.get("action","start"); mode=b.get("mode","sim")
        if mode == "live" and act == "start":
            if b.get("confirm","")!="BTC5M-LIVE":
                self.j({"error":"启动实盘需要输入确认词 BTC5M-LIVE"},400); return
            ch=clh()
            bal = ch.get("balance_allowance", {}) if isinstance(ch.get("balance_allowance"), dict) else {}
            route_ready = bool(ch.get("ok") and ch.get("signature_type")==3 and usd6(bal.get("balance",0)) >= 1)
            if not route_ready:
                self.j({"error":"实盘路线未就绪：CLOB pUSD 余额不足 1 美元或接口未通过健康检查","clob_health":ch},409); return
        fp = SC if mode == "sim" else LC
        cfg=rj(fp); cfg["paused"]=(act=="pause")
        if mode == "live":
            cfg["armed"] = (act=="start")
            cfg["max_live_amount"] = min(float(b.get("max_live_amount", cfg.get("max_live_amount", 1.0)) or 1.0), 1.0)
        wj(fp,cfg)
        root=rj(T/"config.json"); root["mode"]=mode; root["paused"]=cfg.get("paused",True); wj(T/"config.json",root)
        other_fp = LC if mode == "sim" else SC
        other = rj(other_fp)
        other["paused"] = True
        if other_fp == LC:
            other["armed"] = False
        wj(other_fp, other)
        
        # 启动/停止 systemd 服务
        service_name = f"btc5m-{mode}.service"
        other_service_name = "btc5m-live.service" if mode == "sim" else "btc5m-sim.service"
        service_action = "stop" if act == "pause" else "start"
        try:
            stop_cmd = ["wsl","systemctl","--user","stop",other_service_name] if os.name == "nt" else ["systemctl","--user","stop",other_service_name]
            subprocess.run(stop_cmd, capture_output=True, text=True, timeout=2)
            cmd = ["wsl","systemctl","--user",service_action,service_name] if os.name == "nt" else ["systemctl","--user",service_action,service_name]
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=2
            )
            service_started = result.returncode == 0
            service_error = result.stderr if result.returncode != 0 else ""
        except Exception as e:
            service_started = False
            service_error = str(e)
        
        # 检查服务状态
        try:
            status_cmd = ["wsl","systemctl","--user","is-active",service_name] if os.name == "nt" else ["systemctl","--user","is-active",service_name]
            status_result = subprocess.run(
                status_cmd,
                capture_output=True, text=True, timeout=2
            )
            service_active = status_result.stdout.strip() == "active"
        except:
            service_active = False
        
        self.j({
            "ok": True,
            "status": act,
            "mode": mode,
            "paused": cfg.get("paused", True),
            "service_started": service_started,
            "service_active": service_active,
            "service_error": service_error if service_error else None
        })
    def arm(self,b):
        ar=b.get("armed",False); lc=rj(LC)
        if ar:
            if b.get("confirm","")!="BTC5M-LIVE":
                self.j({"error":"确认码错误"},400); return
            lc["armed"]=True; lc["paused"]=False
            lc["max_live_amount"]=float(b.get("max_live_amount",1))
        else: lc["armed"]=False; lc["paused"]=True
        wj(LC,lc); self.j({"ok":True})
    def switch_strat(self,b):
        sid=b.get("strategy_id","1")
        for fp in [LC,SC,T/"config.json"]:
            cfg=rj(fp); cfg["active_strategy"]=sid; wj(fp,cfg)
        self.j({"ok":True,"strategy":sid})
    def up_strat(self,b):
        sid=b.get("strategy_id","1"); params=b.get("params",{}); name=b.get("name","")
        for fp in [LC,SC,T/"config.json"]:
            cfg=rj(fp)
            if sid in cfg.get("strategies",{}):
                for k,v in params.items(): cfg["strategies"][sid]["params"][k]=v
                if name: cfg["strategies"][sid]["name"]=name
                wj(fp,cfg)
        self.j({"ok":True})
    def set_sim_funds(self,b):
        try:
            amount = float(b.get("amount"))
        except Exception:
            self.j({"error":"模拟资金必须是数字"},400); return
        if amount < 1 or amount > 1000000:
            self.j({"error":"模拟资金范围必须在 1 到 1,000,000 之间"},400); return

        for fp in [SC, T / "config.json"]:
            cfg = rj(fp)
            cfg["initial_capital"] = amount
            wj(fp, cfg)

        state_fp = D / "sim" / "state.json"
        state = rj(state_fp)
        sim_state = state.get("sim_state") if isinstance(state.get("sim_state"), dict) else {}
        sim_state["bankroll"] = amount
        state["sim_state"] = sim_state
        state["last_update"] = datetime.now(CN).isoformat()
        state.setdefault("config", {})["initial_capital"] = amount
        wj(state_fp, state)
        self.j({"ok":True,"amount":amount,"stats":trading_stats()})
    def reset(self): self.j({"ok":True})
    def refresh(self):
        global LH_at
        LH_at = 0.0
        self.j({"ok":True})
    def do_markets(self):
        fp = D / "markets.jsonl"
        if not fp.exists(): self.j([]); return
        mkts = []
        try:
            r = subprocess.run(["tail","-n","200",str(fp)], capture_output=True,text=True,timeout=2)
            for line in r.stdout.strip().split("\n"):
                if line.strip():
                    try: mkts.append(json.loads(line))
                    except: pass
        except: pass
        self.j(mkts)
    def do_market_windows(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        try: limit = min(500, max(20, int((qs.get("limit") or ["160"])[0])))
        except Exception: limit = 160
        trades = read_trades()
        resolutions = resolution_by_slug(5000)
        by_slug = defaultdict(list)
        for t in trades:
            slug = t.get("slug") or t.get("market_slug")
            if slug: by_slug[slug].append(t)
        rows = []
        for w in load_windows(limit):
            slug = w.get("slug", "")
            start = int(w.get("window_start_ts") or 0)
            end = int(w.get("window_end_ts") or start + 300)
            ts = by_slug.get(slug, [])
            final_price = resolution_final(resolutions.get(slug))
            winner = ""
            reversal = False
            gaps = []
            for t in ts:
                final_price = final_price or trade_final(t)
                winner = winner or t.get("actual_winner") or t.get("settlement_direction", "")
                for v in (t.get("buy_gap"), t.get("entry_gap"), t.get("settlement_gap")):
                    n = num_or_none(v)
                    if n is not None: gaps.append(n)
            open_price = best_open_price(w, ts)
            if gaps and min(gaps) < 0 < max(gaps):
                reversal = True
            final_gap = round(final_price - open_price, 2) if final_price is not None and open_price else None
            if final_gap is not None:
                winner = "Up" if final_gap >= 0 else "Down"
            rows.append({
                "slug": slug,
                "window_start_ts": start,
                "window_end_ts": end,
                "market_time": market_window_label(start, end),
                "open_price": open_price,
                "final_price": final_price,
                "final_gap": final_gap,
                "winner": winner,
                "ptb_quality": w.get("ptb_quality", ""),
                "token_ready": bool(w.get("token_up") and w.get("token_down")),
                "has_trade": bool(ts),
                "trade_status": ts[-1].get("status", "") if ts else "",
                "reversal": reversal,
            })
        self.j({"markets": rows})
    def do_market_detail(self):
        parsed = urlparse(self.path)
        slug = (parse_qs(parsed.query).get("slug") or [""])[0]
        if not slug:
            self.j({"error":"missing slug"}, 400)
            return
        self.j(market_detail(slug))
    def log_message(self,fmt,*a):
        if a and "200" not in str(a[1] if len(a)>1 else ""):
            super().log_message(fmt,*a)

class S(ThreadingMixIn,HTTPServer): daemon_threads=True

if __name__=="__main__":
    port=int(os.getenv("API_PORT", "8878"))
    s=S(("0.0.0.0",port),H)
    print(f"API on http://0.0.0.0:{port}",flush=True)
    try: s.serve_forever()
    except KeyboardInterrupt: s.server_close()
