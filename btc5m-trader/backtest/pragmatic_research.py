#!/usr/bin/env python3
"""Pragmatic research pass over archived BTC 5M data.

This is intentionally separate from the strict backtester. It answers two
questions:

1. How usable are the archived records if we stop requiring perfect 300/300
   second coverage?
2. Do profit-lock / pause-until-next-sim-loss rules improve the observed
   simulated trade stream, or are they mostly curve-fit noise?
"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

CN = timezone(timedelta(hours=8))


def base_dir() -> Path:
    # Resolve from this script so Chinese Windows paths do not depend on the
    # active console code page.
    return Path(__file__).resolve().parents[2]


BASE = base_dir()
ARCHIVE = BASE / "旧文件"
DATA = BASE / "btc5m数据"
OUT = DATA / "derived" / "backtest"


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


def as_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if v is None or v == "":
            return default
        x = float(v)
    except Exception:
        return default
    if math.isnan(x):
        return default
    return x


def parse_ts(value: Any) -> float:
    if not value:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) / 1000 if value > 1_000_000_000_000 else float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def row_time(row: Dict[str, Any]) -> float:
    for key in ("actual_entry_ts", "window_start_ts"):
        v = as_float(row.get(key))
        if v:
            return float(v)
    for key in ("entry_time", "time", "server_ts", "received_at"):
        ts = parse_ts(row.get(key))
        if ts:
            return ts
    return 0.0


def pct(n: int, d: int) -> float:
    return round(n / d * 100, 2) if d else 0.0


def max_drawdown(values: List[float]) -> float:
    peak = 0.0
    worst = 0.0
    for v in values:
        peak = max(peak, v)
        worst = min(worst, v - peak)
    return round(worst, 6)


def streaks(records: List[Dict[str, Any]]) -> Tuple[int, int]:
    win = loss = best_win = best_loss = 0
    for r in records:
        if r["won"]:
            win += 1
            loss = 0
        else:
            loss += 1
            win = 0
        best_win = max(best_win, win)
        best_loss = max(best_loss, loss)
    return best_win, best_loss


def summarize_trades(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    pnl = [float(r["pnl"]) for r in records]
    equity = []
    cur = 0.0
    for p in pnl:
        cur += p
        equity.append(cur)
    wins = sum(1 for r in records if r["won"])
    best_win, best_loss = streaks(records)
    return {
        "trades": len(records),
        "wins": wins,
        "losses": len(records) - wins,
        "win_rate": pct(wins, len(records)),
        "total_pnl": round(sum(pnl), 6),
        "avg_pnl": round(statistics.mean(pnl), 6) if pnl else 0.0,
        "median_pnl": round(statistics.median(pnl), 6) if pnl else 0.0,
        "max_drawdown": max_drawdown(equity),
        "longest_win_streak": best_win,
        "longest_loss_streak": best_loss,
    }


def summarize_scaled(records: List[Dict[str, Any]], stake: float = 1.0, initial: float = 10.0) -> Dict[str, Any]:
    """Summarize historical signals after normalizing every trade to the same stake.

    Old archived rows used different simulated amounts. Raw pnl is useful for
    auditing the old bot, but strategy selection must compare like-for-like
    stakes.
    """
    equity = []
    cur = 0.0
    scaled = []
    active = []
    bankroll = initial
    for r in records:
        pnl_per_dollar = float(r["pnl"]) / max(float(r["amount"]), 1e-9)
        p = stake * pnl_per_dollar
        scaled.append(p)
        cur += p
        equity.append(cur)
        if bankroll >= 1.0:
            bankroll += min(stake, bankroll) * pnl_per_dollar
            active.append(r)
    wins = sum(1 for r in records if r["won"])
    best_win, best_loss = streaks(records)
    return {
        "trades": len(records),
        "wins": wins,
        "losses": len(records) - wins,
        "win_rate": pct(wins, len(records)),
        "fixed_stake": stake,
        "total_pnl": round(sum(scaled), 6),
        "avg_pnl": round(statistics.mean(scaled), 6) if scaled else 0.0,
        "median_pnl": round(statistics.median(scaled), 6) if scaled else 0.0,
        "max_drawdown": max_drawdown(equity),
        "longest_win_streak": best_win,
        "longest_loss_streak": best_loss,
        "final_bankroll_from_10": round(bankroll, 6),
        "stopped_early": len(active) < len(records),
    }


def find_files(name: str) -> List[Path]:
    paths = []
    if DATA.exists():
        paths.extend(DATA.rglob(name))
    if ARCHIVE.exists():
        paths.extend(ARCHIVE.rglob(name))
    return sorted(set(paths), key=lambda p: (str(p), p.stat().st_size if p.exists() else 0))


def load_sim_trades() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    raw = []
    file_counts = {}
    for path in find_files("trades.jsonl"):
        rows = list(iter_jsonl(path) or [])
        file_counts[str(path)] = len(rows)
        raw.extend(rows)
    # Keep only settled simulated BTC 5m trades and dedupe by slug+entry_ts+direction.
    dedup = {}
    excluded = Counter()
    for row in raw:
        mode = str(row.get("mode", "")).lower()
        slug = row.get("slug") or row.get("market_slug") or ""
        if mode and mode != "sim":
            excluded["not_sim"] += 1
            continue
        if "btc-updown-5m" not in str(slug):
            excluded["not_btc5m"] += 1
            continue
        status = str(row.get("status", "")).lower()
        if status not in ("won", "lost"):
            excluded["not_settled_trade"] += 1
            continue
        if row.get("exclude_from_backtest"):
            excluded["exclude_from_backtest"] += 1
            continue
        if str(row.get("settlement_status", "")).lower() not in ("confirmed", "settled", ""):
            excluded["unconfirmed_settlement"] += 1
            continue
        pnl = as_float(row.get("pnl"))
        prob = as_float(row.get("entry_probability", row.get("probability")))
        amount = as_float(row.get("amount"))
        if pnl is None or prob is None or amount is None:
            excluded["missing_core_fields"] += 1
            continue
        key = (slug, int(as_float(row.get("actual_entry_ts"), row_time(row)) or 0), str(row.get("direction")))
        existing = dedup.get(key)
        if not existing or row_time(row) > row_time(existing):
            dedup[key] = row
    records = []
    for row in dedup.values():
        direction = str(row.get("direction", "")).lower()
        actual = str(row.get("actual_winner", "")).lower()
        records.append({
            "slug": row.get("slug") or row.get("market_slug"),
            "market_time": row.get("market_time", ""),
            "ts": row_time(row),
            "direction": direction,
            "winner": actual,
            "won": str(row.get("status", "")).lower() == "won",
            "pnl": float(row["pnl"]),
            "amount": float(row["amount"]),
            "probability": float(row.get("entry_probability", row.get("probability"))),
            "entry_seconds_before": int(as_float(row.get("entry_seconds_before"), 0) or 0),
            "entry_gap": float(as_float(row.get("entry_gap", row.get("buy_gap")), 0.0) or 0.0),
            "settlement_gap": float(as_float(row.get("settlement_gap", row.get("close_gap")), 0.0) or 0.0),
            "fill_quality": row.get("fill_quality", ""),
            "probability_age_seconds": float(as_float(row.get("probability_age_seconds"), 999.0) or 999.0),
            "source": row.get("probability_source", ""),
        })
    records.sort(key=lambda r: r["ts"])
    return records, {"file_counts": file_counts, "excluded": dict(excluded), "raw_rows": len(raw), "deduped_rows": len(records)}


def data_quality_scan() -> Dict[str, Any]:
    integrity_rows = []
    for path in find_files("market_integrity.jsonl"):
        rows = list(iter_jsonl(path) or [])
        if rows:
            integrity_rows.append((path, rows))
    out = {"integrity_files": []}
    for path, rows in integrity_rows:
        total = len(rows)
        complete = sum(1 for r in rows if r.get("complete_for_backtest") or r.get("usable_for_backtest"))
        abnormal = total - complete
        reason_counts = Counter()
        price_counts = []
        ob_counts = []
        for r in rows:
            reasons = r.get("exclude_reasons") or r.get("reasons") or []
            reason_counts.update(reasons)
            if "official_price_seconds" in r:
                price_counts.append(int(r.get("official_price_seconds") or 0))
            elif "price_ticks" in r:
                price_counts.append(int(r.get("price_ticks") or 0))
            if "orderbook_snapshot_seconds" in r:
                ob_counts.append(int(r.get("orderbook_snapshot_seconds") or 0))
            elif "orderbook_ticks" in r:
                ob_counts.append(int(r.get("orderbook_ticks") or 0))
        out["integrity_files"].append({
            "path": str(path),
            "rows": total,
            "complete_or_usable": complete,
            "abnormal": abnormal,
            "top_reasons": dict(reason_counts.most_common(10)),
            "price_count_median": statistics.median(price_counts) if price_counts else None,
            "orderbook_count_median": statistics.median(ob_counts) if ob_counts else None,
        })
    return out


def filter_records(records: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for r in records:
        if r["amount"] < cfg.get("min_amount", 1.0):
            continue
        if r["fill_quality"] and r["fill_quality"] != "full":
            continue
        if r["probability_age_seconds"] > cfg.get("max_prob_age", 5.0):
            continue
        if r["probability"] < cfg["min_prob"] or r["probability"] > cfg["max_prob"]:
            continue
        if abs(r["entry_gap"]) < cfg["min_gap"]:
            continue
        if r["entry_seconds_before"] < cfg["min_seconds_left"] or r["entry_seconds_before"] > cfg["max_seconds_left"]:
            continue
        out.append(r)
    return out


def simulate_staking(records: List[Dict[str, Any]], mode: str, initial: float = 10.0, stake_value: float = 1.0) -> Dict[str, Any]:
    bankroll = initial
    equity = [bankroll]
    active_records = []
    for r in records:
        if mode == "fixed_1":
            stake = 1.0
        elif mode == "fixed_fraction_10":
            stake = max(1.0, bankroll * 0.10)
        elif mode == "fixed_fraction_20":
            stake = max(1.0, bankroll * 0.20)
        else:
            stake = stake_value
        if bankroll < 1.0:
            break
        stake = min(stake, bankroll)
        pnl_per_dollar = r["pnl"] / max(r["amount"], 1e-9)
        pnl = stake * pnl_per_dollar
        bankroll += pnl
        equity.append(bankroll)
        rr = dict(r)
        rr["stake"] = round(stake, 6)
        rr["scaled_pnl"] = round(pnl, 6)
        rr["bankroll_after"] = round(bankroll, 6)
        active_records.append(rr)
    wins = sum(1 for r in active_records if r["won"])
    return {
        "mode": mode,
        "initial": initial,
        "final_bankroll": round(bankroll, 6),
        "net_pnl": round(bankroll - initial, 6),
        "trades": len(active_records),
        "win_rate": pct(wins, len(active_records)),
        "max_drawdown": max_drawdown([x - initial for x in equity[1:]]),
        "min_bankroll": round(min(equity), 6) if equity else initial,
        "active_records": active_records,
    }


def robustness_score(train_sum: Dict[str, Any], validation_sum: Dict[str, Any]) -> float:
    """Favor repeatable validation performance over pretty but tiny samples."""
    if validation_sum["trades"] < 20 or train_sum["trades"] < 20:
        return -9999.0
    pnl = validation_sum["total_pnl"]
    sample_bonus = min(validation_sum["trades"], 120) * 0.015
    drawdown_penalty = abs(validation_sum["max_drawdown"]) * 0.45 + abs(train_sum["max_drawdown"]) * 0.15
    loss_streak_penalty = validation_sum["longest_loss_streak"] * 0.8
    mismatch_penalty = abs(validation_sum["win_rate"] - train_sum["win_rate"]) * 0.04
    return round(pnl + sample_bonus - drawdown_penalty - loss_streak_penalty - mismatch_penalty, 6)


def simulate_pause_rule(records: List[Dict[str, Any]], multiple: float, initial: float = 10.0, reset_after_lock: bool = True) -> Dict[str, Any]:
    bankroll = initial
    locked = 0.0
    active = True
    equity = []
    active_trades = 0
    skipped = 0
    pauses = 0
    wins = 0
    losses = 0
    resume_after_loss_count = 0
    for r in records:
        if active:
            if bankroll < 1.0:
                break
            stake = min(1.0, bankroll)
            pnl_per_dollar = r["pnl"] / max(r["amount"], 1e-9)
            pnl = stake * pnl_per_dollar
            bankroll += pnl
            active_trades += 1
            wins += 1 if r["won"] else 0
            losses += 0 if r["won"] else 1
            if bankroll >= initial * multiple:
                pauses += 1
                if reset_after_lock:
                    locked += bankroll - initial
                    bankroll = initial
                active = False
        else:
            skipped += 1
            if not r["won"]:
                active = True
                resume_after_loss_count += 1
        equity.append(bankroll + locked)
    return {
        "multiple": multiple,
        "reset_after_lock": reset_after_lock,
        "initial": initial,
        "final_total": round(bankroll + locked, 6),
        "active_bankroll": round(bankroll, 6),
        "locked_profit": round(locked, 6),
        "net_pnl": round(bankroll + locked - initial, 6),
        "active_trades": active_trades,
        "skipped_signals": skipped,
        "pauses": pauses,
        "resumes_after_sim_loss": resume_after_loss_count,
        "win_rate_active": pct(wins, active_trades),
        "max_drawdown_total": max_drawdown([x - initial for x in equity]),
    }


def train_validation(records: List[Dict[str, Any]], ratio: float = 0.7) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    cut = int(len(records) * ratio)
    if cut >= len(records):
        cut = max(0, len(records) - 1)
    return records[:cut], records[cut:]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    sim_records, sim_meta = load_sim_trades()
    scan = data_quality_scan()
    cfgs = []
    for min_prob in (0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.92, 0.95, 0.97, 0.98, 0.99):
        for max_prob in (0.95, 0.97, 0.98, 0.99, 1.0):
            if min_prob > max_prob:
                continue
            for min_gap in (0, 10, 20, 50, 80, 120):
                for max_seconds in (10, 15, 25, 40, 60, 120):
                    for max_prob_age in (1.0, 2.0, 5.0):
                        cfgs.append({
                            "min_prob": min_prob,
                            "max_prob": max_prob,
                            "min_gap": min_gap,
                            "min_seconds_left": 1,
                            "max_seconds_left": max_seconds,
                            "max_prob_age": max_prob_age,
                            "min_amount": 1.0,
                        })
    train, validation = train_validation(sim_records)
    rows = []
    for cfg in cfgs:
        tr = filter_records(train, cfg)
        va = filter_records(validation, cfg)
        if len(tr) < 5:
            continue
        tr_raw = summarize_trades(tr)
        va_raw = summarize_trades(va)
        tr_sum = summarize_scaled(tr, stake=1.0, initial=10.0)
        va_sum = summarize_scaled(va, stake=1.0, initial=10.0)
        rows.append({
            "config": cfg,
            "train": tr_sum,
            "validation": va_sum,
            "train_raw_amounts": tr_raw,
            "validation_raw_amounts": va_raw,
            "robustness_score": robustness_score(tr_sum, va_sum),
        })
    rows.sort(key=lambda x: (
        x["validation"]["total_pnl"],
        x["validation"]["win_rate"],
        x["train"]["total_pnl"],
        x["validation"]["trades"],
    ), reverse=True)
    robust_rows = sorted(rows, key=lambda x: (
        x["robustness_score"],
        x["validation"]["win_rate"],
        x["validation"]["trades"],
    ), reverse=True)
    base_cfg = {"min_prob": 0.60, "max_prob": 1.0, "min_gap": 0, "min_seconds_left": 1, "max_seconds_left": 120, "max_prob_age": 5.0, "min_amount": 1.0}
    base_records = filter_records(sim_records, base_cfg)
    stake_modes = [simulate_staking(base_records, m) for m in ("fixed_1", "fixed_fraction_10", "fixed_fraction_20")]
    # Avoid selecting a row that looks great only because the validation tail was
    # friendly while the training segment already showed a large raw drawdown.
    recommended_rows = [
        r for r in robust_rows
        if r["train"]["max_drawdown"] >= -10 and r["validation"]["max_drawdown"] >= -10
    ]
    selected_cfg = (recommended_rows[0] if recommended_rows else robust_rows[0])["config"] if robust_rows else base_cfg
    selected_records = filter_records(sim_records, selected_cfg)
    selected_stake_modes = [simulate_staking(selected_records, m) for m in ("fixed_1", "fixed_fraction_10", "fixed_fraction_20")]
    pause_rules = []
    for multiple in (1.2, 1.5, 2.0, 3.0, 5.0):
        pause_rules.append(simulate_pause_rule(base_records, multiple, reset_after_lock=True))
        pause_rules.append(simulate_pause_rule(base_records, multiple, reset_after_lock=False))
    selected_pause_rules = []
    for multiple in (1.2, 1.5, 2.0, 3.0, 5.0):
        selected_pause_rules.append(simulate_pause_rule(selected_records, multiple, reset_after_lock=True))
        selected_pause_rules.append(simulate_pause_rule(selected_records, multiple, reset_after_lock=False))
    report = {
        "generated_at": datetime.now(CN).isoformat(),
        "sim_trade_meta": sim_meta,
        "sim_trade_summary_all": summarize_trades(sim_records),
        "sim_trade_summary_all_fixed_1": summarize_scaled(sim_records, stake=1.0, initial=10.0),
        "base_filter": base_cfg,
        "base_filtered_summary": summarize_trades(base_records),
        "base_filtered_summary_fixed_1": summarize_scaled(base_records, stake=1.0, initial=10.0),
        "data_quality_scan": scan,
        "train_validation": {
            "train_records": len(train),
            "validation_records": len(validation),
            "top_parameter_rows": rows[:20],
            "top_robust_rows": robust_rows[:20],
            "recommended_rows": recommended_rows[:20],
        },
        "stake_modes": [{k: v for k, v in r.items() if k != "active_records"} for r in stake_modes],
        "selected_filter": selected_cfg,
        "selected_filter_summary": summarize_trades(selected_records),
        "selected_filter_summary_fixed_1": summarize_scaled(selected_records, stake=1.0, initial=10.0),
        "selected_stake_modes": [{k: v for k, v in r.items() if k != "active_records"} for r in selected_stake_modes],
        "pause_rules": pause_rules,
        "selected_pause_rules": selected_pause_rules,
        "interpretation_flags": [
            "sim_trade_stream_is_not_independent_backtest; it reflects the bot signals that were actually logged",
            "profit-lock rules are evaluated on the same sequence and can overfit clustered wins/losses",
            "missing market data can still hide rare reversals; use as practical triage, not proof of edge",
        ],
    }
    out_path = OUT / "pragmatic_research.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(out_path),
        "sim_trade_summary_all": report["sim_trade_summary_all"],
        "base_filtered_summary": report["base_filtered_summary"],
        "top_parameter_rows": rows[:5],
        "top_robust_rows": robust_rows[:5],
        "stake_modes": report["stake_modes"],
        "selected_filter": report["selected_filter"],
        "selected_filter_summary": report["selected_filter_summary"],
        "selected_stake_modes": report["selected_stake_modes"],
        "pause_rules_top": sorted(pause_rules, key=lambda r: (r["net_pnl"], -r["max_drawdown_total"]), reverse=True)[:8],
        "selected_pause_rules_top": sorted(selected_pause_rules, key=lambda r: (r["net_pnl"], -r["max_drawdown_total"]), reverse=True)[:8],
        "data_quality_scan": scan,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
