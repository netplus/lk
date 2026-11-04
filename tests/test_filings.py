import csv
import tempfile
import unittest
from pathlib import Path
import shutil
from scripts.build_filing_md import ROOT, rows, build_outputs, compute_indicators, amount, ratio
from scripts.validate_filings import validate

class FilingCacheTests(unittest.TestCase):
    def test_integrity(self):
        self.assertEqual(validate()['integrity'],'PASS')
    def test_deterministic(self):
        self.assertEqual(build_outputs(),build_outputs())
    def test_twelve_report_caches(self):
        self.assertEqual(sum(p.startswith('research/filings/') and p!='research/filings/INDEX.md' for p in build_outputs()),12)
    def test_known_capex_gap(self):
        rs=compute_indicators(rows(ROOT,'data/financials/annual_reported.csv'))
        r=next(x for x in rs if x['symbol']=='002460.SZ' and x['period_end']=='2025-12-31')
        self.assertEqual(r['ocf_minus_cash_capex_cny'],'-4476894764.99')
    def test_first_yoy_missing(self):
        rs=compute_indicators(rows(ROOT,'data/financials/annual_reported.csv'))
        self.assertTrue(all(r['revenue_yoy_pct']=='' for r in rs if r['period_end'].startswith('2023')))
    def test_negative_profit_retained(self):
        rs=rows(ROOT,'data/financials/annual_reported.csv')
        self.assertTrue(next(r for r in rs if r['source_id']=='TQ2024')['net_income_parent_cny'].startswith('-'))
    def test_missing_is_not_zero(self):
        self.assertNotEqual(amount(''),'0.0000')
    def test_invalid_ratio(self):
        with self.assertRaises(ValueError):ratio('1','0')
    def test_stale_md_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst=Path(tmp)/'lk';shutil.copytree(ROOT,dst,ignore=shutil.ignore_patterns('.cache','__pycache__','.git'))
            f=dst/'research/filings/tianqi/2025_FY.md';f.write_text(f.read_text()+'\nwrong\n')
            with self.assertRaisesRegex(ValueError,'Stale'):validate(dst)
    def test_source_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst=Path(tmp)/'lk';shutil.copytree(ROOT,dst,ignore=shutil.ignore_patterns('.cache','__pycache__','.git'))
            p=dst/'data/financials/annual_reported.csv';rs=rows(dst,'data/financials/annual_reported.csv');rs[0]['symbol']='002466.SZ'
            with p.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
            with self.assertRaisesRegex(ValueError,'identity'):validate(dst)
    def test_no_fake_pdf_hash(self):
        import json
        m=json.loads((ROOT/'data/filing_cache_manifest.json').read_text())
        self.assertTrue(all(r['pdf_sha256'] is None for r in m['reports']))
    def test_point_in_time_warning(self):
        text=(ROOT/'research/filings/tianqi/2025_FY.md').read_text()
        self.assertIn('不能前置到原季度末',text)

if __name__=='__main__':unittest.main()
