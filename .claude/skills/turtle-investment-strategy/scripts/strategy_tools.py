#!/usr/bin/env python3
"""Deterministic helpers for the turtle investment strategy skill."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

MARKET_KEYS = {"CN": "CN_10Y", "HK": "HK_10Y", "US": "US_10Y"}
MARKET_THRESHOLD_RULES = {
    "CN": (3.5, 2.0),
    "HK": (5.0, 3.0),
    "US": (5.0, 3.0),
}


def write_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def fail(message: str) -> int:
    write_json({"error": message})
    return 2


def parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def market_key(market: str) -> str:
    try:
        return MARKET_KEYS[market.upper()]
    except KeyError as exc:
        raise ValueError("market must be one of CN, HK, US") from exc


def rf_cache(cache_path: Path, market: str, as_of: str) -> dict[str, Any]:
    key = market_key(market)
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"usable": False, "key": key, "reason": "cache_missing"}
    except json.JSONDecodeError as exc:
        return {"usable": False, "key": key, "reason": f"cache_invalid: {exc.msg}"}

    entry = cache.get(key)
    if not isinstance(entry, dict):
        return {"usable": False, "key": key, "reason": "market_entry_missing"}

    required = ("value", "date", "expiry_days")
    if any(field not in entry for field in required):
        return {"usable": False, "key": key, "reason": "market_entry_incomplete"}

    try:
        value = float(entry["value"])
        cached_on = parse_iso_date(str(entry["date"]))
        expiry_days = int(entry["expiry_days"])
        reference_date = parse_iso_date(as_of)
    except (TypeError, ValueError):
        return {"usable": False, "key": key, "reason": "market_entry_invalid"}

    age_days = (reference_date - cached_on).days
    usable = 0 <= age_days <= expiry_days
    return {
        "usable": usable,
        "key": key,
        "value": value,
        "date": cached_on.isoformat(),
        "expiry_days": expiry_days,
        "age_days": age_days,
        "reason": "fresh" if usable else "expired_or_future_dated",
    }


def cash_protection(net_cash_ratio: float) -> tuple[str, float]:
    if net_cash_ratio < 0.2:
        return "无保护", 0.30
    if net_cash_ratio < 0.4:
        return "轻度", 0.25
    if net_cash_ratio < 0.6:
        return "强", 0.20
    return "极强", 0.15


def calculate(payload: dict[str, Any]) -> dict[str, Any]:
    required = (
        "market", "market_cap", "net_income", "depreciation_amortization",
        "maintenance_capex_ratio", "payout_ratio", "dividend_tax_rate",
        "annual_buybacks", "disposable_cash_surplus", "risk_free_rate",
        "net_cash", "cyclical_adjustment_pct", "current_price",
    )
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    market = str(payload["market"]).upper()
    if market not in MARKET_THRESHOLD_RULES:
        raise ValueError("market must be one of CN, HK, US")

    numbers = {field: float(payload[field]) for field in required if field != "market"}
    if numbers["market_cap"] <= 0:
        raise ValueError("market_cap must be greater than zero")

    owner_earnings = (
        numbers["net_income"]
        + numbers["depreciation_amortization"]
        - numbers["depreciation_amortization"] * numbers["maintenance_capex_ratio"]
    )
    distributable_factor = numbers["payout_ratio"] * (1 - numbers["dividend_tax_rate"])
    rough_return = (
        owner_earnings * distributable_factor + numbers["annual_buybacks"]
    ) / numbers["market_cap"] * 100
    precise_return = (
        numbers["disposable_cash_surplus"] * distributable_factor
        + numbers["annual_buybacks"]
    ) / numbers["market_cap"] * 100

    base_threshold, rf_spread = MARKET_THRESHOLD_RULES[market]
    threshold = max(base_threshold, numbers["risk_free_rate"] + rf_spread)
    net_cash_ratio = numbers["net_cash"] / numbers["market_cap"]
    protection_level, default_discount = cash_protection(net_cash_ratio)
    discount = float(payload.get("cash_protection_discount", default_discount))
    adjusted_margin = precise_return - threshold + numbers["cyclical_adjustment_pct"]
    target_price = (
        numbers["current_price"] * (precise_return / threshold) * (1 - discount)
    )

    ev = numbers["market_cap"] - numbers["net_cash"]
    ev_return = None
    if net_cash_ratio > 0.4 and ev > 0:
        ev_return = (
            numbers["disposable_cash_surplus"] * distributable_factor
            + numbers["annual_buybacks"]
        ) / ev * 100

    return {
        "owner_earnings": round(owner_earnings, 4),
        "rough_penetration_return_pct": round(rough_return, 4),
        "precise_penetration_return_pct": round(precise_return, 4),
        "threshold_pct": round(threshold, 4),
        "adjusted_safety_margin_pct": round(adjusted_margin, 4),
        "net_cash_to_market_cap_pct": round(net_cash_ratio * 100, 4),
        "cash_protection_level": protection_level,
        "cash_protection_discount": round(discount, 4),
        "target_buy_price": round(target_price, 4),
        "ev": round(ev, 4),
        "ev_penetration_return_pct": None if ev_return is None else round(ev_return, 4),
    }


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    required = (
        "market_cap", "net_income", "depreciation_amortization",
        "payout_ratio", "dividend_tax_rate", "annual_buybacks",
        "disposable_cash_surplus", "risk_free_rate", "net_cash", "current_price",
    )
    missing_fields = [field for field in required if payload.get(field) is None]
    issues: list[str] = []
    if payload.get("unit") not in {"百万元", "千元", "万元"}:
        issues.append("unit must be one of 百万元, 千元, 万元")
    if not payload.get("currency"):
        issues.append("currency is required")
    return {
        "valid": not missing_fields and not issues,
        "missing_fields": missing_fields,
        "issues": issues,
        "downgrade_recommended": bool(missing_fields or issues),
    }


def prepare(symbol: str, company: str, output_root: Path, as_of: str) -> dict[str, Any]:
    analysis_date = parse_iso_date(as_of)
    target_year = analysis_date.year - (2 if analysis_date.month <= 3 else 1)
    symbol_root = output_root / symbol
    symbol_root.mkdir(parents=True, exist_ok=True)
    version_dir = symbol_root / analysis_date.isoformat()
    if version_dir.exists():
        version_dir = symbol_root / f"{analysis_date:%Y-%m-%d}_{datetime.now():%H-%M}"
    version_dir.mkdir(parents=True, exist_ok=False)
    return {
        "symbol": symbol,
        "company": company,
        "target_year": target_year,
        "symbol_root": str(symbol_root),
        "version_dir": str(version_dir),
    }


def finalize(index_path: Path, latest_dir: Path, version: dict[str, Any]) -> dict[str, Any]:
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        index = {
            "symbol": version["symbol"],
            "company": version["company"],
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "versions": [],
        }
    index.setdefault("versions", []).append(version["record"])
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = index_path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_path, index_path)

    latest_link = index_path.parent / "latest"
    temporary_link = index_path.parent / ".latest.tmp"
    temporary_link.unlink(missing_ok=True)
    temporary_link.symlink_to(latest_dir.name)
    os.replace(temporary_link, latest_link)
    return {"index": str(index_path), "latest": str(latest_link), "versions": len(index["versions"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    rf_parser = subparsers.add_parser("rf-cache")
    rf_parser.add_argument("--cache", type=Path, required=True)
    rf_parser.add_argument("--market", required=True)
    rf_parser.add_argument("--as-of", required=True)

    calculate_parser = subparsers.add_parser("calculate")
    calculate_parser.add_argument("--input-json", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--input-json", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--symbol", required=True)
    prepare_parser.add_argument("--company", required=True)
    prepare_parser.add_argument("--output-root", type=Path, required=True)
    prepare_parser.add_argument("--as-of", required=True)

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--index", type=Path, required=True)
    finalize_parser.add_argument("--latest-dir", type=Path, required=True)
    finalize_parser.add_argument("--version-json", required=True)

    args = parser.parse_args()
    try:
        if args.command == "rf-cache":
            write_json(rf_cache(args.cache, args.market, args.as_of))
        elif args.command == "calculate":
            write_json(calculate(json.loads(args.input_json)))
        elif args.command == "validate":
            write_json(validate(json.loads(args.input_json)))
        elif args.command == "prepare":
            write_json(prepare(args.symbol, args.company, args.output_root, args.as_of))
        else:
            write_json(finalize(args.index, args.latest_dir, json.loads(args.version_json)))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
