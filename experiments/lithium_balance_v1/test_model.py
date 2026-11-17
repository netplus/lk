"""Synthetic arithmetic/guardrail tests. Passing is NOT forecast validation."""
import unittest
from datetime import datetime, timezone
from model import (residual, transfer, warrant_change, contained_lce,
                   recoverable_lce, lagged_arrivals, Vintage,
                   latest_actual_asof, cash_available)


def stamp(day):
    return datetime(2026, 11, day, tzinfo=timezone.utc)


class ModelTests(unittest.TestCase):
    def test_closed_balance(self):
        self.assertEqual(residual(100, 110, 40, 30, 0, same_boundary=True), 0)

    def test_unexplained_residual(self):
        self.assertEqual(residual(100, 115, 40, 30, 0, same_boundary=True), 5)

    def test_missing_is_not_zero(self):
        self.assertIsNone(residual(100, 110, None, 30, 0, same_boundary=True))

    def test_unmeasured_adjustment_blocks(self):
        self.assertIsNone(residual(100, 110, 40, 30, None, same_boundary=True))

    def test_sample_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            residual(100, 110, 40, 30, 0, same_boundary=False)

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            residual(100, float('nan'), 40, 30, 0, same_boundary=True)

    def test_negative_stock_rejected(self):
        with self.assertRaises(ValueError):
            residual(-1, 110, 40, 30, 0, same_boundary=True)

    def test_internal_transfer_conserves(self):
        result = transfer((50, 30, 20), 0, 1, 12)
        self.assertEqual(result, (38, 42, 20))
        self.assertEqual(sum(result), 100)

    def test_overdraw_rejected(self):
        with self.assertRaises(ValueError):
            transfer((5, 2), 0, 1, 6)

    def test_expiry_without_consumption(self):
        # All 20 registered units become unregistered, staying in the same warehouse.
        self.assertEqual(transfer((20, 80), 0, 1, 20), (0, 100))
        self.assertEqual(warrant_change(0, 20, 0), -20)

    def test_reregistration_without_production(self):
        self.assertEqual(transfer((0, 100), 1, 0, 20), (20, 80))
        self.assertEqual(warrant_change(20, 0, 0), 20)

    def test_gross_flows_not_inferred(self):
        self.assertIsNone(warrant_change(None, 20, 0))

    def test_same_net_different_gross(self):
        self.assertEqual(warrant_change(5, 10, 0), warrant_change(95, 100, 0))

    def test_output_up_stock_down(self):
        # Production 40 versus prior 30, but boundary outflow is 45.
        self.assertEqual(residual(100, 95, 40, 45, 0, same_boundary=True), 0)

    def test_warrants_down_stock_up(self):
        self.assertEqual(residual(100, 110, 40, 30, 0, same_boundary=True), 0)
        self.assertEqual(warrant_change(5, 10, 0), -5)

    def test_lce_dry_grade(self):
        self.assertAlmostEqual(contained_lce(100, .10, .06), 13.3536144578)

    def test_unknown_recovery_preserved(self):
        self.assertIsNone(recoverable_lce(100, None))

    def test_percent_unit_error_rejected(self):
        with self.assertRaises(ValueError):
            contained_lce(100, 0, 6)

    def test_recovery_above_one_rejected(self):
        with self.assertRaises(ValueError):
            recoverable_lce(100, 1.1)

    def test_lag_mass_and_tail(self):
        result = lagged_arrivals([100, 0], [0, .25, .75])
        self.assertEqual(result, [0, 25, 75, 0])
        self.assertEqual(sum(result), 100)

    def test_lag_no_hidden_loss(self):
        with self.assertRaises(ValueError):
            lagged_arrivals([100], [.5, .25])

    def test_revision_not_available_in_past(self):
        rows = [Vintage(10, stamp(1), stamp(1), 'actual'),
                Vintage(20, stamp(3), stamp(3), 'actual')]
        self.assertEqual(latest_actual_asof(rows, stamp(2)), 10)

    def test_forecast_is_not_actual(self):
        self.assertIsNone(latest_actual_asof([Vintage(10, stamp(1), stamp(1), 'forecast')], stamp(2)))

    def test_late_observation_is_not_pit(self):
        self.assertIsNone(latest_actual_asof([Vintage(10, stamp(1), stamp(3), 'actual')], stamp(2)))

    def test_unknown_cash_not_zero(self):
        self.assertIsNone(cash_available(100, 10, None, 20, 5))

    def test_cash_bridge_does_not_imply_distribution(self):
        self.assertEqual(cash_available(100, 10, 30, 20, 5), 35)

    def test_funding_need_not_floored(self):
        self.assertEqual(cash_available(10, 10, 30, 20, 5), -55)


if __name__ == '__main__':
    unittest.main(verbosity=2)
