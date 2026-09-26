#!/usr/bin/env python3
"""Validate one issuer-period snapshot and calculate transparent financial ratios."""

import argparse
import datetime as dt
import json
import math
import re
import sys


MONEY_METRICS = {"revenue", "net_income", "operating_cash_flow", "capex", "cash"}
CRITICAL_FIELDS = {"revenue", "net_income", "operating_cash_flow", "capex", "share_count", "net_cash", "currency", "adr_ratio", "fx_rate"}


def finite_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("{} must be a finite number".format(name))
    return float(value)


def canonical_ticker(market, ticker):
    text = str(ticker).upper().strip()
    if market == "HK":
        match = re.fullmatch(r"(?:HK\.)?(\d{1,5})(?:\.HK)?", text)
        if not match:
            raise ValueError("HK ticker must be 1-5 digits, optionally with HK. or .HK")
        number = int(match.group(1))
        if number == 0:
            raise ValueError("HK ticker cannot be zero")
        return "{:04d}.HK".format(number)
    if market == "US":
        if text.startswith("US."):
            text = text[3:]
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]*", text):
            raise ValueError("Invalid US ticker")
        return text
    raise ValueError("market must be US or HK")


def parse_date(value, name):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("{} must be YYYY-MM-DD".format(name)) from exc


def derived(value, formula, inputs, unit):
    return {"value": value, "unit": unit, "label": "D", "formula": formula, "inputs": inputs}


def normalize_snapshot(snapshot):
    if snapshot.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    security = dict(snapshot.get("security") or {})
    market = str(security.get("market", "")).upper()
    security["market"] = market
    security["ticker"] = canonical_ticker(market, security.get("ticker", ""))
    reporting = str(security.get("reporting_currency", "")).upper()
    listing = str(security.get("listing_currency", "")).upper()
    if not re.fullmatch(r"[A-Z]{3}", reporting) or not re.fullmatch(r"[A-Z]{3}", listing):
        raise ValueError("reporting_currency and listing_currency must be three-letter codes")
    security["reporting_currency"] = reporting
    security["listing_currency"] = listing
    instrument_type = security.get("instrument_type", "unknown")
    if instrument_type not in {"common", "adr", "unknown"}:
        raise ValueError("instrument_type must be common, adr, or unknown")
    as_of = parse_date(snapshot.get("as_of"), "as_of")
    try:
        retrieved_at = dt.datetime.fromisoformat(snapshot["retrieved_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("retrieved_at must be ISO 8601 with timezone") from exc
    if retrieved_at.tzinfo is None:
        raise ValueError("retrieved_at needs a timezone offset")
    fiscal_end = parse_date(snapshot.get("fiscal_period_end"), "fiscal_period_end")
    fiscal_type = snapshot.get("fiscal_period_type", "annual")
    if fiscal_type not in {"annual", "quarterly"}:
        raise ValueError("fiscal_period_type must be annual or quarterly")
    fiscal_start = snapshot.get("fiscal_period_start")
    if fiscal_type == "quarterly" and not fiscal_start:
        raise ValueError("quarterly snapshot needs fiscal_period_start")
    if fiscal_start:
        fiscal_start = parse_date(fiscal_start, "fiscal_period_start")
        if fiscal_start > fiscal_end:
            raise ValueError("fiscal_period_start is after fiscal_period_end")
    if fiscal_end > as_of:
        raise ValueError("fiscal period ends after the research cutoff")
    metrics = snapshot.get("metrics") or {}
    if not isinstance(metrics, dict):
        raise ValueError("metrics must be an object")
    issues = []
    for name, metric in metrics.items():
        if not isinstance(metric, dict):
            raise ValueError("metric {} must be an object".format(name))
        finite_number(metric.get("value"), name + ".value")
        if not metric.get("source_url"):
            raise ValueError("metric {} lacks source_url".format(name))
        period_end = parse_date(metric.get("period_end"), name + ".period_end")
        if period_end != fiscal_end:
            raise ValueError("metric {} does not match fiscal_period_end".format(name))
        publication = metric.get("filed_at") or metric.get("published_at")
        filed = parse_date(publication, name + ".filed_at/published_at")
        if filed > as_of:
            raise ValueError("metric {} was not filed by the research cutoff".format(name))
        if (filed - retrieved_at.date()).days > 1:
            raise ValueError("metric {} was published after the recorded retrieval time".format(name))
        if name in MONEY_METRICS:
            if metric.get("unit") != reporting or metric.get("currency") != reporting:
                raise ValueError("metric {} currency differs from reporting currency; provide a sourced conversion".format(name))
        if name == "diluted_shares" and metric.get("unit") != "shares":
            raise ValueError("diluted_shares must use shares")
        expected_type = "point" if name == "cash" else fiscal_type
        if metric.get("period_type") != expected_type:
            raise ValueError("metric {} period_type must be {}".format(name, expected_type))
        if expected_type != "point":
            start = parse_date(metric.get("period_start"), name + ".period_start")
            if fiscal_start and start != fiscal_start:
                raise ValueError("metric {} does not match fiscal_period_start".format(name))
            days = (period_end - start).days + 1
            minimum_days, maximum_days = (330, 380) if fiscal_type == "annual" else (61, 122)
            if not minimum_days <= days <= maximum_days:
                raise ValueError("metric {} duration does not match {} period".format(name, fiscal_type))
        elif metric.get("period_start") is not None:
            raise ValueError("point-in-time metric {} must not have period_start".format(name))
    result = dict(snapshot)
    result["security"] = security
    result["metrics"] = metrics
    output = {}
    revenue = metrics.get("revenue", {}).get("value")
    income = metrics.get("net_income", {}).get("value")
    ocf = metrics.get("operating_cash_flow", {}).get("value")
    capex = metrics.get("capex", {}).get("value")
    if ocf is not None and capex is not None:
        output["free_cash_flow"] = derived(float(ocf) - abs(float(capex)), "operating_cash_flow - abs(capex)", ["operating_cash_flow", "capex"], reporting)
    else:
        issues.append("Free cash flow unavailable: operating cash flow or capex missing.")
    if revenue is not None and revenue > 0:
        if income is not None:
            output["net_margin"] = derived(float(income) / float(revenue), "net_income / revenue", ["net_income", "revenue"], "ratio")
        if "free_cash_flow" in output:
            output["fcf_margin"] = derived(output["free_cash_flow"]["value"] / float(revenue), "free_cash_flow / revenue", ["free_cash_flow", "revenue"], "ratio")
    elif revenue is not None:
        issues.append("Margins unavailable: revenue is not positive.")
    if income is not None and income > 0 and ocf is not None:
        output["cash_conversion"] = derived(float(ocf) / float(income), "operating_cash_flow / net_income", ["operating_cash_flow", "net_income"], "ratio")
    if instrument_type == "adr":
        adr = security.get("adr_ratio")
        if not adr:
            issues.append("ADR ratio missing; do not convert per-share values.")
        elif not isinstance(adr, dict) or not adr.get("source_url") or finite_number(adr.get("ordinary_per_adr"), "adr_ratio.ordinary_per_adr") <= 0:
            raise ValueError("ADR ratio needs a positive ordinary_per_adr and source_url")
    conflicts = snapshot.get("conflicts") or []
    if not isinstance(conflicts, list):
        raise ValueError("conflicts must be a list")
    block_valuation = False
    block_price = False
    for conflict in conflicts:
        if not isinstance(conflict, dict) or not conflict.get("field"):
            raise ValueError("each conflict must name a field")
        field = conflict["field"]
        issues.append("Unresolved source conflict: {}.".format(field))
        if field in CRITICAL_FIELDS or field not in {"quote", "price"}:
            block_valuation = True
        if field in {"quote", "price"} or field not in CRITICAL_FIELDS:
            block_price = True
    if fiscal_type == "quarterly":
        block_valuation = True
        issues.append("Standalone quarter is for earnings review; valuation needs sourced annual or TTM inputs.")
    quote = snapshot.get("quote")
    price_ok = False
    if quote is not None:
        if not isinstance(quote, dict):
            raise ValueError("quote must be an object or null")
        price = finite_number(quote.get("price"), "quote.price")
        if price <= 0 or quote.get("currency") != listing or not quote.get("source_url"):
            raise ValueError("quote needs a positive price, listing currency, and source_url")
        try:
            observed = dt.datetime.fromisoformat(quote["observed_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("quote.observed_at must be ISO 8601 with timezone") from exc
        if observed.tzinfo is None:
            raise ValueError("quote.observed_at needs a timezone offset")
        age = (as_of - observed.date()).days
        if age < 0:
            raise ValueError("quote was observed after the research cutoff")
        if age > 5:
            issues.append("Quote is more than five calendar days old; price-dependent conclusions paused.")
        else:
            price_ok = True
    else:
        issues.append("No verifiable price snapshot; price-dependent conclusions paused.")
    result["derived"] = output
    result["fiscal_period_type"] = fiscal_type
    result["quality"] = {
        "issues": issues,
        "valuation_inputs_ok": not block_valuation,
        "price_comparison_ok": price_ok and not block_price,
    }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", help="JSON snapshot, often output from sec_facts.py")
    args = parser.parse_args(argv)
    try:
        with open(args.snapshot, "r", encoding="utf-8") as handle:
            snapshot = json.load(handle)
        print(json.dumps(normalize_snapshot(snapshot), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("normalize: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
