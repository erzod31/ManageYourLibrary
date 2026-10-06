import unittest
from pathlib import Path

import library_core


class BestMetadataSelectionTests(unittest.TestCase):
    def setUp(self):
        self.book = Path("Gabriel Garcia Marquez - Cien anos de soledad.epub")
        self.base_data = {
            "titulo_local": "Cien anos de soledad",
            "titulo_nombre": "Cien anos de soledad",
            "autor_local": "Gabriel Garcia Marquez",
            "autor_nombre": "Gabriel Garcia Marquez",
            "anio_local": "1967",
            "isbns": ["9780307474728"],
        }

    def test_no_candidates_returns_conservative_result(self):
        result = library_core.elegir_mejor_metadato(Path("Entrada.epub"), {}, [])

        self.assertFalse(result["encontrado"])
        self.assertEqual(result["confianza"], 0)
        self.assertEqual(result["nombre_sugerido"], "Entrada.epub")
        self.assertEqual(result["motivo"], "Sin candidatos web")

    def test_incomplete_candidates_do_not_invent_data(self):
        result = library_core.elegir_mejor_metadato(
            Path("Entrada.epub"),
            {},
            [{"titulo": "", "autor": "", "fuente": "Open Library", "metodo": "Búsqueda"}],
        )

        self.assertFalse(result["encontrado"])
        self.assertEqual(result["titulo"], "")
        self.assertEqual(result["autor"], "")
        self.assertEqual(result["anio"], "")
        self.assertEqual(result["isbn"], "")

    def test_strong_isbn_candidate_wins(self):
        result = library_core.elegir_mejor_metadato(
            self.book,
            self.base_data,
            [
                {
                    "titulo": "Cien anos de soledad",
                    "autor": "Gabriel Garcia Marquez",
                    "anio": "1967",
                    "isbn": "9780307474728",
                    "fuente": "Open Library",
                    "metodo": "ISBN",
                }
            ],
        )

        self.assertTrue(result["encontrado"])
        self.assertGreaterEqual(result["confianza"], library_core.UMBRAL_RENOMBRAR)
        self.assertEqual(result["isbn"], "9780307474728")
        self.assertEqual(result["fuente"], "Open Library")

    def test_strong_title_and_author_candidate_is_accepted(self):
        datos = dict(self.base_data, isbns=[])
        result = library_core.elegir_mejor_metadato(
            self.book,
            datos,
            [
                {
                    "titulo": "Cien anos de soledad",
                    "autor": "Gabriel Garcia Marquez",
                    "anio": "1967",
                    "isbn": "",
                    "fuente": "Open Library",
                    "metodo": "Búsqueda",
                }
            ],
        )

        self.assertTrue(result["encontrado"])
        self.assertEqual(result["titulo"], "Cien anos de soledad")
        self.assertEqual(result["autor"], "Gabriel Garcia Marquez")

    def test_author_confirmed_by_local_evidence_is_kept(self):
        datos = dict(self.base_data, autor_local="Gabriel García Márquez", autor_nombre="Gabriel García Márquez")
        result = library_core.elegir_mejor_metadato(
            self.book,
            datos,
            [
                {
                    "titulo": "Cien anos de soledad",
                    "autor": "Gabriel Garcia Marquez",
                    "anio": "1967",
                    "isbn": "9780307474728",
                    "fuente": "Open Library",
                    "metodo": "ISBN",
                }
            ],
        )

        self.assertTrue(result["encontrado"])
        self.assertEqual(result["autor"], "Gabriel García Márquez")

    def test_ambiguous_year_from_search_is_not_kept_without_local_or_identifier_confirmation(self):
        datos = {
            "titulo_local": "Cien anos de soledad",
            "titulo_nombre": "Cien anos de soledad",
            "autor_local": "Gabriel Garcia Marquez",
            "autor_nombre": "Gabriel Garcia Marquez",
            "isbns": [],
        }
        result = library_core.elegir_mejor_metadato(
            self.book,
            datos,
            [
                {
                    "titulo": "Cien anos de soledad",
                    "autor": "Gabriel Garcia Marquez",
                    "anio": "1970",
                    "isbn": "",
                    "fuente": "Open Library",
                    "metodo": "Búsqueda",
                }
            ],
        )

        self.assertTrue(result["encontrado"])
        self.assertEqual(result["anio"], "")

    def test_low_confidence_candidate_stays_conservative(self):
        result = library_core.elegir_mejor_metadato(
            self.book,
            self.base_data,
            [
                {
                    "titulo": "Manual de jardineria avanzada",
                    "autor": "Otra Persona",
                    "anio": "2010",
                    "isbn": "",
                    "fuente": "Wikidata",
                    "metodo": "Búsqueda",
                }
            ],
        )

        self.assertFalse(result["encontrado"])
        self.assertLess(result["confianza"], library_core.UMBRAL_RENOMBRAR)

    def test_good_confidence_builds_valid_suggested_name(self):
        result = library_core.elegir_mejor_metadato(
            self.book,
            self.base_data,
            [
                {
                    "titulo": "Cien anos de soledad",
                    "autor": "Gabriel Garcia Marquez",
                    "anio": "1967",
                    "isbn": "9780307474728",
                    "fuente": "Open Library",
                    "metodo": "ISBN",
                }
            ],
        )

        self.assertTrue(result["encontrado"])
        self.assertTrue(result["nombre_sugerido"].endswith(".epub"))
        self.assertNotRegex(result["nombre_sugerido"], r'[<>:"/\\|?*]')

    def test_unicode_accent_enye_candidate_is_preserved_from_local_evidence(self):
        datos = {
            "titulo_local": "El niño ñandú",
            "titulo_nombre": "El nino nandu",
            "autor_local": "Álvaro Núñez",
            "autor_nombre": "Alvaro Nunez",
            "anio_local": "2020",
            "isbns": ["123456789X"],
        }
        result = library_core.elegir_mejor_metadato(
            Path("Alvaro Nunez - El nino nandu.epub"),
            datos,
            [
                {
                    "titulo": "El nino nandu",
                    "autor": "Alvaro Nunez",
                    "anio": "2020",
                    "isbn": "123456789X",
                    "fuente": "Open Library",
                    "metodo": "ISBN",
                }
            ],
        )

        self.assertTrue(result["encontrado"])
        self.assertEqual(result["titulo"], "El niño ñandú")
        self.assertEqual(result["autor"], "Álvaro Núñez")

    def test_incomplete_external_candidate_without_local_author_stays_conservative(self):
        datos = {"titulo_nombre": "Cien anos de soledad", "isbns": []}
        result = library_core.elegir_mejor_metadato(
            self.book,
            datos,
            [{"titulo": "Cien anos de soledad", "autor": "", "fuente": "Open Library", "metodo": "Búsqueda"}],
        )

        self.assertFalse(result["encontrado"])
        self.assertEqual(result["autor"], "")
        self.assertLess(result["confianza"], library_core.UMBRAL_RENOMBRAR)

    def test_local_web_title_conflict_with_isbn_uses_current_identifier_path(self):
        result = library_core.elegir_mejor_metadato(
            self.book,
            self.base_data,
            [
                {
                    "titulo": "One Hundred Years of Solitude",
                    "autor": "Gabriel Garcia Marquez",
                    "anio": "1967",
                    "isbn": "9780307474728",
                    "fuente": "Open Library",
                    "metodo": "ISBN",
                }
            ],
        )

        self.assertTrue(result["encontrado"])
        self.assertEqual(result["autor"], "Gabriel Garcia Marquez")
        self.assertEqual(result["isbn"], "9780307474728")
        self.assertTrue(result["titulo"])

    def test_no_sufficient_evidence_returns_conservative_result(self):
        result = library_core.elegir_mejor_metadato(
            Path("Entrada.epub"),
            {},
            [{"titulo": "Entrada", "autor": "", "fuente": "Internet Archive", "metodo": "Recuperación"}],
        )

        self.assertFalse(result["encontrado"])
        self.assertEqual(result["nombre_sugerido"], "Entrada.epub")


if __name__ == "__main__":
    unittest.main()
