"""
Official Polymarket CLOB SDK executor.

This replaces brittle browser-click execution with signed CLOB v2 orders.
It never logs secrets and keeps API credentials in memory only.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from py_clob_client_v2 import (
    ApiCreds,
    AssetType,
    BalanceAllowanceParams,
    ClobClient,
    MarketOrderArgs,
    OrderType,
    PartialCreateOrderOptions,
    Side,
)


TRADER_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path("/mnt/c/Users/yyq/Desktop/自动交易/btc5m数据")
MARKETS_FILE = DATA_ROOT / "shared" / "markets.jsonl"

load_dotenv(TRADER_ROOT / ".env")

HOST = os.getenv("POLYMARKET_CLOB_HOST", "https://clob.polymarket.com").rstrip("/")
CHAIN_ID = int(os.getenv("POLYMARKET_CHAIN_ID", "137"))
DEFAULT_MAX_ORDER_AMOUNT = float(os.getenv("POLYMARKET_MAX_ORDER_AMOUNT", "1.0"))
MIN_MARKET_ORDER_AMOUNT = float(os.getenv("POLYMARKET_MIN_MARKET_ORDER_AMOUNT", "1.0"))

_CREDS_CACHE: ApiCreds | None = None


def _private_key() -> str:
    return os.getenv("PRIVATE_KEY", "").strip()


def _funder() -> str:
    return os.getenv("FUNDER_ADDRESS", os.getenv("POLYMARKET_FUNDER_ADDRESS", "")).strip()


def _signature_type() -> int:
    raw = os.getenv("POLYMARKET_SIGNATURE_TYPE", "").strip()
    if raw:
        return int(raw)
    return 1 if _funder() else 0


def _env_creds() -> ApiCreds | None:
    key = os.getenv("CLOB_API_KEY", "").strip()
    secret = os.getenv("CLOB_SECRET", os.getenv("CLOB_API_SECRET", "")).strip()
    phrase = os.getenv("CLOB_PASS_PHRASE", os.getenv("CLOB_API_PASSPHRASE", "")).strip()
    if key and secret and phrase:
        return ApiCreds(api_key=key, api_secret=secret, api_passphrase=phrase)
    return None


def _sanitize(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {
            k: ("***" if any(s in k.lower() for s in ("secret", "passphrase", "key", "signature")) else _sanitize(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


def _client(level2: bool = True) -> ClobClient:
    private_key = _private_key()
    if not private_key and level2:
        raise RuntimeError("PRIVATE_KEY 未配置")

    signature_type = _signature_type()
    funder = _funder() or None

    if not level2:
        return ClobClient(host=HOST, chain_id=CHAIN_ID)

    creds = _env_creds() or _derive_creds(private_key, signature_type, funder)
    return ClobClient(
        host=HOST,
        chain_id=CHAIN_ID,
        key=private_key,
        creds=creds,
        signature_type=signature_type,
        funder=funder,
        retry_on_error=True,
    )


def _derive_creds(private_key: str, signature_type: int, funder: str | None) -> ApiCreds:
    global _CREDS_CACHE
    if _CREDS_CACHE is not None:
        return _CREDS_CACHE

    temp = ClobClient(
        host=HOST,
        chain_id=CHAIN_ID,
        key=private_key,
        signature_type=signature_type,
        funder=funder,
        retry_on_error=True,
    )
    try:
        _CREDS_CACHE = temp.derive_api_key()
    except Exception:
        _CREDS_CACHE = temp.create_api_key()
    return _CREDS_CACHE


def check_ready() -> bool:
    return health(check_auth=True).get("ok", False)


def health(check_auth: bool = True) -> dict:
    payload: dict[str, Any] = {
        "executor": "clob_sdk",
        "host": HOST,
        "chain_id": CHAIN_ID,
        "signature_type": _signature_type(),
        "has_private_key": bool(_private_key()),
        "has_funder": bool(_funder()),
        "funder": _mask_address(_funder()),
        "ok": False,
        "checks": [],
    }
    try:
        public = _client(level2=False)
        payload["checks"].append({"name": "CLOB public API", "ok": bool(public.get_ok())})
    except Exception as exc:
        payload["checks"].append({"name": "CLOB public API", "ok": False, "detail": str(exc)[:200]})
        return payload

    if not check_auth:
        payload["ok"] = True
        return payload

    try:
        client = _client(level2=True)
        payload["address"] = _mask_address(client.get_address())
        balance = client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
        payload["balance_allowance"] = _sanitize(balance)
        payload["checks"].append({"name": "L2 credentials", "ok": True})
        payload["checks"].append({"name": "pUSD balance/allowance", "ok": True})
        payload["ok"] = True
    except Exception as exc:
        payload["checks"].append({"name": "L2 credentials", "ok": False, "detail": str(exc)[:300]})
        payload["error"] = str(exc)[:300]
    return payload


def place_market_order(
    *,
    direction: str,
    amount: float,
    slug: str,
    token_id: str,
    max_order_amount: float = DEFAULT_MAX_ORDER_AMOUNT,
    order_type: str = OrderType.FAK,
    tick_size: str | None = "0.01",
    neg_risk: bool | None = False,
    dry_run: bool = False,
) -> dict:
    if direction not in ("Up", "Down"):
        return {"success": False, "error": "BAD_DIRECTION"}
    if not token_id:
        return {"success": False, "error": "MISSING_TOKEN_ID"}
    if amount < MIN_MARKET_ORDER_AMOUNT:
        return {"success": False, "error": "AMOUNT_BELOW_MARKET_MIN", "min": MIN_MARKET_ORDER_AMOUNT}
    if amount > max_order_amount:
        return {"success": False, "error": "AMOUNT_EXCEEDS_LIMIT", "max_order_amount": max_order_amount}

    resolved_order_type = OrderType.FOK if str(order_type).upper() == "FOK" else OrderType.FAK
    client = _client(level2=True)
    price = client.calculate_market_price(token_id, Side.BUY, float(amount), resolved_order_type)
    options = PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk)

    order_args = MarketOrderArgs(
        token_id=token_id,
        amount=float(amount),
        side=Side.BUY,
        price=price,
        order_type=resolved_order_type,
    )

    base = {
        "success": False,
        "executor": "clob_sdk",
        "slug": slug,
        "direction": direction,
        "amount": round(float(amount), 4),
        "token_id": token_id,
        "price": price,
        "order_type": resolved_order_type,
        "dry_run": dry_run,
    }
    if dry_run:
        base["success"] = True
        base["status"] = "dry_run"
        return base

    try:
        response = client.create_and_post_market_order(
            order_args=order_args,
            options=options,
            order_type=resolved_order_type,
        )
        data = _sanitize(response)
        if isinstance(data, dict):
            base.update(data)
            base["success"] = bool(data.get("success", True))
            base["orderID"] = data.get("orderID") or data.get("order_id") or ""
            base["status"] = data.get("status", "")
        else:
            base["response"] = data
            base["success"] = True
        return base
    except Exception as exc:
        base["error"] = str(exc)[:500]
        return base


def _mask_address(addr: str) -> str:
    if not addr:
        return ""
    if len(addr) <= 14:
        return addr
    return f"{addr[:8]}...{addr[-6:]}"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Polymarket CLOB SDK executor")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    dry = sub.add_parser("dry-run")
    dry.add_argument("--slug", required=True)
    dry.add_argument("--direction", choices=["Up", "Down"], required=True)
    dry.add_argument("--token-id", required=True)
    dry.add_argument("--amount", type=float, default=1.0)
    dry.add_argument("--order-type", choices=["FAK", "FOK"], default="FAK")
    args = parser.parse_args()

    if args.command == "health":
        print(json.dumps(health(check_auth=True), ensure_ascii=False, indent=2))
    elif args.command == "dry-run":
        print(json.dumps(place_market_order(
            direction=args.direction,
            amount=args.amount,
            slug=args.slug,
            token_id=args.token_id,
            order_type=args.order_type,
            dry_run=True,
        ), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
