#!/usr/bin/env python3
"""Read-only, point-in-time SEC annual and single-quarter facts extractor."""

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request


TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A"}
QUARTERLY_FORMS = {"10-Q", "10-Q/A"}
METRIC_TAGS = {
    "revenue": [
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "Revenues"),
        ("us-gaap", "SalesRevenueNet"),
        ("ifrs-full", "Revenue"),
    ],
    "net_income": [
        ("us-gaap", "NetIncomeLoss"),
        ("ifrs-full", "ProfitLoss"),
    ],
    "operating_cash_flow": [
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
        ("ifrs-full", "CashFlowsFromUsedInOperatingActivities"),
    ],
    "capex": [
        ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
        ("ifrs-full", "PurchaseOfPropertyPlantAndEquipment"),
    ],
    "diluted_shares": [
        ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),
        ("ifrs-full", "WeightedAverageNumberOfDilutedSharesOutstanding"),
    ],
    "cash": [
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
        ("ifrs-full", "CashAndCashEquivalents"),
    ],
}


def parse_date(value):
    return dt.date.fromisoformat(value)


def contact_header():
    value = os.environ.get("SEC_CONTACT", "").strip()
    if "@" not in value or len(value.split()) < 2:
        raise ValueError("Set SEC_CONTACT to a real name or organization and contact email, e.g. 'Researcher name@example.com'.")
    return value


def fetch_json(url, contact, opener=None):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": contact, "Accept": "application/json", "Accept-Encoding": "gzip"},
    )
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(request, timeout=30) as response:
            raw = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                import gzip
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError("SEC request failed with HTTP {} for {}".format(exc.code, url)) from exc


def resolve_ticker(index, ticker):
    needle = ticker.upper().replace(".", "-")
    matches = [row for row in index.values() if str(row.get("ticker", "")).upper().replace(".", "-") == needle]
    if len(matches) != 1:
        raise ValueError("Ticker {} matched {} SEC issuers; supply --cik instead.".format(ticker, len(matches)))
    return int(matches[0]["cik_str"]), str(matches[0]["ticker"]).upper()


def period_candidates(companyfacts, tags, as_of, target_end=None, preferred_unit=None, instant=False, period="annual"):
    if period not in {"annual", "quarterly"}:
        raise ValueError("period must be annual or quarterly")
    forms = ANNUAL_FORMS if period == "annual" else QUARTERLY_FORMS
    minimum_days, maximum_days = (330, 380) if period == "annual" else (61, 122)
    candidates = []
    facts = companyfacts.get("facts", {})
    for rank, (taxonomy, tag) in enumerate(tags):
        item = facts.get(taxonomy, {}).get(tag, {})
        for unit, observations in item.get("units", {}).items():
            if unit not in ({preferred_unit} if preferred_unit else {"USD", "HKD", "CNY", "EUR", "GBP", "JPY", "shares"}):
                continue
            for row in observations:
                if row.get("form") not in forms or not row.get("accn") or not row.get("filed") or not row.get("end"):
                    continue
                try:
                    filed = parse_date(row["filed"])
                    end = parse_date(row["end"])
                except ValueError:
                    continue
                if filed > as_of or end > as_of or (target_end and row["end"] != target_end):
                    continue
                if instant:
                    if row.get("start"):
                        continue
                else:
                    if not row.get("start"):
                        continue
                    try:
                        days = (end - parse_date(row["start"])).days + 1
                    except ValueError:
                        continue
                    if not minimum_days <= days <= maximum_days:
                        continue
                if not isinstance(row.get("val"), (int, float)) or isinstance(row.get("val"), bool):
                    continue
                candidates.append((end, filed, -rank, taxonomy, tag, unit, row))
    return candidates


def pick_metric(companyfacts, metric, as_of, target_end=None, preferred_unit=None, period="annual"):
    instant = metric == "cash"
    candidates = period_candidates(companyfacts, METRIC_TAGS[metric], as_of, target_end, preferred_unit, instant, period)
    if not candidates:
        return None
    end, filed, _, taxonomy, tag, unit, row = max(candidates, key=lambda x: (x[0], x[1], x[2]))
    cik = int(companyfacts["cik"])
    accn = row["accn"]
    return {
        "value": row["val"],
        "unit": unit,
        "currency": None if unit == "shares" else unit,
        "period_start": row.get("start"),
        "period_end": end.isoformat(),
        "period_type": "point" if instant else period,
        "filed_at": filed.isoformat(),
        "form": row["form"],
        "accession": accn,
        "taxonomy_tag": "{}:{}".format(taxonomy, tag),
        "source_url": "https://www.sec.gov/Archives/edgar/data/{}/{}/".format(cik, re.sub(r"[^0-9]", "", accn)),
        "data_url": FACTS_URL.format(cik=cik),
    }


def extract_snapshot(companyfacts, ticker, as_of, period="annual"):
    anchor = pick_metric(companyfacts, "revenue", as_of, period=period) or pick_metric(companyfacts, "net_income", as_of, period=period)
    if anchor is None:
        raise ValueError("No {} revenue or net income fact filed by {} was found; inspect the filing manually.".format(period, as_of))
    fiscal_end = anchor["period_end"]
    fiscal_start = anchor["period_start"]
    currency = anchor["unit"]
    metrics = {}
    missing = []
    for metric in METRIC_TAGS:
        unit = "shares" if metric == "diluted_shares" else currency
        found = pick_metric(companyfacts, metric, as_of, fiscal_end, unit, period)
        if found and found["period_type"] != "point" and found["period_start"] != fiscal_start:
            found = None
        if found:
            metrics[metric] = found
        else:
            missing.append(metric)
    return {
        "schema_version": 1,
        "security": {
            "market": "US",
            "ticker": ticker,
            "company": companyfacts.get("entityName", ""),
            "cik": "{:010d}".format(int(companyfacts["cik"])),
            "instrument_type": "unknown",
            "listing_currency": "USD",
            "reporting_currency": currency,
        },
        "as_of": as_of.isoformat(),
        "fiscal_period_type": period,
        "fiscal_period_start": fiscal_start,
        "fiscal_period_end": fiscal_end,
        "metrics": metrics,
        "missing": missing,
        "quote": None,
        "conflicts": [],
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_url": FACTS_URL.format(cik=int(companyfacts["cik"])),
        "note": "XBRL {} facts only; inspect the filing, ADR terms and restatements. 10-Q cash-flow facts may be year-to-date, so absent standalone-quarter cash flow is left missing.".format(period),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker")
    group.add_argument("--cik", type=int)
    parser.add_argument("--as-of", required=True, help="Research cutoff date YYYY-MM-DD")
    parser.add_argument("--period", choices=("annual", "quarterly"), default="annual")
    args = parser.parse_args(argv)
    try:
        as_of = parse_date(args.as_of)
        if as_of > dt.datetime.now(dt.timezone.utc).date():
            raise ValueError("Research cutoff cannot be in the future (UTC).")
        contact = contact_header()
        if args.ticker:
            index = fetch_json(TICKERS_URL, contact)
            cik, ticker = resolve_ticker(index, args.ticker)
            time.sleep(0.25)
        else:
            cik, ticker = args.cik, "CIK{:010d}".format(args.cik)
        companyfacts = fetch_json(FACTS_URL.format(cik=cik), contact)
        print(json.dumps(extract_snapshot(companyfacts, ticker, as_of, args.period), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, RuntimeError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print("sec_facts: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
