# 财报提炼与复用规则 V1

目标：把已核验的稳定历史数据转成可复用阅读层，避免每次全文重读；不把摘要当最终法律/会计原件。

## 读取顺序

1. 查看`research/filings/INDEX.md`和`data/coverage.json`，确定年份、类型与覆盖范围。
2. 阅读对应公司/报告的MD；跨年比较读`research/financial_comparison.md`。
3. 精确计算读取CSV，不从四舍五入后的MD抄数。
4. 仅在原文更正、新字段、口径冲突、重大附注或抽样核验时返回对应PDF页。

日常新闻更新不重复下载历史年报；新季报只更新新期数据及受影响的比较。历史年报数据不因新季报发布而过期，但不能代表最新经营状态。

## 本版范围

六份2023–2025年报：年度核心财务、季度轨迹、产品收入/成本/毛利、资源相关产销存、合并现金流关键项目。六份2026 Q1/H1/Q3：仅重用初始提交已经核验的核心累计、单季和期末余额。后者未在本轮重新审阅全部原文。

未完成全文转换，未提取完整资产负债表、净债务、受限现金、资产级权益/成本、所有减值和或有事项附注。未提取不等于未披露；PDF字节未归档，不生成伪造原件哈希。

## 字段与来源

- `annual_reported.csv`：元精度、PRC_GAAP_consolidated。核心指标/资产/权益/EPS/ROE对应`main_page`；购建支出、投资收益现金、税费对应`cashflow_page`；现金余额、筹资流量及少数股东分红对应`cash_tail_page`。投资净现金流跨页时查两页。所有页码为印刷页且本批等于PDF第几页（从1开始），截图pageno=页码-1。
- `annual_segments.csv`：管理层讨论中的分产品口径，不是权益利润。`cost_status=not_extracted`不得转零。天齐“其他”仅抽取收入，成本和毛利待提取。两公司产品划分不完全一致。
- `annual_volumes.csv`：天齐原“吨”保留为`tonne_as_reported`；赣锋基础化学材料原“吨LCE”为`tonne_LCE`。不是单矿权益产量，不自动换SC6/LCE。内耗、外购、抵销等未桥接，不强制以产销差还原库存。
- `annual_indicators.csv`：公式生成；不做无输入的估值。2023同比为空；利润跨零使用绝对差额。
- `quarterly.csv`等旧表：保持原有来源、年报回溯/累计差额和未恢复首次披露时点的标识。
- `filing_cache_manifest.json`：输入与生成文件SHA256用于缓存一致性，不是原PDF哈希，也不能替代原文核验。

每条原始行有`source_id`，解析到`data/sources.csv`的URL、报告期及发布日期；MD每节给出页码。来源日期只有日，最早披露时刻未核实，仍不得用于严格历史事件交易研究。

## 预处理公式

| 字段 | 公式 | 限制 |
|---|---|---|
| parent_margin_pct | 归母/营收×100 | 是描述比值，不是主营毛利或合并净利率 |
| parent_less_excl_cny | 归母－扣非 | 净额差，不替代逐项非经常损益分析 |
| ocf_minus_cash_capex_cny | 经营净现金流－购建长期资产现金 | 现金覆盖差额，不是FCFF/FCFE/归母可分配现金 |
| ocf_plus_investing_cf_cny | 经营净现金流＋投资净现金流 | 不含筹资、汇率和现金分配归属分析 |
| cash_capex_over_revenue_pct | 购建现金/营收×100 | 不区分维持与扩张支出 |
| revenue_yoy_pct | (本年/上年－1)×100 | 仅输入完整且口径一致时计算 |
| parent_change_cny / ocf_change_cny | 本年－上年 | 不把跨零增长率当改善强度 |

购建长期资产现金不包含全部并购/股权投资支出，也不等于会计固定资产新增。合并现金、母公司现金和股东可得现金不同；联营收益与到账分红不同。不能只看一个现金覆盖差额排序投资价值。

## 增量维护

先核对公司/报告期/会计准则/合并范围→原页视觉复核→新增或修订带来源数据→记录旧值和理由→重新生成MD→运行检查→提交并读回。原件重述时新建来源版本并保留旧版，不静默覆盖历史可用信息。

```bash
python scripts/build_filing_md.py
python scripts/build_filing_md.py --check
python scripts/validate.py
python scripts/validate_filings.py
python -m unittest discover -s tests -v
```

生成器只读取已审阅表，不联网、不OCR、不自行提炼未见过的PDF。`--check`失败时禁止使用过期MD。校验通过仅表示表间/缓存一致，不证明每一原文事实都正确，更不放开估值和回测门禁。

## 尚需定点提取

优先：两家公司完整债务与受限资金；应收/存货及减值；重大项目权益产量、单位成本、资本支出；天齐SQM收益/分红与Kwinana/ATO；赣锋资源爬坡与电池现金占用。后续仅补相关附注，不反复全文读取。
