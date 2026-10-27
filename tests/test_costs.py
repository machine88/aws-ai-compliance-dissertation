"""Check financial arithmetic and prevent silent omissions in planning examples."""
import unittest
from research.costs import estimate_cost


class CostTests(unittest.TestCase):
    """Exercise exact arithmetic and invalid-input handling without billing APIs."""

    def test_decimal_arithmetic(self):
        """Preserve exact unit arithmetic rather than binary floating-point totals."""
        result = estimate_cost({"items": 100, "checks": 200}, {"items": {"usd_per_unit": "0.003"}, "checks": {"usd_per_unit": "0.001"}})
        self.assertEqual(result["total_usd"], "0.500")

    def test_missing_usage_is_not_silently_ignored(self):
        """Require an explicit usage quantity for every modeled cost category."""
        with self.assertRaises(ValueError):
            estimate_cost({}, {"items": {"usd_per_unit": "0.003"}})

    def test_reject_negative_or_nonfinite_usage(self):
        """Reject quantities that could hide charges or invalidate an estimate."""
        for quantity in [-1, "NaN", "Infinity"]:
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                estimate_cost({"items": quantity}, {"items": {"usd_per_unit": "0.003"}})
