#!/usr/bin/env python3
"""Compare two normalized periods for one issuer without mixing currencies or horizons."""

import argparse
import datetime as dt
import json
import math
import sys


METRICS = ("revenue", "net_income", "operating_cash_flow", "capex", "diluted_shares")


def compare(prior, current, basis):
    if basis not in {"yoy", "qoq"}:
        raise ValueError("basis must be yoy or qoq")
    if not prior.get("quality") or not current.get("quality"):
        raise ValueError("Normalize both snapshots first")
    a, b = prior["security"], current["security"]
    for field in ("market", "ticker", "reporting_currency", "instrument_type"):
        if a.get(field) != b.get(field):
            raise ValueError("Snapshots differ in {}".format(field))
    if a.get("cik") and b.get("cik") and a["cik"] != b["cik"]:
        raise ValueError("Snapshots have different issuer CIKs")
    kind = prior.get("fiscal_period_type", "annual")
    if kind != current.get("fiscal_period_type", "annual"):
        raise ValueError("Annual and quarterly snapshots cannot be mixed")
    if basis == "qoq" and kind != "quarterly":
        raise ValueError("Quarter-on-quarter comparison needs quarterly snapshots")
    if prior.get("conflicts") or current.get("conflicts"):
        raise ValueError("Resolve source conflicts before period comparison")
    old_end = dt.date.fromisoformat(prior["fiscal_period_end"])
    new_end = dt.date.fromisoformat(current["fiscal_period_end"])
    gap = (new_end - old_end).days
    minimum, maximum = (330, 400) if basis == "yoy" else (61, 122)
    if not minimum <= gap <= maximum:
        raise ValueError("Period-end spacing does not support {} comparison".format(basis))
    changes = {}
    missing = []
    for name in METRICS:
        older = prior.get("metrics", {}).get(name)
        newer = current.get("metrics", {}).get(name)
        if older is None or newer is None:
            missing.append(name)
            continue
        old_value = float(older["value"])
        new_value = float(newer["value"])
        if not math.isfinite(old_value) or not math.isfinite(new_value) or older["unit"] != newer["unit"]:
            raise ValueError("Metric {} has invalid values or mismatched units".format(name))
        delta = new_value - old_value
        changes[name] = {
            "prior": old_value,
            "current": new_value,
            "change": delta,
            "change_pct": delta / abs(old_value) * 100 if old_value != 0 else None,
            "unit": newer["unit"],
            "prior_period": older["period_end"],
            "current_period": newer["period_end"],
            "prior_source": older["source_url"],
            "current_source": newer["source_url"],
            "label": "D",
        }
    old_fcf = prior.get("derived", {}).get("free_cash_flow")
    new_fcf = current.get("derived", {}).get("free_cash_flow")
    if old_fcf and new_fcf:
        old_value, new_value = float(old_fcf["value"]), float(new_fcf["value"])
        changes["free_cash_flow"] = {
            "prior": old_value,
            "current": new_value,
            "change": new_value - old_value,
            "change_pct": (new_value - old_value) / abs(old_value) * 100 if old_value != 0 else None,
            "unit": b["reporting_currency"],
            "prior_inputs": old_fcf["inputs"],
            "current_inputs": new_fcf["inputs"],
            "prior_sources": [prior["metrics"][key]["source_url"] for key in ("operating_cash_flow", "capex")],
            "current_sources": [current["metrics"][key]["source_url"] for key in ("operating_cash_flow", "capex")],
            "label": "D",
        }
    return {
        "schema_version": 1,
        "ticker": b["ticker"],
        "basis": basis,
        "fiscal_period_type": kind,
        "prior_period_end": old_end.isoformat(),
        "current_period_end": new_end.isoformat(),
        "reporting_currency": b["reporting_currency"],
        "changes": changes,
        "missing": missing,
        "note": "Percentage change uses absolute prior value in the denominator; interpret sign-crossing and seasonal QoQ changes in context.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prior", help="Prior normalized snapshot JSON")
    parser.add_argument("current", help="Current normalized snapshot JSON")
    parser.add_argument("--basis", choices=("yoy", "qoq"), required=True)
    args = parser.parse_args(argv)
    try:
        with open(args.prior, "r", encoding="utf-8") as handle:
            prior = json.load(handle)
        with open(args.current, "r", encoding="utf-8") as handle:
            current = json.load(handle)
        print(json.dumps(compare(prior, current, args.basis), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print("compare_periods: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
