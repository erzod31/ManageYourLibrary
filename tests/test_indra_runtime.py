import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import ocr_engine
from core import ocr_runtime
from core.cancellation import CancellationToken, OperationCancelled


SERVER = """
import base64, json, os, sys, time
counter = 0
for raw in sys.stdin.buffer:
    request = json.loads(raw)
    value = base64.b64decode(request['image']).decode('ascii')
    if value == 'slow': time.sleep(0.7)
    if value == 'hang': time.sleep(30)
    counter += 1
    print(json.dumps({'text': value, 'lines': [], 'error': None, 'pid': os.getpid(), 'counter': counter}), flush=True)
"""


class IndraWorkerTests(unittest.TestCase):
    def setUp(self):
        self.worker = ocr_runtime.LocalOcrWorker()
        self.command = patch.object(ocr_runtime, "worker_command", return_value=[sys.executable, "-u", "-c", SERVER])
        self.command.start()

    def tearDown(self):
        self.worker.close()
        self.command.stop()

    def test_process_reused_between_different_pages_and_cache_isolated(self):
        first = self.worker.recognize(b"page1")
        first["text"] = "changed by caller"
        second = self.worker.recognize(b"page2")
        again = self.worker.recognize(b"page1")
        self.assertEqual(second["counter"], 2)
        self.assertEqual(second["pid"], again["pid"])
        self.assertEqual(again["text"], "page1")
        self.assertTrue(again["inference_cache"])

    def test_cache_evicts_oldest_page(self):
        for index in range(ocr_runtime.MAX_CACHE_ENTRIES + 1):
            self.assertIsNone(self.worker.recognize(str(index).encode())["error"])
        first_again = self.worker.recognize(b"0")
        self.assertEqual(first_again["counter"], ocr_runtime.MAX_CACHE_ENTRIES + 2)

    def test_timeout_stops_owned_worker_and_next_request_recovers(self):
        result = self.worker.recognize(b"hang", timeout=0.15)
        self.assertIn("timed out", result["error"])
        self.assertIsNone(self.worker._process)
        self.assertEqual(self.worker.recognize(b"recovered")["text"], "recovered")

    def test_cancellation_during_inference_stops_owned_worker(self):
        token = CancellationToken()
        timer = threading.Timer(0.15, token.cancel)
        timer.start()
        start = time.monotonic()
        try:
            with self.assertRaises(OperationCancelled):
                self.worker.recognize(b"hang", cancellation=token)
        finally:
            timer.cancel()
        self.assertLess(time.monotonic() - start, 3)
        self.assertIsNone(self.worker._process)

    def test_cancelling_waiting_request_does_not_kill_active_request(self):
        result = []
        thread = threading.Thread(target=lambda: result.append(self.worker.recognize(b"slow")))
        thread.start()
        deadline = time.monotonic() + 2
        while self.worker._process is None and time.monotonic() < deadline:
            time.sleep(0.01)
        token = CancellationToken()
        timer = threading.Timer(0.1, token.cancel)
        timer.start()
        try:
            with self.assertRaises(OperationCancelled):
                self.worker.recognize(b"waiting", cancellation=token)
        finally:
            timer.cancel()
            thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0]["text"], "slow")

    def test_oversize_and_empty_images_do_not_start_worker(self):
        with patch.object(ocr_runtime, "MAX_IMAGE_BYTES", 3):
            self.assertTrue(self.worker.recognize(b"four")["error"])
            self.assertTrue(self.worker.recognize(b"")["error"])
        self.assertIsNone(self.worker._process)

    def test_idle_worker_is_released(self):
        with patch.object(ocr_runtime, "IDLE_SECONDS", 0.1):
            self.worker.recognize(b"page")
            process = self.worker._process
            deadline = time.monotonic() + 2
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
        self.assertIsNotNone(process.poll())
        self.assertIsNone(self.worker._process)

    def test_invalid_protocol_response_stops_worker(self):
        command = [sys.executable, "-u", "-c", "import sys; sys.stdin.buffer.readline(); print('invalid JSON', flush=True)"]
        with patch.object(ocr_runtime, "worker_command", return_value=command):
            result = self.worker.recognize(b"page")
        self.assertTrue(result["error"])
        self.assertIsNone(self.worker._process)
        self.assertEqual(self.worker.recognize(b"recovered")["text"], "recovered")

    def test_external_model_override_is_ignored(self):
        with patch.dict("os.environ", {"INDRA_OCR_MODEL_DIR": "untrusted-models"}):
            self.assertEqual(ocr_runtime.model_directory(), ocr_runtime.resource_root() / "ocr_models/indra")


class IndraDocumentTests(unittest.TestCase):
    def tearDown(self):
        ocr_engine.limpiar_cache_ocr()

    def page(self, text):
        return {"text": text, "lines": [], "error": None}

    def test_pdf_limit_is_in_cache_key_and_standalone_isbn_does_not_stop_ocr(self):
        def pages(path, count, dpi):
            for index in range(count):
                yield index, str(index).encode()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scan.pdf"
            path.write_bytes(b"synthetic-pdf")
            with patch.object(ocr_engine, "_pdf_images", side_effect=pages), patch.object(
                ocr_runtime, "recognize", return_value=self.page("ISBN 9780307474728")
            ) as inference:
                first = ocr_engine.extraer_texto_documento_ocr(path, max_paginas=1)
                second = ocr_engine.extraer_texto_documento_ocr(path, max_paginas=3)
                third = ocr_engine.extraer_texto_documento_ocr(path, max_paginas=3)
        self.assertEqual(first["paginas_analizadas"], 1)
        self.assertEqual(second["paginas_analizadas"], 3)
        self.assertTrue(third["desde_cache"])
        self.assertEqual(inference.call_count, 4)

    def test_changed_source_is_rejected_and_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.png"
            path.write_bytes(b"original")

            def infer(*args, **kwargs):
                path.write_bytes(b"modified with different size")
                return self.page("A title\nAn Author")

            with patch.object(ocr_runtime, "recognize", side_effect=infer):
                result = ocr_engine.extraer_texto_documento_ocr(path)
        self.assertTrue(result["error"])
        self.assertEqual(result["texto"], "")
        self.assertFalse(ocr_engine._SESSION_OCR_CACHE)

    def test_cancelled_operation_is_not_recast_as_ordinary_ocr_failure(self):
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(OperationCancelled):
            ocr_engine.extraer_texto_imagen_bytes_ocr(b"image", cancellation=token)
