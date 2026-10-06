import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import library_core


RAISE_OFFLINE = object()

PROVIDER_NAMES = [
    "openlibrary_isbn",
    "crossref_doi",
    "openalex_doi",
    "openlibrary_busqueda",
    "openlibrary_busqueda_autor",
    "loc_busqueda",
    "wikidata_busqueda",
    "crossref_busqueda",
    "openalex_busqueda",
]


class ConsultarWebGoldenTests(unittest.TestCase):
    def consult_with_mocks(
        self,
        libro,
        datos,
        provider_results=None,
        *,
        busqueda_amplia=True,
        incluir_identificadores=True,
        consultas_extra=None,
    ):
        provider_results = provider_results or {}
        calls = {}

        def make_provider(results):
            def _provider(*_args, **_kwargs):
                return [dict(item) for item in results]

            return _provider

        with ExitStack() as stack:
            for provider_name in PROVIDER_NAMES:
                configured = provider_results.get(provider_name, [])
                if configured is RAISE_OFFLINE:
                    mock = Mock(side_effect=TimeoutError("offline"))
                else:
                    mock = Mock(side_effect=make_provider(configured))
                calls[provider_name] = mock
                stack.enter_context(patch.object(library_core, provider_name, mock))

            returned_datos, candidatos = library_core.consultar_web(
                Path(libro),
                datos=datos,
                busqueda_amplia=busqueda_amplia,
                incluir_identificadores=incluir_identificadores,
                consultas_extra=consultas_extra,
            )

        final = library_core.elegir_mejor_metadato(Path(libro), returned_datos, candidatos)
        return returned_datos, candidatos, final, calls

    def assert_final(self, final, expected):
        for key, value in expected.items():
            self.assertEqual(final.get(key), value, key)
        self.assertNotIn("Google", final.get("fuente", ""))
        self.assertNotIn("Google", final.get("motivo", ""))

    def test_offline_all_providers_fail_returns_no_candidates(self):
        datos = {
            "titulo_nombre": "Cien anos de soledad",
            "autor_nombre": "Gabriel Garcia Marquez",
            "isbns": ["9780307474728"],
            "dois": ["10.1000/example"],
        }
        mapping = {provider_name: RAISE_OFFLINE for provider_name in PROVIDER_NAMES}

        returned, candidatos, final, _calls = self.consult_with_mocks(
            "Gabriel Garcia Marquez - Cien anos de soledad.epub",
            datos,
            mapping,
        )

        self.assertIs(returned, datos)
        self.assertEqual(candidatos, [])
        self.assert_final(
            final,
            {
                "encontrado": False,
                "confianza": 0,
                "titulo": "",
                "autor": "",
                "anio": "",
                "isbn": "",
                "nombre_sugerido": "Gabriel Garcia Marquez - Cien anos de soledad.epub",
            },
        )

    def test_empty_providers_return_conservative_result(self):
        returned, candidatos, final, calls = self.consult_with_mocks(
            "Libro.epub",
            {"titulo_nombre": "Libro", "autor_nombre": "Autor", "isbns": []},
        )

        self.assertIs(returned.get("_consultas_web_usadas"), returned["_consultas_web_usadas"])
        self.assertEqual(candidatos, [])
        self.assertGreater(calls["openlibrary_busqueda"].call_count, 0)
        self.assert_final(
            final,
            {
                "encontrado": False,
                "confianza": 0,
                "titulo": "",
                "autor": "",
                "anio": "",
                "isbn": "",
                "nombre_sugerido": "Libro.epub",
            },
        )

    def test_openlibrary_search_candidate_becomes_strong_result(self):
        datos = {
            "titulo_nombre": "Cien anos de soledad",
            "autor_nombre": "Gabriel Garcia Marquez",
            "anio_local": "1967",
            "isbns": [],
        }

        _returned, candidatos, final, calls = self.consult_with_mocks(
            "Gabriel Garcia Marquez - Cien anos de soledad.epub",
            datos,
            {
                "openlibrary_busqueda": [
                    {
                        "titulo": "Cien anos de soledad",
                        "autor": "Gabriel Garcia Marquez",
                        "anio": "1967",
                        "isbn": "",
                        "fuente": "Open Library",
                        "metodo": "Búsqueda",
                    }
                ]
            },
        )

        self.assertEqual(len(candidatos), 1)
        self.assertGreater(calls["openlibrary_busqueda"].call_count, 0)
        self.assert_final(
            final,
            {
                "encontrado": True,
                "confianza": 96,
                "titulo": "Cien anos de soledad",
                "autor": "Gabriel Garcia Marquez",
                "anio": "1967",
                "isbn": "",
                "nombre_sugerido": "Gabriel Garcia Marquez - Cien anos de soledad (1967).epub",
            },
        )

    def test_crossref_doi_candidate_becomes_strong_result(self):
        datos = {
            "titulo_nombre": "Interesting Paper",
            "autor_nombre": "Ada Lovelace",
            "dois": ["10.1000/example"],
            "isbns": [],
            "tipo_documento": "paper_academico",
        }

        _returned, candidatos, final, calls = self.consult_with_mocks(
            "Ada Lovelace - Interesting Paper.pdf",
            datos,
            {
                "crossref_doi": [
                    {
                        "titulo": "Interesting Paper",
                        "autor": "Ada Lovelace",
                        "anio": "1843",
                        "isbn": "",
                        "fuente": "Crossref",
                        "metodo": "DOI",
                        "identificador": "10.1000/example",
                    }
                ]
            },
        )

        self.assertEqual(len(candidatos), 1)
        self.assertEqual(calls["crossref_doi"].call_count, 1)
        self.assertEqual(calls["openlibrary_busqueda"].call_count, 0)
        self.assert_final(
            final,
            {
                "encontrado": True,
                "confianza": 96,
                "titulo": "Interesting Paper",
                "autor": "Ada Lovelace",
                "anio": "1843",
                "isbn": "",
                "nombre_sugerido": "Ada Lovelace - Interesting Paper (1843).pdf",
            },
        )

    def test_wikidata_incomplete_candidate_does_not_invent_fields(self):
        _returned, candidatos, final, calls = self.consult_with_mocks(
            "El proceso.epub",
            {"titulo_nombre": "El proceso", "isbns": []},
            {
                "openlibrary_busqueda": [],
                "loc_busqueda": [],
                "wikidata_busqueda": [
                    {
                        "titulo": "El proceso",
                        "autor": "",
                        "anio": "",
                        "isbn": "",
                        "fuente": "Wikidata",
                        "metodo": "Búsqueda",
                    }
                ],
            },
        )

        self.assertEqual(len(candidatos), 1)
        self.assertGreater(calls["wikidata_busqueda"].call_count, 0)
        self.assert_final(
            final,
            {
                "encontrado": False,
                "confianza": 81.0,
                "titulo": "El proceso",
                "autor": "",
                "anio": "",
                "isbn": "",
                "nombre_sugerido": "El proceso.epub",
            },
        )

    def test_similar_candidates_from_multiple_providers_reach_consensus(self):
        datos = {
            "titulo_nombre": "1984",
            "autor_nombre": "George Orwell",
            "anio_local": "1949",
            "isbns": [],
        }

        _returned, candidatos, final, _calls = self.consult_with_mocks(
            "George Orwell - 1984.epub",
            datos,
            {
                "openlibrary_busqueda": [
                    {
                        "titulo": "Nineteen Eighty-Four",
                        "autor": "George Orwell",
                        "anio": "1949",
                        "isbn": "",
                        "fuente": "Open Library",
                        "metodo": "Búsqueda",
                    }
                ],
                "loc_busqueda": [
                    {
                        "titulo": "1984",
                        "autor": "George Orwell",
                        "anio": "1949",
                        "isbn": "",
                        "fuente": "Library of Congress",
                        "metodo": "Búsqueda",
                    }
                ],
                "wikidata_busqueda": [
                    {
                        "titulo": "1984",
                        "autor": "George Orwell",
                        "anio": "1949",
                        "isbn": "",
                        "fuente": "Wikidata",
                        "metodo": "Búsqueda",
                    }
                ],
            },
        )

        self.assertEqual(len(candidatos), 3)
        self.assert_final(
            final,
            {
                "encontrado": True,
                "confianza": 96,
                "fuente": "Library of Congress",
                "titulo": "1984",
                "autor": "George Orwell",
                "anio": "1949",
                "isbn": "",
                "nombre_sugerido": "George Orwell - 1984 (1949).epub",
            },
        )

    def test_contradictory_candidates_stay_conservative_without_author_consensus(self):
        # Several sources agreeing on a title must not override contradictory authors.
        datos = {"titulo_nombre": "Rayuela", "autor_nombre": "Julio Cortazar", "isbns": []}

        _returned, candidatos, final, _calls = self.consult_with_mocks(
            "Rayuela.epub",
            datos,
            {
                "openlibrary_busqueda": [
                    {
                        "titulo": "Rayuela",
                        "autor": "Mario Vargas Llosa",
                        "anio": "1963",
                        "isbn": "",
                        "fuente": "Open Library",
                        "metodo": "Búsqueda",
                    }
                ],
                "loc_busqueda": [
                    {
                        "titulo": "La ciudad y los perros",
                        "autor": "Mario Vargas Llosa",
                        "anio": "1963",
                        "isbn": "",
                        "fuente": "Library of Congress",
                        "metodo": "Búsqueda",
                    }
                ],
                "wikidata_busqueda": [
                    {
                        "titulo": "Rayuela",
                        "autor": "Julio Cortazar",
                        "anio": "1963",
                        "isbn": "",
                        "fuente": "Wikidata",
                        "metodo": "Búsqueda",
                    }
                ],
            },
        )

        self.assertEqual(len(candidatos), 3)
        self.assertFalse(final["encontrado"])
        self.assertLess(final["confianza"], 90)
        self.assertIn("autores contradictorios", final["motivo"])
        self.assertEqual(final["nombre_sugerido"], "Rayuela.epub")

    def test_isbn_identifier_path_wins_and_stops_before_search(self):
        datos = {
            "titulo_nombre": "La casa de los espiritus",
            "autor_nombre": "Isabel Allende",
            "anio_local": "1982",
            "isbns": ["9788401352898"],
        }

        _returned, candidatos, final, calls = self.consult_with_mocks(
            "Isabel Allende - La casa de los espiritus.epub",
            datos,
            {
                "openlibrary_isbn": [
                    {
                        "titulo": "La casa de los espiritus",
                        "autor": "Isabel Allende",
                        "anio": "1982",
                        "isbn": "9788401352898",
                        "fuente": "Open Library",
                        "metodo": "ISBN",
                    }
                ],
                "openlibrary_busqueda": [
                    {
                        "titulo": "Wrong search result",
                        "autor": "Other",
                        "anio": "2020",
                        "isbn": "",
                        "fuente": "Open Library",
                        "metodo": "Búsqueda",
                    }
                ],
            },
        )

        self.assertEqual(len(candidatos), 1)
        self.assertEqual(calls["openlibrary_isbn"].call_count, 1)
        self.assertEqual(calls["openlibrary_busqueda"].call_count, 0)
        self.assert_final(
            final,
            {
                "encontrado": True,
                "confianza": 95,
                "titulo": "La casa de los espiritus",
                "autor": "Isabel Allende",
                "anio": "1982",
                "isbn": "9788401352898",
                "nombre_sugerido": "Isabel Allende - La casa de los espiritus (1982) [9788401352898].epub",
            },
        )

    def test_title_author_without_isbn_is_strong_when_local_year_exists(self):
        datos = {
            "titulo_nombre": "Rayuela",
            "autor_nombre": "Julio Cortazar",
            "anio_local": "1963",
            "isbns": [],
        }

        _returned, _candidatos, final, _calls = self.consult_with_mocks(
            "Julio Cortazar - Rayuela.epub",
            datos,
            {
                "openlibrary_busqueda": [
                    {
                        "titulo": "Rayuela",
                        "autor": "Julio Cortazar",
                        "anio": "1963",
                        "isbn": "",
                        "fuente": "Open Library",
                        "metodo": "Búsqueda",
                    }
                ]
            },
        )

        self.assert_final(
            final,
            {
                "encontrado": True,
                "confianza": 96,
                "titulo": "Rayuela",
                "autor": "Julio Cortazar",
                "anio": "1963",
                "isbn": "",
                "nombre_sugerido": "Julio Cortazar - Rayuela (1963).epub",
            },
        )

    def test_generic_title_with_weak_evidence_stays_for_review(self):
        _returned, _candidatos, final, _calls = self.consult_with_mocks(
            "La vida.epub",
            {"titulo_nombre": "La vida", "isbns": []},
            {
                "openlibrary_busqueda": [
                    {
                        "titulo": "La vida",
                        "autor": "",
                        "anio": "2011",
                        "isbn": "",
                        "fuente": "Open Library",
                        "metodo": "Búsqueda",
                    }
                ]
            },
        )

        self.assert_final(
            final,
            {
                "encontrado": False,
                "confianza": 86.0,
                "titulo": "La vida",
                "autor": "",
                "anio": "2011",
                "isbn": "",
                "nombre_sugerido": "La vida.epub",
            },
        )

    def test_local_strong_data_against_weak_web_remains_conservative(self):
        datos = {
            "titulo_local": "La casa de los espíritus",
            "titulo_nombre": "La casa de los espiritus",
            "autor_local": "Isabel Allende",
            "autor_nombre": "Isabel Allende",
            "anio_local": "1982",
            "isbns": [],
        }

        _returned, _candidatos, final, _calls = self.consult_with_mocks(
            "Isabel Allende - La casa de los espiritus.epub",
            datos,
            {
                "openlibrary_busqueda": [
                    {
                        "titulo": "La casa",
                        "autor": "Otro Autor",
                        "anio": "2001",
                        "isbn": "",
                        "fuente": "Open Library",
                        "metodo": "Búsqueda",
                    }
                ]
            },
        )

        self.assertFalse(final["encontrado"])
        self.assertLess(final["confianza"], library_core.UMBRAL_RENOMBRAR)
        self.assertEqual(final["titulo"], "La casa")
        self.assertEqual(final["autor"], "Otro Autor")
        self.assertEqual(final["nombre_sugerido"], "Isabel Allende - La casa de los espiritus.epub")

    def test_external_incomplete_candidate_does_not_invent_metadata(self):
        _returned, _candidatos, final, _calls = self.consult_with_mocks(
            "Manual desconocido.epub",
            {"titulo_nombre": "Manual desconocido", "isbns": []},
            {
                "openlibrary_busqueda": [],
                "loc_busqueda": [],
                "wikidata_busqueda": [
                    {
                        "titulo": "Manual desconocido",
                        "autor": "",
                        "anio": "",
                        "isbn": "",
                        "fuente": "Wikidata",
                        "metodo": "Búsqueda",
                    }
                ],
            },
        )

        self.assertFalse(final["encontrado"])
        self.assertEqual(final["autor"], "")
        self.assertEqual(final["anio"], "")
        self.assertEqual(final["isbn"], "")

    def test_unicode_accent_and_enye_flow_survives_search(self):
        datos = {
            "titulo_local": "El niño ñandú",
            "titulo_nombre": "El nino nandu",
            "autor_local": "Álvaro Núñez",
            "autor_nombre": "Alvaro Nunez",
            "anio_local": "2020",
            "isbns": [],
        }

        _returned, _candidatos, final, _calls = self.consult_with_mocks(
            "Alvaro Nunez - El nino nandu.epub",
            datos,
            {
                "openlibrary_busqueda": [
                    {
                        "titulo": "El nino nandu",
                        "autor": "Alvaro Nunez",
                        "anio": "2020",
                        "isbn": "",
                        "fuente": "Open Library",
                        "metodo": "Búsqueda",
                    }
                ]
            },
        )

        self.assert_final(
            final,
            {
                "encontrado": True,
                "confianza": 96,
                "titulo": "El niño ñandú",
                "autor": "Álvaro Núñez",
                "anio": "2020",
                "isbn": "",
                "nombre_sugerido": "Álvaro Núñez - El niño ñandú (2020).epub",
            },
        )

    def test_non_latin_identifier_flow_preserves_metadata(self):
        datos = {
            "titulo_local": "三体",
            "titulo_nombre": "三体",
            "autor_local": "刘慈欣",
            "autor_nombre": "刘慈欣",
            "anio_local": "2008",
            "isbns": ["9787229030933"],
        }

        _returned, _candidatos, final, _calls = self.consult_with_mocks(
            "刘慈欣 - 三体.epub",
            datos,
            {
                "openlibrary_isbn": [
                    {
                        "titulo": "三体",
                        "autor": "刘慈欣",
                        "anio": "2008",
                        "isbn": "9787229030933",
                        "fuente": "Open Library",
                        "metodo": "ISBN",
                    }
                ]
            },
        )

        self.assert_final(
            final,
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

    def test_repeat_query_uses_recorded_consultas_and_skips_search(self):
        datos = {
            "titulo_nombre": "Rayuela",
            "autor_nombre": "Julio Cortazar",
            "isbns": [],
            "_consultas_web_usadas": ["julio cortazar rayuela", "rayuela"],
        }

        _returned, candidatos, final, calls = self.consult_with_mocks(
            "Rayuela.epub",
            datos,
            {
                "openlibrary_busqueda": [
                    {
                        "titulo": "Rayuela",
                        "autor": "Julio Cortazar",
                        "anio": "1963",
                        "isbn": "",
                        "fuente": "Open Library",
                        "metodo": "Búsqueda",
                    }
                ]
            },
        )

        self.assertEqual(candidatos, [])
        self.assertEqual(calls["openlibrary_busqueda"].call_count, 0)
        self.assertFalse(final["encontrado"])
        self.assertEqual(final["nombre_sugerido"], "Rayuela.epub")


if __name__ == "__main__":
    unittest.main()
