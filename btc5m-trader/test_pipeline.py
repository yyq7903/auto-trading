import sys, time
sys.path.insert(0, r"C:\Users\yyq\Desktop\自动交易\btc5m-trader")
from shared.btc_price import latest_market_snapshot, fetch_ptb, get_btc_fresh
from datetime import datetime

now = int(time.time())
current_5m = (now // 300) * 300
slug = f"btc-updown-5m-{current_5m}"
remaining = current_5m + 300 - now
print(f"slug: {slug}")
print(f"remaining: {remaining}s")

snap = latest_market_snapshot(slug)
print(f"data_source: {snap.get('market_data_source', 'N/A')}")
print(f"timestamp: {snap.get('timestamp', 'N/A')}")
print(f"btc_price: {snap.get('chainlink_price', 0)}")
print(f"up_bid/up_ask: {snap.get('up_bid', 0)}/{snap.get('up_ask', 0)}")
print(f"down_bid/down_ask: {snap.get('down_bid', 0)}/{snap.get('down_ask', 0)}")

ptb = fetch_ptb(slug)
print(f"ptb: {ptb}")

snap_ts = snap.get("timestamp", "")
try:
    snap_time = datetime.fromisoformat(snap_ts.replace("Z", "+00:00"))
    snap_age = time.time() - snap_time.timestamp()
    print(f"data_age: {snap_age:.1f}s")
    print(f"data_fresh: {snap_age <= 15}")
except Exception as e:
    print(f"timestamp_parse_error: {e}")

btc = snap.get("chainlink_price", 0) or get_btc_fresh()
gap = btc - ptb if ptb > 0 and btc > 0 else 0
print(f"btc: {btc}")
print(f"gap: {gap:.2f}")
print(f"gap_threshold_met: {abs(gap) >= 20}")

up_ask = snap.get("up_ask", 0)
down_ask = snap.get("down_ask", 0)
direction = "Up" if gap > 0 else "Down"
buy_price = up_ask if direction == "Up" else down_ask
print(f"direction: {direction}")
print(f"buy_price: {buy_price}")
print(f"buy_price_valid: {0 < buy_price < 1 and buy_price >= 0.95}")
