import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import ai_model_catalog
import ai_runtime_manager
import library_core
import metadata_decision
from ai_decision_cache import AIDecisionCache
from ai_local_judge import FakeAIJudge, request_ai_judgement
from ai_metadata_schema import ALLOWED_PROBLEM_FLAGS, validate_ai_metadata_response
from ai_prompt_builder import build_prompt, prompt_contains_private_path


def valid_ai_response(candidate_id="A", confidence=0.88, **overrides):
    data = {
        "decision": "choose_candidate",
        "candidate_id": candidate_id,
        "confidence": confidence,
        "normalized_author": "Gabriel García Márquez",
        "normalized_title": "Cien años de soledad",
        "detected_series": None,
        "detected_volume": None,
        "language": "es",
        "suggested_filename": "Gabriel García Márquez - Cien años de soledad.epub",
        "problem_flags": [],
        "review_reasons": [],
        "reason_codes": ["title_match", "author_match"],
        "needs_human_review": False,
    }
    data.update(overrides)
    return data


class LocalAIReinforcementTests(unittest.TestCase):
    def candidate(self):
        return {
            "candidate_id": "A",
            "fuente": "Open Library",
            "titulo": "Cien anos de soledad",
            "autor": "Gabriel Garcia Marquez",
            "anio": "1967",
            "isbn": "9780307474728",
            "score": 88,
        }

    def datos(self):
        return {
            "titulo_nombre": "Cien anos de soledad",
            "autor_nombre": "Gabriel Garcia Marquez",
            "isbns": ["9780307474728"],
            "ocr_texto": "x" * 2000,
            "senales_cortas": ["portada: Cien anos de soledad"],
        }

    def test_catalog_contains_only_allowed_qwen3_models(self):
        ids = [model.model_id for model in ai_model_catalog.get_model_options()]

        self.assertEqual(ids, ["qwen3-1.7b-q4", "qwen3-4b-q4"])

    def test_catalog_visible_labels_and_default_are_fixed(self):
        labels = [model.label for model in ai_model_catalog.get_model_options()]

        self.assertIn("Qwen3 1.7B Q4 — aprox. 1,4 GB — recomendado", labels)
        self.assertIn("Qwen3 4B Q4 — aprox. 2,5 GB — más preciso", labels)
        self.assertEqual(ai_model_catalog.default_model_id(), "qwen3-1.7b-q4")

    def test_library_core_ui_model_options_do_not_expose_extra_models(self):
        self.assertEqual(len(library_core.modelos_ia_local()), 2)

    def test_app_status_works_without_ai_installed(self):
        status = ai_runtime_manager.get_ai_status({"enabled": False})

        self.assertEqual(status["state"], "IA desactivada")

    def test_missing_runtime_does_not_break_status(self):
        with TemporaryDirectory() as tmp:
            status = ai_runtime_manager.get_ai_status({"enabled": True}, root=Path(tmp))

        self.assertEqual(status["state"], "Runtime llama.cpp no encontrado")

    def test_missing_model_does_not_break_status(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / "ai" / "runtime"
            runtime.mkdir(parents=True)
            (runtime / "llama-server.exe").write_text("fixture", encoding="utf-8")

            status = ai_runtime_manager.get_ai_status({"enabled": True}, root=root)

        self.assertEqual(status["state"], "Modelo no instalado")

    def test_prompt_does_not_include_full_private_path(self):
        prompt = build_prompt(
            r"C:\Users\reader\Private\Books\Cien anos.epub",
            self.datos(),
            [self.candidate()],
            local_confidence=88,
        )

        self.assertFalse(prompt_contains_private_path(prompt["user"]))
        self.assertIn("Cien anos.epub", prompt["user"])
        self.assertNotIn("Private", prompt["user"])

    def test_prompt_does_not_include_long_ocr_text(self):
        prompt = build_prompt("Cien anos.epub", self.datos(), [self.candidate()], local_confidence=88)

        self.assertNotIn("x" * 200, prompt["user"])

    def test_prompt_strips_path_flavors_independently_of_host(self):
        for private_path in (
            r"C:\Users\reader\Private\Books\Cien años.epub",
            "C:/Users/reader/Private/Books/Cien años.epub",
            r"\\server\share\Private\Books\Cien años.epub",
            r"\\?\C:\Users\reader\Private\Books\Cien años.epub",
            "/home/reader/Private/Books/Cien años.epub",
            "/Users/reader/Private/Books/Cien años.epub",
            r"C:Private\Cien años.epub",
        ):
            with self.subTest(path=private_path):
                prompt = build_prompt(private_path, self.datos(), [self.candidate()])
                self.assertEqual(prompt["payload"]["file"]["base_name"], "Cien años.epub")
                self.assertEqual(prompt["payload"]["file"]["extension"], ".epub")
                self.assertNotIn("Private", prompt["user"])
                self.assertFalse(prompt_contains_private_path(prompt["user"]))

    def test_prompt_extension_cannot_expose_dotted_parent_directory(self):
        for private_path in (r"C:\Private.epub\Cien años", "/home/reader/Private.epub/Cien años"):
            with self.subTest(path=private_path):
                prompt = build_prompt(private_path, self.datos(), [self.candidate()])
                self.assertEqual(prompt["payload"]["file"]["base_name"], "Cien años")
                self.assertEqual(prompt["payload"]["file"]["extension"], "")
                self.assertNotIn("Private", prompt["user"])

    def test_prompt_includes_only_minimal_signals_and_candidates(self):
        prompt = build_prompt("Cien anos.epub", self.datos(), [self.candidate()], local_confidence=88)

        self.assertIn("local_signals", prompt["payload"])
        self.assertIn("candidates", prompt["payload"])
        self.assertEqual(prompt["payload"]["candidates"][0]["candidate_id"], "A")

    def test_valid_json_response_is_accepted(self):
        prompt = build_prompt("Cien anos.epub", self.datos(), [self.candidate()], local_confidence=88)
        result = validate_ai_metadata_response(valid_ai_response(), prompt["candidates"])

        self.assertTrue(result.ok)

    def test_invalid_json_is_rejected_and_retried_once(self):
        judge = FakeAIJudge(["not-json", valid_ai_response()])
        result = request_ai_judgement(
            "Cien anos.epub",
            self.datos(),
            [self.candidate()],
            local_confidence=88,
            judge=judge,
            cache=AIDecisionCache(),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(judge.calls, 2)

    def test_nonexistent_candidate_is_rejected(self):
        prompt = build_prompt("Cien anos.epub", self.datos(), [self.candidate()], local_confidence=88)
        result = validate_ai_metadata_response(valid_ai_response(candidate_id="Z"), prompt["candidates"])

        self.assertFalse(result.ok)
        self.assertIn("candidate_id_not_found", result.errors)

    def test_normalized_author_cannot_invent_author(self):
        prompt = build_prompt("Cien anos.epub", self.datos(), [self.candidate()], local_confidence=88)
        result = validate_ai_metadata_response(valid_ai_response(normalized_author="Jorge Luis Borges"), prompt["candidates"])

        self.assertFalse(result.ok)
        self.assertIn("normalized_author_not_supported", result.errors)

    def test_normalized_title_cannot_invent_title(self):
        prompt = build_prompt("Cien anos.epub", self.datos(), [self.candidate()], local_confidence=88)
        result = validate_ai_metadata_response(valid_ai_response(normalized_title="El amor en los tiempos del colera"), prompt["candidates"])

        self.assertFalse(result.ok)
        self.assertIn("normalized_title_not_supported", result.errors)

    def test_suggested_filename_cannot_use_unconfirmed_data(self):
        prompt = build_prompt("Cien anos.epub", self.datos(), [self.candidate()], local_confidence=88)
        response = valid_ai_response(suggested_filename="Gabriel García Márquez - Libro inventado.epub")
        result = validate_ai_metadata_response(response, prompt["candidates"])

        self.assertFalse(result.ok)
        self.assertIn("suggested_filename_contains_unconfirmed_data", result.errors)

    def test_problem_flags_are_controlled(self):
        prompt = build_prompt("Cien anos.epub", self.datos(), [self.candidate()], local_confidence=88)
        ok = validate_ai_metadata_response(valid_ai_response(problem_flags=["translation"]), prompt["candidates"])
        bad = validate_ai_metadata_response(valid_ai_response(problem_flags=["invented_flag"]), prompt["candidates"])

        self.assertTrue(ok.ok)
        self.assertFalse(bad.ok)
        self.assertIn("translation", ALLOWED_PROBLEM_FLAGS)

    def test_review_reasons_are_brief(self):
        prompt = build_prompt("Cien anos.epub", self.datos(), [self.candidate()], local_confidence=88)
        response = valid_ai_response(review_reasons=["x" * 181])
        result = validate_ai_metadata_response(response, prompt["candidates"])

        self.assertFalse(result.ok)
        self.assertIn("review_reason_too_long", result.errors)

    def test_confidence_above_92_does_not_call_ai(self):
        self.assertFalse(metadata_decision.should_call_ai_for_confidence(92))

    def test_confidence_between_75_and_92_calls_ai_when_available(self):
        self.assertTrue(metadata_decision.should_call_ai_for_confidence(88))

    def test_confidence_below_75_goes_to_review_without_ai(self):
        self.assertFalse(metadata_decision.should_call_ai_for_confidence(74.9))

    def test_ai_contradicts_exact_isbn_goes_to_review(self):
        ai_result = request_ai_judgement(
            "Cien anos.epub",
            {"isbns": ["9780000000000"]},
            [self.candidate()],
            local_confidence=88,
            judge=FakeAIJudge([valid_ai_response()]),
            cache=AIDecisionCache(),
        )

        evaluation = metadata_decision.evaluate_ai_decision(ai_result, {"isbns": ["9780000000000"]})
        self.assertEqual(evaluation["action"], "needs_review")

    def test_cache_avoids_repeated_ai_calls(self):
        cache = AIDecisionCache()
        judge = FakeAIJudge([valid_ai_response()])
        kwargs = {
            "file_path_or_name": "Cien anos.epub",
            "datos": self.datos(),
            "candidates": [self.candidate()],
            "local_confidence": 88,
            "judge": judge,
            "cache": cache,
        }

        request_ai_judgement(**kwargs)
        request_ai_judgement(**kwargs)

        self.assertEqual(judge.calls, 1)

    def test_duplicate_equivalence_by_translation_is_suggestion_only(self):
        prompt = build_prompt("One Hundred Years.epub", self.datos(), [self.candidate()], local_confidence=88)
        result = validate_ai_metadata_response(
            valid_ai_response(problem_flags=["duplicate_equivalence_suggested"]),
            prompt["candidates"],
        )

        self.assertTrue(result.ok)

    def test_series_and_volume_are_accepted_when_attached_to_existing_candidate(self):
        prompt = build_prompt("Sanderson - Mistborn 01 - The Final Empire.epub", {}, [self.candidate()], local_confidence=88)
        result = validate_ai_metadata_response(
            valid_ai_response(detected_series="Mistborn", detected_volume="01"),
            prompt["candidates"],
        )

        self.assertTrue(result.ok)

    def test_problematic_edition_can_request_review(self):
        prompt = build_prompt("Preview.epub", {}, [self.candidate()], local_confidence=80)
        response = valid_ai_response(
            decision="needs_review",
            candidate_id=None,
            confidence=0.55,
            problem_flags=["preview"],
            review_reasons=["Parece una muestra o preview"],
            needs_human_review=True,
        )
        result = validate_ai_metadata_response(response, prompt["candidates"])

        self.assertTrue(result.ok)

    def test_language_conflict_flag_is_allowed(self):
        prompt = build_prompt("Libro.epub", {"idioma": "es"}, [self.candidate()], local_confidence=88)
        result = validate_ai_metadata_response(valid_ai_response(problem_flags=["language_conflict"]), prompt["candidates"])

        self.assertTrue(result.ok)

    def test_library_core_refinement_uses_fake_ai_without_runtime(self):
        candidate = self.candidate()
        candidate["score"] = 88

        with patch.object(library_core, "cargar_configuracion_ia", return_value={"enabled": True, "model_id": "qwen3-1.7b-q4"}):
            result = library_core.reforzar_candidato_dudoso_con_ia(
                Path("Cien anos.epub"),
                self.datos(),
                [candidate],
                candidate,
                88,
                "fixture",
                judge=FakeAIJudge([valid_ai_response(confidence=0.91)]),
            )

        self.assertEqual(result["tipo"], "choose")
        self.assertGreaterEqual(result["confianza"], 90)


if __name__ == "__main__":
    unittest.main()
