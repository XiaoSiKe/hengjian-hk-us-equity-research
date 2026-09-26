# 内部计算数据契约

本文件只供 Skill 在后台选择计算工具，**不是给用户的准备清单**。不得要求用户为获得建议单而安装软件、配置环境变量、登录券商或开通行情。工具不可用时，改从可直接访问的公司披露与公开资料取证，继续交付建议单。脚本使用 Python 3.9+，只读或计算，不下单。`recommendation_gate.py` 只复核分析者已经形成的、有来源的判断；它不会自行发现或验证事实。

## 1. SEC 全年与单季事实

```bash
python3 scripts/sec_facts.py --ticker AAPL --as-of 2025-11-15 > /tmp/aapl-facts.json
python3 scripts/sec_facts.py --ticker AAPL --as-of 2026-05-15 --period quarterly > /tmp/aapl-quarter.json
```

仅在脚本**已经可用**时运行；遇到调用条件缺失就跳过，不转成用户任务。也可用 `--cik 320193`。脚本从 SEC ticker 列表解析 CIK，读取 Company Facts；默认选研究截止日前已申报的 10-K／20-F 全年事实，`--period quarterly` 只选 10-Q 中约三个月的单季事实。输出最近符合条件的期间，包含每项指标的 XBRL 标签、期间、单位、申报日、accession 和归档链接。10-Q 经营现金流与资本开支常为年初至今累计值；找不到真正单季值时 `missing` 留空，不把累计值伪装成季度。第四季度、外国发行人 6-K 等不适合强行套用 10-Q 规则，应读公司披露。输出的 `instrument_type` 为 `unknown`，使用前必须按发行人原始材料核实是普通股还是 ADR。

`sec_facts.py` 不给当前价格、净现金或现时发行股数。`diluted_shares` 是报告期间加权平均稀释股数，**不能自动当成估值日已发行股数**。SEC XBRL 事实也不能代替阅读申报正文与附注。

## 2. 统一快照与规范化

```bash
python3 scripts/normalize.py /tmp/aapl-facts.json > /tmp/aapl-normalized.json
```

手工建立港股或用户授权数据快照时，也使用下述结构。所有数值采用**完整货币单位和完整股数**，例如 `1000000000` 表示十亿，不用“亿元”“百万股”混填。每个指标须携带来源、申报日 `filed_at` 或发布时间 `published_at`，以及完整会计期间。`capex` 是资本开支现金流出，正负输入均按流出绝对值处理。来源冲突可放到 `conflicts`，脚本会暂停受影响的估值或价格比较。

```json
{
  "schema_version": 1,
  "security": {
    "market": "HK", "ticker": "0700.HK", "company": "示例公司",
    "instrument_type": "common", "listing_currency": "HKD", "reporting_currency": "CNY"
  },
  "as_of": "2025-04-30",
  "retrieved_at": "2025-04-30T20:00:00+00:00",
  "fiscal_period_type": "annual",
  "fiscal_period_start": "2024-01-01",
  "fiscal_period_end": "2024-12-31",
  "metrics": {
    "revenue": {
      "value": 1000000000, "unit": "CNY", "currency": "CNY",
      "period_start": "2024-01-01", "period_end": "2024-12-31", "period_type": "annual",
      "filed_at": "2025-03-20", "source_url": "用户提供的有权使用的文件路径或公司IR链接"
    }
  },
  "quote": null,
  "conflicts": []
}
```

示例数字是格式占位，**不代表任何真实公司数据**。`retrieved_at` 记录本次取数时刻，可晚于历史研究截止日；历史报告仍只能使用截止日前已经发布的事实。其他常用 `metrics` 键为 `net_income`、`operating_cash_flow`、`capex`、`cash`、`diluted_shares`；股数字段的 `unit` 用 `shares` 且 `currency` 为 `null`。现金为 `period_type: point`、`period_start: null`。行情 `quote` 需要 `price`、`currency`、带时区的 `observed_at`、`source_url`，可加 `provider`、`delay_status` 和 `session`。研究日之前超过五个自然日的价格不可用于差距计算。未知／延迟行情不可写成实时价。

`normalize.py` 输出 `derived`（自由现金流、利润率、现金转换率）和 `quality`。任何财务计算都使用同一期间与报告币种；取数时间不能早于资料发布。旧版快照未写 `fiscal_period_type` 时仍按年度解释。季度快照可用于财报分析，估值脚本要求有来源的全年或 TTM 数据，因此季度快照会暂停估值。若 `quality.valuation_inputs_ok` 为假，估值脚本停止；若 `quality.price_comparison_ok` 为假，可估企业价值但不算现价差距。

## 3. 可比期间计算

```bash
python3 scripts/normalize.py prior.json > /tmp/prior-normalized.json
python3 scripts/normalize.py current.json > /tmp/current-normalized.json
python3 scripts/compare_periods.py /tmp/prior-normalized.json /tmp/current-normalized.json --basis yoy
```

同一发行人、相同财务期间类型和报告币种才能比较；`qoq` 只支持相邻两个单季快照，`yoy` 要求期间结束日约相隔一年。输出逐项保留两个来源与绝对变化；旧值为零时百分比为空。跨币种、期间错位或来源冲突会停止。同行公司横向比较须另核行业和会计口径，不能把这份同比脚本当同业排名器。

## 4. 估值假设

```bash
python3 scripts/valuation.py /tmp/aapl-normalized.json assumptions.json
```

`assumptions.json` 由分析者基于可引用材料和明确判断填写。三个情景必须都有 `bear`、`base`、`bull`。现金流稳定且自由现金流为正时可用 `dcf`；另外可选 `ev_revenue`、`ev_ebitda`、`pe`、`pb`、`p_ffo`。行业适用性见[行业判断](sector-lenses.md)。倍数法的 `metric_growth` 默认为 0，表示不外推；需要前瞻值时显式写入假设。不要把固定倍数当行业真理。

```json
{
  "method": "dcf",
  "share_count": {"value": 100000000, "basis": "ordinary", "as_of": "2025-04-30", "source_url": "发行人披露的股数来源"},
  "net_cash": {"value": 200000000, "currency": "CNY", "as_of": "2025-04-30", "source_url": "净现金计算与原始财报来源"},
  "fx": {"listing_per_reporting": 1.08, "from_currency": "CNY", "to_currency": "HKD", "as_of": "2025-04-30", "source_url": "有权使用的汇率来源"},
  "scenarios": {
    "bear": {"growth_rate": 0.00, "discount_rate": 0.12, "terminal_growth": 0.01, "years": 5},
    "base": {"growth_rate": 0.05, "discount_rate": 0.10, "terminal_growth": 0.02, "years": 5},
    "bull": {"growth_rate": 0.10, "discount_rate": 0.09, "terminal_growth": 0.025, "years": 5}
  }
}
```

这里的数字也只是**演示输入格式**。净现金以报告币种表示，负值代表净债务；不得默认为零。股数必须来自接近研究时点的来源，不直接拿全年加权平均稀释股数代替。若标的是 ADR 且股数口径为普通股，还须提供 `"adr_ratio": {"ordinary_per_adr": 8, "as_of": "...", "source_url": "..."}`；比例必须来自发行人或存托协议。FX 是“1 单位报告币 = 多少交易币”。

倍数法每个情景用 `{"multiple": 10, "metric_growth": 0}`。`ev_ebitda` 另需 `ebitda` 对象；`pe` 另需 `earnings_attributable`；`pb` 另需归属普通股股东的 `book_value_attributable`；`p_ffo` 另需归属普通股股东的 `ffo_attributable`。这些对象都含 `value`、`currency`、`period_end`、`as_of`、`source_url`。`pe`／`pb`／`p_ffo` 是股权倍数，脚本不会重复加净现金。DCF 在可核价格存在时附 `reverse_dcf`：固定基准情景的折现率、永续增长率与年数，反求价格隐含的恒定自由现金流增长率；超出可求范围时返回 `null`。这是一项敏感性检查，不是预测。所有方法的输出为情景估值，非交易建议。

若企业价值低于净债务，有限责任下的上市股权情景价值以零为下限，输出 `equity_floor_applied` 并提示；不得呈现负的每股股权价格。

## 5. 建议一致性复核

```bash
python3 scripts/recommendation_gate.py assessment.json /tmp/valuation.json
```

`assessment.json` 是内部工作材料，不向用户索取。最小字段包括 `ticker`、`as_of`、`identity_verified`、`critical_claims_verified`、`critical_sources`、`sector_method_suitable`、`business_thesis`（`intact`／`broken`／`uncertain`）、`fatal_risk`（`verified`、`reason`、`source_url`）和 `bear_case`（`manageable`、`reason`）；可加 `holding`、`portfolio_risk_checked`、`within_portfolio_limit`。输入必须来自实际核查，不得为了得到「买入」而把未知填成 `true`。若只有已证实重大风险，可省略估值文件；若价格或估值缺失，脚本应给「等待核实」。输出只是[建议形成规则](recommendation-policy.md)的候选结论，最终建议单仍需逐项引用证据。

## 6. 可选 Futu 行情

```bash
python3 scripts/futu_quote.py HK.00700
python3 scripts/futu_quote.py US.AAPL
```

只有当前环境已经具备只读行情时才使用该可选脚本；它只调 `OpenQuoteContext.get_market_snapshot`，不会调用交易 API。快照包含本地市场时区的更新时间，`delay_status` 保留 `unknown`。接口不可用时忽略此路径，从可直接访问的公开报价核价；仍无法核价时按证据边界完成建议单。
