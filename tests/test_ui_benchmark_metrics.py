"""Do not hide a slow fifth UI interaction by rounding the percentile down."""
import unittest

from tools.benchmark_ui import percentile95


class UiBenchmarkMetricsTests(unittest.TestCase):
    def test_small_batch_includes_its_slow_tail(self):
        measurements = [1, 2, 3, 4, 140]
        self.assertEqual(percentile95(measurements), 140)
        self.assertEqual(measurements, [1, 2, 3, 4, 140])

    def test_twenty_samples_select_the_nineteenth(self):
        self.assertEqual(percentile95(list(range(20, 0, -1))), 19)

    def test_empty_batch_is_not_reported_as_zero_latency(self):
        with self.assertRaises(ValueError):
            percentile95([])
