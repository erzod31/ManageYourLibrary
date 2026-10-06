import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import library_core
from core import performance_pipeline


class FastAnalysisPipelineTests(unittest.TestCase):
    def test_structured_metadata_fast_path_does_not_call_ocr(self):
        datos = {
            "titulo_local": "El libro rápido",
            "autor_local": "Autora Ñ",
            "anio_local": "2026",
            "isbns": ["9780306406157"],
        }
        local = {
            "encontrado": True,
            "confianza": 96,
            "titulo": "El libro rápido",
            "autor": "Autora Ñ",
            "anio": "2026",
            "isbn": "9780306406157",
            "nombre_sugerido": "Autora Ñ - El libro rápido (2026) [9780306406157].epub",
            "fuente": "Local analysis",
            "motivo": "structured metadata",
        }
        with (
            patch.object(library_core, "extraer_datos_rapidos", return_value=datos),
            patch.object(library_core, "elegir_metadatos_locales", return_value=local),
            patch.object(library_core, "evidencia_rapida_suficiente", return_value=True),
            patch("ocr_engine.extraer_texto_documento_ocr") as ocr,
        ):
            result = library_core.analizar_archivo_rapido(Path("Autora Ñ - El libro rápido.epub"))

        self.assertEqual(result["status"], performance_pipeline.FAST_OK)
        self.assertEqual(result["title"], "El libro rápido")
        self.assertEqual(result["author"], "Autora Ñ")
        self.assertEqual(result["format"], ".epub")
        self.assertEqual(result["identity_result"]["estado_analisis"], performance_pipeline.FAST_OK)
        ocr.assert_not_called()

    def test_incomplete_pdf_is_marked_for_deferred_ocr(self):
        with (
            patch.object(library_core, "extraer_datos_rapidos", return_value={}),
            patch.object(library_core, "elegir_metadatos_locales", return_value={"encontrado": False, "confianza": 20}),
            patch.object(library_core, "evidencia_rapida_suficiente", return_value=False),
        ):
            result = library_core.analizar_archivo_rapido(Path("escaneado.pdf"))

        self.assertEqual(result["status"], performance_pipeline.NEEDS_OCR)
        self.assertEqual(result["primary_method"], "local_fast_incomplete")

    def test_incomplete_plain_text_goes_to_review_without_ocr(self):
        with (
            patch.object(library_core, "extraer_datos_rapidos", return_value={}),
            patch.object(library_core, "elegir_metadatos_locales", return_value={"encontrado": False, "confianza": 10}),
            patch.object(library_core, "evidencia_rapida_suficiente", return_value=False),
        ):
            result = library_core.analizar_archivo_rapido(Path("dudoso.txt"))

        self.assertEqual(result["status"], performance_pipeline.NEEDS_REVIEW)
        self.assertFalse(performance_pipeline.supports_deferred_ocr("dudoso.txt"))

    def test_low_confidence_fast_result_is_never_accepted(self):
        with (
            patch.object(library_core, "extraer_datos_rapidos", return_value={}),
            patch.object(
                library_core,
                "elegir_metadatos_locales",
                return_value={"encontrado": True, "confianza": 45, "titulo": "Dudoso", "autor": "Autor"},
            ),
            patch.object(library_core, "evidencia_rapida_suficiente", return_value=False),
        ):
            result = library_core.analizar_archivo_rapido(Path("dudoso.epub"))

        self.assertEqual(result["status"], performance_pipeline.NEEDS_OCR)
        self.assertNotEqual(result["status"], performance_pipeline.FAST_OK)

    def test_fast_result_shape_is_stable(self):
        result = performance_pipeline.make_analysis_result(
            "三体 ñ.epub",
            performance_pipeline.NEEDS_OCR,
            title="三体",
            author="Autor Ñ",
            year="2008",
            isbn="9780306406157",
            confidence=42,
            primary_method="local_fast_incomplete",
        )

        self.assertEqual(
            set(result),
            {
                "original_path",
                "format",
                "status",
                "title",
                "author",
                "year",
                "isbn",
                "confidence",
                "primary_method",
                "identity_result",
                "error",
            },
        )
        self.assertEqual(result["title"], "三体")

    def test_deferred_ocr_runs_only_after_fast_local_collection(self):
        fast_local = {"ocr_recomendado": True, "ocr_metodo": "", "ocr_diferido_ejecutado": False}
        ocr_local = {"ocr_recomendado": True, "ocr_metodo": "pdf_ocr", "ocr_diferido_ejecutado": True}
        with patch.object(library_core, "extraer_datos_locales", side_effect=[fast_local, ocr_local]) as extract:
            result = library_core.recolectar_datos_con_ocr_diferido(Path("escaneado.pdf"))

        self.assertIs(result, ocr_local)
        self.assertEqual(extract.call_count, 2)
        self.assertFalse(extract.call_args_list[0].kwargs["permitir_ocr"])
        self.assertTrue(extract.call_args_list[1].kwargs["permitir_ocr"])
        self.assertEqual(extract.call_args_list[1].kwargs["max_paginas_ocr"], 12)

    def test_fast_mode_leaves_ocr_for_review_queue(self):
        fast_local = {"ocr_recomendado": True, "ocr_metodo": "", "ocr_diferido_ejecutado": False}
        with patch.object(library_core, "extraer_datos_locales", return_value=fast_local) as extract:
            result = library_core.recolectar_datos_con_ocr_diferido(
                Path("escaneado.pdf"),
                modo_analisis=performance_pipeline.FAST_MODE,
            )

        self.assertIs(result, fast_local)
        self.assertEqual(extract.call_count, 1)
        self.assertFalse(extract.call_args.kwargs["permitir_ocr"])

    def test_low_confidence_after_ocr_stays_conservative(self):
        result = library_core.aplicar_estado_analisis(
            {"encontrado": False, "confianza": 42},
            {"ocr_metodo": "pdf_ocr", "ocr_diferido_ejecutado": True},
        )

        self.assertEqual(result["estado_analisis"], performance_pipeline.NEEDS_REVIEW)

    def test_success_after_deferred_ocr_is_marked_ocr_ok(self):
        result = library_core.aplicar_estado_analisis(
            {"encontrado": True, "confianza": 91},
            {"ocr_metodo": "pdf_ocr", "ocr_diferido_ejecutado": True},
        )

        self.assertEqual(result["estado_analisis"], performance_pipeline.OCR_OK)

    def test_fast_batch_preserves_input_order_and_uses_light_pool(self):
        seen_threads = set()
        lock = threading.Lock()
        events = []
        paths = [Path(f"libro-{index}.epub") for index in range(6)]

        def analyzer(path):
            with lock:
                seen_threads.add(threading.get_ident())
            time.sleep(0.02)
            return performance_pipeline.make_analysis_result(path, performance_pipeline.FAST_OK)

        results = performance_pipeline.process_fast_batch(
            paths,
            analyzer,
            max_workers=4,
            event_callback=events.append,
        )

        self.assertEqual([result["original_path"] for result in results], [str(path) for path in paths])
        self.assertGreaterEqual(len(seen_threads), 2)
        self.assertEqual(len(events), len(paths))
        self.assertTrue(all(event["phase"] == "fast" for event in events))

    def test_fast_batch_does_not_mix_metadata_between_paths(self):
        paths = [Path(f"libro-{index}.epub") for index in range(12)]

        def analyzer(path):
            time.sleep(0.001 * (12 - int(path.stem.split("-")[-1])))
            return performance_pipeline.make_analysis_result(
                path,
                performance_pipeline.FAST_OK,
                title=f"title:{path.name}",
                author=f"author:{path.name}",
            )

        results = performance_pipeline.process_fast_batch(paths, analyzer, max_workers=4)

        for path, result in zip(paths, results):
            self.assertEqual(result["original_path"], str(path))
            self.assertEqual(result["title"], f"title:{path.name}")
            self.assertEqual(result["author"], f"author:{path.name}")

    def test_ocr_batch_only_processes_pending_items_with_conservative_limit(self):
        lock = threading.Lock()
        active = 0
        peak_active = 0
        analyzed = []
        analyses = [
            performance_pipeline.make_analysis_result("uno.pdf", performance_pipeline.NEEDS_OCR),
            performance_pipeline.make_analysis_result("dos.pdf", performance_pipeline.FAST_OK),
            performance_pipeline.make_analysis_result("tres.pdf", performance_pipeline.NEEDS_OCR),
            performance_pipeline.make_analysis_result("cuatro.pdf", performance_pipeline.NEEDS_REVIEW),
        ]

        def analyzer(path):
            nonlocal active, peak_active
            with lock:
                analyzed.append(path.name)
                active += 1
                peak_active = max(peak_active, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return {"encontrado": True, "titulo": path.stem, "confianza": 90}

        results = performance_pipeline.process_ocr_batch(analyses, analyzer, max_workers=2)

        self.assertEqual(sorted(analyzed), ["tres.pdf", "uno.pdf"])
        self.assertLessEqual(peak_active, 2)
        self.assertTrue(all(result["status"] == performance_pipeline.OCR_OK for result in results))

    def test_ui_event_queue_runs_callbacks_only_when_main_thread_drains(self):
        queue = performance_pipeline.UiEventQueue()
        called = []
        worker = threading.Thread(target=lambda: queue.post(called.append, "ok"))
        worker.start()
        worker.join()

        self.assertEqual(called, [])
        self.assertEqual(queue.drain(), 1)
        self.assertEqual(called, ["ok"])

    def test_ui_event_queue_rejects_drain_from_worker_thread(self):
        queue = performance_pipeline.UiEventQueue()
        errors = []

        def drain_from_worker():
            try:
                queue.drain()
            except RuntimeError as exc:
                errors.append(str(exc))

        worker = threading.Thread(target=drain_from_worker)
        worker.start()
        worker.join()

        self.assertEqual(errors, ["UI events must be drained from the main thread"])


if __name__ == "__main__":
    unittest.main()
