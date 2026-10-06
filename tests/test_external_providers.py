import inspect
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import library_core
from metadata import external_providers


class FakeResponse:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class ExternalProvidersTests(unittest.TestCase):
    def setUp(self):
        external_providers.WEB_CACHE.clear()

    def test_openlibrary_search_normalizes_expected_response(self):
        response = {
            "docs": [
                {
                    "title": "Cien anos de soledad",
                    "author_name": ["Gabriel Garcia Marquez"],
                    "first_publish_year": 1967,
                    "isbn": ["978-0-307-47472-8"],
                    "key": "/works/OL123W",
                }
            ]
        }

        result = external_providers.openlibrary_busqueda("cien anos", http_get_func=lambda _url: response)

        self.assertEqual(result[0]["fuente"], "Open Library")
        self.assertEqual(result[0]["titulo"], "Cien anos de soledad")
        self.assertEqual(result[0]["autor"], "Gabriel Garcia Marquez")
        self.assertEqual(result[0]["anio"], "1967")
        self.assertEqual(result[0]["isbn"], "9780307474728")
        self.assertEqual(
            result[0]["cover_url"],
            "https://covers.openlibrary.org/b/isbn/9780307474728-M.jpg?default=false",
        )

    def test_openlibrary_search_preserves_work_and_edition_identity(self):
        seen_urls = []
        response = {
            "docs": [
                {
                    "title": "The Mote in God's Eye",
                    "author_name": ["Larry Niven", "Jerry Pournelle"],
                    "author_key": ["OL1A"],
                    "first_publish_year": 1974,
                    "key": "/works/OL123W",
                    "edition_count": 12,
                    "editions": {
                        "docs": [
                            {
                                "key": "/books/OL456M",
                                "title": "La paja en el ojo de Dios",
                                "publish_date": "1997",
                                "publisher": ["Ediciones B"],
                                "language": [{"key": "/languages/spa"}],
                                "isbn": ["9788440680013"],
                            }
                        ]
                    },
                }
            ]
        }

        def fake_http(url):
            seen_urls.append(url)
            return response

        result = external_providers.openlibrary_busqueda("La paja en el ojo de Dios", language="spa", http_get_func=fake_http)

        self.assertEqual(result[0]["titulo"], "La paja en el ojo de Dios")
        self.assertEqual(result[0]["autor"], "Larry Niven")
        self.assertEqual(result[0]["anio"], "1997")
        self.assertEqual(result[0]["isbn"], "9788440680013")
        self.assertEqual(result[0]["work_id"], "/works/OL123W")
        self.assertEqual(result[0]["edition_id"], "/books/OL456M")
        self.assertEqual(result[0]["language"], "spa")
        self.assertEqual(result[0]["publisher"], "Ediciones B")
        self.assertIn("editions.title", seen_urls[0])
        self.assertIn("cover_i", seen_urls[0])
        self.assertIn("language=spa", seen_urls[0])

    def test_openlibrary_prefers_cover_id_over_rate_limited_isbn_url(self):
        url = external_providers._openlibrary_cover_url("9780307474728", 12345)

        self.assertEqual(
            url,
            "https://covers.openlibrary.org/b/id/12345-M.jpg?default=false",
        )

    def test_wikidata_search_normalizes_expected_response(self):
        response = {"search": [{"label": "El proceso", "id": "Q123"}]}

        result = external_providers.wikidata_busqueda("el proceso", http_get_func=lambda _url: response)

        self.assertEqual(result[0]["fuente"], "Wikidata")
        self.assertEqual(result[0]["titulo"], "El proceso")
        self.assertEqual(result[0]["identificador"], "Q123")

    def test_wikidata_search_reads_structured_book_properties(self):
        def fake_http(url):
            if "w/api.php" in url:
                return {"search": [{"label": "Taxi", "id": "QBOOK"}]}
            if "QBOOK.json" in url:
                return {
                    "entities": {
                        "QBOOK": {
                            "labels": {"es": {"value": "Taxi"}},
                            "claims": {
                                "P50": [{"mainsnak": {"datavalue": {"value": {"id": "QAUTHOR"}}}}],
                                "P577": [{"mainsnak": {"datavalue": {"value": {"time": "+2006-00-00T00:00:00Z"}}}}],
                                "P212": [{"mainsnak": {"datavalue": {"value": "9788498670622"}}}],
                                "P407": [{"mainsnak": {"datavalue": {"value": {"id": "QLANG"}}}}],
                                "P123": [{"mainsnak": {"datavalue": {"value": {"id": "QPUB"}}}}],
                            },
                        }
                    }
                }
            if "QAUTHOR.json" in url:
                return {"entities": {"QAUTHOR": {"labels": {"es": {"value": "Khaled Al Khamissi"}}}}}
            if "QLANG.json" in url:
                return {"entities": {"QLANG": {"labels": {"es": {"value": "árabe"}}}}}
            if "QPUB.json" in url:
                return {"entities": {"QPUB": {"labels": {"es": {"value": "Almuzara"}}}}}
            return None

        result = external_providers.wikidata_busqueda("Taxi Khaled Al Khamissi", http_get_func=fake_http)

        self.assertEqual(result[0]["titulo"], "Taxi")
        self.assertEqual(result[0]["autor"], "Khaled Al Khamissi")
        self.assertEqual(result[0]["anio"], "2006")
        self.assertEqual(result[0]["isbn"], "9788498670622")
        self.assertEqual(result[0]["language"], "árabe")
        self.assertEqual(result[0]["publisher"], "Almuzara")
        self.assertEqual(result[0]["source_scope"], "structured_work")

    def test_wikidata_cjk_query_tries_chinese_language_first(self):
        urls = []

        def fake_http(url):
            urls.append(url)
            return {"search": []}

        external_providers.wikidata_busqueda("三体", http_get_func=fake_http)

        self.assertIn("language=zh", urls[0])

    def test_library_of_congress_search_normalizes_expected_response(self):
        response = {"results": [{"title": "The Hobbit", "contributor": ["J. R. R. Tolkien"], "date": "1937", "id": "loc1"}]}

        result = external_providers.loc_busqueda("hobbit", http_get_func=lambda _url: response)

        self.assertEqual(result[0]["fuente"], "Library of Congress")
        self.assertEqual(result[0]["autor"], "J. R. R. Tolkien")
        self.assertEqual(result[0]["anio"], "1937")

    def test_crossref_search_normalizes_expected_response(self):
        response = {
            "message": {
                "items": [
                    {
                        "title": ["Interesting Paper"],
                        "author": [{"given": "Ada", "family": "Lovelace"}],
                        "issued": {"date-parts": [[1843]]},
                        "ISBN": ["978-1-234-56789-7"],
                        "DOI": "10.1000/example",
                    }
                ]
            }
        }

        result = external_providers.crossref_busqueda("interesting paper", http_get_func=lambda _url: response)

        self.assertEqual(result[0]["fuente"], "Crossref")
        self.assertEqual(result[0]["titulo"], "Interesting Paper")
        self.assertEqual(result[0]["autor"], "Ada Lovelace")
        self.assertEqual(result[0]["anio"], "1843")
        self.assertEqual(result[0]["identificador"], "10.1000/example")

    def test_openalex_search_normalizes_expected_response(self):
        response = {
            "results": [
                {
                    "title": "Open Knowledge",
                    "publication_year": 2020,
                    "authorships": [{"author": {"display_name": "Jane Doe"}}],
                    "ids": {"doi": "https://doi.org/10.1234/open"},
                }
            ]
        }

        result = external_providers.openalex_busqueda("open knowledge", http_get_func=lambda _url: response)

        self.assertEqual(result[0]["fuente"], "OpenAlex")
        self.assertEqual(result[0]["titulo"], "Open Knowledge")
        self.assertEqual(result[0]["autor"], "Jane Doe")
        self.assertEqual(result[0]["anio"], "2020")

    def test_internetarchive_and_gutendex_tolerate_missing_fields(self):
        archive_response = {"response": {"docs": [{"identifier": "id1"}]}}
        gutendex_response = {"results": [{"id": 1, "title": "Anonymous Text"}]}

        archive = external_providers.internetarchive_busqueda("missing fields", http_get_func=lambda _url: archive_response)
        gutendex = external_providers.gutendex_busqueda("missing fields", http_get_func=lambda _url: gutendex_response)

        self.assertEqual(archive[0]["fuente"], "Internet Archive")
        self.assertEqual(archive[0]["titulo"], "")
        self.assertEqual(gutendex[0]["fuente"], "Gutendex / Project Gutenberg")
        self.assertEqual(gutendex[0]["autor"], "")

    def test_http_error_timeout_returns_none_conservatively(self):
        with patch("metadata.external_providers.time.sleep", return_value=None):
            with patch("metadata.external_providers.urllib.request.urlopen", side_effect=TimeoutError("timeout")):
                self.assertIsNone(external_providers.http_get("https://example.invalid/timeout"))

    def test_invalid_json_response_returns_none_conservatively(self):
        with patch("metadata.external_providers.time.sleep", return_value=None):
            with patch("metadata.external_providers.urllib.request.urlopen", return_value=FakeResponse(b"not-json")):
                self.assertIsNone(external_providers.http_get("https://example.invalid/bad-json"))

    def test_incomplete_candidate_does_not_invent_metadata(self):
        result = external_providers.candidato("Test Source")

        self.assertEqual(result["titulo"], "")
        self.assertEqual(result["autor"], "")
        self.assertEqual(result["anio"], "")
        self.assertEqual(result["isbn"], "")

    def test_no_forbidden_provider_reference_in_external_provider_module(self):
        source = inspect.getsource(external_providers).lower()

        self.assertNotIn("google" + " books", source)
        self.assertNotIn("books." + "googleapis", source)

    def test_offline_consultar_web_keeps_local_flow_conservative(self):
        def offline_provider(*_args, **_kwargs):
            raise TimeoutError("offline")

        datos = {
            "isbns": ["9780307474728"],
            "dois": ["10.1000/example"],
            "titulo_nombre": "Cien anos de soledad",
            "autor_nombre": "Gabriel Garcia Marquez",
        }

        provider_names = [
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
        with ExitStack() as stack:
            for provider_name in provider_names:
                stack.enter_context(patch.object(library_core, provider_name, side_effect=offline_provider))
            returned_datos, candidatos = library_core.consultar_web(
                Path("Gabriel Garcia Marquez - Cien anos de soledad.epub"),
                datos=datos,
                busqueda_amplia=True,
            )

        self.assertIs(returned_datos, datos)
        self.assertEqual(candidatos, [])


if __name__ == "__main__":
    unittest.main()
