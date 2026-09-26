"""Decision gates are tested against outcomes, not report wording."""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import recommendation_gate  # noqa: E402


def assessment(**overrides):
    item = {
        "ticker": "TEST",
        "as_of": "2025-04-30",
        "identity_verified": True,
        "critical_claims_verified": True,
        "critical_sources": ["https://example.org/filing"],
        "sector_method_suitable": True,
        "business_thesis": "intact",
        "fatal_risk": {"verified": False},
        "bear_case": {"manageable": True, "reason": "Source-backed balance sheet can absorb the modeled loss."},
    }
    item.update(overrides)
    return item


def valuation(price=100, bear=90, base=130, bull=160, observed="2025-04-30T16:00:00-04:00"):
    return {
        "ticker": "TEST", "as_of": "2025-04-30", "listing_currency": "USD", "method": "dcf",
        "quote": {"price": price, "currency": "USD", "observed_at": observed, "source_url": "https://example.org/quote"},
        "scenarios": {
            "bear": {"per_listed_security": bear},
            "base": {"per_listed_security": base},
            "bull": {"per_listed_security": bull},
        },
    }


class RecommendationGateTests(unittest.TestCase):
    def test_buy_requires_verified_thesis_and_favorable_asymmetry(self):
        result = recommendation_gate.decide(assessment(), valuation())
        self.assertEqual(result["recommendation"], "可考虑买入")
        self.assertEqual(result["computed"]["upside_to_downside"], 3)

    def test_negative_asymmetry_waits_even_below_base(self):
        result = recommendation_gate.decide(assessment(), valuation(bear=50, base=120))
        self.assertEqual(result["recommendation"], "等待")

    def test_verified_impairment_and_overpriced_bull_avoid(self):
        fatal = assessment(fatal_risk={"verified": True, "source_url": "https://example.org/filing", "reason": "Audited going-concern warning."})
        self.assertEqual(recommendation_gate.decide(fatal)["recommendation"], "回避")
        self.assertEqual(recommendation_gate.decide(assessment(), valuation(price=170))["recommendation"], "回避")
        self.assertEqual(recommendation_gate.decide(assessment(), valuation(bear=0, base=0, bull=0))["recommendation"], "回避")

    def test_missing_stale_or_wrong_security_data_never_becomes_buy(self):
        self.assertEqual(recommendation_gate.decide(assessment(), None)["recommendation"], "等待核实")
        self.assertEqual(recommendation_gate.decide(assessment(), valuation(observed="2025-04-20T16:00:00-04:00"))["recommendation"], "等待核实")
        wrong = valuation()
        wrong["ticker"] = "OTHER"
        self.assertEqual(recommendation_gate.decide(assessment(), wrong)["recommendation"], "等待核实")
        self.assertEqual(recommendation_gate.decide(assessment(sector_method_suitable=False), valuation())["recommendation"], "等待核实")

    def test_holding_does_not_auto_increase_without_portfolio_check(self):
        result = recommendation_gate.decide(assessment(holding=True), valuation())
        self.assertEqual(result["recommendation"], "可考虑买入")
        self.assertEqual(result["action"], "持有，新增仓位待组合核对")

    def test_sector_guard_rejects_generic_dcf_for_financials_and_reit(self):
        self.assertEqual(recommendation_gate.decide(assessment(sector="bank"), valuation())["recommendation"], "等待核实")
        bank_value = valuation()
        bank_value["method"] = "pb"
        self.assertEqual(recommendation_gate.decide(assessment(sector="bank"), bank_value)["recommendation"], "可考虑买入")
        self.assertEqual(recommendation_gate.decide(assessment(sector="reit"), bank_value)["recommendation"], "等待核实")
        reit_value = valuation()
        reit_value["method"] = "p_ffo"
        self.assertEqual(recommendation_gate.decide(assessment(sector="reit"), reit_value)["recommendation"], "可考虑买入")
        self.assertEqual(recommendation_gate.decide(assessment(sector="biotech"), valuation())["recommendation"], "等待核实")

    def test_cli_returns_same_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = pathlib.Path(temp)
            a = directory / "assessment.json"
            v = directory / "valuation.json"
            a.write_text(json.dumps(assessment()), encoding="utf-8")
            v.write_text(json.dumps(valuation()), encoding="utf-8")
            run = subprocess.run([sys.executable, str(ROOT / "scripts/recommendation_gate.py"), str(a), str(v)], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(run.stdout)["recommendation"], "可考虑买入")


if __name__ == "__main__":
    unittest.main()
