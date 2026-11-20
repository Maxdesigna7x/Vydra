import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vydra_core'))
from gui_worker import PhaseRate


class PhaseRateTests(unittest.TestCase):
    def test_resumed_units_are_not_counted_as_new_work(self):
        rate = PhaseRate()
        self.assertIsNone(rate.observe(800, 10))
        self.assertIsNone(rate.observe(800, 12))
        self.assertEqual(rate.observe(820, 15), 4)
        self.assertEqual(rate.observe(820, 16), 4)
        self.assertEqual(rate.observe(830, 20), 3)

    def test_counter_rollback_requires_a_new_measurement(self):
        rate = PhaseRate()
        self.assertIsNone(rate.observe(30, 10))
        self.assertEqual(rate.observe(50, 15), 4)
        self.assertIsNone(rate.observe(20, 16))
        self.assertEqual(rate.observe(30, 21), 2)


if __name__ == '__main__':
    unittest.main()
