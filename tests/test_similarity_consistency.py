import unittest
from difflib import SequenceMatcher

import library_core
from core import duplicate_engine, normalizer
from metadata import scoring


class SimilarityConsistencyTests(unittest.TestCase):
    def test_similarity_metric_is_stable_across_modules_and_environments(self):
        left = "El mar de la vida"
        right = "La vida en el mar"
        expected = SequenceMatcher(
            None,
            normalizer.normalizar_texto(left),
            normalizer.normalizar_texto(right),
        ).ratio()

        self.assertEqual(library_core.similitud(left, right), expected)
        self.assertEqual(scoring.default_similitud(left, right), expected)
        self.assertEqual(duplicate_engine.default_similitud(left, right), expected)


if __name__ == "__main__":
    unittest.main()
