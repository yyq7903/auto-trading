#!/usr/bin/env python3
"""Strict BTC 5M backtest on collected Polymarket data.

This script intentionally refuses to fill missing BTC ticks with Binance,
Coinbase, generic Chainlink, or any other fallback. It uses:

- market_integrity.jsonl for the complete-market allowlist
- true_market/price_ticks.jsonl for official RTDS/Chainlink BTC ticks
- true_market/orderbook_ticks.jsonl for Polymarket CLOB order books
- platform open/close already recorded in market_integrity.jsonl

The current data set has many complete settlement/orderbook markets but far
fewer markets with official second-level BTC ticks. Results are therefore
reported with sample-size warnings instead of being treated as production
strategy proof.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

CN = timezone(timedelta(hours=8))
FEE_RATE = 0.07
AMOUNT_USD = 1.0
MAX_ORDERBOOK_AGE_SECONDS = 2.5


def project_base() -> Path:
    return Path.home() / "Desktop" / "\u81ea\u52a8\u4ea4\u6613"


BASE = project_base()
DATA = BASE / "btc5m\u6570\u636e"
TRUE = DATA / "true_market"
DERIVED = DATA / "derived"
OUT_DIR = DERIVED / "backtest"


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                yield row


def num(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        v = float(value)
    except Exception:
        return None
    if math.isnan(v):
        return None
    return v


def parse_ts(value: Any) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def row_ts(row: Dict[str, Any]) -> float:
    for key in ("server_ts", "received_at", "time"):
        ts = parse_ts(row.get(key))
        if ts:
            return ts
    for key in ("rtds_timestamp_ms", "timestamp_ms", "actual_entry_ts", "entry_time"):
        v = num(row.get(key))
        if v:
            return v / 1000 if v > 1_000_000_000_000 else v
    return 0.0


def fmt_time(ts: int) -> str:
    return datetime.fromtimestamp(ts, CN).strftime("%m-%d %H:%M")


def load_integrity() -> List[Dict[str, Any]]:
    rows = list(iter_jsonl(DERIVED / "market_integrity.jsonl") or [])
    rows.sort(key=lambda r: int(r.get("window_start_ts") or 0))
    return rows


def load_price_ticks(slugs: set[str]) -> Dict[str, List[Tuple[int, float]]]:
    out: Dict[str, Dict[int, float]] = defaultdict(dict)
    for row in iter_jsonl(TRUE / "price_ticks.jsonl") or []:
        slug = row.get("slug")
        if slug not in slugs:
            continue
        ts = row.get("rtds_timestamp_ms")
        ts_float = float(ts) / 1000 if ts else row_ts(row)
        value = num(row.get("value", row.get("price")))
        if ts_float and value and value > 1000:
            out[str(slug)][int(ts_float)] = float(value)
    return {slug: sorted(values.items()) for slug, values in out.items()}


def parse_levels(levels: Any, side: str) -> List[Dict[str, float]]:
    parsed = []
    if not isinstance(levels, list):
        return parsed
    for item in levels:
        if not isinstance(item, dict):
            continue
        price = num(item.get("price"))
        size = num(item.get("size"))
        if price is None or size is None or price <= 0 or price >= 1 or size <= 0:
            continue
        parsed.append({"price": float(price), "size": float(size)})
    if side == "asks":
        parsed.sort(key=lambda x: x["price"])
    else:
        parsed.sort(key=lambda x: x["price"], reverse=True)
    return parsed


def side_from_obj(obj: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "asks": parse_levels(obj.get("asks"), "asks"),
        "bids": parse_levels(obj.get("bids"), "bids"),
    }


def load_orderbook_snapshots(slugs: set[str]) -> Dict[str, List[Dict[str, Any]]]:
    books: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    snapshots: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for row in iter_jsonl(TRUE / "orderbook_ticks.jsonl") or []:
        slug = row.get("slug")
        if slug not in slugs:
            continue
        slug = str(slug)
        ts = row_ts(row)
        if not ts:
            continue

        if isinstance(row.get("up"), dict):
            books[slug]["up"] = side_from_obj(row["up"])
        if isinstance(row.get("down"), dict):
            books[slug]["down"] = side_from_obj(row["down"])

        side = str(row.get("side") or "").lower()
        if side in {"up", "down"}:
            books[slug][side] = {
                "asks": parse_levels(row.get("asks"), "asks"),
                "bids": parse_levels(row.get("bids"), "bids"),
            }

        if "up" in books[slug] and "down" in books[slug]:
            snapshots[slug].append({
                "ts": float(ts),
                "up": books[slug]["up"],
                "down": books[slug]["down"],
            })

    for slug in list(snapshots):
        snapshots[slug].sort(key=lambda r: r["ts"])
    return snapshots


def simulate_market_buy(asks: List[Dict[str, float]], amount_usd: float = AMOUNT_USD) -> Dict[str, Any]:
    if not asks:
        return {
            "avg_fill_price": 0.0,
            "shares": 0.0,
            "available_liquidity": 0.0,
            "fill_quality": "none",
        }

    remaining = float(amount_usd)
    shares = 0.0
    cost = 0.0
    available_liquidity = sum(float(a["size"]) for a in asks)

    for ask in asks:
        price = float(ask["price"])
        size = float(ask["size"])
        max_shares = remaining / price
        buy_shares = min(max_shares, size)
        if buy_shares <= 0:
            continue
        line_cost = buy_shares * price
        shares += buy_shares
        cost += line_cost
        remaining -= line_cost
        if remaining <= 0.001:
            break

    if shares <= 0:
        fill_quality = "none"
        avg = 0.0
    else:
        avg = cost / shares
        fill_quality = "full" if remaining <= 0.001 else "partial" if cost > amount_usd * 0.5 else "none"
    return {
        "avg_fill_price": round(avg, 6),
        "shares": round(shares, 6),
        "available_liquidity": round(available_liquidity, 4),
        "fill_quality": fill_quality,
        "cost": round(cost, 6),
    }


@dataclass(frozen=True)
class Strategy:
    name: str
    entry_second: int
    gap_threshold: float
    min_prob: float
    max_prob: float = 0.99
    min_seconds_left: int = 1
    max_orderbook_age: float = MAX_ORDERBOOK_AGE_SECONDS


def latest_snapshot_at(snapshots: List[Dict[str, Any]], ts: int) -> Optional[Dict[str, Any]]:
    if not snapshots:
        return None
    times = [s["ts"] for s in snapshots]
    idx = bisect_right(times, ts) - 1
    if idx < 0:
        return None
    return snapshots[idx]


def evaluate_market(
    market: Dict[str, Any],
    price_ticks: List[Tuple[int, float]],
    snapshots: List[Dict[str, Any]],
    strategy: Strategy,
) -> Dict[str, Any]:
    slug = market["slug"]
    start = int(market["window_start_ts"])
    end = int(market["window_end_ts"])
    open_price = float(market["open_price"])
    final_gap = float(market["final_gap"])
    winner = "up" if final_gap >= 0 else "down"

    skip_reasons = Counter()
    for ts, price in price_ticks:
        seconds_left = end - int(ts)
        if seconds_left < strategy.min_seconds_left or seconds_left > strategy.entry_second:
            continue
        gap = price - open_price
        if abs(gap) < strategy.gap_threshold:
            skip_reasons["gap_below_threshold"] += 1
            continue
        direction = "up" if gap > 0 else "down"
        snapshot = latest_snapshot_at(snapshots, int(ts))
        if not snapshot:
            skip_reasons["no_orderbook_before_tick"] += 1
            continue
        age = float(ts) - float(snapshot["ts"])
        if age < -0.001 or age > strategy.max_orderbook_age:
            skip_reasons["orderbook_stale"] += 1
            continue
        fill = simulate_market_buy(snapshot[direction]["asks"], AMOUNT_USD)
        if fill["fill_quality"] != "full":
            skip_reasons[f"fill_{fill['fill_quality']}"] += 1
            continue
        prob = float(fill["avg_fill_price"])
        if prob < strategy.min_prob:
            skip_reasons["prob_below_min"] += 1
            continue
        if prob > strategy.max_prob:
            skip_reasons["prob_above_max"] += 1
            continue

        shares = float(fill["shares"])
        cost = float(fill.get("cost") or AMOUNT_USD)
        fee_per_share = FEE_RATE * prob * (1 - prob)
        fee = shares * fee_per_share
        won = direction == winner
        pnl = shares * (1 - prob) - fee if won else -(cost + fee)
        return {
            "slug": slug,
            "market_time": market.get("market_time", ""),
            "status": "trade",
            "direction": direction,
            "winner": winner,
            "entry_ts": int(ts),
            "entry_time": fmt_time(int(ts)) + datetime.fromtimestamp(int(ts), CN).strftime(":%S"),
            "seconds_left": seconds_left,
            "open_price": round(open_price, 4),
            "entry_price": round(price, 4),
            "final_price": market.get("final_price"),
            "entry_gap": round(gap, 4),
            "final_gap": round(final_gap, 4),
            "avg_fill_price": prob,
            "shares": round(shares, 6),
            "fee": round(fee, 6),
            "pnl": round(pnl, 6),
            "won": won,
            "orderbook_age_seconds": round(age, 3),
        }

    return {
        "slug": slug,
        "market_time": market.get("market_time", ""),
        "status": "skip",
        "skip_reasons": dict(skip_reasons),
    }


def max_drawdown(equity: List[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        worst = min(worst, value - peak)
    return round(worst, 6)


def streaks(results: List[Dict[str, Any]]) -> Tuple[int, int]:
    best_win = best_loss = cur_win = cur_loss = 0
    for r in results:
        if r.get("status") != "trade":
            continue
        if r.get("won"):
            cur_win += 1
            cur_loss = 0
        else:
            cur_loss += 1
            cur_win = 0
        best_win = max(best_win, cur_win)
        best_loss = max(best_loss, cur_loss)
    return best_win, best_loss


def summarize(strategy: Strategy, markets: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> Dict[str, Any]:
    trades = [r for r in results if r.get("status") == "trade"]
    skips = [r for r in results if r.get("status") != "trade"]
    wins = sum(1 for r in trades if r.get("won"))
    losses = len(trades) - wins
    pnl_values = [float(r["pnl"]) for r in trades]
    equity = []
    running = 0.0
    for pnl in pnl_values:
        running += pnl
        equity.append(running)
    best_win, best_loss = streaks(results)
    skip_reasons = Counter()
    for r in skips:
        skip_reasons.update(r.get("skip_reasons") or {"no_signal": 1})
    time_buckets = defaultdict(lambda: {"markets": 0, "trades": 0, "wins": 0, "pnl": 0.0})
    by_slug = {r["slug"]: r for r in results}
    for market in markets:
        dt = datetime.fromtimestamp(int(market["window_start_ts"]), CN)
        bucket = f"{dt.hour:02d}:00"
        item = time_buckets[bucket]
        item["markets"] += 1
        r = by_slug.get(market["slug"])
        if r and r.get("status") == "trade":
            item["trades"] += 1
            item["wins"] += 1 if r.get("won") else 0
            item["pnl"] += float(r.get("pnl") or 0)
    return {
        "strategy": strategy.__dict__,
        "sample_markets": len(markets),
        "time_range": {
            "first": markets[0].get("market_time") if markets else "",
            "last": markets[-1].get("market_time") if markets else "",
        },
        "trades": len(trades),
        "skips": len(skips),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(trades) * 100, 2) if trades else 0.0,
        "avg_pnl": round(statistics.mean(pnl_values), 6) if pnl_values else 0.0,
        "total_pnl": round(sum(pnl_values), 6),
        "max_drawdown": max_drawdown(equity),
        "longest_win_streak": best_win,
        "longest_loss_streak": best_loss,
        "skip_reasons": dict(skip_reasons.most_common(8)),
        "time_buckets": {
            k: {
                **v,
                "pnl": round(v["pnl"], 6),
                "win_rate": round(v["wins"] / v["trades"] * 100, 2) if v["trades"] else 0.0,
            }
            for k, v in sorted(time_buckets.items())
        },
    }


def split_train_validation(markets: List[Dict[str, Any]], ratio: float = 0.7) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    cut = max(1, int(len(markets) * ratio))
    if cut >= len(markets):
        cut = max(0, len(markets) - 1)
    return markets[:cut], markets[cut:]


def candidate_strategies() -> List[Strategy]:
    out = []
    for entry in (15, 25, 45, 60, 90, 120):
        for gap in (5, 10, 15, 20, 30, 50, 80, 120):
            for min_prob in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.90, 0.95):
                out.append(Strategy(
                    name=f"T{entry}_gap{gap}_p{min_prob:.2f}",
                    entry_second=entry,
                    gap_threshold=gap,
                    min_prob=min_prob,
                ))
    return out


def evaluate_strategy(
    markets: List[Dict[str, Any]],
    price_by_slug: Dict[str, List[Tuple[int, float]]],
    books_by_slug: Dict[str, List[Dict[str, Any]]],
    strategy: Strategy,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    results = [
        evaluate_market(m, price_by_slug.get(m["slug"], []), books_by_slug.get(m["slug"], []), strategy)
        for m in markets
    ]
    return summarize(strategy, markets, results), results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-price-ticks", type=int, default=1)
    args = parser.parse_args()

    all_rows = load_integrity()
    complete = [r for r in all_rows if r.get("usable_for_backtest")]
    strict = [r for r in complete if int(r.get("price_ticks") or 0) >= args.min_price_ticks]
    strict = [r for r in strict if int(r.get("orderbook_last120") or 0) > 0]
    slugs = {r["slug"] for r in strict}

    price_by_slug = load_price_ticks(slugs)
    # Keep only markets that actually have price ticks in the last 120 seconds.
    strict_last120 = []
    for market in strict:
        end = int(market["window_end_ts"])
        ticks = price_by_slug.get(market["slug"], [])
        if any(0 < end - ts <= 120 for ts, _ in ticks):
            strict_last120.append(market)
    slugs = {r["slug"] for r in strict_last120}
    price_by_slug = {slug: ticks for slug, ticks in price_by_slug.items() if slug in slugs}
    books_by_slug = load_orderbook_snapshots(slugs)

    train, validation = split_train_validation(strict_last120, 0.7)
    candidates = candidate_strategies()
    train_rows = []
    validation_rows = []
    for strategy in candidates:
        train_summary, _ = evaluate_strategy(train, price_by_slug, books_by_slug, strategy)
        validation_summary, _ = evaluate_strategy(validation, price_by_slug, books_by_slug, strategy)
        if train_summary["trades"] > 0:
            train_rows.append(train_summary)
            validation_rows.append(validation_summary)

    def score(row: Dict[str, Any]) -> Tuple[float, float, int]:
        return (row["total_pnl"], row["win_rate"], row["trades"])

    train_ranked = sorted(train_rows, key=score, reverse=True)
    validation_by_name = {r["strategy"]["name"]: r for r in validation_rows}
    top = []
    for row in train_ranked[:30]:
        val = validation_by_name.get(row["strategy"]["name"])
        top.append({"train": row, "validation": val})

    existing = [
        Strategy("slot1_current", 25, 10, 0.60),
        Strategy("slot2_current", 120, 120, 0.70),
        Strategy("slot3_current", 60, 60, 0.65),
        Strategy("slot4_current", 45, 30, 0.62),
        Strategy("slot5_current", 15, 25, 0.75),
    ]
    existing_results = []
    for strategy in existing:
        summary, results = evaluate_strategy(strict_last120, price_by_slug, books_by_slug, strategy)
        existing_results.append({"summary": summary, "sample_trades": [r for r in results if r.get("status") == "trade"][:20]})

    report = {
        "generated_at": datetime.now(CN).isoformat(),
        "data_scope": {
            "complete_markets": len(complete),
            "complete_with_any_price_ticks": len(strict),
            "strict_last120_price_markets": len(strict_last120),
            "strict_time_range": {
                "first": strict_last120[0].get("market_time") if strict_last120 else "",
                "last": strict_last120[-1].get("market_time") if strict_last120 else "",
            },
            "warning": "Only strict_last120_price_markets are used for parameter backtest. Other complete markets lack official BTC ticks in the strategy entry window.",
        },
        "train_validation_split": {
            "train_markets": len(train),
            "validation_markets": len(validation),
            "train_time_range": {"first": train[0].get("market_time") if train else "", "last": train[-1].get("market_time") if train else ""},
            "validation_time_range": {"first": validation[0].get("market_time") if validation else "", "last": validation[-1].get("market_time") if validation else ""},
        },
        "top_train_candidates": top,
        "existing_strategy_results": existing_results,
        "recommendation": {
            "status": "insufficient_strict_sample",
            "message": "Do not switch simulation strategy from this backtest alone. The strict official-price sample is too small for production confidence.",
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "btc5m_backtest_strict.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(out_json),
        "data_scope": report["data_scope"],
        "split": report["train_validation_split"],
        "top": top[:5],
        "existing": [x["summary"] for x in existing_results],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
