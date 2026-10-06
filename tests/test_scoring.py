import unittest
from pathlib import Path

import library_core
from metadata import scoring


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.book = Path("Gabriel Garcia Marquez - Cien anos de soledad.epub")
        self.datos = {
            "titulo_local": "Cien anos de soledad",
            "titulo_texto": "",
            "titulo_nombre": "Cien anos de soledad",
            "autor_local": "Gabriel Garcia Marquez",
            "autor_nombre": "Gabriel Garcia Marquez",
            "anio_local": "1967",
            "isbns": [],
        }

    def score_direct_with_core_callbacks(self, candidate, datos=None, book=None):
        return scoring.puntuar_candidato(
            book or self.book,
            candidate,
            datos or self.datos,
            candidato_web_parece_ficha_de_autor_func=library_core.candidato_web_parece_ficha_de_autor,
            linea_parece_nombre_autor_func=library_core._linea_parece_nombre_autor,
            limpiar_nombre_como_pista_func=library_core.limpiar_nombre_como_pista,
            limpiar_titulo_para_busqueda_func=library_core.limpiar_titulo_para_busqueda,
            similitud_func=library_core.similitud,
            similitud_titulo_compacto_func=library_core.similitud_titulo_compacto,
            similitud_titulo_compacto_datos_func=library_core.similitud_titulo_compacto_datos,
            titulo_compacto_confirmado_por_candidato_func=library_core.titulo_compacto_confirmado_por_candidato,
            autor_es_usable_func=library_core.autor_es_usable,
            tokens_distintivos_titulo_func=library_core.tokens_distintivos_titulo,
            normalizar_texto_func=library_core.normalizar_texto,
        )

    def test_exact_isbn_candidate_gets_high_confidence(self):
        datos = dict(self.datos, isbns=["9780307474728"])
        candidate = {"titulo": "Cien anos de soledad", "autor": "Gabriel Garcia Marquez", "isbn": "9780307474728"}

        score, reason = library_core.puntuar_candidato(self.book, candidate, datos)

        self.assertEqual(score, 98)
        self.assertIn("ISBN", reason)

    def test_exact_title_scores_strongly(self):
        candidate = {"titulo": "Cien anos de soledad", "autor": "", "fuente": "Open Library", "metodo": "Busqueda"}

        score, _reason = library_core.puntuar_candidato(self.book, candidate, self.datos)

        self.assertGreaterEqual(score, 85)

    def test_matching_author_increases_score(self):
        without_author = {"titulo": "Cien anos de soledad", "autor": "", "fuente": "Open Library", "metodo": "Busqueda"}
        with_author = {
            "titulo": "Cien anos de soledad",
            "autor": "Gabriel Garcia Marquez",
            "fuente": "Open Library",
            "metodo": "Busqueda",
        }

        score_without, _ = library_core.puntuar_candidato(self.book, without_author, self.datos)
        score_with, _ = library_core.puntuar_candidato(self.book, with_author, self.datos)

        self.assertGreater(score_with, score_without)

    def test_matching_year_avoids_existing_mismatch_penalty(self):
        matched_year = {
            "titulo": "Cien anos de la soledad",
            "autor": "Gabriel Garcia Marquez",
            "anio": "1967",
            "fuente": "Open Library",
            "metodo": "Busqueda",
        }
        mismatched_year = dict(matched_year, anio="1985")

        score_matched, _ = library_core.puntuar_candidato(self.book, matched_year, self.datos)
        score_mismatched, _ = library_core.puntuar_candidato(self.book, mismatched_year, self.datos)

        self.assertGreater(score_matched, score_mismatched)

    def test_similar_but_unconfirmed_title_stays_below_rename_threshold(self):
        candidate = {
            "titulo": "Cien anos de soledad edicion anotada critica",
            "autor": "",
            "anio": "1967",
            "fuente": "Internet Archive",
            "metodo": "Busqueda",
        }

        score, _reason = library_core.puntuar_candidato(self.book, candidate, self.datos)

        self.assertLess(score, library_core.UMBRAL_RENOMBRAR)

    def test_incomplete_candidate_stays_conservative(self):
        score, _reason = scoring.puntuar_candidato(self.book, {"titulo": "", "autor": ""}, self.datos)

        self.assertLess(score, 50)

    def test_auxiliary_external_source_does_not_win_unconfirmed(self):
        candidate = {
            "titulo": "Cien anos de soledad edicion anotada critica",
            "autor": "",
            "fuente": "Internet Archive",
            "metodo": "Busqueda",
        }

        score, _reason = library_core.puntuar_candidato(self.book, candidate, self.datos)

        self.assertLess(score, library_core.UMBRAL_RENOMBRAR)

    def test_unicode_accents_and_enye_do_not_break_scoring(self):
        book = Path("Alvaro Nunez - El nino nandu.epub")
        datos = {
            "titulo_local": "El niño ñandú",
            "titulo_nombre": "El nino nandu",
            "autor_local": "Álvaro Núñez",
            "autor_nombre": "Alvaro Nunez",
            "isbns": [],
        }
        candidate = {"titulo": "El nino nandu", "autor": "Alvaro Nunez", "fuente": "Open Library", "metodo": "Busqueda"}

        score, _reason = library_core.puntuar_candidato(book, candidate, datos)

        self.assertGreaterEqual(score, 90)

    def test_low_confidence_still_goes_to_review(self):
        action = scoring.decide_final_action(
            {"encontrado": False},
            {"confidence_total": 60, "confidence_title": 60, "confidence_author": 0, "conflicts": []},
        )

        self.assertEqual(action, "revisar_nuevamente")

    def test_wrapper_preserves_scoring_behavior_for_known_fixture(self):
        candidate = {
            "titulo": "Cien anos de la soledad",
            "autor": "Gabriel Garcia Marquez",
            "anio": "1967",
            "fuente": "Open Library",
            "metodo": "Busqueda",
        }

        self.assertEqual(
            library_core.puntuar_candidato(self.book, candidate, self.datos),
            self.score_direct_with_core_callbacks(candidate),
        )

    def test_consensus_uses_isbn_title_and_author_evidence(self):
        resultado = {
            "titulo": "Cien anos de soledad",
            "autor": "Gabriel Garcia Marquez",
            "isbn": "9780307474728",
            "confianza": 92,
            "fuente": "Open Library",
        }
        evidencias = [
            scoring.crear_evidencia("metadata_structured", "title", "Cien anos de soledad", 85),
            scoring.crear_evidencia("metadata_structured", "author", "Gabriel Garcia Marquez", 85),
            scoring.crear_evidencia("local_isbn", "isbn", "9780307474728", 92),
        ]

        confidence = scoring.calculate_confidence(resultado, evidencias)

        self.assertGreaterEqual(confidence["confidence_total"], 85)
        self.assertGreaterEqual(confidence["confidence_isbn"], 80)


if __name__ == "__main__":
    unittest.main()
