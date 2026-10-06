import unittest

from core.library_view_model import LibraryViewIndex, cover_grid_positions
from tools.benchmark_catalog import benchmark_size, synthetic_catalog


class CatalogViewPerformanceTests(unittest.TestCase):
    def test_prepared_index_matches_expected_search_and_filter(self):
        view = LibraryViewIndex(synthetic_catalog(100))

        self.assertEqual(len(view.filter()), 100)
        self.assertEqual(len(view.filter(extension="pdf")), 25)
        self.assertEqual([item["titulo"] for item in view.filter("Title 42")], ["Title 42"])
        self.assertEqual(view.stats["books"], 100)
        self.assertEqual(view.formats, ("CBZ", "EPUB", "MOBI", "PDF"))

    def test_benchmark_report_has_stable_schema(self):
        result = benchmark_size(100, repetitions=1)

        self.assertEqual(result["size"], 100)
        self.assertIn("prepare_ms", result)
        self.assertIn("search_p50_ms", result)
        self.assertIn("search_p95_ms", result)
        self.assertIn("format_filter_p95_ms", result)
        self.assertIn("all_items_p95_ms", result)
        self.assertIsInstance(result["within_budget"], bool)

    def test_cover_layout_is_bounded_and_stable(self):
        self.assertEqual(
            cover_grid_positions(7, 3),
            [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0)],
        )


if __name__ == "__main__":
    unittest.main()
