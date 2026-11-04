import sys
import unittest
from decimal import Decimal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from validate import (validate, check_ohlc, quarter_difference, next_session,
                      available_asof, relative_volume, pe_or_none, number)

class TestResearchData(unittest.TestCase):
    def test_repository_integrity(self):
        r = validate()
        self.assertEqual(r['financial_rows'], 30)
        self.assertEqual(r['backtest_gate'], 'BLOCKED')
    def test_ohlc_good(self):
        check_ohlc(dict(open='10', high='12', low='9', close='11'))
    def test_ohlc_bad(self):
        with self.assertRaises(ValueError):
            check_ohlc(dict(open='40.64', high='38.79', low='37', close='38.11'))
    def test_negative_quarter_is_not_missing(self):
        self.assertEqual(quarter_difference('100.00','120.00'), Decimal('-20.00'))
    def test_decimal_precision(self):
        self.assertEqual(quarter_difference('0.30','0.20'), Decimal('0.10'))
    def test_annual_not_known_at_quarter_end(self):
        self.assertFalse(available_asof('2024-03-28','2023-09-30'))
    def test_same_day_not_assumed_preopen(self):
        self.assertFalse(available_asof('2026-10-26','2026-10-26'))
        self.assertTrue(available_asof('2026-10-26','2026-10-27'))
    def test_next_session_uses_given_calendar(self):
        self.assertEqual(next_session('2026-10-16',['2026-10-16','2026-10-19']), '2026-10-19')
    def test_incomplete_calendar_fails(self):
        with self.assertRaises(ValueError):
            next_session('2026-10-16',['2026-10-16'])
    def test_volume_excludes_today(self):
        self.assertEqual(relative_volume([100]*20,200),2)
    def test_insufficient_volume_fails(self):
        with self.assertRaises(ValueError):
            relative_volume([100],200)
    def test_negative_earnings_no_pe(self):
        self.assertIsNone(pe_or_none('100','-10'))
        self.assertIsNone(pe_or_none('100','0'))
    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            number('NaN')

if __name__ == '__main__':
    unittest.main()
