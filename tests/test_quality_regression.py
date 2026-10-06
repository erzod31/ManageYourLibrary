import unittest

from tools import compare_quality_regression as quality


def snapshot(records, duplicates=None):
    return {
        "records": records,
        "duplicates": {"exact_duplicate_groups": duplicates or []},
    }


def record(path="book.epub", **overrides):
    item = {
        "relative_path": path,
        "format": ".epub",
        "title": "Título",
        "author": "Autor Ñ",
        "year": "2026",
        "isbn": "9780306406157",
        "confidence": 96,
        "status": "ACCEPTED",
        "found": True,
        "sent_to_review": False,
        "action": "renombrar",
        "error": "",
        "ocr_used": False,
    }
    item.update(overrides)
    return item


class QualityRegressionTests(unittest.TestCase):
    def test_detects_accepted_low_confidence(self):
        baseline = snapshot([record()])
        candidate = snapshot([record(status="FAST_OK", confidence=70)])

        differences = quality.compare_quality(baseline, candidate)

        self.assertTrue(any(item.severity == "RISK" and "low confidence" in item.detail for item in differences))

    def test_detects_lost_metadata(self):
        baseline = snapshot([record()])
        candidate = snapshot([record(status="FAST_OK", isbn="")])

        differences = quality.compare_quality(baseline, candidate)

        self.assertTrue(any(item.severity == "RISK" and "lost baseline isbn" in item.detail for item in differences))

    def test_allows_complete_high_confidence_fast_result(self):
        baseline = snapshot([record(status="NEEDS_REVIEW", found=False, sent_to_review=True, action="", confidence=30)])
        candidate = snapshot([record(status="FAST_OK", confidence=96)])

        differences = quality.compare_quality(baseline, candidate)

        self.assertFalse(any(item.severity == "RISK" for item in differences))
        self.assertTrue(any(item.severity == "IMPROVEMENT" for item in differences))

    def test_review_only_analysis_action_is_not_accepted(self):
        baseline = snapshot([record(status="NEEDS_REVIEW", found=False, sent_to_review=True, action="solo_analizar", confidence=0)])
        candidate = snapshot([record(status="NEEDS_REVIEW", found=False, sent_to_review=True, action="solo_analizar", confidence=0)])

        differences = quality.compare_quality(baseline, candidate)

        self.assertFalse(any(item.severity == "RISK" for item in differences))

    def test_detects_duplicate_group_regression(self):
        baseline = snapshot([record()], duplicates=[["a.epub", "b.epub"]])
        candidate = snapshot([record()], duplicates=[])

        differences = quality.compare_quality(baseline, candidate)

        self.assertTrue(any(item.severity == "RISK" and item.path == "*duplicates*" for item in differences))

    def test_parallel_equivalence_detects_mixed_metadata(self):
        sequential = snapshot([record(path="a.epub", title="A"), record(path="b.epub", title="B")])
        parallel = snapshot([record(path="a.epub", title="B"), record(path="b.epub", title="A")])

        differences = quality.compare_equivalence(sequential, parallel)

        self.assertEqual(len([item for item in differences if item.severity == "RISK"]), 2)

    def test_parallel_equivalence_accepts_identical_results(self):
        sequential = snapshot([record(path="a.epub"), record(path="b.epub")], duplicates=[["a.epub", "b.epub"]])
        parallel = snapshot([record(path="a.epub"), record(path="b.epub")], duplicates=[["a.epub", "b.epub"]])

        self.assertEqual(quality.compare_equivalence(sequential, parallel), [])


if __name__ == "__main__":
    unittest.main()
