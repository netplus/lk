"""Build compact, source-linked filing caches from reviewed tables; never fetch PDFs."""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-11-04'
BASE_COMMIT = '6694f12aea33c2257f1a017fa142d05830d3adc9'
CORE = ['revenue_cny', 'net_income_parent_cny', 'net_income_parent_excl_nonrec_cny', 'ocf_cny']
LABELS = ['营业收入', '归母净利润', '扣非归母净利润', '经营现金流净额']
INPUTS = ['data/sources.csv', 'data/financials/quarterly.csv',
          'data/financials/cumulative_2026.csv', 'data/financials/balance_2026.csv',
          'data/financials/annual_reported.csv', 'data/financials/annual_segments.csv',
          'data/operations/annual_volumes.csv', 'data/filing_notes.json']


def rows(root: Path, path: str) -> list[dict[str, str]]:
    with (root/path).open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def dec(value: str) -> Decimal:
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError('Non-finite number')
    return result


def amount(value: str) -> str:
    if value == '':
        return '未提取/原表空白'
    return format((dec(value)/Decimal('100000000')).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP), 'f')


def ratio(num: str, den: str) -> str:
    if dec(den) == 0:
        raise ValueError('Zero denominator')
    return format((dec(num)/dec(den)*100).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP), 'f')


def table(headers: list[str], body: list[list[str]]) -> str:
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                       '| ' + ' | '.join(['---']*len(headers)) + ' |'] +
                      ['| ' + ' | '.join(row) + ' |' for row in body])


def csv_text(data: list[dict[str, str]]) -> str:
    buf = io.StringIO(newline='')
    w = csv.DictWriter(buf, fieldnames=list(data[0]), lineterminator='\n')
    w.writeheader(); w.writerows(data)
    return buf.getvalue()


def company(symbol: str) -> tuple[str, str]:
    return ('天齐锂业', 'tianqi') if symbol == '002466.SZ' else ('赣锋锂业', 'ganfeng')


def compute_indicators(annual: list[dict[str, str]]) -> list[dict[str, str]]:
    lookup = {(r['symbol'], r['period_end']): r for r in annual}
    out = []
    for r in annual:
        prev = lookup.get((r['symbol'], str(int(r['period_end'][:4])-1)+'-12-31'))
        out.append(dict(symbol=r['symbol'], period_end=r['period_end'],
            parent_margin_pct=ratio(r['net_income_parent_cny'], r['revenue_cny']),
            parent_less_excl_cny=str(dec(r[CORE[1]])-dec(r[CORE[2]])),
            ocf_minus_cash_capex_cny=str(dec(r['ocf_cny'])-dec(r['cash_capex_cny'])),
            ocf_plus_investing_cf_cny=str(dec(r['ocf_cny'])+dec(r['investing_cf_cny'])),
            cash_capex_over_revenue_pct=ratio(r['cash_capex_cny'], r['revenue_cny']),
            revenue_yoy_pct=ratio(str(dec(r['revenue_cny'])-dec(prev['revenue_cny'])),prev['revenue_cny']) if prev else '',
            parent_change_cny=str(dec(r[CORE[1]])-dec(prev[CORE[1]])) if prev else '',
            ocf_change_cny=str(dec(r['ocf_cny'])-dec(prev['ocf_cny'])) if prev else '',
            source_ids=r['source_id'] + (' | '+prev['source_id'] if prev else ''),
            evidence_class='direct_calculation', formula_version='filing-cache-v1'))
    return out


def build_outputs(root: Path = ROOT) -> dict[str, str]:
    src = {r['source_id']: r for r in rows(root, INPUTS[0])}
    quarters = rows(root, INPUTS[1]); cumul = rows(root, INPUTS[2]); bal = rows(root, INPUTS[3])
    annual = rows(root, INPUTS[4]); seg = rows(root, INPUTS[5]); vol = rows(root, INPUTS[6])
    notes = json.loads((root/INPUTS[7]).read_text(encoding='utf-8'))
    derived = compute_indicators(annual)
    dmap = {(r['symbol'],r['period_end']):r for r in derived}
    out = {'data/financials/annual_indicators.csv': csv_text(derived)}
    index_rows, manifest_reports = [], []
    for a in annual:
        sid=a['source_id']; s=src[sid]; title,slug=company(a['symbol']); year=a['period_end'][:4]
        path=f'research/filings/{slug}/{year}_FY.md'; d=dmap[(a['symbol'],a['period_end'])]
        q=[r for r in quarters if r['symbol']==a['symbol'] and r['period_end'].startswith(year)]
        ss=[r for r in seg if r['source_id']==sid]; vv=[r for r in vol if r['source_id']==sid]
        core = [[lab,amount(a[key])] for lab,key in zip(LABELS,CORE)]
        core += [['期末总资产',amount(a['total_assets_cny'])],['期末归母权益',amount(a['equity_parent_cny'])],
                 ['基本每股收益（元/股）',a['eps_basic_cny']],['加权ROE（%）',a['roe_weighted_pct']]]
        cash_fields = [('购建长期资产现金支出','cash_capex_cny'),('取得投资收益收到的现金','investment_income_cash_cny'),
            ('投资活动净现金流','investing_cf_cny'),('筹资活动净现金流','financing_cf_cny'),
            ('期末现金及现金等价物','cash_equivalents_end_cny'),('支付各项税费','tax_cash_paid_cny'),
            ('向少数股东支付股利/利润','minority_dividends_cash_cny')]
        text=f'''# {title}｜{year}年报研究摘要

> 选择性提炼版，不是财报全文；仅代表本报告期间，不作为当前经营结论。金额默认亿元，底表保留元精度。

来源ID：`{sid}`；证券：`{a['symbol']}`；报告期：{a['period_end']}；来源发布日期：{s['source_published_date']}（日期级，最早披露时刻未验证）。  
本次复核：{DATE}；会计口径：中国准则、合并报表；全文{notes[sid]['pages']}页；原PDF字节/哈希未归档。  
[原始年报]({s['url']})｜[字段定义](../../../docs/filing_cache.md)｜[跨年比较](../../financial_comparison.md)

## 1. 年度核心事实

{table(['指标','披露值'],core)}

来源：原文p.{a['main_page']}。四项核心流量已与原有四季加总核对；这不是对全部附注的审阅。

## 2. 季度轨迹（年报回溯版本）

{table(['期间','营收','归母','扣非','经营现金流'],[[r['period_end']]+[amount(r[k]) for k in CORE] for r in q])}

来源：原文p.{s['printed_pages']}；复用已核验`quarterly.csv`。这是年报披露时的版本，不能前置到原季度末做回测。

## 3. 分产品与实物经营

{table(['产品','收入','成本','毛利率%'],[[r['product_name'],amount(r['revenue_cny']),amount(r['cost_cny']),r['gross_margin_reported_pct'] or '未提取'] for r in ss])}

来源：原文p.{ss[0]['printed_pages']}；毛利不是归母利润，天齐与赣锋产品分类不完全同义。

{table(['原披露分类','原单位','产量','销量','期末库存'],[[r['product_name'],r['unit'],r['production'],r['sales'],r['inventory_end']] for r in vv])}

来源：原文p.{vv[0]['printed_pages']}。`tonne_as_reported`为报告原“吨”；`tonne_LCE`为原“吨LCE”。未做权益、SC6或LCE转换；不得相加两公司产量，也不强制用产销差解释库存。

## 4. 现金与投入

{table(['合并现金流字段','披露值'],[[lab,amount(a[k])] for lab,k in cash_fields])}

来源：原文p.{a['cashflow_page']}、p.{a['cash_tail_page']}。原表空白不填零；现金等价物不等于全部货币资金。取得投资收益现金不等于当期权益法收益。

## 5. 预处理结果（直接计算）

{table(['指标','结果'],[['归母－扣非（亿元）',amount(d['parent_less_excl_cny'])],['经营现金流－购建支出（亿元）',amount(d['ocf_minus_cash_capex_cny'])],['经营＋投资净现金流（亿元）',amount(d['ocf_plus_investing_cf_cny'])],['购建支出/营收（%）',d['cash_capex_over_revenue_pct']]])}

公式及全部输入见`annual_indicators.csv`。经营现金流减购建支出只是现金覆盖差额，不是FCFF/FCFE，也不是上市公司股东可分配现金；未扣并购/股权投资，不区分维持/扩张资本开支。

## 6. 阅读提示与边界

'''
        text+='\n\n'.join(notes[sid]['notes'])+'\n\n'
        if notes[sid].get('note_pages'):
            text+='补充说明来源：原文p.'+notes[sid]['note_pages']+'。\n\n'
        text+='待专项补齐：'+'；'.join(notes[sid]['review_targets'])+'。本摘要未逐项提取这些附注，不代表不存在相关风险。\n\n'
        text+='优先复用本摘要和底表。仅在新更正、字段缺失、口径冲突、重大附注或样本抽查时回原文对应页；新增数值须先入带来源的底表，再重新生成MD。\n'
        out[path]=text
        index_rows.append([title,year+' FY',s['source_published_date'],f'[{sid}]({slug}/{year}_FY.md)','年度核心＋分产品＋产销＋现金'])
        manifest_reports.append(dict(source_id=sid,path=path,status='selective_annual_tables_checked',pdf_sha256=None))
    # Interim caches reuse previously verified repository tables without claiming a new full review.
    for c in cumul:
        sid=c['source_ids']; s=src[sid]; title,slug=company(c['symbol']); suffix={'03-31':'Q1','06-30':'H1','09-30':'Q3'}[c['period_end'][5:]]
        path=f'research/filings/{slug}/2026_{suffix}.md'
        b=next(r for r in bal if r['symbol']==c['symbol'] and r['period_end']==c['period_end'])
        q=next(r for r in quarters if r['symbol']==c['symbol'] and r['period_end']==c['period_end'])
        text=f'''# {title}｜2026 {suffix}核心数据卡

> 复用既有核验底表的阅读缓存，不是本轮重新审阅全部季报/半年报。未经审计；不是全年数字。

来源ID：`{sid}`；报告期：{c['period_end']}；来源发布日期：{s['source_published_date']}（日期级、最早时刻未验证）。  
继承底表提交：`{BASE_COMMIT}`；整理日期：{DATE}。  
[原始报告]({s['url']})｜[使用边界](../../../docs/filing_cache.md)

## 累计财务（亿元）

{table(['指标','年初至期末'],[[lab,amount(c[k])] for lab,k in zip(LABELS,CORE)])}

## 期末余额（亿元）

{table(['指标','期末值'],[['总资产',amount(b['total_assets_cny'])],['归母权益',amount(b['equity_parent_cny'])]])}

来源：原文p.{s['printed_pages']}；累计流量和时点余额分开。

## 对应单季度（亿元）

{table(['指标','单季度'],[[lab,amount(q[k])] for lab,k in zip(LABELS,CORE)])}

性质：{'Q1直接披露' if suffix=='Q1' else '同口径累计差额，直接计算'}；公式：`{q['formula']}`；输入：`{q['source_ids']}`。来源可用日取最新输入日，不冒充最早公告时间。

## 未覆盖与复核入口

未提取本期分产品毛利、资本开支、净债务、资产项目运营和重大附注。不能用全年旧值冒充本期；需要这些字段时回原报告定点补录，而不是默认没有变化。

来源备注：{s['note']}。

基于这张卡只能做累计/单季核心数据比较，不能据此生成完整盈利预测、自由现金流或交易结论。更正与重述应保留旧版本。
'''
        out[path]=text
        index_rows.append([title,'2026 '+suffix,s['source_published_date'],f'[{sid}]({slug}/2026_{suffix}.md)','核心累计＋单季＋期末余额；继承核验'])
        manifest_reports.append(dict(source_id=sid,path=path,status='inherited_verified_core_tables_only',pdf_sha256=None))
    out['research/filings/INDEX.md']='''# 财报阅读缓存入口

先读索引→所需报告MD→同名结构化底表；原PDF是最终证据，不是每次研究的默认输入。

本次覆盖：六份2023–2025年报的选择性提炼，另将六份2026 Q1/H1/Q3既有核心数据整理为阅读卡。MD不是全文转换，不宣称全部附注已读。

'''+table(['公司','报告','来源发布日期','阅读入口','已覆盖'],index_rows)+'''

## 结构化数据

- `data/financials/annual_reported.csv`：年度直接披露值及主表/现金流页码。
- `data/financials/annual_segments.csv`：18条分产品收入/成本/毛利记录。
- `data/operations/annual_volumes.csv`：9条原口径产销存记录。
- `data/financials/annual_indicators.csv`：6条公式预计算记录。
- `data/financials/quarterly.csv`：30条季度核心记录，保留年报回溯版本标识。
- [三年比较](../financial_comparison.md)：复盘入口，不是投资排名。
- [字段、方法与增量规则](../../docs/filing_cache.md)。

## 缓存失效条件

原文更正/重述、新一期报告、输入表哈希变化、指标口径冲突或缺少关键附注。运行`python scripts/build_filing_md.py --check`检查MD与输入是否一致；失败时先修复，不继续引用过期缓存。

原件未在仓库归档，PDF哈希为空。报告发布日期来自来源目录，不能据此宣称已经恢复完整point-in-time数据。没有改变回测和估值门禁。
'''
    comp=[]
    for r in annual:
        d=dmap[(r['symbol'],r['period_end'])]
        comp.append([company(r['symbol'])[0],r['period_end'][:4],amount(r['revenue_cny']),amount(r[CORE[1]]),amount(r[CORE[2]]),amount(r['ocf_cny']),amount(r['cash_capex_cny']),amount(d['ocf_minus_cash_capex_cny'])])
    out['research/financial_comparison.md']='''# 天齐与赣锋｜三年财报预整理

数据期2023–2025；整理日2026-11-04。仅为事后财报比较，不是当前行业判断、估值排名或历史可交易信号。所有金额亿元。

'''+table(['公司','年度','营收','归母','扣非','经营现金流','购建支出','现金覆盖差额'],comp)+'''

现金覆盖差额=经营现金流－购建固定资产/无形资产/其他长期资产支付现金。它未计全部投资、融资和股东分配，也未区分少数股东权益，不能命名为FCFF/FCFE或可分红现金。

## 分产品毛利率（%）

'''+table(['公司','年度','原产品类别','披露毛利率'],[[company(r['symbol'])[0],r['period_end'][:4],r['product_name'],r['gross_margin_reported_pct'] or '未提取'] for r in seg if r['product_code']!='other'])+'''

两家公司分类、产品组合和权益结构不同，不直接以毛利率排公司价值。现有数据能够显示经营差异，但不能识别股价周期、证明价格领先期或预测回报。

## 已预处理与尚不能计算

已算：四季/全年勾稽、收入同比（2024/2025）、归母利润绝对变化、归母－扣非差额、购建投入强度、现金覆盖差额、经营与投资净现金流合计。

不算：缺债务和受限现金的净债务/EV；缺统一投入资本的ROIC；缺维护/扩张及权益桥的股东自由现金流；缺日线和首次披露版本的事件收益、胜率、目标价。

2023同比未填，不以未提取的2022全年数据补齐。跨零利润不输出夸张的增长率，采用绝对差额和盈亏状态。分产品成本空白不当零。原单位“吨”未自动改成LCE或SC6，产销差不自动解释为库存变化。

来源与逐报告入口：[财报索引](filings/INDEX.md)。完整元精度及计算输入在`annual_reported.csv`、`annual_segments.csv`、`annual_indicators.csv`；原始链接在`data/sources.csv`。最新2026数据见索引内各期卡，不与全年值混为同比。
'''
    manifest = dict(version='filing-cache-v1',generated_on=DATE,base_commit_for_inherited_core=BASE_COMMIT,
        input_sha256={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in INPUTS},reports=manifest_reports,
        output_sha256={p:hashlib.sha256(t.encode()).hexdigest() for p,t in out.items()},
        full_reports_converted=False,raw_pdf_files_archived=0)
    out['data/filing_cache_manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
    return out


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');args=p.parse_args()
    outputs=build_outputs();different=[]
    for name,text in outputs.items():
        path=ROOT/name
        if args.check:
            if not path.exists() or path.read_bytes()!=text.encode():different.append(name)
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
    if different:
        raise SystemExit('STALE CACHE: '+', '.join(different))
    print(('CHECK PASS: ' if args.check else 'BUILT: ')+str(len(outputs))+' generated files')

if __name__=='__main__':main()
