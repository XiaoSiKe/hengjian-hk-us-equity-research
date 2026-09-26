#!/usr/bin/env python3
"""Apply the Hengjian decision gates to sourced analyst judgments and valuation output."""

import argparse
import datetime as dt
import json
import math
import sys


SECTOR_METHODS = {
    "general": {"dcf", "ev_revenue", "ev_ebitda", "pe", "pb"},
    "bank": {"pb", "pe"},
    "insurer": {"pb", "pe"},
    "reit": {"p_ffo"},
    "biotech": set(),
    "loss_making_growth": {"ev_revenue"},
}


def finite_positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def finite_nonnegative(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def usable_quote(valuation):
    quote = valuation.get("quote")
    if not isinstance(quote, dict) or quote.get("currency") != valuation.get("listing_currency"):
        return False
    try:
        cutoff = dt.date.fromisoformat(valuation["as_of"])
        observed = dt.datetime.fromisoformat(quote["observed_at"])
    except (KeyError, TypeError, ValueError):
        return False
    return observed.tzinfo is not None and 0 <= (cutoff - observed.date()).days <= 5


def finish(label, reason, assessment, valuation=None, metrics=None):
    holding = assessment.get("holding") is True
    thesis = assessment.get("business_thesis")
    if not holding:
        action = label
    elif label == "回避":
        action = "考虑减持／退出，并核对执行条件"
    elif label == "等待核实":
        action = "暂停加仓，优先核实关键事实"
    elif label == "等待":
        action = "持有并观察" if thesis == "intact" else "暂停加仓，复核持有论点"
    elif assessment.get("portfolio_risk_checked") is True and assessment.get("within_portfolio_limit") is True:
        action = "可考虑增持"
    else:
        action = "持有，新增仓位待组合核对"
    return {
        "recommendation": label,
        "action": action,
        "reason": reason,
        "ticker": valuation.get("ticker") if isinstance(valuation, dict) else assessment.get("ticker"),
        "as_of": valuation.get("as_of") if isinstance(valuation, dict) else assessment.get("as_of"),
        "computed": metrics or {},
        "note": "Internal decision consistency check; the report must cite the evidence behind each judgment.",
    }


def decide(assessment, valuation=None):
    if not isinstance(assessment, dict):
        raise ValueError("assessment must be a JSON object")
    if assessment.get("identity_verified") is not True:
        return finish("等待核实", "发行人、股类或上市证券身份尚未核实。", assessment, valuation)

    fatal = assessment.get("fatal_risk") or {}
    if not isinstance(fatal, dict):
        raise ValueError("fatal_risk must be an object")
    if fatal.get("verified") is True:
        if fatal.get("source_url") and fatal.get("reason"):
            return finish("回避", "有来源支持的重大永久性损失风险：{}".format(fatal["reason"]), assessment, valuation)
        return finish("等待核实", "重大风险尚缺可核实出处。", assessment, valuation)

    thesis = assessment.get("business_thesis")
    if thesis == "broken" and assessment.get("critical_claims_verified") is True and assessment.get("critical_sources"):
        return finish("回避", "有可靠事实表明核心经营论点已经失效。", assessment, valuation)
    if thesis not in {"intact", "broken", "uncertain"}:
        return finish("等待核实", "核心经营论点尚未形成可检验状态。", assessment, valuation)
    if thesis != "intact":
        return finish("等待核实", "经营论点尚未得到足够证据支持。", assessment, valuation)
    if assessment.get("critical_claims_verified") is not True or not assessment.get("critical_sources"):
        return finish("等待核实", "决定结论的事实或原始来源尚未核实。", assessment, valuation)
    if assessment.get("sector_method_suitable") is not True:
        return finish("等待核实", "行业指标或估值方法尚未匹配企业类型。", assessment, valuation)
    sector = assessment.get("sector", "general")
    if sector not in SECTOR_METHODS:
        return finish("等待核实", "企业类型尚未匹配行业专用判断。", assessment, valuation)
    if isinstance(valuation, dict) and valuation.get("method") not in SECTOR_METHODS[sector]:
        return finish("等待核实", "所用估值方法不适合当前企业类型。", assessment, valuation)
    if not isinstance(valuation, dict) or not usable_quote(valuation):
        return finish("等待核实", "缺少可核实的同期价格或估值情景。", assessment, valuation)
    if assessment.get("ticker") and assessment["ticker"] != valuation.get("ticker"):
        return finish("等待核实", "论点与估值引用了不同证券。", assessment, valuation)
    if assessment.get("as_of") and assessment["as_of"] != valuation.get("as_of"):
        return finish("等待核实", "论点与估值的研究截止日不一致。", assessment, valuation)
    quote = valuation["quote"]
    price = quote.get("price")
    cases = valuation.get("scenarios") or {}
    values = [cases.get(name, {}).get("per_listed_security") for name in ("bear", "base", "bull")]
    if not finite_positive(price) or not all(finite_nonnegative(value) for value in values):
        return finish("等待核实", "价格或情景值无效，无法判断风险收益。", assessment, valuation)
    bear, base, bull = values
    if not bear <= base <= bull:
        return finish("等待核实", "悲观、基准、乐观情景顺序不一致。", assessment, valuation)
    if price >= bull:
        return finish("回避", "当前价格不低于可信乐观情景价值。", assessment, valuation, {"price": price, "bear": bear, "base": base, "bull": bull})
    if price >= base:
        return finish("等待", "当前价格已达到或超过基准情景价值。", assessment, valuation, {"price": price, "bear": bear, "base": base, "bull": bull})

    bear_case = assessment.get("bear_case") or {}
    if not isinstance(bear_case, dict) or bear_case.get("manageable") is not True or not bear_case.get("reason"):
        return finish("等待", "悲观情景的损失承受依据不足。", assessment, valuation, {"price": price, "bear": bear, "base": base, "bull": bull})
    upside = base - price
    downside = max(price - bear, 0)
    asymmetry = None if downside == 0 else upside / downside
    metrics = {"price": price, "bear": bear, "base": base, "bull": bull, "base_upside": upside, "bear_downside": downside, "upside_to_downside": asymmetry}
    if downside > upside:
        return finish("等待", "基准上行空间不足以覆盖悲观下行空间。", assessment, valuation, metrics)
    return finish("可考虑买入", "经营论点仍成立，价格低于基准情景，且已解释的悲观下行不大于基准上行。", assessment, valuation, metrics)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assessment", help="Sourced analyst assessment JSON")
    parser.add_argument("valuation", nargs="?", help="Optional output from valuation.py")
    args = parser.parse_args(argv)
    try:
        with open(args.assessment, "r", encoding="utf-8") as handle:
            assessment = json.load(handle)
        valuation = None
        if args.valuation:
            with open(args.valuation, "r", encoding="utf-8") as handle:
                valuation = json.load(handle)
        print(json.dumps(decide(assessment, valuation), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("recommendation_gate: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
