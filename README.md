# lk — 锂资源产业研究

**最新公开研究：** [2026-11-11 日度增量｜LAR Cauchari项目Q3实绩与现金分配](reports/daily_2026-11-11.md)；[2026-11-10 日度增量](reports/daily_2026-11-10.md)；[2026-11-09 周度报告](reports/weekly_2026-11-09.md)。已新增LAR Q3项目100%口径生产/销量/成本及其分配信息，但赣锋上市公司最终可得现金桥仍未完成；三年全量行情、权益估值及回测门禁未通过。

天齐锂业（002466.SZ）、赣锋锂业（002460.SZ）。资源供需与成本→实际资产运营→权益利润/现金→估值及反证；不扩展成全新能源或自动交易。

## 当前交付（2026-11-04）

**历史底座＋财报阅读缓存，不是完整三年行情库。**

财报优先入口：[12份财报Markdown索引](research/filings/INDEX.md)｜[三年财务预整理](research/financial_comparison.md)｜[提炼与复用规则](docs/filing_cache.md)。先查MD和CSV，再按缺口回原文。

| 项目 | 已落地 | 限制 |
|---|---|---|
| 原始财报核验 | 12份，保留URL与印刷页 | PDF字节未归档 |
| 季度核心财务 | 每公司2023Q1–2026Q3共15季，合计30行/120项值 | 年报回溯版不是原季首次披露版 |
| 2026累计/余额 | 各6行 | 仅核心流量与总资产/归母权益，不是完整三表 |
| 财报阅读缓存 | 6份年报选择性提炼＋6份2026核心卡 | 非全文转换；完整附注与资产级模型待补 |
| 年报新增底表 | 6条年度主表、18条分产品、9条产销存、6条预计算 | 已核原页；吨/LCE、合并/母公司不可混用 |
| 年度加总 | 2023–2025两公司共6行 | 由分季值直接计算 |
| 行情样本 | 两公司各19天，共38行 | 网页量为舍入值、复权未知，仅staging |
| 三年全量日线 | **尚未取得** | 批量端点不可达，不以近月样本冒充 |
| 校验 | 50项离线测试通过（含25项周度回放合成测试）；年度/季度、产品收入、现金流及缓存检查通过 | 实盘取数/样本外回测未完成 |

目标行情窗口：2023-11-04至2026-11-03。早期2023财务用于TTM预热。三年是观察窗，不代表固定三年周期。数据不足时不发布周期胜率、精确目标价或买卖点。

## 入口

- [研究规则](AGENTS.md)
- [周期分析方法 V3](docs/methodology.md)
- [数据字典、规模与补齐清单](docs/data_and_backlog.md)
- [披露来源目录](data/sources.csv)
- [季度财务](data/financials/quarterly.csv)
- [行情样本（隔离）](data/market/staging_display.csv)
- [覆盖与门禁](data/coverage.json)
- [数据质量问题](data/quality/issues.csv)
- [本次实施记录](reports/bootstrap_2026-11-04.md)

```bash
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/build_filing_md.py --check
python scripts/validate_filings.py
```

本仓库公开：不保存个人账户、持仓成本、流水、密钥及付费数据库全文。来源使用和再分发权需分别核对；新下载数据默认只入本地.cache。没有GitHub Actions或收费运行环境，也没有自动交易。

后续先补齐原始日线与point-in-time财报，再做历史周期验证。每次任务先读本仓库已核验版本和缺口，不继承聊天旧数字为事实。

## 一年周度回放实验

[实验协议](experiments/weekly_replay_v1/PROTOCOL.md)｜[实际状态与缺口](reports/weekly_replay_v1_readiness_2026-11-04.md)｜[逐周计划](experiments/weekly_replay_v1/weekly_plan.csv)

固定窗口2023-11-06—2024-11-05。已准备242个交易日、53个周度检查点及成交计算原型；行情、当时可得证据和基准不足，**尚无收益成绩，不能声称跑赢或0%收益**。CLI目前只做就绪审计：`python scripts/weekly_replay.py --audit`，预期退出码2。
