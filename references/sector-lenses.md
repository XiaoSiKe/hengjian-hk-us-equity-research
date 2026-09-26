# 行业专用判断

先识别实际商业模式，再选指标与估值。混合集团分业务分析，不因股票代码或上市地直接归类。这里是**核查框架**；任何数值、同业和估值倍数仍需来自该发行人的同期披露。

| 企业类型 | 优先核查 | 合适的估值比较 | 避免的错误 |
| --- | --- | --- | --- |
| 一般盈利企业 | 收入驱动、毛利与利润率、ROIC、经营现金与资本开支、股本稀释、净债务 | 现金流情景、与业务相似同业的 EV/EBITDA 或 P/E | 只看低 P/E，不查衰退和资本再投入 |
| 银行 | 存款结构与资金成本、净息差、贷款质量／拨备、不良或分类贷款、CET1 与流动性 | 有据可查的可持续 ROE 对有形净资产／账面价值，结合资本要求；脚本可用 `pb` 比较 | 把存款当普通企业债务，机械套用 FCFF／EV/EBITDA；指标定义见 [FDIC](https://www.fdic.gov/quarterly-banking-profile/fdic-qbp-graph-book-536)、[美联储](https://www.federalreserve.gov/publications/2025-december-supervision-and-regulation-report-banking-system-conditions)与[香港金管局](https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/banking/capital-adequacy/) |
| 保险 | 业务类型、保费质量、赔付与费用、准备金发展、投资资产风险、法定偿付资本；财险可看综合成本率 | 经调整账面价值／可持续 ROE、分部价值及资本充足约束 | 将财险综合成本率套给寿险，忽视准备金与法定资本；定义见 [NAIC](https://content.naic.org/es/node/11821) 和[风险资本说明](https://content.naic.org/cipr_topics/topic_risk_based_capital.htm) |
| REIT | 物业类型、出租率、同店 NOI、租约到期、维护资本开支、债务期限与融资成本、分派覆盖 | 以公司披露口径核对 FFO／每股 FFO、NAV 和可比资产交易；脚本可用 `p_ffo` 比较 | 用普通企业净利润或未经核对的 AFFO 当唯一依据；[Nareit 的 FFO 定义](https://www.reit.com/glossary/funds-operation-ffo)为补充指标，不能替代 GAAP 报表 |
| 开发阶段生物科技 | 现金跑道、在研项目、试验设计与主要终点、临床阶段、监管状态、后续融资与稀释 | 对可核项目使用明确概率和现金流假设的情景；证据不足时只分析现金与里程碑。现有通用脚本不自动给买入结论 | 把早期试验当获批收入，虚构成功率或稳定终值；成熟、已商业化且现金流稳定的药企可按一般盈利企业另作判断。试验阶段见 [FDA](https://www.fda.gov/patients/drug-development-process/step-3-clinical-research) |
| 持续亏损的成长企业 | 收入质量、客户留存与单位经济、毛利、经营杠杆、现金消耗、SBC／股数稀释、融资跑道 | 叙事到数字的里程碑情景，收入倍数仅作为同质量同业的粗比较 | 假设当前负现金流突然变成稳定正现金流；故事与估值输入必须互相一致，见 [Damodaran](https://pages.stern.nyu.edu/adamodar/New_Home_Page/inv4E/inv4edquesanswrs.htm) |

若核心行业指标缺失，在[建议形成规则](recommendation-policy.md)的证据关停下：仍交付建议单，结论为「等待核实」，写明最能改变判断的那一个行业数据。行业工具的局限应体现在估值区间与把握程度中，不要把不可比公司凑成同业均值。

## 银行：利润首先取决于资产质量与资本

先识别零售、企业贷款、投行、财富管理等业务各占多少；再看净息差由贷款收益还是存款成本驱动。信用质量至少核不良或分类贷款、拨备覆盖、净核销及集中行业；资本至少核 CET1、杠杆率和主要监管要求。短期利润增长若来自少提拨备，不能直接外推为可持续 ROE。

用 P/B 或 P/TBV 时，要说明所用账面价值是否含商誉、资产减值是否充分、预期 ROE 与资本成本的关系。价格低于账面价值可能反映资产风险；不能自动称作安全边际。美国发行人的监管数据可与[FDIC](https://www.fdic.gov/quarterly-banking-profile/fdic-qbp-graph-book-536)口径对照，港股银行留意[香港金管局资本口径](https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/banking/capital-adequacy/)及发行人披露。

## 保险：先分清承保业务和投资资产

财险检查赔付率、费用率及综合成本率的趋势，还要看准备金是否持续向不利方向发展；寿险关注新业务利润／价值、退保、负债久期和保证收益。两类业务不可混用一套指标。再检查投资组合的信用、利率、久期与再投资风险，以及法定偿付资本；[NAIC 风险资本说明](https://content.naic.org/cipr_topics/topic_risk_based_capital.htm)提供美国口径背景。

估值使用归属股东的账面价值、可持续 ROE 与分部价值时，明确会计价值和法定资本并非同一概念。准备金释放造成的利润不能当作永久改善。

## REIT：现金分派能力不是净利润的同义词

按物业类型看出租率、租金修订、同店 NOI、主要租户、租约到期和维护／改造支出。再看债务到期结构、固定与浮动利率比例、再融资成本及分派覆盖。FFO 是 [Nareit 定义的补充指标](https://www.reit.com/glossary/funds-operation-ffo)；AFFO 的调整由公司定义，必须核对其中是否扣除了维持性资本开支。

P/FFO 与 NAV 只是不同的估值视角。比较同业时，物业质量、杠杆、地区和租约周期须相近；利率敏感性不能替代实际租金和现金流分析。

## 开发阶段生物科技：把里程碑与融资跑道放在同一页

逐个主要项目记录适应症、临床阶段、试验设计、主要终点、对照组、样本与监管里程碑。公开试验结果须区分统计结果、临床意义和批准状态；[FDA 临床研究说明](https://www.fda.gov/patients/drug-development-process/step-3-clinical-research)指出不同阶段回答的问题并不相同。

现金跑道与潜在增发同样重要。若无法有出处地估计试验成功率、上市时间和商业化利润，不给貌似精确的风险调整后目标价。已经商业化且现金流稳定的药企可按一般盈利企业研究，但须交代成熟业务与在研项目各贡献多少。

## 持续亏损成长企业：让叙事接受数字约束

追踪客户留存、单位经济、毛利、销售与研发投入效率，以及收入增长减速时费用能否调整。计算现金消耗时检查受限制现金、债务期限和股权激励；融资跑道应同时展示保守与当前消耗情景。

若用 EV/收入比较，必须解释同业的增长、毛利、留存和资本需求是否相近。估值叙事要能落到市场份额、利润率、再投资与现金流的同一条路径；这与 [Damodaran 的叙事—数字方法](https://pages.stern.nyu.edu/adamodar/New_Home_Page/numbers%26narrative.htm)一致。尚未证明盈利路径时，不把假定的终值称作已核实内在价值。

## 混合集团：先拆分，后合并

跨银行、保险、地产、平台或控股投资的公司，先分别建立业务指标和合理估值，再考虑净债务、总部成本、少数股东权益与交叉持股。合并财报数字不能在分部估值中重复计算。若重要分部披露不足，减少估值精度，并说明哪一块业务决定结论。
