"""Bounded local runtime checks; never load a personal library or configuration."""
from __future__ import annotations

import io
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_LANGUAGES = ("eng", "spa", "fra", "nld", "chi_sim")
FIXTURE_TEXT = "LIBRARY TEST 2026"


def run_checks(version: str) -> dict:
    report = {"version": version, "frozen": bool(getattr(sys, "frozen", False)),
              "created_at": datetime.now(timezone.utc).isoformat(), "checks": {}}
    checks = report["checks"]

    def check(name, callback):
        try:
            callback()
            checks[name] = "passed"
        except Exception as exc:
            checks[name] = f"failed: {type(exc).__name__}: {exc}"

    def pillow():
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new("RGB", (1200, 220), "white")
        draw = ImageDraw.Draw(image)
        draw.text((45, 70), FIXTURE_TEXT, fill="black", font=ImageFont.load_default(size=64))
        return image

    def tk_runtime():
        import tkinter as tk
        root = tk.Tk()
        try:
            root.withdraw()
            root.update_idletasks()
            from ui.accessibility import available, expose
            native = available(root)
            report['gui'] = {'tk': root.tk.call('package', 'present', 'Tk'),
                             'native_accessibility': native}
            if native:
                fixture = tk.Button(root, text='Accessibility fixture')
                expose(fixture, role='Button', name='Accessibility fixture')
                if root.tk.call('::tk::accessible::get_acc_name', str(fixture)) != 'Accessibility fixture':
                    raise RuntimeError('Native accessibility name was not retained')
                fixture.destroy()
        finally:
            root.destroy()

    def bundled_languages():
        import os
        import ocr_engine
        base = ocr_engine._resource_path("tesseract")
        if not getattr(sys, 'frozen', False):
            selected = os.environ.get('MANAGE_YOUR_LIBRARY_OCR_DIR')
            if not selected:
                candidate = ocr_engine._tesseract_path()
                if candidate and (candidate.parent / 'native-ocr-manifest.json').is_file():
                    selected = str(candidate.parent)
            if selected:
                base = Path(selected)
                from tools.verify_ocr_payload import validate_payload
                validate_payload(base)
        executable = base / ("tesseract.exe" if sys.platform == "win32" else "tesseract")
        if not executable.is_file() or ocr_engine._tesseract_path() != executable:
            raise RuntimeError("Expected the bundled OCR executable, not a PATH fallback")
        for language in REQUIRED_LANGUAGES:
            if not (base / "tessdata" / f"{language}.traineddata").is_file():
                raise RuntimeError(f"Missing OCR language: {language}")

    def recognize(image):
        import ocr_engine
        with io.BytesIO() as stream:
            image.save(stream, format="PNG")
            text, error = ocr_engine._run_tesseract_bytes(stream.getvalue(), "eng", timeout=20)
        if error or FIXTURE_TEXT not in text.upper():
            raise RuntimeError(error or f"Synthetic OCR text mismatch: {text!r}")

    def image_ocr():
        with pillow() as image:
            recognize(image)

    def reader_isolation():
        import os
        from core.reader_worker import run_reader, decode_image_result
        result = run_reader('probe', {}, timeout=20)
        if not result['isolated'] or result['pid'] == os.getpid():
            raise RuntimeError('Reader did not run in an isolated process')
        from core.document_readers import extract_document
        with tempfile.TemporaryDirectory(prefix='myl_reader_probe_') as directory:
            fixture = Path(directory) / 'fixture.txt'
            fixture.write_text(FIXTURE_TEXT, encoding='utf-8')
            if FIXTURE_TEXT not in extract_document(fixture)['text']:
                raise RuntimeError('Isolated reader output mismatch')
            # Exercise the bundled native libraries inside the actual worker,
            # including the OCR descendant's Job membership, not just in main.
            for suffix in ('png', 'pdf'):
                fixture = Path(directory) / f'fixture.{suffix}'
                with pillow() as image:
                    image.save(fixture)
                result = run_reader('ocr_file', {'path': str(fixture), 'kwargs': {'max_paginas': 1}}, timeout=90)
                if result.get('error') or FIXTURE_TEXT not in result.get('texto', '').upper():
                    raise RuntimeError(f'Isolated {suffix} OCR mismatch: {result.get("error")}')
            decoded = decode_image_result(run_reader('cover', {'path': str(fixture), 'size': [120, 172]},
                                                    timeout=20, memory_mb=512))
            if decoded is None:
                raise RuntimeError('Isolated PDF cover was not decoded')
            decoded.close()

    def pdf_ocr():
        import pypdfium2 as pdfium
        with pillow() as image, io.BytesIO() as stream:
            image.save(stream, format="PDF", resolution=96)
            with pdfium.PdfDocument(stream.getvalue()) as document:
                page = document[0]
                bitmap = None
                rendered = None
                try:
                    bitmap = page.render(scale=2)
                    rendered = bitmap.to_pil()
                    recognize(rendered)
                finally:
                    if rendered is not None:
                        rendered.close()
                    if bitmap is not None:
                        bitmap.close()
                    page.close()

    # The synthetic checks write no application state and use no network.
    with tempfile.TemporaryDirectory(prefix="myl_runtime_"):
        check("tk_init", tk_runtime)
        check("bundled_languages", bundled_languages)
        check("image_ocr", image_ocr)
        check("pdfium_ocr", pdf_ocr)
        check("reader_isolation", reader_isolation)
    report["passed"] = all(value == "passed" for value in checks.values())
    report["manual_installed_ui"] = "not_run"
    return report


def run_and_record(output: Path, *, version: str) -> int:
    report = run_checks(version)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1
