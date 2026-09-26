"""Behavioral checks with synthetic issuer data; no live market data or trading."""

import datetime as dt
import json
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import futu_quote  # noqa: E402
import compare_periods  # noqa: E402
import normalize  # noqa: E402
import sec_facts  # noqa: E402
import valuation  # noqa: E402


SOURCE = "https://example.org/issuer-report"


def metric(value, currency="USD", name="revenue", filed="2025-03-20"):
    shares = name == "diluted_shares"
    point = name == "cash"
    return {
        "value": value,
        "unit": "shares" if shares else currency,
        "currency": None if shares else currency,
        "period_start": None if point else "2024-01-01",
        "period_end": "2024-12-31",
        "period_type": "point" if point else "annual",
        "filed_at": filed,
        "source_url": SOURCE,
    }


def snapshot(market="US", ticker="TEST", reporting="USD", listing="USD", instrument="common"):
    return {
        "schema_version": 1,
        "security": {
            "market": market, "ticker": ticker, "company": "SYNTHETIC TEST ISSUER",
            "instrument_type": instrument,
            "reporting_currency": reporting, "listing_currency": listing,
        },
        "as_of": "2025-04-30",
        "retrieved_at": "2025-04-30T20:00:00+00:00",
        "fiscal_period_end": "2024-12-31",
        "metrics": {
            "revenue": metric(2000, reporting),
            "net_income": metric(200, reporting, "net_income"),
            "operating_cash_flow": metric(150, reporting, "operating_cash_flow"),
            "capex": metric(50, reporting, "capex"),
            "diluted_shares": metric(100, reporting, "diluted_shares"),
        },
        "quote": None,
        "conflicts": [],
    }


def assumptions(method="dcf", currency="USD"):
    return {
        "method": method,
        "share_count": {"value": 100, "basis": "ordinary", "as_of": "2025-04-30", "source_url": SOURCE},
        "net_cash": {"value": 20, "currency": currency, "as_of": "2025-04-30", "source_url": SOURCE},
        "scenarios": {
            "bear": {"growth_rate": 0, "discount_rate": 0.12, "terminal_growth": 0.01, "years": 5},
            "base": {"growth_rate": 0.05, "discount_rate": 0.10, "terminal_growth": 0.02, "years": 5},
            "bull": {"growth_rate": 0.1, "discount_rate": 0.09, "terminal_growth": 0.025, "years": 5},
        },
    }


class SecFactsTests(unittest.TestCase):
    def test_only_year_and_filings_known_by_cutoff(self):
        fake = {
            "cik": 1, "entityName": "SYNTHETIC TEST ISSUER",
            "facts": {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {"USD": [
                    {"start": "2024-01-01", "end": "2024-12-31", "val": 100, "filed": "2025-02-01", "form": "10-K", "accn": "0000000001-25-000001"},
                    {"start": "2024-01-01", "end": "2024-12-31", "val": 900, "filed": "2025-06-01", "form": "10-K/A", "accn": "0000000001-25-000002"},
                    {"start": "2025-01-01", "end": "2025-03-31", "val": 999, "filed": "2025-04-15", "form": "10-Q", "accn": "0000000001-25-000003"},
                ]}
            }}},
        }
        result = sec_facts.extract_snapshot(fake, "TEST", dt.date(2025, 4, 30))
        self.assertEqual(result["metrics"]["revenue"]["value"], 100)
        self.assertEqual(result["fiscal_period_end"], "2024-12-31")
        self.assertIn("operating_cash_flow", result["missing"])
        self.assertIsNone(result["quote"])

    def test_quarterly_extraction_ignores_ytd_cash_flow(self):
        fake = {
            "cik": 2, "entityName": "SYNTHETIC TEST ISSUER",
            "facts": {"us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                    {"start": "2025-01-01", "end": "2025-03-31", "val": 100, "filed": "2025-04-20", "form": "10-Q", "accn": "0000000002-25-000001"},
                    {"start": "2025-04-01", "end": "2025-06-30", "val": 120, "filed": "2025-08-01", "form": "10-Q", "accn": "0000000002-25-000002"},
                    {"start": "2025-01-01", "end": "2025-06-30", "val": 220, "filed": "2025-08-01", "form": "10-Q", "accn": "0000000002-25-000002"},
                ]}},
                "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
                    {"start": "2025-01-01", "end": "2025-06-30", "val": 50, "filed": "2025-08-01", "form": "10-Q", "accn": "0000000002-25-000002"},
                ]}},
            }},
        }
        result = sec_facts.extract_snapshot(fake, "TEST", dt.date(2025, 8, 10), "quarterly")
        self.assertEqual(result["metrics"]["revenue"]["value"], 120)
        self.assertEqual(result["fiscal_period_start"], "2025-04-01")
        self.assertIn("operating_cash_flow", result["missing"])


class NormalizationTests(unittest.TestCase):
    def test_hk_currency_period_and_free_cash_flow(self):
        item = snapshot("HK", "HK.00700", "CNY", "HKD")
        item["metrics"]["capex"]["value"] = -50
        result = normalize.normalize_snapshot(item)
        self.assertEqual(result["security"]["ticker"], "0700.HK")
        self.assertEqual(result["derived"]["free_cash_flow"]["value"], 100)
        self.assertAlmostEqual(result["derived"]["net_margin"]["value"], 0.1)
        self.assertFalse(result["quality"]["price_comparison_ok"])

    def test_future_filing_and_currency_mismatch_stop(self):
        item = snapshot()
        item["metrics"]["revenue"]["filed_at"] = "2025-05-01"
        with self.assertRaisesRegex(ValueError, "not filed"):
            normalize.normalize_snapshot(item)
        item["metrics"]["revenue"]["filed_at"] = "2025-03-20"
        item["metrics"]["revenue"]["currency"] = "HKD"
        with self.assertRaisesRegex(ValueError, "currency differs"):
            normalize.normalize_snapshot(item)

    def test_retrieval_cannot_precede_publication(self):
        item = snapshot()
        item["retrieved_at"] = "2025-03-01T10:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "published after"):
            normalize.normalize_snapshot(item)

    def test_stale_or_conflicting_price_pauses_comparison(self):
        item = snapshot()
        item["quote"] = {"price": 10, "currency": "USD", "observed_at": "2025-04-20T16:00:00-04:00", "source_url": SOURCE}
        result = normalize.normalize_snapshot(item)
        self.assertFalse(result["quality"]["price_comparison_ok"])
        item["quote"]["observed_at"] = "2025-04-30T16:00:00-04:00"
        item["conflicts"] = [{"field": "price", "description": "Two providers disagree"}]
        result = normalize.normalize_snapshot(item)
        self.assertFalse(result["quality"]["price_comparison_ok"])
        self.assertTrue(result["quality"]["valuation_inputs_ok"])

    def test_quarterly_snapshot_supports_review_but_blocks_annual_valuation(self):
        item = snapshot()
        item["as_of"] = "2025-08-10"
        item["retrieved_at"] = "2025-08-10T20:00:00+00:00"
        item["fiscal_period_type"] = "quarterly"
        item["fiscal_period_start"] = "2025-04-01"
        item["fiscal_period_end"] = "2025-06-30"
        for metric_item in item["metrics"].values():
            metric_item.update({"period_start": "2025-04-01", "period_end": "2025-06-30", "period_type": "quarterly", "filed_at": "2025-08-01"})
        result = normalize.normalize_snapshot(item)
        self.assertEqual(result["fiscal_period_type"], "quarterly")
        self.assertFalse(result["quality"]["valuation_inputs_ok"])
        with self.assertRaisesRegex(ValueError, "quality gate blocks valuation"):
            valuation.calculate(result, assumptions())


class ComparisonTests(unittest.TestCase):
    def test_yoy_compares_same_issuer_period_and_sources(self):
        prior = snapshot()
        prior["as_of"] = "2025-04-30"
        current = snapshot()
        current["as_of"] = "2026-04-30"
        current["retrieved_at"] = "2026-04-30T20:00:00+00:00"
        current["fiscal_period_end"] = "2025-12-31"
        for entry in current["metrics"].values():
            entry.update({"period_start": "2025-01-01", "period_end": "2025-12-31", "filed_at": "2026-03-20"})
        current["metrics"]["revenue"]["value"] = 2200
        output = compare_periods.compare(normalize.normalize_snapshot(prior), normalize.normalize_snapshot(current), "yoy")
        self.assertAlmostEqual(output["changes"]["revenue"]["change_pct"], 10)
        self.assertEqual(output["changes"]["revenue"]["current_source"], SOURCE)

    def test_refuses_cross_currency_and_non_adjacent_periods(self):
        prior = normalize.normalize_snapshot(snapshot())
        wrong = snapshot("HK", "0700.HK", "CNY", "HKD")
        with self.assertRaisesRegex(ValueError, "market"):
            compare_periods.compare(prior, normalize.normalize_snapshot(wrong), "yoy")
        with self.assertRaisesRegex(ValueError, "spacing"):
            compare_periods.compare(prior, normalize.normalize_snapshot(snapshot()), "yoy")

    def test_qoq_requires_true_single_quarters(self):
        prior = snapshot()
        current = snapshot()
        for item, start, end, filed, retrieved in (
            (prior, "2025-01-01", "2025-03-31", "2025-04-20", "2025-04-30T20:00:00+00:00"),
            (current, "2025-04-01", "2025-06-30", "2025-08-01", "2025-08-10T20:00:00+00:00"),
        ):
            item["as_of"] = retrieved[:10]
            item["retrieved_at"] = retrieved
            item["fiscal_period_type"] = "quarterly"
            item["fiscal_period_start"] = start
            item["fiscal_period_end"] = end
            for entry in item["metrics"].values():
                entry.update({"period_start": start, "period_end": end, "period_type": "quarterly", "filed_at": filed})
        current["metrics"]["revenue"]["value"] = 2100
        result = compare_periods.compare(normalize.normalize_snapshot(prior), normalize.normalize_snapshot(current), "qoq")
        self.assertAlmostEqual(result["changes"]["revenue"]["change_pct"], 5)
        self.assertEqual(result["fiscal_period_type"], "quarterly")


class ValuationTests(unittest.TestCase):
    def test_hk_dcf_no_quote_has_no_price_gap(self):
        item = normalize.normalize_snapshot(snapshot("HK", "0700.HK", "CNY", "HKD"))
        model = assumptions(currency="CNY")
        model["fx"] = {"listing_per_reporting": 1.08, "from_currency": "CNY", "to_currency": "HKD", "as_of": "2025-04-30", "source_url": SOURCE}
        result = valuation.calculate(item, model)
        self.assertLess(result["scenarios"]["bear"]["per_listed_security"], result["scenarios"]["base"]["per_listed_security"])
        self.assertIsNone(result["scenarios"]["base"]["price_gap_pct"])
        self.assertEqual(result["listing_currency"], "HKD")

    def test_adr_ratio_and_fx_change_per_security_value(self):
        item = normalize.normalize_snapshot(snapshot("US", "BABA", "CNY", "USD", "adr"))
        model = assumptions(currency="CNY")
        model["fx"] = {"listing_per_reporting": 0.14, "from_currency": "CNY", "to_currency": "USD", "as_of": "2025-04-30", "source_url": SOURCE}
        with self.assertRaisesRegex(ValueError, "adr_ratio"):
            valuation.calculate(item, model)
        model["adr_ratio"] = {"ordinary_per_adr": 8, "as_of": "2025-04-30", "source_url": SOURCE}
        result = valuation.calculate(item, model)
        base = result["scenarios"]["base"]
        expected = base["equity_value_reporting_currency"] / 100 * 8 * 0.14
        self.assertAlmostEqual(base["per_listed_security"], expected)

    def test_missing_fcf_or_net_cash_never_defaults_to_zero(self):
        item = normalize.normalize_snapshot(snapshot())
        model = assumptions()
        del model["net_cash"]
        with self.assertRaisesRegex(ValueError, "net_cash"):
            valuation.calculate(item, model)
        model = assumptions()
        del item["derived"]["free_cash_flow"]
        with self.assertRaisesRegex(ValueError, "free_cash_flow"):
            valuation.calculate(item, model)

    def test_pe_does_not_add_cash_and_price_gap_requires_quote(self):
        item = snapshot()
        item["quote"] = {"price": 10, "currency": "USD", "observed_at": "2025-04-30T16:00:00-04:00", "source_url": SOURCE}
        normalized = normalize.normalize_snapshot(item)
        model = assumptions("pe")
        model["earnings_attributable"] = {"value": 200, "currency": "USD", "period_end": "2024-12-31", "as_of": "2025-04-30", "source_url": SOURCE}
        model["scenarios"] = {"bear": {"multiple": 5}, "base": {"multiple": 10}, "bull": {"multiple": 15}}
        result = valuation.calculate(normalized, model)
        self.assertEqual(result["scenarios"]["base"]["equity_value_reporting_currency"], 2000)
        self.assertAlmostEqual(result["scenarios"]["base"]["price_gap_pct"], 100)

    def test_bank_book_value_and_reit_ffo_are_equity_multiples(self):
        item = normalize.normalize_snapshot(snapshot())
        for method, name, metric_value, expected_base in (
            ("pb", "book_value_attributable", 500, 5),
            ("p_ffo", "ffo_attributable", 80, 12),
        ):
            model = assumptions(method)
            del model["net_cash"]
            model[name] = {"value": metric_value, "currency": "USD", "period_end": "2024-12-31", "as_of": "2025-04-30", "source_url": SOURCE}
            multiples = (0.8, 1, 1.2) if method == "pb" else (10, 15, 20)
            model["scenarios"] = {case: {"multiple": multiple} for case, multiple in zip(("bear", "base", "bull"), multiples)}
            result = valuation.calculate(item, model)
            self.assertEqual(result["scenarios"]["base"]["per_listed_security"], expected_base)
            self.assertIsNone(result["input_provenance"]["net_cash"])

    def test_net_debt_cannot_make_shareholder_value_negative(self):
        model = assumptions()
        model["net_cash"]["value"] = -1000000
        result = valuation.calculate(normalize.normalize_snapshot(snapshot()), model)
        self.assertEqual(result["scenarios"]["bear"]["per_listed_security"], 0)
        self.assertTrue(result["scenarios"]["bear"]["equity_floor_applied"])

    def test_reverse_dcf_recovers_base_growth_when_quote_equals_base_value(self):
        initial = valuation.calculate(normalize.normalize_snapshot(snapshot()), assumptions())
        price = initial["scenarios"]["base"]["per_listed_security"]
        item = snapshot()
        item["quote"] = {"price": price, "currency": "USD", "observed_at": "2025-04-30T16:00:00-04:00", "source_url": SOURCE}
        result = valuation.calculate(normalize.normalize_snapshot(item), assumptions())
        self.assertAlmostEqual(result["reverse_dcf"]["implied_annual_fcf_growth_rate"], 0.05, places=8)

    def test_cli_end_to_end_reads_and_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            source = root / "snapshot.json"
            normalized = root / "normalized.json"
            assumptions_path = root / "assumptions.json"
            source.write_text(json.dumps(snapshot()), encoding="utf-8")
            assumptions_path.write_text(json.dumps(assumptions()), encoding="utf-8")
            run = subprocess.run([sys.executable, str(ROOT / "scripts/normalize.py"), str(source)], capture_output=True, text=True, check=True)
            normalized.write_text(run.stdout, encoding="utf-8")
            run = subprocess.run([sys.executable, str(ROOT / "scripts/valuation.py"), str(normalized), str(assumptions_path)], capture_output=True, text=True, check=True)
            self.assertIn("per_listed_security", json.loads(run.stdout)["scenarios"]["base"])
            next_snapshot = snapshot()
            next_snapshot["as_of"] = "2026-04-30"
            next_snapshot["retrieved_at"] = "2026-04-30T20:00:00+00:00"
            next_snapshot["fiscal_period_end"] = "2025-12-31"
            next_snapshot["metrics"]["revenue"]["value"] = 2200
            for entry in next_snapshot["metrics"].values():
                entry.update({"period_start": "2025-01-01", "period_end": "2025-12-31", "filed_at": "2026-03-20"})
            next_path = root / "next.json"
            next_path.write_text(json.dumps(next_snapshot), encoding="utf-8")
            run = subprocess.run([sys.executable, str(ROOT / "scripts/normalize.py"), str(next_path)], capture_output=True, text=True, check=True)
            next_normalized = root / "next-normalized.json"
            next_normalized.write_text(run.stdout, encoding="utf-8")
            run = subprocess.run([sys.executable, str(ROOT / "scripts/compare_periods.py"), str(normalized), str(next_normalized), "--basis", "yoy"], capture_output=True, text=True, check=True)
            self.assertAlmostEqual(json.loads(run.stdout)["changes"]["revenue"]["change_pct"], 10)


class QuoteIdentityTests(unittest.TestCase):
    def test_futu_codes_do_not_strip_hk_identity(self):
        self.assertEqual(futu_quote.futu_code("0700.HK")[0], "HK.00700")
        self.assertEqual(futu_quote.futu_code("BABA")[0], "US.BABA")

    def test_read_only_futu_snapshot_adapter_closes_connection(self):
        class RowFrame:
            def __len__(self):
                return 1

            @property
            def iloc(self):
                return [{"last_price": 300.0, "update_time": "2025-04-30 16:00:00"}]

        class Context:
            closed = False
            requested = None

            def __init__(self, host, port):
                pass

            def get_market_snapshot(self, codes):
                self.requested = codes
                return 0, RowFrame()

            def close(self):
                self.closed = True

        fake = types.ModuleType("futu")
        context = Context("127.0.0.1", 11111)
        fake.OpenQuoteContext = lambda host, port: context
        fake.RET_OK = 0
        with mock.patch.dict(sys.modules, {"futu": fake}):
            result = futu_quote.snapshot("HK.00700")
        self.assertEqual(context.requested, ["HK.00700"])
        self.assertTrue(context.closed)
        self.assertEqual(result["quote"]["currency"], "HKD")
        self.assertEqual(result["quote"]["delay_status"], "unknown")


if __name__ == "__main__":
    unittest.main()
