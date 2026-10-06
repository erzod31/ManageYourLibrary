import unittest
from pathlib import Path

import library_core


class GoldenMetadataSelectionTests(unittest.TestCase):
    def assert_golden(self, result, expected):
        for key, value in expected.items():
            self.assertEqual(result.get(key), value, key)
        self.assertNotIn("Google", result.get("fuente", ""))
        self.assertNotIn("Google", result.get("motivo", ""))

    def test_book_with_clear_isbn_keeps_stable_identity(self):
        result = library_core.elegir_mejor_metadato(
            Path("Isabel Allende - La casa de los espiritus.epub"),
            {
                "titulo_local": "La casa de los espíritus",
                "titulo_nombre": "La casa de los espiritus",
                "autor_local": "Isabel Allende",
                "autor_nombre": "Isabel Allende",
                "anio_local": "1982",
                "isbns": ["9788401352898"],
            },
            [
                {
                    "titulo": "La casa de los espiritus",
                    "autor": "Isabel Allende",
                    "anio": "1982",
                    "isbn": "9788401352898",
                    "fuente": "Open Library",
                    "metodo": "ISBN",
                }
            ],
        )

        self.assert_golden(
            result,
            {
                "encontrado": True,
                "confianza": 95,
                "titulo": "La casa de los espíritus",
                "autor": "Isabel Allende",
                "anio": "1982",
                "isbn": "9788401352898",
                "nombre_sugerido": "Isabel Allende - La casa de los espíritus (1982) [9788401352898].epub",
            },
        )

    def test_book_without_isbn_but_strong_title_and_author_is_accepted(self):
        result = library_core.elegir_mejor_metadato(
            Path("Julio Cortazar - Rayuela.epub"),
            {
                "titulo_local": "Rayuela",
                "titulo_nombre": "Rayuela",
                "autor_local": "Julio Cortázar",
                "autor_nombre": "Julio Cortazar",
                "anio_local": "1963",
                "isbns": [],
            },
            [
                {
                    "titulo": "Rayuela",
                    "autor": "Julio Cortazar",
                    "anio": "1963",
                    "isbn": "",
                    "fuente": "Wikidata",
                    "metodo": "Búsqueda",
                }
            ],
        )

        self.assert_golden(
            result,
            {
                "encontrado": True,
                "confianza": 96,
                "titulo": "Rayuela",
                "autor": "Julio Cortázar",
                "anio": "1963",
                "isbn": "",
                "nombre_sugerido": "Julio Cortázar - Rayuela (1963).epub",
            },
        )

    def test_similar_title_with_different_web_author_keeps_local_author(self):
        result = library_core.elegir_mejor_metadato(
            Path("Julio Cortazar - Rayuela.epub"),
            {
                "titulo_local": "Rayuela",
                "titulo_nombre": "Rayuela",
                "autor_local": "Julio Cortázar",
                "autor_nombre": "Julio Cortazar",
                "anio_local": "1963",
                "isbns": [],
            },
            [
                {
                    "titulo": "Rayuela",
                    "autor": "Laura Garcia",
                    "anio": "2015",
                    "isbn": "",
                    "fuente": "Open Library",
                    "metodo": "Búsqueda",
                }
            ],
        )

        self.assert_golden(
            result,
            {
                "encontrado": True,
                "confianza": 91.0,
                "titulo": "Rayuela",
                "autor": "Julio Cortázar",
                "anio": "1963",
                "isbn": "",
                "nombre_sugerido": "Julio Cortázar - Rayuela (1963).epub",
            },
        )

    def test_ambiguous_anonymous_author_is_preserved_when_confirmed(self):
        result = library_core.elegir_mejor_metadato(
            Path("Anonimo - Lazarillo de Tormes.epub"),
            {
                "titulo_local": "Lazarillo de Tormes",
                "titulo_nombre": "Lazarillo de Tormes",
                "autor_local": "Anónimo",
                "autor_nombre": "Anonimo",
                "anio_local": "1554",
                "isbns": [],
            },
            [
                {
                    "titulo": "Lazarillo de Tormes",
                    "autor": "Anónimo",
                    "anio": "1554",
                    "isbn": "",
                    "fuente": "Wikidata",
                    "metodo": "Búsqueda",
                }
            ],
        )

        self.assert_golden(
            result,
            {
                "encontrado": True,
                "confianza": 96,
                "titulo": "Lazarillo de Tormes",
                "autor": "Anónimo",
                "anio": "1554",
                "isbn": "",
                "nombre_sugerido": "Anónimo - Lazarillo de Tormes (1554).epub",
            },
        )

    def test_local_year_wins_over_web_year_when_isbn_matches(self):
        result = library_core.elegir_mejor_metadato(
            Path("Mary Shelley - Frankenstein.epub"),
            {
                "titulo_local": "Frankenstein",
                "titulo_nombre": "Frankenstein",
                "autor_local": "Mary Shelley",
                "autor_nombre": "Mary Shelley",
                "anio_local": "1818",
                "isbns": ["9780141439471"],
            },
            [
                {
                    "titulo": "Frankenstein",
                    "autor": "Mary Shelley",
                    "anio": "1831",
                    "isbn": "9780141439471",
                    "fuente": "Open Library",
                    "metodo": "ISBN",
                }
            ],
        )

        self.assert_golden(
            result,
            {
                "encontrado": True,
                "confianza": 95,
                "titulo": "Frankenstein",
                "autor": "Mary Shelley",
                "anio": "1818",
                "isbn": "9780141439471",
                "nombre_sugerido": "Mary Shelley - Frankenstein (1818) [9780141439471].epub",
            },
        )

    def test_incomplete_external_data_goes_to_review_without_inventing_author(self):
        result = library_core.elegir_mejor_metadato(
            Path("Entrada.epub"),
            {"titulo_nombre": "Entrada", "isbns": []},
            [
                {
                    "titulo": "Entrada",
                    "autor": "",
                    "anio": "",
                    "isbn": "",
                    "fuente": "Internet Archive",
                    "metodo": "Recuperación",
                }
            ],
        )

        self.assert_golden(
            result,
            {
                "encontrado": False,
                "confianza": 77.0,
                "titulo": "Entrada",
                "autor": "",
                "anio": "",
                "isbn": "",
                "nombre_sugerido": "Entrada.epub",
            },
        )

    def test_multiple_candidates_prefers_clear_isbn_match(self):
        result = library_core.elegir_mejor_metadato(
            Path("George Orwell - 1984.epub"),
            {
                "titulo_local": "1984",
                "titulo_nombre": "1984",
                "autor_local": "George Orwell",
                "autor_nombre": "George Orwell",
                "anio_local": "1949",
                "isbns": ["9780451524935"],
            },
            [
                {
                    "titulo": "1984",
                    "autor": "Otro Autor",
                    "anio": "2001",
                    "isbn": "",
                    "fuente": "Wikidata",
                    "metodo": "Búsqueda",
                },
                {
                    "titulo": "1984",
                    "autor": "George Orwell",
                    "anio": "1949",
                    "isbn": "9780451524935",
                    "fuente": "Open Library",
                    "metodo": "ISBN",
                },
            ],
        )

        self.assert_golden(
            result,
            {
                "encontrado": True,
                "confianza": 95,
                "titulo": "1984",
                "autor": "George Orwell",
                "anio": "1949",
                "isbn": "9780451524935",
                "nombre_sugerido": "George Orwell - 1984 (1949) [9780451524935].epub",
            },
        )

    def test_multiple_similar_candidates_stay_below_threshold(self):
        result = library_core.elegir_mejor_metadato(
            Path("El Aleph.epub"),
            {"titulo_nombre": "El Aleph", "isbns": []},
            [
                {
                    "titulo": "Aleph",
                    "autor": "Autor Uno",
                    "anio": "2000",
                    "isbn": "",
                    "fuente": "Open Library",
                    "metodo": "Búsqueda",
                },
                {
                    "titulo": "El Aleph",
                    "autor": "Autor Dos",
                    "anio": "2010",
                    "isbn": "",
                    "fuente": "Wikidata",
                    "metodo": "Búsqueda",
                },
            ],
        )

        self.assert_golden(
            result,
            {
                "encontrado": False,
                "confianza": 81.0,
                "titulo": "El Aleph",
                "autor": "Autor Dos",
                "anio": "2010",
                "isbn": "",
                "nombre_sugerido": "El Aleph.epub",
            },
        )

    def test_spanish_accents_and_enye_are_preserved_from_local_evidence(self):
        result = library_core.elegir_mejor_metadato(
            Path("Alvaro Nunez - El nino nandu.epub"),
            {
                "titulo_local": "El niño ñandú",
                "titulo_nombre": "El nino nandu",
                "autor_local": "Álvaro Núñez",
                "autor_nombre": "Alvaro Nunez",
                "anio_local": "2020",
                "isbns": ["123456789X"],
            },
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

        self.assert_golden(
            result,
            {
                "encontrado": True,
                "confianza": 95,
                "titulo": "El niño ñandú",
                "autor": "Álvaro Núñez",
                "anio": "2020",
                "isbn": "123456789X",
                "nombre_sugerido": "Álvaro Núñez - El niño ñandú (2020) [123456789X].epub",
            },
        )

    def test_non_latin_title_and_author_are_not_normalized_away(self):
        result = library_core.elegir_mejor_metadato(
            Path("刘慈欣 - 三体.epub"),
            {
                "titulo_local": "三体",
                "titulo_nombre": "三体",
                "autor_local": "刘慈欣",
                "autor_nombre": "刘慈欣",
                "anio_local": "2008",
                "isbns": ["9787229030933"],
            },
            [
                {
                    "titulo": "三体",
                    "autor": "刘慈欣",
                    "anio": "2008",
                    "isbn": "9787229030933",
                    "fuente": "Open Library",
                    "metodo": "ISBN",
                }
            ],
        )

        self.assert_golden(
            result,
            {
                "encontrado": True,
                "confianza": 95,
                "titulo": "三体",
                "autor": "刘慈欣",
                "anio": "2008",
                "isbn": "9787229030933",
                "nombre_sugerido": "刘慈欣 - 三体 (2008) [9787229030933].epub",
            },
        )

    def test_generic_title_currently_accepts_single_external_author(self):
        # Current behavior: a generic title can be accepted when the external author gives enough score.
        # Candidate for future tightening, but this phase only captures the existing result.
        result = library_core.elegir_mejor_metadato(
            Path("La vida.epub"),
            {"titulo_nombre": "La vida", "isbns": []},
            [
                {
                    "titulo": "La vida",
                    "autor": "Autor Generico",
                    "anio": "2011",
                    "isbn": "",
                    "fuente": "Open Library",
                    "metodo": "Búsqueda",
                }
            ],
        )

        self.assert_golden(
            result,
            {
                "encontrado": True,
                "confianza": 91.0,
                "titulo": "La vida",
                "autor": "Autor Generico",
                "anio": "",
                "isbn": "",
                "nombre_sugerido": "Autor Generico - La vida.epub",
            },
        )

    def test_classic_with_multiple_editions_prefers_exact_local_title(self):
        result = library_core.elegir_mejor_metadato(
            Path("Miguel de Cervantes - Don Quijote de la Mancha.epub"),
            {
                "titulo_local": "Don Quijote de la Mancha",
                "titulo_nombre": "Don Quijote de la Mancha",
                "autor_local": "Miguel de Cervantes",
                "autor_nombre": "Miguel de Cervantes",
                "anio_local": "1605",
                "isbns": [],
            },
            [
                {
                    "titulo": "Don Quijote de la Mancha",
                    "autor": "Miguel de Cervantes",
                    "anio": "1605",
                    "isbn": "",
                    "fuente": "Wikidata",
                    "metodo": "Búsqueda",
                },
                {
                    "titulo": "Don Quixote",
                    "autor": "Miguel de Cervantes",
                    "anio": "2003",
                    "isbn": "",
                    "fuente": "Open Library",
                    "metodo": "Búsqueda",
                },
            ],
        )

        self.assert_golden(
            result,
            {
                "encontrado": True,
                "confianza": 96,
                "titulo": "Don Quijote de la Mancha",
                "autor": "Miguel de Cervantes",
                "anio": "1605",
                "isbn": "",
                "nombre_sugerido": "Miguel de Cervantes - Don Quijote de la Mancha (1605).epub",
            },
        )

    def test_local_web_conflict_stays_conservative(self):
        result = library_core.elegir_mejor_metadato(
            Path("Rayuela.epub"),
            {"titulo_nombre": "Rayuela", "autor_nombre": "Julio Cortazar", "isbns": []},
            [
                {
                    "titulo": "La ciudad y los perros",
                    "autor": "Mario Vargas Llosa",
                    "anio": "1963",
                    "isbn": "",
                    "fuente": "Open Library",
                    "metodo": "Búsqueda",
                }
            ],
        )

        self.assertFalse(result["encontrado"])
        self.assertEqual(result["nombre_sugerido"], "Rayuela.epub")
        self.assertLess(result["confianza"], library_core.UMBRAL_RENOMBRAR)

    def test_review_path_keeps_original_name_for_low_evidence(self):
        result = library_core.elegir_mejor_metadato(
            Path("Manual desconocido.epub"),
            {},
            [
                {
                    "titulo": "Manual desconocido",
                    "autor": "",
                    "anio": "",
                    "isbn": "",
                    "fuente": "Gutendex",
                    "metodo": "Búsqueda",
                }
            ],
        )

        self.assert_golden(
            result,
            {
                "encontrado": False,
                "confianza": 86.0,
                "titulo": "Manual desconocido",
                "autor": "",
                "anio": "",
                "isbn": "",
                "nombre_sugerido": "Manual desconocido.epub",
            },
        )


if __name__ == "__main__":
    unittest.main()
