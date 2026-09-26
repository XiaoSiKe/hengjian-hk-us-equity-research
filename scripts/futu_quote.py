#!/usr/bin/env python3
"""Optional read-only Futu OpenD quote snapshot; never touches trading APIs."""

import argparse
import datetime as dt
import json
import math
import re
import sys
from zoneinfo import ZoneInfo


DOC_URL = "https://openapi.futunn.com/futu-api-doc/en/quote/get-market-snapshot.html"


def futu_code(value):
    text = value.upper().strip()
    if text.startswith("HK."):
        text = text[3:]
        market = "HK"
    elif text.endswith(".HK"):
        text = text[:-3]
        market = "HK"
    elif text.startswith("US."):
        text = text[3:]
        market = "US"
    else:
        market = "US"
    if market == "HK":
        if not re.fullmatch(r"\d{1,5}", text) or int(text) == 0:
            raise ValueError("Invalid HK code")
        return "HK.{:05d}".format(int(text)), "HKD", ZoneInfo("Asia/Hong_Kong")
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]*", text):
        raise ValueError("Invalid US code")
    return "US." + text, "USD", ZoneInfo("America/New_York")


def snapshot(code, host="127.0.0.1", port=11111):
    security_code, currency, timezone = futu_code(code)
    try:
        from futu import OpenQuoteContext, RET_OK
    except ImportError as exc:
        raise RuntimeError("Install the official futu-api Python package and start your authorized OpenD session") from exc
    context = OpenQuoteContext(host=host, port=port)
    try:
        ret, data = context.get_market_snapshot([security_code])
        if ret != RET_OK:
            raise RuntimeError("Futu quote request failed: {}".format(data))
        if data is None or len(data) != 1:
            raise RuntimeError("Futu returned no unique snapshot for {}".format(security_code))
        row = data.iloc[0]
        price = float(row["last_price"])
        if not math.isfinite(price) or price <= 0:
            raise RuntimeError("Futu returned an invalid last_price")
        observed = dt.datetime.strptime(str(row["update_time"]), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone)
        return {
            "security_code": security_code,
            "quote": {
                "price": price,
                "currency": currency,
                "observed_at": observed.isoformat(),
                "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "provider": "Futu OpenAPI market snapshot",
                "source_url": DOC_URL,
                "delay_status": "unknown",
                "session": "unknown",
            },
            "note": "Check your market-data entitlement and session; this script does not claim the snapshot is real-time.",
        }
    finally:
        context.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("code", help="US.AAPL, HK.00700, AAPL, or 0700.HK")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11111)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(snapshot(args.code, args.host, args.port), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, RuntimeError, KeyError) as exc:
        print("futu_quote: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
