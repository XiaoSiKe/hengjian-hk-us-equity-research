#!/usr/bin/env python3
"""Deterministic bear/base/bull equity valuation; no implicit market assumptions."""

import argparse
import datetime as dt
import json
import math
import sys


SCENARIOS = ("bear", "base", "bull")


def number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("{} must be a finite number".format(name))
    result = float(value)
    if positive and result <= 0:
        raise ValueError("{} must be positive".format(name))
    return result


def dated_evidence(item, name, cutoff, max_age_days=365):
    if not isinstance(item, dict) or not item.get("source_url"):
        raise ValueError("{} needs a source_url".format(name))
    try:
        date = dt.date.fromisoformat(item["as_of"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("{}.as_of must be YYYY-MM-DD".format(name)) from exc
    age = (cutoff - date).days
    if age < 0 or age > max_age_days:
        raise ValueError("{} evidence is after the cutoff or too old".format(name))
    return date


def dcf_value(starting_fcf, growth, discount, terminal_growth, years):
    if growth <= -1 or discount <= -1 or terminal_growth <= -1 or discount <= terminal_growth:
        raise ValueError("DCF requires growth/discount/terminal growth > -100% and discount > terminal growth")
    if isinstance(years, bool) or not isinstance(years, int) or not 1 <= years <= 10:
        raise ValueError("DCF horizon must be an integer from 1 to 10")
    pv = 0.0
    current = starting_fcf
    for year in range(1, years + 1):
        current *= 1 + growth
        pv += current / ((1 + discount) ** year)
    terminal = current * (1 + terminal_growth) / (discount - terminal_growth)
    value = pv + terminal / ((1 + discount) ** years)
    if not math.isfinite(value):
        raise ValueError("DCF value is not finite; inspect the assumptions")
    return value


def implied_growth_rate(starting_fcf, target_enterprise_value, discount, terminal_growth, years):
    """Return constant FCF growth implied by price within a broad numerical bracket."""
    if target_enterprise_value <= 0:
        return None
    lower, upper = -0.95, 5.0
    if dcf_value(starting_fcf, lower, discount, terminal_growth, years) > target_enterprise_value:
        return None
    if dcf_value(starting_fcf, upper, discount, terminal_growth, years) < target_enterprise_value:
        return None
    for _ in range(80):
        middle = (lower + upper) / 2
        if dcf_value(starting_fcf, middle, discount, terminal_growth, years) < target_enterprise_value:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2


def calculate(snapshot, assumptions):
    if snapshot.get("schema_version") != 1 or not snapshot.get("quality"):
        raise ValueError("Run normalize.py first and pass its output")
    if not snapshot["quality"].get("valuation_inputs_ok"):
        raise ValueError("Snapshot quality gate blocks valuation; inspect quality.issues")
    security = snapshot["security"]
    cutoff = dt.date.fromisoformat(snapshot["as_of"])
    reporting = security["reporting_currency"]
    listing = security["listing_currency"]
    method = assumptions.get("method")
    if method not in {"dcf", "ev_revenue", "ev_ebitda", "pe", "pb", "p_ffo"}:
        raise ValueError("method must be dcf, ev_revenue, ev_ebitda, pe, pb, or p_ffo")
    shares = assumptions.get("share_count")
    dated_evidence(shares, "share_count", cutoff)
    share_count = number(shares.get("value"), "share_count.value", positive=True)
    basis = shares.get("basis")
    instrument = security.get("instrument_type")
    if instrument == "adr":
        if basis not in {"ordinary", "adr"}:
            raise ValueError("ADR share_count.basis must be ordinary or adr")
    elif instrument == "common":
        if basis not in {"ordinary", "listed"}:
            raise ValueError("Common share_count.basis must be ordinary or listed")
    else:
        raise ValueError("Set security.instrument_type to common or adr before per-security valuation")
    ratio = 1.0
    if instrument == "adr" and basis == "ordinary":
        adr = assumptions.get("adr_ratio")
        dated_evidence(adr, "adr_ratio", cutoff, max_age_days=3650)
        ratio = number(adr.get("ordinary_per_adr"), "adr_ratio.ordinary_per_adr", positive=True)
    fx_rate = 1.0
    if reporting != listing:
        fx = assumptions.get("fx")
        dated_evidence(fx, "fx", cutoff, max_age_days=5)
        fx_rate = number(fx.get("listing_per_reporting"), "fx.listing_per_reporting", positive=True)
        if fx.get("from_currency") != reporting or fx.get("to_currency") != listing:
            raise ValueError("FX direction must be reporting currency to listing currency")
    net_cash = 0.0
    if method not in {"pe", "pb", "p_ffo"}:
        item = assumptions.get("net_cash")
        dated_evidence(item, "net_cash", cutoff)
        if item.get("currency") != reporting:
            raise ValueError("net_cash currency differs from reporting currency")
        net_cash = number(item.get("value"), "net_cash.value")
    reference_value = None
    if method == "dcf":
        metric = snapshot.get("derived", {}).get("free_cash_flow")
        if metric is None:
            raise ValueError("DCF needs derived free_cash_flow; missing OCF or capex")
        reference_value = number(metric["value"], "free_cash_flow", positive=True)
    elif method == "ev_revenue":
        metric = snapshot.get("metrics", {}).get("revenue")
        if metric is None:
            raise ValueError("EV/revenue needs revenue")
        reference_value = number(metric["value"], "revenue", positive=True)
    elif method == "pe":
        metric = assumptions.get("earnings_attributable")
        dated_evidence(metric, "earnings_attributable", cutoff)
        if metric.get("currency") != reporting or metric.get("period_end") != snapshot["fiscal_period_end"]:
            raise ValueError("P/E earnings currency/period must match the snapshot")
        reference_value = number(metric.get("value"), "earnings_attributable.value", positive=True)
    elif method in {"pb", "p_ffo"}:
        name = "book_value_attributable" if method == "pb" else "ffo_attributable"
        metric = assumptions.get(name)
        dated_evidence(metric, name, cutoff)
        if metric.get("currency") != reporting or metric.get("period_end") != snapshot["fiscal_period_end"]:
            raise ValueError("{} currency/period must match the snapshot".format(name))
        reference_value = number(metric.get("value"), name + ".value", positive=True)
    else:
        metric = assumptions.get("ebitda")
        dated_evidence(metric, "ebitda", cutoff)
        if metric.get("currency") != reporting or metric.get("period_end") != snapshot["fiscal_period_end"]:
            raise ValueError("EBITDA currency/period must match the snapshot")
        reference_value = number(metric.get("value"), "ebitda.value", positive=True)
    supplied = assumptions.get("scenarios") or {}
    if set(supplied) != set(SCENARIOS):
        raise ValueError("scenarios must contain exactly bear, base, and bull")
    results = {}
    for name in SCENARIOS:
        case = supplied[name]
        if not isinstance(case, dict):
            raise ValueError("scenario {} must be an object".format(name))
        if method == "dcf":
            growth = number(case.get("growth_rate"), name + ".growth_rate")
            discount = number(case.get("discount_rate"), name + ".discount_rate")
            terminal = number(case.get("terminal_growth"), name + ".terminal_growth")
            enterprise = dcf_value(reference_value, growth, discount, terminal, case.get("years"))
            equity_before_floor = enterprise + net_cash
            equity = max(0.0, equity_before_floor)
            formula = "PV(projected FCF) + PV(terminal value) + net_cash"
        else:
            multiple = number(case.get("multiple"), name + ".multiple", positive=True)
            metric_growth = number(case.get("metric_growth", 0), name + ".metric_growth")
            if metric_growth <= -1:
                raise ValueError("metric_growth must exceed -100%")
            projected = reference_value * (1 + metric_growth)
            if method in {"pe", "pb", "p_ffo"}:
                enterprise = None
                equity = projected * multiple
                equity_before_floor = equity
                formula = {
                    "pe": "projected earnings attributable to ordinary shareholders * P/E",
                    "pb": "projected equity book value attributable to ordinary shareholders * P/B",
                    "p_ffo": "projected FFO attributable to ordinary shareholders * P/FFO",
                }[method]
            else:
                enterprise = projected * multiple
                equity_before_floor = enterprise + net_cash
                equity = max(0.0, equity_before_floor)
                formula = "projected metric * EV multiple + net_cash"
        listed_value = (equity / share_count) * ratio * fx_rate
        result = {
            "assumptions": case,
            "enterprise_value_reporting_currency": enterprise,
            "equity_value_reporting_currency": equity,
            "equity_floor_applied": equity_before_floor < 0,
            "per_listed_security": listed_value,
            "listing_currency": listing,
            "formula": formula,
            "label": "D",
        }
        if snapshot["quality"].get("price_comparison_ok"):
            price = number(snapshot["quote"]["price"], "quote.price", positive=True)
            result["price_gap_pct"] = (listed_value / price - 1) * 100
        else:
            result["price_gap_pct"] = None
        results[name] = result
    values = [results[name]["per_listed_security"] for name in SCENARIOS]
    warnings = []
    if values != sorted(values):
        warnings.append("Scenario values are not bear <= base <= bull; inspect assumptions.")
    if any(results[name]["equity_floor_applied"] for name in SCENARIOS):
        warnings.append("At least one scenario had enterprise value below net debt; listed equity value was floored at zero.")
    if not snapshot["quality"].get("price_comparison_ok"):
        warnings.append("No usable price; price gap and price-dependent decision ranges were not calculated.")
    reverse_dcf = None
    if method == "dcf" and snapshot["quality"].get("price_comparison_ok"):
        base = supplied["base"]
        base_discount = number(base["discount_rate"], "base.discount_rate")
        base_terminal = number(base["terminal_growth"], "base.terminal_growth")
        base_years = base["years"]
        market_equity = number(snapshot["quote"]["price"], "quote.price", positive=True) * share_count / (ratio * fx_rate)
        target_enterprise = market_equity - net_cash
        implied = implied_growth_rate(reference_value, target_enterprise, base_discount, base_terminal, base_years)
        reverse_dcf = {
            "implied_annual_fcf_growth_rate": implied,
            "target_enterprise_value_reporting_currency": target_enterprise,
            "discount_rate": base_discount,
            "terminal_growth": base_terminal,
            "years": base_years,
            "label": "D",
            "note": "Mechanical price-implied constant FCF growth under base discount and terminal assumptions; not a forecast.",
        }
        if implied is None:
            warnings.append("Price-implied FCF growth is outside the supported numerical range or market-implied enterprise value is non-positive.")
    return {
        "schema_version": 1,
        "ticker": security["ticker"],
        "as_of": snapshot["as_of"],
        "method": method,
        "reporting_currency": reporting,
        "listing_currency": listing,
        "input_provenance": {
            "share_count": shares,
            "net_cash": assumptions.get("net_cash") if method not in {"pe", "pb", "p_ffo"} else None,
            "fx": assumptions.get("fx") if reporting != listing else None,
            "adr_ratio": assumptions.get("adr_ratio") if instrument == "adr" and basis == "ordinary" else None,
            "reference_metric": metric,
        },
        "quote": snapshot.get("quote") if snapshot["quality"].get("price_comparison_ok") else None,
        "scenarios": results,
        "reverse_dcf": reverse_dcf,
        "warnings": warnings,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("normalized", help="Output JSON from normalize.py")
    parser.add_argument("assumptions", help="Explicit valuation assumptions JSON")
    args = parser.parse_args(argv)
    try:
        with open(args.normalized, "r", encoding="utf-8") as handle:
            snapshot = json.load(handle)
        with open(args.assumptions, "r", encoding="utf-8") as handle:
            assumptions = json.load(handle)
        print(json.dumps(calculate(snapshot, assumptions), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("valuation: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
