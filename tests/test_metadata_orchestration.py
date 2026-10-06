import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import library_core
from metadata import orchestration


class MetadataOrchestrationTests(unittest.TestCase):
    def test_empty_candidates_return_conservative_result(self):
        result = library_core.elegir_mejor_metadato(Path("Libro.epub"), {}, [])

        self.assertFalse(result["encontrado"])
        self.assertEqual(result["confianza"], 0)
        self.assertEqual(result["nombre_sugerido"], "Libro.epub")
        self.assertEqual(result["motivo"], "Sin candidatos web")

    def test_incomplete_candidate_does_not_invent_metadata(self):
        result = library_core.elegir_mejor_metadato(
            Path("Libro.epub"),
            {},
            [{"titulo": "", "autor": "", "fuente": "Open Library", "metodo": "Búsqueda"}],
        )

        self.assertFalse(result["encontrado"])
        self.assertEqual(result["titulo"], "")
        self.assertEqual(result["autor"], "")
        self.assertEqual(result["isbn"], "")

    def test_final_year_and_isbn_keep_current_rules(self):
        datos = {"anio_local": "1967", "isbns": ["9780307474728"]}
        best = {"anio": "1970", "isbn": "9999999999", "metodo": "Búsqueda"}

        year, isbn = orchestration.resolver_anio_isbn_final(best, datos, set(datos["isbns"]))

        self.assertEqual(year, "1967")
        self.assertEqual(isbn, "9780307474728")

    def test_unicode_accent_enye_title_wrapper_matches_direct_helper(self):
        datos = {"titulo_local": "El niño ñandú", "titulo_nombre": "El nino nandu"}

        wrapped = library_core.elegir_titulo_final(datos, "El nino nandu")
        direct = orchestration.elegir_titulo_final(
            datos,
            "El nino nandu",
            limpiar_titulo_legible_func=library_core.limpiar_titulo_legible,
            tokens_distintivos_titulo_func=library_core.tokens_distintivos_titulo,
            similitud_titulo_compacto_func=library_core.similitud_titulo_compacto,
            similitud_titulo_compacto_datos_func=library_core.similitud_titulo_compacto_datos,
            similitud_func=library_core.similitud,
            limpiar_nombre_archivo_func=library_core.limpiar_nombre_archivo,
            normalizar_texto_func=library_core.normalizar_texto,
        )

        self.assertEqual(wrapped, direct)
        self.assertEqual(wrapped, "El niño ñandú")

    def test_low_confidence_result_stays_conservative(self):
        best = {"titulo": "Libro", "autor": "Autor", "anio": "2001", "isbn": "", "fuente": "Wikidata"}

        result = orchestration.resultado_baja_confianza(
            "Libro.epub",
            best,
            72,
            "Consenso textual débil",
            limpiar_titulo_legible_func=library_core.limpiar_titulo_legible,
        )

        self.assertFalse(result["encontrado"])
        self.assertEqual(result["confianza"], 72)
        self.assertEqual(result["nombre_sugerido"], "Libro.epub")

    def test_strong_evidence_keeps_expected_action(self):
        datos = {
            "titulo_local": "Cien anos de soledad",
            "titulo_nombre": "Cien anos de soledad",
            "autor_local": "Gabriel Garcia Marquez",
            "autor_nombre": "Gabriel Garcia Marquez",
            "anio_local": "1967",
            "isbns": ["9780307474728"],
        }
        candidates = [
            {
                "titulo": "Cien anos de soledad",
                "autor": "Gabriel Garcia Marquez",
                "anio": "1967",
                "isbn": "9780307474728",
                "fuente": "Open Library",
                "metodo": "ISBN",
            }
        ]

        result = library_core.elegir_mejor_metadato(
            Path("Gabriel Garcia Marquez - Cien anos de soledad.epub"),
            datos,
            candidates,
        )

        self.assertTrue(result["encontrado"])
        self.assertGreaterEqual(result["confianza"], library_core.UMBRAL_RENOMBRAR)
        self.assertEqual(result["titulo"], "Cien anos de soledad")
        self.assertEqual(result["autor"], "Gabriel Garcia Marquez")
        self.assertEqual(result["anio"], "1967")
        self.assertEqual(result["isbn"], "9780307474728")

    def test_offline_fallback_does_not_break(self):
        def offline_provider(*_args, **_kwargs):
            raise TimeoutError("offline")

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
        datos = {
            "isbns": ["9780307474728"],
            "dois": ["10.1000/example"],
            "titulo_nombre": "Cien anos de soledad",
            "autor_nombre": "Gabriel Garcia Marquez",
        }

        with ExitStack() as stack:
            for provider_name in provider_names:
                stack.enter_context(patch.object(library_core, provider_name, side_effect=offline_provider))
            returned_datos, candidates = library_core.consultar_web(
                Path("Gabriel Garcia Marquez - Cien anos de soledad.epub"),
                datos=datos,
            )

        self.assertIs(returned_datos, datos)
        self.assertEqual(candidates, [])

    def test_suggested_name_does_not_include_invalid_characters(self):
        datos = {
            "titulo_local": "Libro invalido",
            "autor_local": "Autor Valido",
            "anio_local": "2020",
            "isbns": ["123456789X"],
        }
        candidates = [
            {
                "titulo": "Libro: invalido / raro?",
                "autor": "Autor Valido",
                "anio": "2020",
                "isbn": "123456789X",
                "fuente": "Open Library",
                "metodo": "ISBN",
            }
        ]

        result = library_core.elegir_mejor_metadato(Path("entrada.epub"), datos, candidates)

        self.assertTrue(result["encontrado"])
        self.assertNotRegex(result["nombre_sugerido"], r'[<>:"/\\|?*]')

    def test_library_core_wrappers_for_author_confirmation(self):
        datos = {"autor_local": "Gabriel García Márquez", "titulo_local": "Cien años de soledad"}

        self.assertTrue(library_core.autor_web_confirmado_por_local("Gabriel Garcia Marquez", datos))
        self.assertTrue(library_core.autor_anonimo_confirmado_por_web("Anónimo", {"titulo_local": "Romancero"}, 92))

    def test_filtrar_consultas_web_skips_used_short_and_repeated_queries(self):
        usadas = {"rayuela"}

        result = orchestration.filtrar_consultas_web(
            ["  Rayuela  ", "El    Aleph", "El Aleph", "abc", ""],
            usadas,
            normalizar_texto_func=library_core.normalizar_texto,
        )

        self.assertEqual(result, ["El Aleph"])

    def test_registrar_consulta_web_usada_wrapper_updates_sorted_state(self):
        datos = {"_consultas_web_usadas": ["rayuela"]}
        usadas = set(datos["_consultas_web_usadas"])

        key = library_core.registrar_consulta_web_usada(datos, usadas, "Julio Cortazar Rayuela")
        compact_key = library_core.registrar_consulta_web_usada(
            datos,
            usadas,
            "Julio Cortazar",
            prefijo="compact-author:",
        )

        self.assertEqual(key, "julio cortazar rayuela")
        self.assertEqual(compact_key, "compact-author:julio cortazar")
        self.assertEqual(datos["_consultas_web_usadas"], sorted(usadas))

    def test_invocar_proveedor_seguro_extends_candidates_and_ignores_errors(self):
        candidatos = [{"titulo": "Inicial"}]

        result = library_core.invocar_proveedor_seguro(
            candidatos,
            lambda query: [{"titulo": query}],
            "Rayuela",
        )
        after_error = library_core.invocar_proveedor_seguro(
            candidatos,
            lambda _query: (_ for _ in ()).throw(TimeoutError("offline")),
            "ignored",
        )

        self.assertIs(result, candidatos)
        self.assertIs(after_error, candidatos)
        self.assertEqual(candidatos, [{"titulo": "Inicial"}, {"titulo": "Rayuela"}])

    def test_construir_proveedores_respaldo_busqueda_preserves_order(self):
        normal = library_core.construir_proveedores_respaldo_busqueda(False)
        academico = library_core.construir_proveedores_respaldo_busqueda(True)

        self.assertEqual([name for name, _func in normal], [
            "Library of Congress Search",
            "Wikidata Search",
        ])
        self.assertEqual([name for name, _func in academico], [
            "Library of Congress Search",
            "Wikidata Search",
            "Crossref Search",
            "OpenAlex Search",
        ])

    def test_resultado_parada_temprana_web_returns_none_when_candidate_is_not_strong(self):
        libro = Path("Rayuela.epub")
        datos = {"titulo_nombre": "Rayuela"}
        candidatos = [{"titulo": "Rayuela"}]
        umbrales = []

        def hay_candidato_web_fuerte(_libro, _datos, _candidatos, *, umbral):
            umbrales.append(umbral)
            return False

        def deduplicar_no_esperado(_candidatos):
            self.fail("No debe deduplicar para retorno temprano si no hay candidato fuerte")

        result = orchestration.resultado_parada_temprana_web(
            libro,
            datos,
            candidatos,
            umbral=95,
            hay_candidato_web_fuerte_func=hay_candidato_web_fuerte,
            deduplicar_candidatos_func=deduplicar_no_esperado,
        )

        self.assertIsNone(result)
        self.assertEqual(umbrales, [95])

    def test_resultado_parada_temprana_web_wrapper_returns_deduplicated_candidates(self):
        libro = Path("Rayuela.epub")
        datos = {"titulo_nombre": "Rayuela"}
        candidatos = [{"titulo": "Rayuela"}, {"titulo": "Rayuela"}]
        deduplicados = [{"titulo": "Rayuela"}]

        with patch.object(library_core, "_hay_candidato_web_fuerte", return_value=True) as fuerte:
            with patch.object(library_core, "deduplicar_candidatos", return_value=deduplicados) as deduplicar:
                result = library_core.resultado_parada_temprana_web(libro, datos, candidatos, umbral=96)

        self.assertEqual(result, (datos, deduplicados))
        fuerte.assert_called_once_with(libro, datos, candidatos, umbral=96)
        deduplicar.assert_called_once_with(candidatos)

    def test_invocar_proveedores_con_parada_temprana_preserves_order_args_and_threshold(self):
        libro = Path("Rayuela.epub")
        datos = {"titulo_nombre": "Rayuela"}
        candidatos = []
        llamadas = []
        parada = (datos, [{"titulo": "Rayuela"}])

        def proveedor_uno(query, *, limit):
            return [{"titulo": query, "fuente": "uno", "limit": limit}]

        def proveedor_dos(query, *, limit):
            return [{"titulo": query, "fuente": "dos", "limit": limit}]

        def invocar(acumulador, proveedor_func, *args, **kwargs):
            llamadas.append((proveedor_func.__name__, args, kwargs))
            acumulador.extend(proveedor_func(*args, **kwargs))
            return acumulador

        def resultado_temprano(_libro, _datos, _candidatos, umbral):
            llamadas.append(("parada", umbral))
            return parada

        result = orchestration.invocar_proveedores_con_parada_temprana(
            libro,
            datos,
            candidatos,
            [("uno", proveedor_uno), ("dos", proveedor_dos)],
            "Rayuela",
            umbral=96,
            invocar_proveedor_seguro_func=invocar,
            resultado_parada_temprana_web_func=resultado_temprano,
            limit=25,
        )

        self.assertEqual(result, parada)
        self.assertEqual(llamadas, [
            ("proveedor_uno", ("Rayuela",), {"limit": 25}),
            ("proveedor_dos", ("Rayuela",), {"limit": 25}),
            ("parada", 96),
        ])
        self.assertEqual([item["fuente"] for item in candidatos], ["uno", "dos"])


if __name__ == "__main__":
    unittest.main()
