import unittest

import library_core
from core import naming


class NamingTests(unittest.TestCase):
    def test_filename_cleanup_removes_windows_forbidden_characters(self):
        cleaned = naming.sanitize_filename('  A<book>: "title" / part?  ')
        self.assertEqual(cleaned, "A book title part")
        self.assertNotRegex(cleaned, r'[<>:"/\\|?*]')

    def test_mojibake_is_repaired_without_losing_unicode(self):
        self.assertEqual(naming.repair_mojibake("GarcÃ­a Márquez"), "García Márquez")
        self.assertEqual(naming.repair_mojibake("百年孤独"), "百年孤独")

    def test_attached_author_is_removed_only_from_a_substantial_title(self):
        self.assertEqual(
            naming.remove_attached_author("El jardín invisible Clara Montes", "Clara Montes"),
            "El jardín invisible",
        )
        self.assertEqual(naming.remove_attached_author("Clara Montes", "Clara Montes"), "Clara Montes")

    def test_readable_title_collapses_repetition_and_ocr_noise(self):
        self.assertEqual(
            library_core.limpiar_titulo_legible("Fortunata y Jacinta - Fortunata y Jacinta"),
            "Fortunata y Jacinta",
        )
        self.assertEqual(
            library_core.limpiar_titulo_legible("Tarzán Y y los hombres ERA hormiga ER"),
            "Tarzán y los hombres hormiga",
        )

    def test_non_latin_author_prefers_explicit_latin_alias(self):
        self.assertEqual(naming.prefer_latin_author_alias("鳥山 明 [Akira Toriyama]"), "Akira Toriyama")

    def test_suggested_filename_preserves_public_compatibility(self):
        result = library_core.crear_nombre_sugerido(
            "鳥山 明 [Akira Toriyama]",
            "Sand Land",
            "2003",
            "9781234567890",
            ".CBZ",
        )
        self.assertEqual(result, "Akira Toriyama - Sand Land (2003) [9781234567890].cbz")


if __name__ == "__main__":
    unittest.main()
