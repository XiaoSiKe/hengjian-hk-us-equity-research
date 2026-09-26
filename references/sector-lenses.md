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
