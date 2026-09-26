"""Frozen, source-linked issuer cases; these are historical checks, not live advice."""

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import normalize  # noqa: E402
import recommendation_gate  # noqa: E402


RETRIEVED = "2026-09-26T12:00:00+00:00"
APPLE = "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm"
TENCENT = "https://static.www.tencent.com/uploads/2026/03/18/bd32d8ee320b72f0d72d545fd2d65851.pdf"
ALIBABA = "https://www.sec.gov/Archives/edgar/data/1577552/000095017025090161/baba-20250331.htm"
ALIBABA_ADR = "https://www.alibabagroup.com/en-US/faqs-investor-information"


def report_fact(value, currency, start, end, published, url):
    return {"value": value, "unit": currency, "currency": currency, "period_start": start,
            "period_end": end, "period_type": "annual", "published_at": published, "source_url": url}


def issuer_case(market, ticker, company, reporting, listing, start, end, published, source, revenue, as_of, adr=False):
    security = {"market": market, "ticker": ticker, "company": company,
                "instrument_type": "adr" if adr else "common", "reporting_currency": reporting,
                "listing_currency": listing}
    if adr:
        security["underlying_ticker"] = "9988.HK"
        security["adr_ratio"] = {"ordinary_per_adr": 8, "source_url": ALIBABA_ADR}
    return normalize.normalize_snapshot({
        "schema_version": 1, "security": security, "as_of": as_of, "retrieved_at": RETRIEVED,
        "fiscal_period_type": "annual", "fiscal_period_start": start, "fiscal_period_end": end,
        "metrics": {"revenue": report_fact(revenue, reporting, start, end, published, source)},
        "quote": None, "conflicts": [],
    })


class RealIssuerSmokeTests(unittest.TestCase):
    def test_apple_sec_history_has_source_and_no_unsourced_price_call(self):
        item = issuer_case("US", "AAPL", "Apple Inc.", "USD", "USD", "2024-09-29", "2025-09-27",
                           "2025-10-31", APPLE, 416161000000, "2025-11-15")
        self.assertEqual(item["metrics"]["revenue"]["value"], 416161000000)
        self.assertFalse(item["quality"]["price_comparison_ok"])
        self.assertEqual(recommendation_gate.decide({"ticker": "AAPL", "identity_verified": True, "business_thesis": "uncertain"})["recommendation"], "等待核实")

    def test_tencent_company_ir_uses_reporting_currency_not_hk_quote_currency(self):
        item = issuer_case("HK", "HK.00700", "Tencent Holdings Limited", "CNY", "HKD", "2025-01-01",
                           "2025-12-31", "2026-03-18", TENCENT, 751766000000, "2026-04-30")
        self.assertEqual(item["security"]["ticker"], "0700.HK")
        self.assertEqual(item["metrics"]["revenue"]["currency"], "CNY")
        self.assertEqual(item["security"]["listing_currency"], "HKD")
        self.assertFalse(item["quality"]["price_comparison_ok"])

    def test_alibaba_adr_cannot_use_ordinary_share_price_without_ratio_and_fx(self):
        item = issuer_case("US", "BABA", "Alibaba Group Holding Limited", "CNY", "USD", "2024-04-01",
                           "2025-03-31", "2025-06-26", ALIBABA, 996347000000, "2025-07-01", adr=True)
        self.assertEqual(item["security"]["adr_ratio"]["ordinary_per_adr"], 8)
        self.assertEqual(item["security"]["underlying_ticker"], "9988.HK")
        self.assertFalse(item["quality"]["price_comparison_ok"])


if __name__ == "__main__":
    unittest.main()
